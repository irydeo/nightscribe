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
    assert dlg.tabs.count() == 3
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Blink", "Compare", "Annotate"]
    assert dlg.frm_histogram is not None
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
    assert dlg.tabs.count() == 4
    assert dlg.tabs.tabText(idx) == "Future"
