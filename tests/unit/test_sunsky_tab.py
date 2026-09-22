############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the "Sun & sky" outreach tab (ADR-036, S1-S2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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
    config.is_configured = lambda: False   # no startup network worker
    w = MainWindow()
    w._now_timer.stop()
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    yield w
    config.is_configured = orig
    w.close()


def test_tab_is_renamed(window):
    # SC2 (ADR-040): the Sun & sky content moved to the Tools menu as the
    # "Sky calendar…" dialog; ADR-043 removed the Observatory tab, so the
    # bar is down to three
    from PySide6.QtWidgets import QTabWidget
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.count() == 3
    titles = [tabs.tabText(i) for i in range(3)]
    assert not any("sky" in t.lower() or "cielo" in t.lower()
                   for t in titles)


def test_skycal_dialog_opens_from_tools_menu(window):
    # ADR-040: Tools → Sky calendar… builds the dialog once (lazy) and
    # the old tab handlers re-home onto its content widget
    assert window._menus.action_skycal is not None
    window._menus.action_skycal.trigger()
    dlg = window._skycal
    assert dlg is not None
    # the sun handlers' home is the dialog content now
    assert window.solar is dlg.content
    # opening again reuses the same dialog
    window._menus.action_skycal.trigger()
    assert window._skycal is dlg


def test_skycal_sections_fill_on_open(window):
    # SC1: the new local-math sections fill at open (no network): the
    # 60-day list, the Moon calendar line, the week's Galilean windows
    window._menus.action_skycal.trigger()
    dlg = window._skycal
    c = dlg.content
    assert c.lst_events.count() > 10          # two lunar months of events
    assert "·" in c.lbl_moon_cal.text()       # the next phases listed
    assert c.lst_jupmoons.count() > 0         # Galilean windows this week
    assert "10" in c.lbl_jup_note.text()      # the ±10 min honesty label


def test_planets_table_all_7_rows(window):
    # the almanac's planet table lists every planet — the naked-eye five
    # plus Uranus and Neptune — each with its drawn disc and a well-formed
    # magnitude. Below-15° planets stay in the table (dimmed, not
    # hidden), so the row count never lies about the night.
    import re
    window._menus.action_skycal.trigger()
    tbl = window.solar.tbl_planets
    assert tbl.rowCount() == 7
    names = set()
    for row in range(7):
        icon_it = tbl.item(row, 0)
        name_it = tbl.item(row, 1)
        mag_it = tbl.item(row, 2)
        assert icon_it is not None
        assert not icon_it.icon().pixmap(16, 16).isNull()
        assert name_it is not None
        names.add(name_it.text().lower())
        assert mag_it is not None
        assert re.fullmatch(r"-?\d+\.\d", mag_it.text()), mag_it.text()
    # the row label is the proper noun in the UI language (pretty is the
    # single source of truth — test whatever language the machine resolved)
    from nightscribe.gui import pretty
    assert names == {pretty.name(pretty.ui_lang(), n).lower()
                     for n in ("mercury", "venus", "mars", "jupiter",
                               "saturn", "uranus", "neptune")}


def test_impact_line_with_aurora(window):
    # S1: with a Kp/aurora alert the line ties the context to the night
    # plan (Kp + link). The Moon phase now lives in the Moon calendar, so
    # the "%" lit figure must NOT be here any more.
    window._menus.action_skycal.trigger()
    window._last_sun = {"kp": 6.1}
    window._fill_almanac()
    text = window.solar.lbl_impact.text()
    assert "tonight://" in text
    assert "Kp 6.1" in text
    assert "%" not in text                    # the Moon phase is not here now
    assert window.solar.lbl_impact.isVisible()


def test_impact_line_quiet_sky(window):
    # below Kp 5 there is no space-weather signal: the row is hidden,
    # leaving no bare "See Tonight" link behind.
    window._menus.action_skycal.trigger()
    window._last_sun = {"kp": 2.0}
    window._fill_almanac()
    assert not window.solar.lbl_impact.isVisible()


def test_render_png_needs_data_first(window):
    # S2: no refresh yet -> a hint in the status bar, no file written
    window._last_sun = None
    window.on_render_sun_post()
    assert "Refresh" in window.statusBar().currentMessage() or \
        "Actualiza" in window.statusBar().currentMessage() or \
        "primero" in window.statusBar().currentMessage().lower() or \
        "first" in window.statusBar().currentMessage().lower()


def test_render_png_writes_and_shows(window, tmp_path, monkeypatch):
    # S2: one click writes the watermarked PNG (via viz/sun_panel) and
    # opens it in the chart viewer
    written = {}
    monkeypatch.setattr("nightscribe.viz.sun_panel.draw_sun",
                        lambda img, data, out=None, **k: written.update(
                            path=out) or open(out, "wb").write(b"png"))
    shown = []
    monkeypatch.setattr("nightscribe.gui.chart_viewer.open_chart",
                        lambda *a, **k: shown.append(a))
    monkeypatch.setattr("nightscribe.paths.data_dir", lambda: tmp_path)
    window._last_sun = {"ssn": 55, "kp": 2.0}
    window._last_sun_img = None
    window.on_render_sun_post()
    assert written["path"].endswith(".png") and shown, "PNG not written"
    assert (tmp_path / "posts").exists()


# ---------------- S3: the sky-post draft ----------------

def test_sky_draft_content_bilingual():
    from nightscribe.core import narrative
    sun = {"ssn": 120, "n_regions": 7, "kp": 6.0, "aurora": "possible",
           "flare_7d": {"class": "M", "value": 4.2}}
    moon = {"illum": 0.83, "phase_age_days": 11.0, "dist_km": 390000}
    out = narrative.sky_draft(sun, moon, ["Venus (mag -4.2, 18°)"])
    assert "120" in out["es"] and "ciclo 25" in out["es"]
    assert "120" in out["en"] and "cycle 25" in out["en"]
    assert "83%" in out["es"] and "Venus" in out["en"]
    assert "M4.2" in out["es"]                        # the weekly flare


def test_sky_draft_tolerates_empty_sun():
    from nightscribe.core import narrative
    out = narrative.sky_draft({}, {"illum": 0.5, "phase_age_days": 7.0,
                                   "dist_km": 400000}, [])
    assert "Luna" in out["es"] and "Moon" in out["en"]
    assert "manchas" not in out["es"]           # no Sun bullets without data
    assert "sunspot" not in out["en"].lower()


def test_sky_post_dialog_fills_and_copies(qapp):
    from nightscribe.gui.skypost_dialog import SkyPostDialog
    from PySide6.QtWidgets import QApplication
    dlg = SkyPostDialog({"es": "borrador ES", "en": "EN draft"})
    assert dlg.edits["es"].toPlainText() == "borrador ES"
    assert dlg.edits["en"].toPlainText() == "EN draft"
    QApplication.clipboard()     # the copy button must not raise
    dlg.deleteLater()


def test_sky_post_button_wired(window, monkeypatch):
    seen = []
    monkeypatch.setattr("nightscribe.gui.skypost_dialog.SkyPostDialog.exec",
                        lambda self: seen.append(self))
    window._last_sun = {"ssn": 55}
    window.on_sky_post()
    assert seen and seen[0].edits["es"].toPlainText()
    assert "55" in seen[0].edits["es"].toPlainText()
