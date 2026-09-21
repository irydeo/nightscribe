############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - base chart widget tests (offscreen, ADR-029)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/widgets/base_chart.py (ADR-029).

Patterns:
  * one QApplication per module, offscreen, throwaway;
  * a small QGraphicsRectItem is added as stand-in content when no
    concrete chart (OrbitChart, SkyChart) is under test;
  * no network, no matplotlib import from the widget package (asserted
    in its own test, below).
"""

import os
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    if os.environ.get("QT_QPA_PLATFORM") is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def _events(qapp):
    qapp.processEvents()


def _mk_view(qapp, w=600, h=400):
    # @return: a ChartView with a stand-in rect (0..100, 0..60) and a
    #          fixed scene rect (-5, -5, 110, 70), sized to (w, h).
    from PySide6.QtWidgets import QGraphicsRectItem
    from nightscribe.gui.widgets.base_chart import ChartView
    v = ChartView()
    v.add_item(QGraphicsRectItem(0, 0, 100, 60))
    v.set_scene_rect(-5, -5, 110, 70)
    v.resize(w, h)
    _events(qapp)
    v.fit_to_scene()
    return v


def test_basic_view_is_not_empty(qapp):
    v = _mk_view(qapp)
    assert v.scene() is not None
    assert len(v._items_registered) == 1
    assert v.scene_rect_hint().width() > 0
    assert v.scene_rect_hint().height() > 0
    v.close()


def test_fit_to_scene_refills_on_resize(qapp):
    # resize the parent, the scene must stay fitted — no letterbox
    v = _mk_view(qapp, 400, 300)
    scale_small = v.transform().m11()
    # scale > 0 means the scene fits the viewport (non-degenerate)
    assert scale_small > 0
    v.resize(1200, 900)
    _events(qapp)
    scale_big = v.transform().m11()
    assert scale_big > 0
    # fitting a bigger viewport should not make the scene scale smaller
    # (it grows to fill) — a regression test for "keep aspect, fill slot"
    assert scale_big >= scale_small * 0.99
    v.close()


def test_zoom_in_clamps_at_upper_limit(qapp):
    from PySide6.QtGui import QColor
    v = _mk_view(qapp)
    v.set_hover_probe(None)
    for _ in range(80):
        v._zoom_by(1.25)
    scale = v.transform().m11()
    assert scale <= 8.0, f"zoom-in went past the ceiling: {scale}"


def test_zoom_out_clamps_at_lower_limit(qapp):
    v = _mk_view(qapp)
    v.set_hover_probe(None)
    for _ in range(300):
        v._zoom_by(1.0 / 1.25)
    scale = v.transform().m11()
    assert scale >= 0.05, f"zoom-out dropped below the floor: {scale}"


def test_export_png_writes_file(qapp, tmp_path):
    # the key export path — whatever the user has zoomed in, it is
    # rendered to a PNG at the viewport aspect.
    v = _mk_view(qapp)
    out = tmp_path / "chart.png"
    p = v.export_png(out)
    assert p.exists(), "export_png should create the file"
    size = p.stat().st_size
    assert size > 2 * 1024, f"PNG too small ({size} bytes) — probably blank"
    # re-import as a raw byte check (no need for PIL to assert non-blank)
    # the file is definitely a PNG
    with open(p, "rb") as fh:
        magic = fh.read(4)
    assert magic == b"\x89PNG", f"not a PNG: {magic!r}"


def _has_watermark_pixels(img):
    # @args: img - QImage; @return: True when pixels close to palette.MUTED
    #        appear in the bottom-right corner region (the watermark spot).
    muted = (138, 144, 166)          # palette.MUTED "#8a90a6"
    tol = 60
    rx0, rx1 = int(img.width() * 0.7), img.width()
    ry0, ry1 = img.height() - 60, img.height()
    for y in range(ry0, ry1):
        for x in range(rx0, rx1):
            c = img.pixelColor(x, y)
            if (abs(c.red() - muted[0]) <= tol
                    and abs(c.green() - muted[1]) <= tol
                    and abs(c.blue() - muted[2]) <= tol):
                return True
    return False


def test_export_png_stamps_bottom_right_watermark(qapp, tmp_path):
    # The chart stamps its signature bottom-right — on screen (drawForeground)
    # and, crucially, in the exported PNG (scene.render alone would skip it).
    from PySide6.QtGui import QImage
    v = _mk_view(qapp)
    assert v._watermark == "NightScribe", "default watermark missing"
    out = tmp_path / "wm.png"
    v.export_png(out)
    assert _has_watermark_pixels(QImage(str(out))), (
        "watermark not painted in the bottom-right corner of the export")
    # set_watermark("") disables it
    v.set_watermark("")
    out2 = tmp_path / "nowm.png"
    v.export_png(out2)
    assert not _has_watermark_pixels(QImage(str(out2))), (
        "watermark still present after set_watermark('')")
    # a custom signature is honoured
    v.set_watermark("Irydeo")
    out3 = tmp_path / "custom.png"
    v.export_png(out3)
    assert _has_watermark_pixels(QImage(str(out3)))
    v.close()


def test_hover_probe_shows_and_hides_tooltip(qapp):
    # the contract: set_hover_probe(fn) where fn(x, y) -> (hit, text).
    # While hit=True a tooltip is on the scene; after leaveEvent it is
    # gone. This is exactly what OrbitChart and SkyChart depend on.
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    v = _mk_view(qapp)
    hits = []

    def probe(x, y):
        hits.append((round(x, 1), round(y, 1)))
        return True, f"r=1.00, nu={round(x, 1)}°"

    v.set_hover_probe(probe)
    # Qt 6: QMouseEvent(type, localPos, scenePos, globalPos,
    #                   button, buttons, modifiers[, device])
    evt = QMouseEvent(QEvent.Type.MouseMove, QPointF(300, 200),
                      QPointF(300, 200), QPointF(300, 200),
                      Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    v.mouseMoveEvent(evt)
    assert hits, "probe was not called"
    assert v._tooltip is not None, "tooltip should be on the scene"
    assert "r=1.00" in v._tooltip.text()

    v.leaveEvent(QEvent(QEvent.Type.Leave))
    assert v._tooltip is None, "tooltip should be off the scene after leave"
    v.close()


def test_hover_probe_can_be_disabled(qapp):
    # set_hover_probe(None) removes the probe and cleans the tooltip.
    v = _mk_view(qapp)
    v.set_hover_probe(lambda x, y: (True, "x"))
    v.set_hover_probe(None)
    assert v._probe_active() is False
    v.close()


def test_tooltip_font_tracks_zoom_for_a_constant_screen_size(qapp):
    # The tooltip is a scene item: its font is divided by the view scale
    # so it reads the same on screen at fit and at deep zoom (a fixed
    # scene size read tiny at fit and huge when zoomed in).
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    def move(v):
        evt = QMouseEvent(QEvent.Type.MouseMove, QPointF(300, 200),
                          QPointF(300, 200), QPointF(300, 200),
                          Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        v.mouseMoveEvent(evt)

    v = _mk_view(qapp)
    v.set_hover_probe(lambda x, y: (True, "probe"))
    move(v)
    scale1 = v.transform().m11()
    size1 = v._tooltip.font().pointSizeF()
    v.scale(2.0, 2.0)
    move(v)
    scale2 = v.transform().m11()
    size2 = v._tooltip.font().pointSizeF()
    assert scale2 == pytest.approx(scale1 * 2.0)
    # the scene-unit font halves when the view doubles: the on-screen
    # size stays put
    assert size2 == pytest.approx(size1 / 2.0, rel=0.02)
    assert size1 * scale1 == pytest.approx(size2 * scale2, rel=0.02)
    v.close()


def test_clear_drops_registered_items(qapp):
    from PySide6.QtWidgets import QGraphicsRectItem
    from nightscribe.gui.widgets.base_chart import ChartView
    v = ChartView()
    v.add_item(QGraphicsRectItem(0, 0, 10, 10))
    v.add_item(QGraphicsRectItem(20, 20, 10, 10))
    assert len(v._items_registered) == 2
    v.clear()
    assert len(v._items_registered) == 0
    assert v._tooltip is None
    v.close()


def test_scene_clicked_fires_on_no_drag_release(qapp):
    # a left-press + left-release with no move fires scene_clicked.
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    v = _mk_view(qapp)
    fired = []
    v.scene_clicked.connect(lambda: fired.append(True))

    down = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(100, 100),
                       QPointF(100, 100), QPointF(100, 100),
                       Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    v.mousePressEvent(down)
    up = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(101, 100),
                     QPointF(101, 100), QPointF(101, 100),
                     Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    v.mouseReleaseEvent(up)
    assert fired, "scene_clicked should fire on a click without drag"
    v.close()


def _wheel(angle_dy=120):
    # @args: angle_dy - vertical angle delta (positive = zoom-in direction)
    # @return: a wheel event over the view at (100, 100).
    from PySide6.QtCore import QPointF, QPoint, Qt
    from PySide6.QtGui import QWheelEvent
    return QWheelEvent(QPointF(100, 100), QPointF(100, 100),
                       QPoint(0, 0), QPoint(0, angle_dy),
                       Qt.NoButton, Qt.NoModifier,
                       Qt.ScrollPhase.NoScrollPhase, False)


def test_default_mode_zooms_on_wheel(qapp):
    # Regression guard: a standalone view (the one ChartViewer builds)
    # still zooms centred on the cursor and keeps the wheel event.
    v = _mk_view(qapp)
    before = v.transform().m11()
    evt = _wheel()
    v.wheelEvent(evt)
    assert v.transform().m11() > before, (
        "the wheel should zoom a standalone view in")
    assert evt.isAccepted(), (
        "a standalone view must keep the wheel event")
    v.close()


def test_embedded_mode_ignores_wheel_and_pans(qapp):
    # Panel preview (the "Detalles del proyecto" fix): when embedded,
    # the wheel must pass through to the enclosing QScrollArea (event
    # not accepted, transform untouched) and the drag must not pan the
    # scene; hovering and clicks are a separate path, not touched here.
    from PySide6.QtWidgets import QGraphicsView
    v = _mk_view(qapp)
    before = v.transform().m11()
    v.set_embedded(True)
    assert v.dragMode() == QGraphicsView.NoDrag
    evt = _wheel()
    v.wheelEvent(evt)
    assert v.transform().m11() == pytest.approx(before), (
        "the wheel in embedded (passive preview) mode must not zoom")
    assert not evt.isAccepted(), (
        "an embedded view must not keep the wheel event: it belongs to "
        "the page scrolling")
    # Toggling back off restores the fully interactive mode.
    v.set_embedded(False)
    assert v.dragMode() == QGraphicsView.ScrollHandDrag
    v.close()


def test_overview_marks_panel_charts_embedded(qapp):
    # The panel helper marks live charts as passive previews, whichever
    # shape they come in (composite widget exposing `.view`, or a
    # ChartView subclass), and leaves non-chart widgets alone.
    from PySide6.QtWidgets import QGraphicsView, QWidget
    from nightscribe.gui.overview import _mark_embedded
    from nightscribe.gui.widgets.orbit_widget import OrbitChart
    from nightscribe.gui.widgets.lightcurve_widget import LightCurveChart

    oc = OrbitChart()
    _mark_embedded(oc)
    assert oc.view.dragMode() == QGraphicsView.NoDrag
    assert oc.view._embedded is True
    oc.close()

    lc = LightCurveChart()
    _mark_embedded(lc)
    assert lc.dragMode() == QGraphicsView.NoDrag
    lc.close()

    plain = QWidget()
    _mark_embedded(plain)          # must not raise
    plain.close()


def test_widgets_package_does_not_import_matplotlib(qapp, tmp_path):
    # ADR-029: gui/widgets/* must not import matplotlib. The palette lives
    # in viz/palette.py (matplotlib-free); if a future change pulled
    # viz.style (which does import matplotlib) into the widget package,
    # this subprocess would come back non-zero.
    code = (
        "import sys;"
        "from PySide6.QtWidgets import QApplication;"
        "_ = QApplication.instance() or QApplication([]);"
        "import nightscribe.gui.widgets.base_chart;"
        "print('matplotlib' if any(m.startswith('matplotlib') for m in sys.modules) else 'clean')"
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, f"import failed:\n{r.stderr}"
    assert r.stdout.strip() == "clean", (
        f"gui.widgets pulled in matplotlib:\n{r.stdout}\n{r.stderr}")
