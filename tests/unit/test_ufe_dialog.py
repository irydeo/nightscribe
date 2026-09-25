############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the Unified FITS Editor dialog (ADR-044)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_dialog.py: the layout (top bar, dominant
image, one tab per feature, histogram strip), load and error paths with
file dialogs stubbed, the histogram Invert mirroring the state, zoom
presets, PNG export and the add_feature_tab extension API. No network.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES = Path(__file__).parents[1] / "fixtures"
MONO = FIXTURES / "sn2026zji_new_image.fits"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture
def dlg(qapp):
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    yield d
    d.view._render_timer.stop()   # never fire on a deleted widget
    d.deleteLater()


def test_layout_three_placeholder_tabs(dlg):
    assert dlg.tabs.count() == 3          # Blink, Photometry, Annotate
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Blink", "Photometry", "Annotate"]
    assert dlg.histogram is not None      # the phase-B histogram strip
    # the image dominates: at 1280 px the view is wider than the tab column
    assert dlg.view.width() > dlg.tabs.width()


def test_buttons_disabled_until_a_plate_lands(dlg):
    assert not dlg.btn_export.isEnabled()
    assert not dlg.histogram.btn_invert.isEnabled()
    dlg.state.load(MONO)
    assert dlg.btn_export.isEnabled()
    assert dlg.histogram.btn_invert.isEnabled()


def test_load_via_dialog_updates_title_state(dlg):
    dlg.state.load(MONO)
    assert dlg.state.has_image
    assert dlg.view._pix_item is not None


def test_invert_mirrors_state_via_the_histogram(dlg):
    # Invert lives in the histogram strip, with the other stretch
    # controls; the strip's button mirrors the state
    dlg.state.load(MONO)
    dlg.histogram.btn_invert.setChecked(True)
    assert dlg.state.inverted
    # loading a fresh plate resets the inversion and the button
    dlg.state.load(MONO)
    assert not dlg.state.inverted
    assert not dlg.histogram.btn_invert.isChecked()


def test_zoom_preset_buttons(dlg, qapp):
    dlg.state.load(MONO)
    dlg.btn_zoom["100"].click()
    assert dlg.view.transform().m11() == pytest.approx(1.0)
    dlg.btn_zoom["400"].click()
    assert dlg.view.transform().m11() == pytest.approx(4.0)
    dlg.btn_zoom["Fit"].click()
    assert 0 < dlg.view.transform().m11() < 1.0


def test_load_error_shows_a_warning(dlg, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    seen = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k:
                                     (str(FIXTURES / "bogus.fits"), "")))
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: seen.append(a))
    dlg._on_load()
    assert seen                       # the error surfaced in a box
    assert not dlg.state.has_image    # and no plate was adopted


