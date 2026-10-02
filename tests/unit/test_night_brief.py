############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: tonight's brief (core/night_brief.py)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The one source of the night's numbers and words.

Welcome, the navigation sky bar and the resting panel of the projects view
all read this module, so these tests are what keeps the three from
disagreeing about the Moon.

No network: it is all local ephemeris.
"""

import datetime as dt
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def nb():
    from nightscribe.core import night_brief
    return night_brief


MADRID = (40.41678, -3.70379)


def test_brief_gives_a_window_a_moon_and_planets(qapp, nb):
    b = nb.brief(*MADRID, when=dt.date(2026, 10, 2))
    assert b["window"] is not None
    dusk, dawn = b["window"]
    assert dusk < dawn
    assert b["moon"] is not None
    assert 0.0 <= b["moon"]["illum"] <= 1.0
    assert isinstance(b["moon"]["waxing"], bool)
    assert isinstance(b["planets"], list)
    for p in b["planets"]:
        assert p["alt"] >= nb.MIN_PLANET_ALT
        assert p["key"] in ("mercury", "venus", "mars", "jupiter", "saturn")


def test_the_moon_matches_the_ephemeris(qapp, nb):
    # The brief must not invent a phase: it reads ephem_minor.
    from nightscribe.core import coords, ephem_minor
    b = nb.brief(*MADRID, when=dt.date(2026, 10, 2))
    jd = coords.jd_from_datetime(b["window"][0])
    m = ephem_minor.moon(jd)
    assert b["moon"]["illum"] == pytest.approx(m["illum"], abs=1e-9)
    assert b["moon"]["age"] == pytest.approx(m["phase_age_days"], abs=1e-9)
    assert b["moon"]["waxing"] == (m["elong_deg"] > 0.0)


def test_planets_are_ordered_by_altitude(qapp, nb):
    b = nb.brief(*MADRID, when=dt.date(2026, 10, 2))
    alts = [p["alt"] for p in b["planets"]]
    assert alts == sorted(alts, reverse=True)


def test_a_polar_site_without_astronomical_night(qapp, nb):
    # 78 N in early October: the Sun only dips to about -15, so there is no
    # astronomical night. It must say so instead of inventing one.
    b = nb.brief(78.0, 15.0, when=dt.date(2026, 10, 2))
    assert b["window"] is None
    assert b["moon"] is None
    assert b["planets"] == []
    assert "18" in nb.window_line(b)


def test_the_lines_speak_in_the_observers_clock(qapp, nb):
    b = nb.brief(*MADRID, when=dt.date(2026, 10, 2))
    window = nb.window_line(b)
    assert "→" in window and "h" in window
    assert "%" in nb.moon_line(b)
    assert nb.planets_line(b)
    assert "%" in nb.moon_short(b)


def test_phase_names_cover_the_cycle(qapp, nb):
    names = [nb.phase_name(age) for age in
             (0.2, 3.0, 7.0, 10.0, 14.5, 18.0, 22.0, 26.0, 29.0)]
    assert len(set(names)) == 8          # eight bands, no repeats
    assert names[0] == names[-1]         # new moon wraps around


def test_compass_letters(qapp, nb):
    assert nb.compass(0.0) == "N"
    assert nb.compass(90.0) == "E"
    assert nb.compass(180.0) == "S"
    assert nb.compass(270.0) == "W"
    assert nb.compass(359.0) == "N"


def test_the_empty_brief_does_not_explode(qapp, nb):
    empty = {"window": None, "moon": None, "planets": []}
    assert nb.window_line(empty)
    assert nb.moon_line(empty) == ""
    assert nb.planets_line(empty)
    assert nb.moon_short(empty) == ""
    assert nb.planets_short(empty) == ""
