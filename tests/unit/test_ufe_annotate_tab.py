############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE Annotate tab (ADR-044, phase D)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_annotate_tab.py: the marker follows the
click only while the tab is current, the nudge lands clamped, the save
writes AIJ-style ANNOTATE + NS_* cards through the real backend (the
original file is never touched), and listed visits get the same marker
through their own WCS. No network.
"""

import os
import shutil
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
    d.state.load(MONO)
    d.tabs.setCurrentWidget(d.tab_annotate)     # take the stage
    yield d
    d.view._render_timer.stop()      # never fire on a deleted widget
    d.deleteLater()


def test_tab_replaces_the_placeholder(dlg):
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Blink", "Photometry", "Annotate"]
    tab = dlg.tab_annotate
    assert dlg.tabs.indexOf(tab) == 2


def test_marker_starts_centred_and_tab_enabled(dlg):
    tab = dlg.tab_annotate
    assert tab.isEnabled()
    assert tab._marker == [1023.5, 1023.5]
    assert len(tab._items) == 5               # circle + 4 ticks
    assert "marker 1023.5" in tab.lbl_position.text()
    assert "RA " in tab.lbl_position.text()   # the plate carries a WCS


def test_click_places_marker_with_fits_flip(dlg):
    from PySide6.QtCore import QPointF
    tab = dlg.tab_annotate
    dlg.view.scene_clicked.emit(QPointF(100.0, 200.0))
    assert tab._marker == [100.0, 2047 - 1 - 200.0]


def test_clicks_are_ignored_while_another_tab_is_current(dlg):
    from PySide6.QtCore import QPointF
    tab = dlg.tab_annotate
    before = list(tab._marker)
    dlg.tabs.setCurrentIndex(0)               # the Blink placeholder
    assert len(tab._items) == 0               # overlays leave the stage
    dlg.view.scene_clicked.emit(QPointF(500.0, 500.0))
    assert tab._marker == before
    dlg.tabs.setCurrentWidget(tab)
    assert len(tab._items) == 5               # and come back


def test_nudge_applies_and_clamps(dlg):
    from PySide6.QtCore import QPointF
    tab = dlg.tab_annotate
    tab.spin_dx.setValue(10.0)
    tab.spin_dy.setValue(-6.0)
    tab.btn_nudge.click()
    assert tab._marker == [1033.5, 1017.5]
    # near the bottom edge (data row 5), a big downward nudge clamps
    dlg.view.scene_clicked.emit(QPointF(1023.0, 2047 - 1 - 5.0))
    tab.spin_dx.setValue(0.0)
    tab.spin_dy.setValue(-100.0)              # the spin's own floor
    tab.btn_nudge.click()
    assert tab._marker[1] == 0.0              # clamped at the plate edge


def test_marker_toggle_hides_overlay_but_keeps_position(dlg):
    tab = dlg.tab_annotate
    before = list(tab._marker)
    tab.chk_marker.setChecked(False)
    assert tab._items == []
    assert tab._marker == before


def test_label_adds_a_text_item(dlg):
    tab = dlg.tab_annotate
    tab.edit_label.setText("SN 2026zji")
    assert len(tab._items) == 6


def _stub_save_dialog(monkeypatch, dest):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(dest), "")))


def test_save_writes_aij_cards_and_never_touches_the_source(dlg, tmp_path,
                                                            monkeypatch):
    from nightscribe.core import fits_io
    tab = dlg.tab_annotate
    tab.spin_dx.setValue(10.0)
    tab.btn_nudge.click()
    tab.edit_label.setText("SN 2026zji")
    tab.edit_notes.setText("12x180s V")
    before_bytes = MONO.read_bytes()
    out = tmp_path / "annotated.fits"
    _stub_save_dialog(monkeypatch, out)
    tab._save()
    header = fits_io.read_header(out)
    assert header["ANNOTATE"].startswith("1033.50,1023.50,30,1,0,1,1,orange")
    assert abs(header["NS_RA"] - 301.16) < 0.05    # marker next to centre
    assert abs(header["NS_SCALE"] - 1.0661) < 1e-3
    assert header["NS_NOTES"] == "12x180s V"
    assert MONO.read_bytes() == before_bytes       # original intact
    assert "Saved 1" in tab.lbl_status.text()


def test_save_with_visits_annotates_each_through_its_own_wcs(dlg, tmp_path,
                                                             monkeypatch):
    from nightscribe.core import fits_io
    from PySide6.QtWidgets import QFileDialog
    tab = dlg.tab_annotate
    visit = tmp_path / "visit2.fits"
    shutil.copy(MONO, visit)                       # same field, own file
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        staticmethod(lambda *a, **k: ([str(visit)], "")))
    tab._add_extras()
    assert tab.lst_extra.count() == 1
    out = tmp_path / "main_annotated.fits"
    _stub_save_dialog(monkeypatch, out)
    tab._save()
    visit_out = tmp_path / "visit2_annotated.fits"
    assert visit_out.exists()
    header = fits_io.read_header(visit_out)
    assert "ANNOTATE" in header                    # the marker landed there
    assert "Saved 2" in tab.lbl_status.text()
    # Remove drops the row
    tab.lst_extra.setCurrentRow(0)
    tab._remove_extra()
    assert tab.lst_extra.count() == 0


def test_save_failure_reports_and_keeps_going(dlg, tmp_path, monkeypatch):
    from nightscribe.core import fits_annotate
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "critical",
                        lambda *a, **k: seen.append(a))
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(fits_annotate, "write_annotated_fits", boom)
    _stub_save_dialog(monkeypatch, tmp_path / "x.fits")
    dlg.tab_annotate._save()
    assert seen                                     # the error surfaced
    assert "Saved" not in dlg.tab_annotate.lbl_status.text()


def test_save_cancel_writes_nothing(dlg, tmp_path, monkeypatch):
    _stub_save_dialog(monkeypatch, "")
    dlg.tab_annotate._save()
    assert list(tmp_path.iterdir()) == []


def test_save_uses_the_in_memory_solved_wcs(dlg, tmp_path, monkeypatch):
    # A plate solved this session (in memory; the disk file is never
    # touched) still writes NS_SCALE/NS_NORTH and the marker.
    from test_fits_annotate import _make_fits
    from nightscribe.core import fits_io
    plate = _make_fits(tmp_path / "plain.fits")
    dlg.state.load(plate)
    assert dlg.state.wcs is None
    cards = {"CRVAL1": 300.0, "CRVAL2": 60.0, "CRPIX1": 8.0,
             "CRPIX2": 8.0, "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
             "CD1_1": -0.0003, "CD1_2": 0.0, "CD2_1": 0.0,
             "CD2_2": 0.0003}
    assert dlg.state.set_wcs_cards(cards)
    tab = dlg.tab_annotate
    tab.edit_label.setText("SN x")
    out = tmp_path / "out.fits"
    _stub_save_dialog(monkeypatch, out)
    tab._save()
    header = fits_io.read_header(out)
    assert "ANNOTATE" in header                     # marker at the click
    assert abs(header["NS_SCALE"] - 1.08) < 0.01    # from the solved WCS
    assert "NS_NORTH" in header
    assert "NS_RA" in header and "NS_DEC" in header


def test_marker_cross_style_spans_the_plate(dlg, monkeypatch):
    # ADR-046: the "cross" look (Settings) swaps the ring+ticks for a
    # full-frame crosshair with a box; the label and the readout stay
    from nightscribe.config import config
    from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsRectItem
    monkeypatch.setitem(config._data, "marker_style", "cross")
    tab = dlg.tab_annotate
    tab._refresh_marker()
    lines = [it for it in tab._items
             if isinstance(it, QGraphicsLineItem)]
    boxes = [it for it in tab._items
             if isinstance(it, QGraphicsRectItem)]
    w, h = dlg.state.plate_shape
    assert len(lines) == 4 and len(boxes) == 1
    xs = [c for ln in lines for c in (ln.line().x1(), ln.line().x2())]
    ys = [c for ln in lines for c in (ln.line().y1(), ln.line().y2())]
    assert min(xs) == 0.0 and max(xs) == float(w)  # full-frame arms
    assert min(ys) == 0.0 and max(ys) == float(h)
    monkeypatch.setitem(config._data, "marker_style", "ring")
    tab._refresh_marker()
    assert len(tab._items) == 5                    # the classic ring back