def test_load_cancel_keeps_state(dlg, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    dlg._on_load()
    assert not dlg.state.has_image


def test_export_png_via_dialog(dlg, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    dlg.state.load(MONO)
    out = tmp_path / "export.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    dlg._on_export_png()
    assert out.exists() and out.stat().st_size > 0


def test_add_feature_tab_is_the_whole_extension_api(dlg):
    from PySide6.QtWidgets import QLabel
    idx = dlg.add_feature_tab("Future", QLabel("soon"))
    assert dlg.tabs.count() == 4
    assert dlg.tabs.tabText(idx) == "Future"


def _fire(dlg, seq):
    # The offscreen QPA never delivers window-activation, so synthetic
    # key events cannot reach the shortcut map; emitting the registered
    # shortcut's signal exercises the same wiring (the house's other
    # shortcuts, Ctrl+1..4 in main_window, share this blind spot).
    from PySide6.QtGui import QKeySequence, QShortcut
    for sc in dlg.findChildren(QShortcut):
        if sc.key() == QKeySequence(seq):
            sc.activated.emit()
            return True
    return False


def test_keyboard_shortcuts_registered_and_wired(dlg):
    dlg.state.load(MONO)
    assert _fire(dlg, "1")
    assert dlg.view.transform().m11() == pytest.approx(1.0)
    assert _fire(dlg, "+")
    assert dlg.view.transform().m11() == pytest.approx(1.5)
    assert _fire(dlg, "-")
    assert dlg.view.transform().m11() == pytest.approx(1.0)
    assert _fire(dlg, "F")
    assert 0 < dlg.view.transform().m11() < 1.0
    # arrows pan a quarter viewport per press
    dlg.view.fit_to_factor(4.0)
    h0 = dlg.view.horizontalScrollBar().value()
    assert _fire(dlg, "Right")
    assert dlg.view.horizontalScrollBar().value() - h0 > 100
    # the load/export shortcuts exist too
    for seq in ("Ctrl+O", "Ctrl+E", "=", "Left", "Up", "Down"):
        from PySide6.QtGui import QKeySequence, QShortcut
        assert any(sc.key() == QKeySequence(seq)
                   for sc in dlg.findChildren(QShortcut))


def test_zoom_keys_noop_on_empty_state(dlg):
    assert _fire(dlg, "1")              # registered...
    assert dlg.view._pix_item is None   # ...but nothing to zoom


def test_zoom_label_follows_the_view(dlg):
    dlg.state.load(MONO)
    dlg.view.fit_to_factor(2.0)
    assert dlg.lbl_zoom.text() == "200 %"


def test_title_carries_the_file_name(dlg):
    assert dlg.windowTitle() == "NightScribe Image Workbench"
    dlg.state.load(MONO)
    assert "sn2026zji_new_image.fits" in dlg.windowTitle()
    assert dlg.windowTitle().startswith("NightScribe Image Workbench")


def test_keep_stretch_checkbox_drives_the_state(dlg):
    dlg.state.load(MONO)
    dlg.state.set_stretch(black=3000.0, white=9000.0)
    dlg.histogram.chk_keep.setChecked(True)
    assert dlg.state.keep_stretch
    dlg.state.load(MONO)
    assert dlg.state.black == 3000.0 and dlg.state.white == 9000.0


def test_accessible_names(dlg):
    assert dlg.view.accessibleName()
    assert dlg.histogram.canvas.accessibleName()
    assert dlg.histogram.spn_black.accessibleName()


_FAKE_CARDS = {"CRVAL1": 300.0, "CRVAL2": 60.0, "CRPIX1": 8.0,
               "CRPIX2": 8.0, "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
               "CD1_1": -0.0003, "CD1_2": 0.0, "CD2_1": 0.0,
               "CD2_2": 0.0003}


def test_hud_buttons_follow_the_wcs(dlg, tmp_path):
    from test_fits_annotate import _make_fits
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    assert not dlg.btn_north.isEnabled()           # no WCS: no HUD toggles
    assert not dlg.btn_scale.isEnabled()
    assert dlg.btn_solve.isEnabled()               # but solving is offered
    dlg.state.load(MONO)
    assert dlg.btn_north.isEnabled() and dlg.btn_scale.isEnabled()
    dlg.btn_north.setChecked(False)
    assert not dlg.view.show_north                 # button drives the HUD


def test_solve_without_api_key_explains(dlg, monkeypatch):
    from nightscribe import config
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(config.config, "get",
                        lambda *a, **k: "")
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: seen.append(a))
    dlg.state.load(MONO)
    dlg._on_solve()
    assert seen                                     # pointed at Settings
    assert dlg._solve_worker is None


def test_solved_cards_land_in_memory(dlg, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: None)
    dlg.state.load(MONO)
    old_scale = dlg.state.wcs.pixel_scale()
    dlg._on_solved(_FAKE_CARDS)                    # the worker's payload
    assert dlg.state.wcs.pixel_scale() != old_scale
    assert dlg.btn_solve.isEnabled()
    assert dlg.btn_solve.text() == "Solve astrometry…"


def test_solve_failure_warns(dlg, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: seen.append(a))
    dlg.state.load(MONO)
    dlg._on_solved({})
    assert seen


# ------------------------------------------------- chart boxes (ADR-046)

def test_chart_boxes_provider_reads_the_live_state(dlg, monkeypatch):
    # name: the plate stem when nothing else speaks; the attached object
    # wins over it. Date/exposure from the header, position/scale/FOV
    # from the WCS, brightness only after a measurement.
    from nightscribe.config import config
    monkeypatch.setitem(config._data, "observer_name", "F. Calvo")
    monkeypatch.setitem(config._data, "mpc_code", "Z41")
    monkeypatch.setitem(config._data, "chart_boxes", True)
    assert dlg._chart_boxes() == {}                    # no plate, no boxes
    dlg.state.load(MONO)
    boxes = dlg._chart_boxes()
    assert boxes["top_left"] == ["sn2026zji_new_image"]
    assert "Date: 2026-08-21 20:54 UT" in boxes["top_right"]
    assert "Exp: 10.0 s" in boxes["top_right"]
    # solved plate: scale and FOV always; the RA/Dec lines wait for a
    # known object position (a field centre is not the object)
    assert not any(ln.startswith("RA: ") for ln in boxes["top_right"])
    assert any(ln.startswith("PSc: ") for ln in boxes["bottom_left"])
    assert "Obs: F. Calvo" in boxes["bottom_left"]
    assert "Stn: Z41" in boxes["bottom_left"]
    # no measurement yet: no Mag line
    assert not any(ln.startswith("Mag: ") for ln in boxes["top_right"])
    # the attached object wins the name and pins the position (an
    # off-plate object would paint no position lines at all)
    from nightscribe.core import coords
    cra, cdec = dlg.state.wcs.center()
    dlg.set_object({"name": "AT 2026zji", "ra": cra, "dec": cdec,
                    "mag": 17.1})
    boxes = dlg._chart_boxes()
    assert boxes["top_left"] == ["AT 2026zji"]
    col, row = dlg.state.wcs.sky_to_pixel(cra, cdec)
    era, edec = dlg.state.wcs.pixel_to_sky(col, row)
    assert f"RA: {coords.ra_deg_to_hms(era)}" in boxes["top_right"]
    assert f"Dec: {coords.dec_deg_to_dms(edec)}" in boxes["top_right"]
    # a catalog magnitude from the project is NOT a calibration: no Mag
    assert not any(ln.startswith("Mag: ") for ln in boxes["top_right"])
    # a calibrated measurement this session is
    dlg.tab_measure._last = {"mag": 16.391, "err": 0.04, "band": "V",
                             "col": 100.0, "row": 200.0}
    boxes = dlg._chart_boxes()
    assert "Mag: 16.39 ± 0.04 (V)" in boxes["top_right"]
    # ... and the position now speaks from the measured centroid
    ra, dec = dlg.state.wcs.pixel_to_sky(100.0, 200.0)
    assert f"RA: {coords.ra_deg_to_hms(ra)}" in boxes["top_right"]


def test_chart_boxes_toggle_default_comes_from_config(dlg, monkeypatch):
    from nightscribe.config import config
    monkeypatch.setitem(config._data, "chart_boxes", True)
    dlg.hide()
    dlg.show()                          # showEvent re-reads the default
    assert dlg.btn_boxes.isChecked()
    assert dlg.view.show_boxes
    monkeypatch.setitem(config._data, "chart_boxes", False)
    dlg.hide()
    dlg.show()
    assert not dlg.btn_boxes.isChecked()
    assert not dlg.view.show_boxes


# ------------------------------------- top-bar style (ADR-044 rev, 2026-09-24)


def test_topbar_icons_only_is_the_default(dlg):
    # Pinned ufe_bar_icons: True -> a compact glyph bar. The short
    # actions drop their labels entirely; Solve and Move keep theirs in
    # both modes, because the actions are long and the glyphs only hint
    # at them.
    from PySide6.QtGui import QIcon
    from nightscribe.gui import theme
    for name in ("btn_load", "btn_export", "btn_north", "btn_scale",
                 "btn_annot", "btn_boxes"):
        btn = getattr(dlg, name)
        assert btn.text() == ""
        assert not btn.icon().isNull()
    # the checked toggles sit on the _on glyph (they start checked)
    want = QIcon(str(theme.asset("ufe_north_on.svg"))).pixmap(16, 16)
    assert dlg.btn_north.icon().pixmap(16, 16).toImage() == \
        want.toImage()
    assert dlg.btn_solve.text() == "Solve astrometry…"
    assert dlg.btn_move.text() == "Move marker…"
    assert not dlg.btn_move.icon().isNull()
    assert dlg.lbl_zoom_hint.isVisible() == False
    for btn in dlg.btn_zoom.values():
        assert btn.text() == ""
        assert not btn.icon().isNull()


def test_topbar_text_mode_restores_the_labels(dlg, monkeypatch):
    from PySide6.QtGui import QIcon
    from nightscribe.config import config
    from nightscribe.gui import theme
    # The same cached dialog reskins between shows: text mode brings the
    # labels back (icon stays as a hint), icon mode puts them away again.
    monkeypatch.setitem(config._data, "ufe_bar_icons", False)
    dlg.hide()
    dlg.show()
    assert dlg.btn_load.text() == "Load FITS…"
    assert dlg.btn_north.text() == "N"
    assert dlg.btn_scale.text() == "Scale"
    assert dlg.btn_annot.text() == "A"
    assert dlg.btn_boxes.text() == "Boxes"
    assert dlg.btn_solve.text() == "Solve astrometry…"   # unchanged either way
    assert dlg.btn_move.text() == "Move marker…"         # ...
    assert dlg.lbl_zoom_hint.isVisible()
    assert dlg.btn_zoom["100"].text() == "100"
    assert not dlg.btn_zoom["100"].icon().isNull()
    monkeypatch.setitem(config._data, "ufe_bar_icons", True)
    dlg.hide()
    dlg.show()
    assert dlg.btn_load.text() == ""
    assert dlg.btn_north.text() == ""
    assert dlg.btn_zoom["Fit"].text() == ""
    # a checked-state flip re-skins the glyph in icon mode
    dlg.btn_north.setChecked(False)
    off = QIcon(str(theme.asset("ufe_north_off.svg"))).pixmap(16, 16)
    assert dlg.btn_north.icon().pixmap(16, 16).toImage() == off.toImage()
    dlg.btn_north.setChecked(True)


def test_topbar_missing_asset_keeps_the_text(dlg, monkeypatch):
    # The SVG is missing: the button must not go silent.
    from pathlib import Path
    from nightscribe.gui import theme
    monkeypatch.setattr(
        theme, "asset",
        staticmethod(lambda name: Path("/nonexistent") / name))
    dlg.hide()
    dlg.show()
    assert dlg.btn_load.text() == "Load FITS…"
    assert dlg.btn_load.icon().isNull()
    assert dlg.btn_zoom["100"].text() == "100"
    # and the toggle re-skin silently does nothing with no asset
    dlg.btn_north.setChecked(False)
    assert dlg.btn_north.text() == "N"


# The bar's Move marker lands on the Sequence section, whatever tab is
# open (ADR-044 rev, 2026-09-24: it used to live inside the tab).


def test_move_marker_without_a_plate_is_honest(dlg, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []

    def _info(parent, title, message, *a, **k):
        seen.append((title, message))

    monkeypatch.setattr(QMessageBox, "information", staticmethod(_info))
    dlg._on_move_marker()
    assert len(seen) == 1
    assert "load a plate" in seen[0][1]
    # nothing got armed, the tab did not move either
    assert dlg.tab_photometry.tab_compare._moving_target is False
    assert dlg.tabs.currentWidget() is not dlg.tab_photometry


def test_move_marker_lands_on_the_sequence_section(dlg):
    dlg.state.load(MONO)
    comp = dlg.tab_photometry.tab_compare
    comp._view = dlg.view
    comp._field = {"stars": []}         # the field exists (synthetic)
    dlg.tabs.setCurrentWidget(dlg.tab_blink)
    dlg.btn_move.click()
    assert dlg.tabs.currentWidget() is dlg.tab_photometry
    assert dlg.tab_photometry._mode == "sequence"
    assert comp._moving_target is True
