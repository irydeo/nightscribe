############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE plate image view (ADR-044)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/widgets/ufe_image_view.py: the scene lives in
original plate pixels, zoom presets are absolute (100 % = 1:1), resizes
and stretch re-renders keep the observer's zoom, and overlays can be
cleared without dropping the plate. No network.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES = Path(__file__).parents[1] / "fixtures"
MONO = FIXTURES / "sn2026zji_new_image.fits"
AIJ = FIXTURES / "sample_annotated_image_from_aij.fits"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(qapp):
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.widgets.ufe_image_view import UfeImageView
    state = UfeImageState()
    v = UfeImageView(state)
    v.resize(1000, 700)
    v.show()
    yield v
    v._render_timer.stop()      # never fire on a deleted widget (shiboken)
    v.deleteLater()


def test_empty_state_shows_hint(view):
    assert view._hint is not None
    assert view._pix_item is None


def test_load_sets_scene_to_plate_pixels(view):
    view._state.load(MONO)
    r = view.sceneRect()
    assert r.width() >= 2047 and r.height() >= 2047   # relaxed margins
    assert view._pix_item is not None
    assert 0 < view.transform().m11() < 1.0           # fitted below 100 %


def test_fit_to_factor_is_absolute(view):
    view._state.load(MONO)
    view.fit_to_factor(1.0)
    assert view.transform().m11() == pytest.approx(1.0)
    view.fit_to_factor(4.0)
    assert view.transform().m11() == pytest.approx(4.0)
    view.fit_to_factor(0.5)
    assert view.transform().m11() == pytest.approx(0.5)


def test_fit_to_factor_clamps_to_zoom_max(view):
    view._state.load(MONO)
    view.fit_to_factor(500.0)
    assert view.transform().m11() == pytest.approx(view.ZOOM_MAX)


def test_resize_keeps_the_user_zoom(view, qapp):
    view._state.load(MONO)
    view.fit_to_factor(2.0)
    view.resize(500, 400)
    qapp.processEvents()
    assert view.transform().m11() == pytest.approx(2.0)


def test_stretch_rerender_keeps_zoom(view):
    view._state.load(MONO)
    view.fit_to_factor(4.0)
    view._state.toggle_invert()
    view._render()                   # the coalesce timer's job, on demand
    assert view.transform().m11() == pytest.approx(4.0)
    assert view._pix_item.pixmap().width() > 0


def test_hover_probe_is_the_states(view):
    view._state.load(MONO)
    assert view._hover_probe == view._state.probe_text


def test_clear_overlays_keeps_the_plate(view):
    from PySide6.QtWidgets import QGraphicsRectItem
    view._state.load(MONO)
    view.add_overlay(QGraphicsRectItem(0, 0, 50, 50))
    assert len(view._items_registered) == 2
    view.clear_overlays()
    assert view._items_registered == [view._pix_item]


def test_export_png_writes_a_file(view, tmp_path):
    view._state.load(MONO)
    out = view.export_png(tmp_path / "ufe.png")
    assert out.exists() and out.stat().st_size > 0


def test_zoom_changed_signal_reports_absolute_scale(view):
    seen = []
    view.zoom_changed.connect(seen.append)
    view._state.load(MONO)                 # the load-time fit reports
    assert seen and seen[-1] < 1.0
    seen.clear()
    view.fit_to_factor(2.0)
    view.zoom_in()
    assert seen[-2:] == [pytest.approx(2.0), pytest.approx(3.0)]
    view.zoom_out()
    assert seen[-1] == pytest.approx(2.0)


def test_double_click_returns_to_fit(view, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    view._state.load(MONO)
    view.fit_to_factor(4.0)
    QTest.mouseDClick(view.viewport(), Qt.LeftButton)
    qapp.processEvents()
    assert 0 < view.transform().m11() < 1.0


def test_annotate_cards_paint_as_a_read_only_layer(view):
    view._state.load(AIJ)
    assert len(view._annotation_items) == 26       # 13 circles + 13 labels
    view.clear_overlays()                          # tabs own nothing here
    assert len(view._annotation_items) == 26       # the layer survives
    # labels keep a constant screen size: zooming in shrinks the scene pt
    f_fit = view._annotation_labels[0][0].font().pointSizeF()
    view.fit_to_factor(4.0)
    f_zoom = view._annotation_labels[0][0].font().pointSizeF()
    assert f_zoom < f_fit


def test_round_arcsec_picks_125_steps(view):
    # the rounding is in log space (the legacy annotate dialog's rule):
    # 93 sits nearer 50 than 100 there, 37 nearer 50, 1.4 nearer 1
    from nightscribe.gui.widgets.ufe_image_view import _round_arcsec
    assert _round_arcsec(93.0) == pytest.approx(50.0)
    assert _round_arcsec(1.4) == pytest.approx(1.0)
    assert _round_arcsec(37.0) == pytest.approx(50.0)
    assert _round_arcsec(0.0) > 0.0              # degenerate input stays safe


def test_hud_paints_with_and_without_wcs(view, tmp_path):
    view._state.load(MONO)
    view.repaint()                                 # WCS: arrow + bar paint
    from test_fits_annotate import _make_fits
    view._state.load(_make_fits(tmp_path / "plain.fits"))
    view.repaint()                                 # no WCS: HUD no-ops
    assert True                                    # nothing exploded


def test_export_png_stamps_the_hud(view, tmp_path):
    view._state.load(MONO)
    out = view.export_png(tmp_path / "hud.png")
    assert out.exists() and out.stat().st_size > 0
    view.set_hud(north=False, scale=False)
    assert not view.show_north and not view.show_scale
    out2 = view.export_png(tmp_path / "plain.png")
    assert out2.exists()
