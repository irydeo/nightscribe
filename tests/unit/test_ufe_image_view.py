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
from PySide6.QtCore import QPointF

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


def test_pick_cursor_and_snap(view, qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QPointingDevice
    import numpy as np
    # at rest the viewport carries the pan affordance (open hand)
    assert view.viewport().cursor().shape() == Qt.OpenHandCursor
    view.set_pick_cursor(True)
    assert view.viewport().cursor().shape() == Qt.CrossCursor
    # a plate with one bright star: hovering near it snaps the reticle
    data = np.full((200, 200), 800.0, dtype=np.float32)
    yy, xx = np.ogrid[:200, :200]
    data += 9000 * np.exp(-((xx - 100.4) ** 2 + (yy - 99.6) ** 2)
                          / (2 * 2.2 ** 2))
    view._state.data = data
    view._state.d_min, view._state.d_max = 790.0, 9800.0
    sx, sy = view._state.data_to_scene(100.4, 99.6)
    vp = view.mapFromScene(sx, sy)
    ev = QMouseEvent(QMouseEvent.MouseMove, QPointF(vp), QPointF(vp),
                     QPointF(vp), Qt.NoButton, Qt.NoButton, Qt.NoModifier,
                     QPointingDevice.primaryPointingDevice())
    view.mouseMoveEvent(ev)
    view._snap_now()
    assert view._snap_scene is not None
    assert abs(view._snap_scene[0] - sx) < 1.0
    assert abs(view._snap_scene[1] - sy) < 1.0
    view.repaint()                       # the reticle paints cleanly
    view.set_pick_cursor(False)
    assert view.viewport().cursor().shape() == Qt.OpenHandCursor
    assert view._mouse_vp is None


def test_pick_mode_uses_full_viewport_updates(view):
    # the reticle paints viewport-wide in device coords: only a full
    # repaint policy keeps it from leaving trails behind
    from PySide6.QtWidgets import QGraphicsView
    assert view.viewportUpdateMode() == QGraphicsView.MinimalViewportUpdate
    view.set_pick_cursor(True)
    assert view.viewportUpdateMode() == QGraphicsView.FullViewportUpdate
    view.set_pick_cursor(False)
    assert view.viewportUpdateMode() == QGraphicsView.MinimalViewportUpdate


def test_pick_cursor_survives_a_pan_drag(view, qapp):
    # ScrollHandDrag restores the OPEN hand on every release; in pick
    # mode the view must claim the crosshair back, and out of pick mode
    # the pan affordance stays
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    view._state.load(MONO)
    view.set_pick_cursor(True)
    QTest.mousePress(view.viewport(), Qt.LeftButton, pos=QPoint(300, 300))
    QTest.mouseMove(view.viewport(), QPoint(380, 340))
    QTest.mouseRelease(view.viewport(), Qt.LeftButton, pos=QPoint(380, 340))
    qapp.processEvents()
    assert view.viewport().cursor().shape() == Qt.CrossCursor
    view.set_pick_cursor(False)
    QTest.mousePress(view.viewport(), Qt.LeftButton, pos=QPoint(300, 300))
    QTest.mouseMove(view.viewport(), QPoint(380, 340))
    QTest.mouseRelease(view.viewport(), Qt.LeftButton, pos=QPoint(380, 340))
    qapp.processEvents()
    assert view.viewport().cursor().shape() == Qt.OpenHandCursor


def test_the_probe_readout_is_anchored_to_the_corner(view):
    # Reported: the readout chased the cursor and covered the coordinates /
    # the pixels being looked at. It is a status line now: anchored to the
    # bottom-left, in picking mode and out of it, and it never follows the
    # mouse.
    from PySide6.QtCore import QPointF
    factor = view.current_factor()
    for picking in (True, False):
        view.set_pick_cursor(picking)
        view._show_tooltip(QPointF(400, 300), ["(10, 10)  DN 800.0"])
        pos = view._tooltip.pos()
        bl = view.mapToScene(0, view.viewport().height() - 6)
        assert (pos.x() - bl.x()) * factor == pytest.approx(10.0, abs=2.0)
        assert pos.y() < bl.y()              # its bottom sits at the corner
        assert (pos.y() + view._tooltip.boundingRect().height()) * factor == \
            pytest.approx(bl.y() * factor, abs=4.0)
    view._hide_tooltip()


def test_export_never_carries_the_reticle(view, tmp_path):
    import numpy as np
    data = np.full((100, 100), 800.0, dtype=np.float32)
    data += 9000 * np.exp(-((np.arange(100)[None, :] - 50.0) ** 2
                            + (np.arange(100)[:, None] - 50.0) ** 2)
                          / (2 * 2.2 ** 2))
    view._state.data = data
    view._state.d_min, view._state.d_max = 790.0, 9800.0
    view._state.load  # noqa - just show we do NOT load here; data set raw
    view._render()
    a = view.export_png(tmp_path / "a.png").read_bytes()
    view.set_pick_cursor(True)
    from PySide6.QtCore import QPoint
    view._mouse_vp = QPoint(50, 50)
    view.repaint()
    b = view.export_png(tmp_path / "b.png").read_bytes()
    view.set_pick_cursor(False)
    assert a == b      # the reticle is viewport-only, never in the file


def test_snap_locks_faint_sources_on_structure(view, qapp):
    # The AT2026acka SN corner at fit zoom: the reticle must snap to the
    # faint bump under the cursor (the robust local detector sees it),
    # not reach for the bright star 7 px away; and past the plate-px
    # reach cap it must not snap at all (the old 12/scale reach was a
    # ~30 px grab at fit zoom: "the crosshair jumps to the bright stars").
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QPointingDevice
    view._state.load(FIXTURES / "AT2026acka.fit")
    view.set_pick_cursor(True)

    def hover(data_x, data_y):
        sx, sy = view._state.data_to_scene(data_x, data_y)
        vp = view.mapFromScene(sx, sy)
        ev = QMouseEvent(QMouseEvent.MouseMove, QPointF(vp), QPointF(vp),
                         QPointF(vp), Qt.NoButton, Qt.NoButton,
                         Qt.NoModifier,
                         QPointingDevice.primaryPointingDevice())
        view.mouseMoveEvent(ev)
        view._snap_now()

    hover(1039.0, 1010.0)          # the faint SN bump in its galaxy
    assert view._snap_scene is not None
    sx, sy = view._state.data_to_scene(1039.0, 1011.0)
    assert abs(view._snap_scene[0] - sx) < 3.0
    assert abs(view._snap_scene[1] - sy) < 3.0
    hover(1020.0, 1000.0)          # >20 px from anything: no grab
    assert view._snap_scene is None
    view.set_pick_cursor(False)


# ------------------------------------------------- chart boxes (ADR-046)

def _band_sample():
    # the plate's heading, as core/chart_annotate decides it: two lines of
    # segments, each with its role and the field the drop order uses
    return {"lines": [
        [{"text": "AT 2026acka", "role": "name", "field": "name"},
         {"text": "RA 22 02 16.4 · Dec +39 49 46.6", "role": "pos",
          "field": "pos"},
         {"text": "17.10 (G)", "role": "mag", "field": "mag"}],
        [{"text": "2026-09-20 21:06 UT", "role": "context", "field": "date"},
         {"text": "Stn Z41", "role": "context", "field": "stn"},
         {"text": "1.07″/px", "role": "context", "field": "psc"}]]}


def test_cross_marker_items_span_the_plate(view):
    from nightscribe.gui.widgets.ufe_image_view import cross_marker_items
    items = cross_marker_items(100.0, 60.0, 400.0, 300.0, "#ffb347", 12.0)
    assert len(items) == 5
    seg = [(ln.line().x1(), ln.line().y1(), ln.line().x2(), ln.line().y2())
           for ln in items[:4]]
    gap = 12.0 * 1.4
    assert (0.0, 60.0, 100.0 - gap, 60.0) in seg      # west arm
    assert (100.0 + gap, 60.0, 400.0, 60.0) in seg    # east arm
    assert (100.0, 0.0, 100.0, 60.0 - gap) in seg     # north arm
    assert (100.0, 60.0 + gap, 100.0, 300.0) in seg   # south arm
    rect = items[4].rect()
    assert rect.center().x() == pytest.approx(100.0)
    assert rect.center().y() == pytest.approx(60.0)
    assert rect.width() == pytest.approx(24.0)
    assert all(it.pen().isCosmetic() for it in items)


def test_the_band_follows_the_toggle_on_export(view, tmp_path):
    # The band burns into the exported PNG (what you see is what lands in
    # the file) and the toggle governs what it says: with the data off it
    # keeps the object's name, which is the plate's name.
    view._state.load(MONO)
    view.set_band_provider(_band_sample)
    full = view.export_png(tmp_path / "full.png").read_bytes()
    view.set_hud(data=False)                  # only the name
    name_only = view.export_png(tmp_path / "name.png").read_bytes()
    assert full != name_only
    view.set_hud(data=True)
    assert view.export_png(tmp_path / "full2.png").read_bytes() == full
    view.set_band_provider(None)              # no band at all
    assert view.export_png(tmp_path / "none.png").read_bytes() != full


def test_the_band_paints_without_a_solution(view, tmp_path):
    # The object's name, the frame's date and its exposure do not need a
    # WCS: the band is there on an unsolved plate too (and the position it
    # shows is marked as the catalogue's).
    from nightscribe.core import chart_annotate as ca
    from test_fits_annotate import _make_fits
    view._state.load(_make_fits(tmp_path / "plain.fits"))
    view.set_band_provider(lambda: ca.build_band(
        name="Thing", meta={"date_obs": "2026-09-30T21:06:00",
                            "exptime_s": 30.0}))
    with_band = view.export_png(tmp_path / "with.png").read_bytes()
    view.set_band_provider(None)
    without = view.export_png(tmp_path / "without.png").read_bytes()
    assert with_band != without


def test_a_band_provider_hiccup_never_breaks_the_paint(view, tmp_path):
    view._state.load(MONO)

    def boom():
        raise RuntimeError("no band today")
    view.set_band_provider(boom)
    out = view.export_png(tmp_path / "fine.png")
    assert out.exists() and out.stat().st_size > 0
    view.viewport().repaint()                 # the screen paint survives


def test_the_readout_sits_low_and_the_scale_bar_steps_aside(view, tmp_path):
    # The readout is anchored to the bottom-left (see
    # test_the_probe_readout_is_anchored_to_the_corner) and the band lives
    # at the top, so the two cannot meet. What shares the bottom with the
    # readout is the scale bar, and IT steps up while the readout shows.
    from PySide6.QtCore import QPointF, QRectF
    view._state.load(MONO)
    view.set_pick_cursor(True)
    _x, y_plain = view._tooltip_anchor_pos(QPointF(3, 3),
                                           QRectF(0, 0, 50, 20))
    view.set_band_provider(_band_sample)
    view.export_png(tmp_path / "band.png")
    assert view._title_h > 0                      # the band is up there
    _x, y_banded = view._tooltip_anchor_pos(QPointF(3, 3),
                                            QRectF(0, 0, 50, 20))
    assert y_banded == pytest.approx(y_plain)     # the band does not move it
    # the scale bar, though, steps up by the readout's own height
    class _Spy:
        def __init__(self):
            self.lines = []

        def setPen(self, *_a):
            pass

        def setFont(self, *_a):
            pass

        def drawLine(self, a, b):
            self.lines.append((a.y(), b.y()))

        def drawText(self, *_a):
            pass

    spy = _Spy()
    view._tooltip = type("T", (), {"boundingRect": lambda self: QRectF(
        0, 0, 80, 24)})()
    view._paint_scale(spy, 600, 400, 1.0)
    ducked = min(y for line in spy.lines for y in line)
    spy2 = _Spy()
    view._tooltip = None
    view._paint_scale(spy2, 600, 400, 1.0)
    plain = min(y for line in spy2.lines for y in line)
    assert ducked < plain                         # the bar moved UP
    assert plain - ducked >= 24                   # by the readout's height
    view.set_pick_cursor(False)


# ------------------------------------------------- global object mark

def _plate_centre_sky(view):
    # @return: (ra, dec) of the loaded plate's centre pixel
    w, h = view._state.plate_shape
    return view._state.wcs.pixel_to_sky(w / 2.0, h / 2.0)


def test_object_mark_follows_object_and_survives_tabs(view):
    assert view._object_mark_items == []        # no object, no mark
    view._state.load(MONO)
    view.set_object_mark(*_plate_centre_sky(view))
    assert len(view._object_mark_items) == 5    # 4 arms + the box
    assert all(it.isVisible() for it in view._object_mark_items)
    view.set_object_mark_visible(False)         # the bar toggle
    assert all(not it.isVisible() for it in view._object_mark_items)
    assert len(view._object_mark_items) == 5    # hidden, never dropped
    view.clear_overlays()                       # tabs own nothing here
    assert len(view._object_mark_items) == 5    # the layer survives
    view.set_object_mark(None, None)
    assert view._object_mark_items == []


def test_object_mark_needs_wcs_and_in_plate_coords(view, tmp_path):
    from test_fits_annotate import _make_fits
    view._state.load(_make_fits(tmp_path / "plain.fits"))   # no WCS
    view.set_object_mark(10.0, 20.0)
    assert view._object_mark_items == []
    view._state.load(MONO)
    view.set_object_mark(10.0, 20.0)            # off-plate sky: no mark
    assert view._object_mark_items == []
    view.set_object_mark("not-a-number", None)  # garbage parses to nothing
    assert view._object_mark_radec is None
    assert view._object_mark_items == []


def test_object_mark_burns_into_the_export_when_visible(view, tmp_path):
    view._state.load(MONO)
    a = view.export_png(tmp_path / "off.png").read_bytes()
    view.set_object_mark(*_plate_centre_sky(view))
    b = view.export_png(tmp_path / "on.png").read_bytes()
    assert a != b                               # visible: it burns in
    view.set_object_mark_visible(False)
    assert view.export_png(tmp_path / "off2.png").read_bytes() == a


# ---------------- the display mirror (E6) ----------------

def _flip(view, axis, state_ready=True):
    # Toggles the mirror and applies it the way the app does (the state
    # emits stretch_changed -> the view coalesces a render).
    view._state.toggle_flip(axis)
    view._render()


def test_the_mirror_turns_the_picture_not_the_scene(view):
    # The invariant that keeps the science safe: the scene stays in
    # original plate pixels, so mirroring the plate to compare it with
    # someone else's chart cannot move a click, a saved mark or a
    # measured centroid.
    view._state.load(MONO)
    view.fit_to_scene()
    before = view.transform()
    scene_box = view.sceneRect()
    _flip(view, "h")
    after = view.transform()
    assert after.m11() == pytest.approx(-before.m11(), rel=1e-9)
    assert after.m22() == pytest.approx(before.m22(), rel=1e-9)
    # the scene is untouched: same rect, same plate shape
    assert view.sceneRect() == scene_box
    assert view._state.plate_shape is not None
    # and the mapping is still a bijection: a click lands where it looks
    q = view.viewportTransform()
    inv, ok = q.inverted()
    assert ok
    for vp in (QPointF(10.0, 20.0), QPointF(300.0, 150.0)):
        scene_pt = inv.map(vp)
        back = q.map(scene_pt)
        assert back.x() == pytest.approx(vp.x(), abs=1e-6)
        assert back.y() == pytest.approx(vp.y(), abs=1e-6)


def test_the_mirror_is_about_the_centre_of_the_view(view):
    # Qt applies the view transform around the viewport's own centre, so
    # pre-multiplying a mirror keeps the picture where it was instead of
    # pushing it off screen. Checked empirically, because that is the part
    # a reader would doubt.
    view._state.load(MONO)
    view.fit_to_scene()
    vw = view.viewport().width()
    vh = view.viewport().height()
    left = view.mapToScene(vw // 4, vh // 2)
    middle = view.mapToScene(vw // 2, vh // 2)
    _flip(view, "h")
    assert view.mapToScene(vw - vw // 4, vh // 2).x() == \
        pytest.approx(left.x(), abs=1e-6)
    # the centre is on the mirror axis: what is in the middle stays there
    assert view.mapToScene(vw // 2, vh // 2).x() == \
        pytest.approx(middle.x(), abs=1e-6)


def test_mirroring_twice_returns_to_the_same_view(view):
    view._state.load(MONO)
    view.fit_to_scene()
    before = view.transform()
    _flip(view, "h")
    _flip(view, "h")
    assert view.transform() == before


def test_both_mirrors_are_the_180_turn(view):
    view._state.load(MONO)
    view.fit_to_scene()
    before = view.transform()
    _flip(view, "h")
    _flip(view, "v")
    after = view.transform()
    assert after.m11() == pytest.approx(-before.m11(), rel=1e-9)
    assert after.m22() == pytest.approx(-before.m22(), rel=1e-9)


def test_the_mirror_survives_a_fit(view):
    # fit_to_scene/fit_to_factor reset the transform; the mirror must be
    # re-applied or the orientation would silently jump back
    view._state.load(MONO)
    _flip(view, "v")
    view.fit_to_scene()
    assert view.transform().m22() < 0
    view.fit_to_factor(1.0)
    assert view.transform().m22() < 0
    assert view.transform().m11() == pytest.approx(1.0)


def test_the_export_saves_what_you_see_mirrored(view, tmp_path):
    # "Export PNG…" promises the visible scene, and a mirror is part of how
    # the observer is looking at the plate.
    from PySide6.QtGui import QImage
    view._state.load(MONO)
    view.fit_to_scene()
    plain = view.export_png(tmp_path / "plain.png")
    _flip(view, "v")
    flipped = view.export_png(tmp_path / "flip.png")
    a = QImage(str(plain))
    b = QImage(str(flipped))
    assert a.size() == b.size()
    # row 0 of the mirrored file is the original's last row
    top = b.pixelColor(a.width() // 2, 0)
    bottom = a.pixelColor(a.width() // 2, a.height() - 1)
    assert top == bottom


def test_the_mirror_is_undone_by_a_state_reset(view):
    # Back to first sight of a plate (ADR-047): no inversion, no mirror.
    view._state.load(MONO)
    _flip(view, "h")
    assert view._state.flip_h is True
    view._state.reset_stretch()
    assert view._state.flip_h is False
    assert view._state.flip_v is False
    assert "flip_h" in view._state.stretch_state()


def test_the_compass_follows_the_mirror(view):
    # The compass is painted in viewport coordinates: if it did not follow
    # the mirror it would keep pointing at the old north while the sky on
    # screen has turned around.
    assert view._flip_angle(10.0) == pytest.approx(10.0)
    view._state.flip_h = True
    assert view._flip_angle(10.0) == pytest.approx(-10.0)
    view._state.flip_v = True
    assert view._flip_angle(10.0) == pytest.approx(190.0)   # -10 -> 180+10
    assert view._flip_angle(0.0) == pytest.approx(180.0)
