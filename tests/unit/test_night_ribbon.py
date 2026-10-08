############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the night ribbon (Interfaz 1.8)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The band that draws one night: the dark window, the object's arc, the
Moon and the overlays.

The point of these tests is not the pixels (the caption is the widget's
readable output) but that the band is HONEST in every state it can be put
in: no site, no object, an object that never rises, one that barely does,
a polar site with no astronomical night, and overlays half outside the
night. It is used by three tabs, so a crash here is a crash everywhere.

Offscreen, no network.
"""

import datetime as dt
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

MADRID = (40.55, -3.37)
# an object high in the autumn sky from Madrid
HIGH = (30.0, 40.0)
# never rises from Madrid
NEVER = (30.0, -80.0)
# barely clears the horizon (about 7 degrees)
LOW = (30.0, -42.0)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def ribbon(qapp):
    from nightscribe.gui.widgets.night_ribbon import NightRibbon
    w = NightRibbon()
    w.resize(560, 70)
    return w


def test_without_a_site_it_says_so(ribbon):
    assert not ribbon.has_night()
    assert "observatory" in ribbon.caption().lower()
    ribbon.grab()                       # must paint, not crash


def test_a_bare_night_has_the_window_and_the_moon(ribbon):
    # The window is tonight's, so the test reads it back from the widget
    # instead of hard-coding times (the old hard-coded pair only matched
    # the date the test was written on: it failed on any other night).
    from nightscribe.core import night_brief as nb
    ribbon.set_site(*MADRID)
    assert ribbon.has_night()
    text = ribbon.caption()
    dusk, dawn = ribbon.window()
    assert nb.local_hhmm(dusk) in text and nb.local_hhmm(dawn) in text
    assert "Dark" in text
    assert " h" in text                 # hours of darkness
    assert "%" in text                  # the Moon
    assert "up " not in text            # no object: no arc, no up-window
    ribbon.grab()


def test_an_object_high_up_reports_its_window(ribbon):
    ribbon.set_site(*MADRID)
    ribbon.set_object(*HIGH, name="2026abc")
    text = ribbon.caption()
    assert "up " in text
    assert "max " in text
    up = ribbon.up_window()
    alt, when = ribbon.peak()
    assert up is not None and up[0] < up[1]
    assert alt > 45.0
    assert when is not None
    ribbon.grab()


def test_an_object_that_never_rises_says_so(ribbon):
    ribbon.set_site(*MADRID)
    ribbon.set_object(*NEVER)
    assert "never rises" in ribbon.caption()
    assert ribbon.up_window() is None
    ribbon.grab()


def test_an_object_that_barely_rises_is_called_out(ribbon):
    # "up 04:40 -> 04:40, max 0 degrees" is true and useless: the band says
    # the object is not worth the trip instead
    ribbon.set_site(*MADRID)
    ribbon.set_object(*LOW)
    assert "too low" in ribbon.caption()
    ribbon.grab()


def test_a_polar_site_without_astronomical_night(ribbon, monkeypatch):
    # The band says so when the Sun never drops 18 degrees at the site. That
    # is a SEASON, not a place: at 78 N there is no astronomical night in the
    # summer and there IS one from early October on, so a test that read
    # tonight's sky passed until the season turned and failed on 2026-10-08
    # (on every platform that day: the date, not the font). The date is
    # pinned to the summer solstice, when the site has no night: the
    # behaviour under test is the band's, not the calendar's.
    import datetime as dt
    from nightscribe.core import night_brief as nb
    real = nb.brief
    monkeypatch.setattr(
        nb, "brief",
        lambda lat, lon, when=None: real(lat, lon, dt.date(2026, 6, 21)))
    ribbon.set_site(78.0, 15.0)
    assert not ribbon.has_night()
    assert "18" in ribbon.caption()     # the "never drops 18 degrees" line
    ribbon.grab()


def test_blocks_need_both_ends_and_survive_being_outside(ribbon):
    ribbon.set_site(*MADRID)
    dusk = ribbon._brief["window"][0]
    ribbon.set_blocks([
        {"start": dusk, "end": None},                       # incomplete: out
        {"start": dusk + dt.timedelta(hours=1),
         "end": dusk + dt.timedelta(hours=2), "label": "1 h"},
        {"start": dusk - dt.timedelta(hours=9),             # outside: drawn
         "end": dusk - dt.timedelta(hours=8)},              # but clamped
    ])
    assert len(ribbon._blocks) == 2
    ribbon.grab()


def test_the_accent_can_be_the_kind_colour(ribbon):
    from nightscribe.gui import theme
    ribbon.set_accent(theme.KIND_COLORS["sn"])
    assert ribbon._accent == theme.KIND_COLORS["sn"]
    ribbon.set_accent(None)
    assert ribbon._accent == theme.C_ACCENT


def test_refresh_is_idempotent(ribbon):
    ribbon.set_site(*MADRID)
    ribbon.set_object(*HIGH)
    first = ribbon.caption()
    ribbon.refresh()
    assert ribbon.caption() == first
