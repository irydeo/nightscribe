############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: sky-event chips in the Tonight header
# (Track SC2, ADR-040)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Tonight header carries at most three sky-event chips — the big
things first (eclipse > Galilean window > opposition > …), one per family,
satellites only when observable from the site, and a click opens the Sky
calendar dialog. The chips are injected with a synthetic event list, so
the tests are date-independent and offline.
"""

import datetime
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nightscribe.core import coords

# the tests are date-robust: "today" is the real now
NOW_JD = coords.jd_from_datetime(
    datetime.datetime.now(datetime.timezone.utc))


def _ev(kind, jd, objects, tonight=False, **extra):
    # @return: a minimal engine-shaped event dict for chip selection
    e = {"jd": jd,
         "date": coords.datetime_from_jd(jd),
         "kind": kind, "icon": "✨", "objects": objects,
         "mag": None, "sep_deg": None, "alt_deg": None,
         "tonight": tonight}
    e.update(extra)
    return e


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture(scope="module")
def window(qapp):
    from nightscribe.config import config
    from nightscribe.gui.main_window import MainWindow
    orig = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    yield w
    config.is_configured = orig
    w.close()


def _sky_chips(window):
    # @return: the sky chips currently in the Tonight header
    from PySide6.QtWidgets import QLabel
    return window.tonight.findChildren(QLabel, "ns_skyevent_chip")


def test_chips_big_first_and_one_per_family(window):
    # an eclipse outranks an opposition outranks a Moon-planet pass;
    # two lunar eclipses collapse to the single earliest one
    evs = [
        _ev("moon_conjunction", NOW_JD + 0.2, ["moon", "mars"],
            up_at_dusk=True, sep_deg=2.0),
        _ev("opposition", NOW_JD + 5, ["saturn"], mag=0.6),
        _ev("lunar_eclipse", NOW_JD + 9, ["moon"], detail="total"),
        _ev("lunar_eclipse", NOW_JD + 10, ["moon"], detail="partial"),
        _ev("perigee", NOW_JD + 1, ["moon"], dist_km=357000),
    ]
    picks = window._skyevent_chips(evs)
    assert [p["kind"] for p in picks] == ["lunar_eclipse", "opposition",
                                          "moon_conjunction"]
    chips = _sky_chips(window)
    assert len(chips) == 3
    assert "eclipse" in chips[0].text().lower() or "eclipse" \
        in chips[0].text()


def test_satellite_chips_need_observability(window):
    # a Galilean window only chips when observable from the site
    t0 = coords.datetime_from_jd(NOW_JD + 0.5)
    t1 = coords.datetime_from_jd(NOW_JD + 0.6)
    evs = [
        _ev("sat_transit", NOW_JD + 0.5, ["io", "jupiter"],
            observable=False, t0=t0, t1=t1, tonight=True),
        _ev("full_moon", NOW_JD + 1, ["moon"], tonight=False),
    ]
    picks = window._skyevent_chips(evs)
    assert [p["kind"] for p in picks] == ["full_moon"]
    # and when it IS observable it chips (and outranks the full Moon)
    evs[0]["observable"] = True
    picks = window._skyevent_chips(evs)
    assert picks[0]["kind"] == "sat_transit"
    assert "UT" in _sky_chips(window)[0].text()


def test_chip_click_opens_sky_calendar(window):
    evs = [_ev("opposition", NOW_JD + 5, ["saturn"], mag=0.6)]
    window._skyevent_chips(evs)
    chips = _sky_chips(window)
    assert len(chips) == 1
    chips[0].clicked.emit()
    assert window._skycal is not None and window._skycal.isVisible()
    window._skycal.hide()


def test_no_events_means_no_chips(window):
    picks = window._skyevent_chips([])
    assert picks == []
    assert _sky_chips(window) == []


def test_real_list_chips_today(window):
    # the real engine on the real config: at most 3 chips, all well-formed
    window._skyevent_chips()
    chips = _sky_chips(window)
    assert len(chips) <= 3
    for c in chips:
        assert c.text().strip()


def test_planets_visible_tonight(window):
    # the almanac answers "which planets will be up tonight" in a table:
    # all seven rows, and exactly the naked-eye planets the *moving*
    # ephemeris never pushes above 15° are dimmed (not hidden). The
    # dimming is recomputed here offline from the same building blocks
    # (Schlyter + core.coords), so the test holds for any date.
    import re
    from PySide6.QtGui import QColor
    from nightscribe.config import config
    from nightscribe.gui import pretty

    lang = pretty.ui_lang()
    lat, lon = float(config.get("lat")), float(config.get("lon"))
    now = datetime.datetime.now(datetime.timezone.utc)
    dim = QColor("#8a90a6")

    window._menus.action_skycal.trigger()
    tbl = window.solar.tbl_planets
    assert tbl.rowCount() == 7
    by_name = {}
    for row in range(tbl.rowCount()):
        name_it, mag_it = tbl.item(row, 1), tbl.item(row, 2)
        assert name_it is not None and re.fullmatch(r"[A-Z]\w+", name_it.text())
        assert mag_it is not None and re.fullmatch(r"-?\d+\.\d", mag_it.text())
        by_name[name_it.text().lower()] = name_it

    for name in ("mercury", "venus", "mars", "jupiter", "saturn"):
        # the label is the UI-language proper noun (pretty, not tr())
        disp = pretty.name(lang, name).lower()
        assert disp in by_name, f"{name} missing from the table"
        arc = coords.planet_rise_set_max_alt(name, lat, lon, now.date())
        expect_dim = (arc["max_alt"] is None) or (arc["max_alt"] < 15.0)
        got_dim = by_name[disp].foreground().color() == dim
        assert got_dim == expect_dim, \
            f"{name}: dim={got_dim} but best alt {arc['max_alt']}° tonight"
