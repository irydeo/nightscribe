############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: plate image view (ADR-044)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Unified FITS Editor's image view (ADR-044): a ChartView whose scene
lives in ORIGINAL plate pixels (y down, screen convention), so zoom never
corrupts what tabs annotate and 100 % means exactly one device pixel per
plate pixel.

Differences from the plain ChartView:

* The base re-fits the scene on every resize; here the observer's zoom
  survives window resizes, so the auto-fit only happens when a new plate
  lands (and on the first resize big enough to hold one).
* Zoom reaches pixel level (ZOOM_MAX 40, wheel step 1.5, like the finder
  chart) and the pixmap uses nearest-neighbour scaling: at 200/400 % you
  inspect real plate pixels, not an interpolation.
* Stretch re-renders swap the pixmap in place: the transform (zoom, pan)
  is untouched.
"""

import logging
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPen,
                           QPixmap, QTransform)
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsPixmapItem,
                               QGraphicsSimpleTextItem, QGraphicsView)

from ...viz import palette
from .base_chart import ChartView

logger = logging.getLogger("nightscribe.gui.ufe_image_view")

_RENDER_COALESCE_MS = 120   # stretch drags collapse into a single render


def _round_arcsec(target):
    # The round 1/2/5 x 10^exp span nearest to the target, for the scale
    # bar (the legacy annotate dialog uses the same rounding).
    # @args: target - arcsec the bar should roughly cover
    # @return: a round arcsec value
    target = max(float(target), 1e-9)
    exp = math.floor(math.log10(target))
    m = min((1.0, 2.0, 5.0),
            key=lambda v: abs(math.log10(v * 10.0 ** exp)
                              - math.log10(target)))
    return m * 10.0 ** exp


class UfeImageView(ChartView):
    # @args: state - the shared UfeImageState; the view subscribes to its
    #        signals and renders whatever display_uint8() returns

    ZOOM_MIN = 0.05
    ZOOM_MAX = 40.0    # pixel-level inspection of subtle targets
    WHEEL_STEP = 1.5   # a bolder notch: 40x must be reachable by wheel

    zoom_changed = Signal(float)   # the absolute scale after any zoom move

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self._pix_item = None       # QGraphicsPixmapItem, None when empty
        self._hint = None           # empty-state text item
        self._need_initial_fit = False
        self._annotation_items = []  # read-only ANNOTATE layer (survives
                                     # clear_overlays, rebuilt per plate)
        self._annotation_labels = []  # [(label item, ann dict)]
        self.show_north = True      # HUD toggles (need a WCS to paint)
        self.show_scale = True

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render)

        state.image_loaded.connect(self._on_image_loaded)
        state.stretch_changed.connect(self._render_soon)
        state.wcs_changed.connect(self.update)   # the HUD depends on WCS
        self.zoom_changed.connect(lambda _f: self._layout_annotations())
        self.set_hover_probe(state.probe_text)
        self.setAccessibleName(self.tr("FITS image view"))
        self._show_hint()

    # ------------------------------------------------------------ image

    def _on_image_loaded(self):
        # A new plate landed (or was cleared): rebuild the pixmap item and
        # the read-only ANNOTATE layer, and fit once. The fit is deferred
        # while the viewport is not sized.
        self.clear()
        self._pix_item = None
        self._hint = None             # clear() removed it from the scene
        self._annotation_items = []   # same fate; rebuilt below
        self._annotation_labels = []
        if not self._state.has_image:
            self._show_hint()
            return
        w, h = self._state.plate_shape
        self.set_scene_rect(0, 0, w, h)
        self._render()
        self._rebuild_annotations()
        if self.viewport().width() >= 4 and self.viewport().height() >= 4:
            self.fit_to_scene()
        else:
            self._need_initial_fit = True

    def _render_soon(self):
        # @return: None. Coalesces a burst of stretch ticks into one render.
        if not self._render_timer.isActive():
            self._render_timer.start(_RENDER_COALESCE_MS)

    def _render(self):
        # Swaps the display pixmap in place; zoom and pan stay put.
        img8 = self._state.display_uint8()
        if img8 is None:
            return
        h, w = img8.shape
        qimg = QImage(img8.data, w, h, w,
                      QImage.Format_Grayscale8).copy()  # own the buffer
        pix = QPixmap.fromImage(qimg)
        plate_w, plate_h = self._state.plate_shape
        if self._pix_item is None:
            self._pix_item = QGraphicsPixmapItem()
            # nearest neighbour: real plate pixels at high zoom
            self._pix_item.setTransformationMode(Qt.FastTransformation)
            self.add_item(self._pix_item)
        self._pix_item.setPixmap(pix)
        # scene units stay ORIGINAL plate px even when the pixmap was
        # downscaled to the display cap: stretch it back over the plate
        tr = QTransform()
        tr.scale(plate_w / w, plate_h / h)
        self._pix_item.setTransform(tr)

    # ------------------------------------------------------- fit / zoom

    def fit_to_scene(self, pad=0.02):
        # The base fit pins the sceneRect to the padded frame, which would
        # clamp panning at the plate edge when zoomed deep into a corner.
        # After fitting, relax the bounds with a 25 % margin all around.
        super().fit_to_scene(pad)
        if self._state.has_image:
            w, h = self._state.plate_shape
            self.setSceneRect(QRectF(-0.25 * w, -0.25 * h,
                                     1.5 * w, 1.5 * h))
        self.zoom_changed.emit(self.current_factor())

    def fit_to_factor(self, factor):
        # Absolute zoom presets: 1.0 shows one plate pixel per device
        # pixel. Keeps the current view centre.
        # @args: factor - absolute scale (0.5, 1, 2, 4 for the presets)
        factor = min(max(float(factor), self.ZOOM_MIN), self.ZOOM_MAX)
        centre = self.mapToScene(self.viewport().rect().center())
        self.resetTransform()
        self.scale(factor, factor)
        self.centerOn(centre)
        self.zoom_changed.emit(self.current_factor())

    def _zoom_by(self, factor):
        # Wheel / +/- key zoom through the base clamp, then report.
        old = self.transform().m11()
        super()._zoom_by(factor)
        new = self.transform().m11()
        if new != old:
            self.zoom_changed.emit(new)

    def mouseDoubleClickEvent(self, event):
        # Double-click returns to the fit (the base's reset_view).
        if event.button() == Qt.LeftButton and self._state.has_image:
            self.fit_to_scene()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def current_factor(self):
        # @return: the current absolute scale (1.0 = 100 %)
        return self.transform().m11()

    def zoom_in(self):
        # One wheel-notch up (the +/- keys and the wheel share the step).
        self._zoom_by(self.WHEEL_STEP)

    def zoom_out(self):
        # One wheel-notch down.
        self._zoom_by(1.0 / self.WHEEL_STEP)

    def resizeEvent(self, event):
        # Overrides the base's auto-fit-on-resize: the observer's zoom
        # survives window drags. The one exception is the deferred initial
        # fit of a plate that loaded before the viewport was sized.
        QGraphicsView.resizeEvent(self, event)
        if self._need_initial_fit and self.viewport().width() >= 4 \
                and self.viewport().height() >= 4:
            self._need_initial_fit = False
            self.fit_to_scene()

    # ---------------------------------------------------------- overlays

    def add_overlay(self, item):
        # @args: item - a QGraphicsItem in scene (plate px) coordinates
        # @return: the item (registered, so clear_overlays drops it)
        return self.add_item(item)

    def clear_overlays(self):
        # Drops every feature-tab overlay; the plate pixmap and the
        # read-only ANNOTATE layer stay (they belong to the plate, not
        # to whichever tab is on stage).
        keep = set([self._pix_item] + self._annotation_items)
        for it in list(self._items_registered):
            if it not in keep:
                self.scene().removeItem(it)
                self._items_registered.remove(it)

    # ------------------------------------------------------ annotations

    def _rebuild_annotations(self):
        # Paints the plate's ANNOTATE cards (read from the header at load)
        # as read-only circles with labels; radii are plate px (they zoom
        # with the image, like AIJ), labels stay constant screen size.
        self._annotation_items = []
        self._annotation_labels = []      # [(label item, ann dict)]
        for ann in self._state.annotations:
            color = QColor(ann["color"])
            if not color.isValid():
                color = QColor("#ffb347")
            pen = QPen(color)
            pen.setWidthF(2.0)
            pen.setCosmetic(True)
            x, y = self._state.data_to_scene(ann["x"], ann["y"])
            r = max(float(ann["size"]), 2.0)
            circle = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
            circle.setPen(pen)
            circle.setZValue(40)
            self._annotation_items.append(self.add_item(circle))
            if ann["label"]:
                label = QGraphicsSimpleTextItem(ann["label"])
                label.setBrush(QBrush(color))
                label.setZValue(40)
                self._annotation_items.append(self.add_item(label))
                self._annotation_labels.append((label, ann))
        self._layout_annotations()

    def _layout_annotations(self):
        # Re-seats the annotation labels for the current zoom (constant
        # screen size, just above their circle; circles keep plate-px
        # radii so they mean the same patch of sky at any zoom).
        if not self._annotation_labels:
            return
        scale = max(self.current_factor(), 1e-3)
        for item, ann in self._annotation_labels:
            f = QFont()
            f.setPointSizeF(max(0.5, 10.0 / scale))
            item.setFont(f)
            x, y = self._state.data_to_scene(ann["x"], ann["y"])
            r = max(float(ann["size"]), 2.0)
            item.setPos(x - item.boundingRect().width() / 2,
                        y - r - item.boundingRect().height() - 4.0 / scale)

    # ------------------------------------------------------------- HUD

    def set_hud(self, north=None, scale=None):
        # @args: north, scale - True/False to toggle each HUD piece
        #        (they only paint when the plate carries a WCS)
        if north is not None:
            self.show_north = bool(north)
        if scale is not None:
            self.show_scale = bool(scale)
        self.update()

    def drawForeground(self, painter, rect):
        # Viewport-space HUD (north arrow, scale bar) under the base's
        # watermark; device coordinates, so zoom/pan never move them.
        painter.save()
        painter.resetTransform()
        self._paint_hud(painter, self.viewport().width(),
                        self.viewport().height())
        painter.restore()
        super().drawForeground(painter, rect)

    def _paint_hud(self, painter, w, h, k=1.0):
        # @args: painter - device-coords painter, w, h - surface size in
        #        device px, k - export pixel ratio (1.0 on screen)
        if not self._state.has_image or self._state.wcs is None:
            return
        if self.show_north:
            self._paint_north(painter, w, h, k)
        if self.show_scale:
            self._paint_scale(painter, w, h, k)

    def _paint_north(self, painter, w, h, k):
        # North arrow in the top-right corner, rotated by the plate PA
        # (positive = east of north, clockwise; the legacy convention).
        pa = -self._state.wcs.rotation()
        cx, cy = w - 44 * k, 48 * k
        length = 30 * k
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(pa)
        for color, width in ((QColor(0, 0, 0, 160), 3.6 * k),
                             (QColor(palette.FG), 2.0 * k)):
            painter.setPen(QPen(color, width))
            painter.drawLine(QPointF(0, length / 2), QPointF(0, -length / 2))
            ah = length * 0.3
            painter.drawLine(QPointF(0, -length / 2),
                             QPointF(-ah / 2, -length / 2 + ah))
            painter.drawLine(QPointF(0, -length / 2),
                             QPointF(ah / 2, -length / 2 + ah))
        f = QFont()
        f.setPointSizeF(10 * k)
        painter.setFont(f)
        painter.drawText(QRectF(-14 * k, length / 2 + 2 * k,
                                28 * k, 14 * k), Qt.AlignHCenter, "N")
        painter.restore()

    def _paint_scale(self, painter, w, h, k):
        # Scale bar in the bottom-left corner: a round arcsec span that
        # lands near 90 screen px at the current zoom.
        factor = max(self.current_factor(), 1e-6) * k
        per_px = self._state.wcs.pixel_scale() / factor   # arcsec/device px
        arcsec = _round_arcsec(90.0 * k * per_px)
        bar = min(max(arcsec / per_px, 12.0 * k), w * 0.35)
        x0, y0 = 16 * k, h - 26 * k
        for color, width in ((QColor(0, 0, 0, 160), 3.6 * k),
                             (QColor(palette.FG), 2.0 * k)):
            painter.setPen(QPen(color, width))
            painter.drawLine(QPointF(x0, y0), QPointF(x0 + bar, y0))
            painter.drawLine(QPointF(x0, y0 - 5 * k), QPointF(x0, y0 + 5 * k))
            painter.drawLine(QPointF(x0 + bar, y0 - 5 * k),
                             QPointF(x0 + bar, y0 + 5 * k))
        f = QFont()
        f.setPointSizeF(9 * k)
        painter.setFont(f)
        painter.setPen(QPen(QColor(palette.FG)))
        painter.drawText(QRectF(x0, y0 - 22 * k, bar + 40 * k, 18 * k),
                         Qt.AlignLeft, f"{arcsec:g}″")

    # ----------------------------------------------------------- export

    def export_png(self, path, dpi=100, bg=palette.BG):
        # The base export renders only scene items; the HUD is painted in
        # the view's foreground, so it is re-stamped here between the
        # scene and the watermark (scaled by the export pixel ratio).
        # @args: path - output file, dpi - output density, bg - background
        # @return: the Path written
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        vw = self.viewport().size().width()
        vh = self.viewport().size().height()
        if vw < 2 or vh < 2:
            vw, vh = 800, 450
        k = dpi / 96.0
        pw = max(1, int(vw * k))
        ph = max(1, int(vh * k))
        pix = QPixmap(pw, ph)
        pix.fill(QColor(bg))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        left = self.mapToScene(0, 0).toPoint().x()
        top = self.mapToScene(0, 0).toPoint().y()
        w = self.mapToScene(vw, 0).x() - left
        h = self.mapToScene(0, vh).y() - top
        painter.save()
        self._scene.render(painter, target=QRectF(0, 0, pw, ph),
                           source=QRectF(left, top, w, h))
        painter.restore()
        self._paint_hud(painter, pw, ph, k=k)
        self._paint_watermark(painter, pw, ph)
        painter.end()
        pix.save(str(path))
        return path

    # ------------------------------------------------------ empty state

    def _show_hint(self):
        # The empty state: a muted hint centred in the scene.
        if self._hint is not None:
            return
        self._hint = QGraphicsSimpleTextItem(
            self.tr("Open a FITS image to start"))
        f = QFont()
        f.setPointSize(16)
        self._hint.setFont(f)
        self._hint.setBrush(QBrush(QColor(palette.MUTED)))
        self._hint.setZValue(50)
        br = self._hint.boundingRect()
        self._hint.setPos(-br.width() / 2, -br.height() / 2)
        self.set_scene_rect(-400, -300, 800, 600)
        self.add_item(self._hint)
        self.fit_to_scene()
