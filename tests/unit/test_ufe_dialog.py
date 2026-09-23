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
image, one tab per feature, histogram placeholder), load and error paths
with file dialogs stubbed, invert sync, zoom presets, PNG export and the
add_feature_tab extension API. No network.
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
    assert dlg.tabs.count() == 4          # Blink, Compare, Measure, Annotate
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Blink", "Compare", "Measure", "Annotate"]
    assert dlg.histogram is not None      # the phase-B histogram strip
    # the image dominates: at 1280 px the view is wider than the tab column
    assert dlg.view.width() > dlg.tabs.width()


def test_buttons_disabled_until_a_plate_lands(dlg):
    assert not dlg.btn_invert.isEnabled()
    assert not dlg.btn_export.isEnabled()
    dlg.state.load(MONO)
    assert dlg.btn_invert.isEnabled()
    assert dlg.btn_export.isEnabled()


def test_load_via_dialog_updates_title_state(dlg):
    dlg.state.load(MONO)
    assert dlg.state.has_image
    assert dlg.view._pix_item is not None


def test_invert_button_mirrors_state(dlg):
    dlg.state.load(MONO)
    dlg.btn_invert.setChecked(True)
    assert dlg.state.inverted
    # loading a fresh plate resets the inversion and the button
    dlg.state.load(MONO)
    assert not dlg.state.inverted
    assert not dlg.btn_invert.isChecked()


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
    assert dlg.tabs.count() == 5
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
