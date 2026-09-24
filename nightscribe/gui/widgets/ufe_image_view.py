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
* While a picking tab is on stage (pick mode) the resting cursor is the
  crosshair (the hand only shows while a pan drag is held), the reticle
  forces full-viewport repaints so it never leaves trails, and the probe
  panel pins itself to the top-left corner instead of chasing the cursor.
"""

import logging
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPen,
                           QPixmap, QTransform)
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsLineItem,
                               QGraphicsPixmapItem, QGraphicsRectItem,
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


def cross_marker_items(x, y, scene_w, scene_h, color, box_half):
    # The "cross" object marker (ADR-046): a full-frame crosshair with a
    # central box, in the spirit of the classic tracker charts. The
    # lines span the plate in scene coordinates and the pens are
    # cosmetic, so the marker stays thin and crisp at any zoom, and an
    # export of a visible region still shows the cross crossing it.
    # @args: x, y - object position in scene (plate px) coordinates,
    #        scene_w, scene_h - plate size in px, color - marker colour
    #        (hex string or QColor), box_half - central box half side
    #        in scene px
    # @return: [4 QGraphicsLineItem + 1 QGraphicsRectItem]
    pen = QPen(QColor(color))
    pen.setWidthF(1.8)
    pen.setCosmetic(True)
    gap = box_half * 1.4
    items = []
    for x0, y0, x1, y1 in ((0.0, y, x - gap, y), (x + gap, y, scene_w, y),
                           (x, 0.0, x, y - gap), (x, y + gap, x, scene_h)):
        ln = QGraphicsLineItem(x0, y0, x1, y1)
        ln.setPen(pen)
        items.append(ln)
    box = QGraphicsRectItem(x - box_half, y - box_half,
                            2.0 * box_half, 2.0 * box_half)
    box.setPen(pen)
    items.append(box)
    return items


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
        self._show_annotations = True   # the top bar can hide the plate's
                                        # saved marks; the default is on
        self._frame_override = None  # Blink tab: fn() -> uint8 display
                                     # frame replacing the state's own
        # pick mode (the Measure/Annotate/Compare tabs while on stage):
        # a crosshair cursor plus a viewport reticle that snaps to the
        # gaussian centroid of the source under the mouse
        self._pick_mode = False
        self._mouse_vp = None        # last viewport cursor pos (or None)
        self._snap_scene = None      # snapped scene point (or None)
        self._snap_timer = QTimer(self)
        self._snap_timer.setSingleShot(True)
        self._snap_timer.timeout.connect(self._snap_now)
        self.show_north = True      # HUD toggles (need a WCS to paint)
        self.show_scale = True
        # metadata corner boxes (ADR-046): the provider is consulted at
        # paint time, so solving, measuring or attaching an object all
        # show up without any invalidation wiring
        self.show_boxes = False
        self._boxes_provider = None    # fn() -> chart_annotate boxes dict
        self._boxes_tl_h = 0.0         # painted top-left box height
                                       # (device px; the probe ducks it)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render)

        state.image_loaded.connect(self._on_image_loaded)
        state.stretch_changed.connect(self._render_soon)
        # the HUD depends on WCS, and it paints on the viewport
        state.wcs_changed.connect(self.viewport().update)
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

    def set_frame_override(self, fn):
        # A feature tab (the Blink one, phase E) may own the displayed
        # frame: fn() returns a uint8 array in SCREEN orientation that the
        # normal pipeline (plate-covering transform included) paints
        # instead of the state's. None hands the plate back.
        # @args: fn - callable or None
        self._frame_override = fn
        self._render()

    def refresh_frame(self):
        # Re-pulls the frame (the Blink tab's timer swaps phases here).
        self._render()

    def _render(self):
        # Swaps the display pixmap in place; zoom and pan stay put.
        if self._frame_override is not None:
            img8 = self._frame_override()
        else:
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
        self.set_annotations_visible(self._show_annotations)
        self._layout_annotations()

    def set_annotations_visible(self, on):
        # @args: on - show or hide the plate's saved ANNOTATE marks (the
        #        photometry markers and the sequence stars are other
        #        layers and always follow their own tabs)
        self._show_annotations = bool(on)
        for it in self._annotation_items:
            it.setVisible(self._show_annotations)

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

    def set_hud(self, north=None, scale=None, boxes=None):
        # @args: north, scale - True/False to toggle each HUD piece
        #        (they only paint when the plate carries a WCS),
        #        boxes - the metadata corner boxes (ADR-046; they paint
        #        with or without a WCS: the name and the site lines do
        #        not need one)
        if north is not None:
            self.show_north = bool(north)
        if scale is not None:
            self.show_scale = bool(scale)
        if boxes is not None:
            self.show_boxes = bool(boxes)
        self.viewport().update()

    def set_boxes_provider(self, fn):
        # @args: fn - callable returning a core/chart_annotate boxes dict
        #        (or {}), consulted at every paint; None drops the layer
        self._boxes_provider = fn
        self.viewport().update()

    def drawForeground(self, painter, rect):
        # Viewport-space HUD (north arrow, scale bar, corner boxes) under
        # the base's watermark; device coordinates, so zoom/pan never
        # move them. The pick reticle goes last: it must sit on top of
        # everything.
        painter.save()
        painter.resetTransform()
        self._paint_hud(painter, self.viewport().width(),
                        self.viewport().height())
        painter.restore()
        super().drawForeground(painter, rect)
        if self._pick_mode and self._mouse_vp is not None:
            painter.save()
            painter.resetTransform()
            self._paint_reticle(painter)
            painter.restore()

    # -------------------------------------------------- pick reticle

    def set_pick_cursor(self, on):
        # Picking mode for the clicking tabs: a crosshair cursor plus the
        # snapping reticle. The overlay never reaches the PNG export (it
        # renders the scene; the reticle is view foreground only).
        # @args: on - pick mode on or off
        self._pick_mode = bool(on)
        self._apply_rest_cursor()
        if self._pick_mode:
            # the reticle spans the whole viewport in device coords but
            # owns no scene rect: with partial (scene-rect) repaints it
            # gets clipped into segments that stay behind as trails
            self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        else:
            self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
            self._mouse_vp = None
            self._snap_scene = None
        self.viewport().update()

    def _apply_rest_cursor(self):
        # The resting cursor says what a click does here: the crosshair
        # while a picking tab is on stage (a precise centroid cannot be
        # marked with the hand), the open hand elsewhere (the pan
        # affordance). ScrollHandDrag shows the closed hand while a
        # button is held and restores the OPEN hand on release, so
        # mouseReleaseEvent / enterEvent re-apply this.
        self.viewport().setCursor(Qt.CrossCursor if self._pick_mode
                                  else Qt.OpenHandCursor)

    def mouseReleaseEvent(self, event):
        # ScrollHandDrag hands the cursor back as an open hand on every
        # release; in pick mode the resting shape is the crosshair.
        super().mouseReleaseEvent(event)
        self._apply_rest_cursor()

    def enterEvent(self, event):
        # The resting cursor is ours to keep: dialogs and drags may have
        # stomped it while the pointer was away.
        self._apply_rest_cursor()
        super().enterEvent(event)

    def _tooltip_anchor_pos(self, viewport_pos, br):
        # While picking, the probe panel never chases the cursor (it would
        # cover the very star being marked): it pins to the viewport's
        # top-left corner, the one free of HUD pieces (north arrow
        # top-right, scale bar bottom-left, watermark bottom-right).
        if self._pick_mode:
            scale = max(self.current_factor(), 1e-3)
            margin = 12.0 / scale
            tl = self.mapToScene(0, 0)
            # the metadata top-left box would sit under the panel: duck
            extra = self._boxes_tl_h / scale if self.show_boxes else 0.0
            return tl.x() + margin, tl.y() + margin + extra
        return super()._tooltip_anchor_pos(viewport_pos, br)

    def mouseMoveEvent(self, event):
        # The probe stays as always; in pick mode the cursor position is
        # remembered for the reticle and a snap recompute is coalesced.
        if self._pick_mode:
            self._mouse_vp = event.position().toPoint()
            if not self._snap_timer.isActive():
                self._snap_timer.start(60)      # one search per 60 ms
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        # The cursor left: no reticle hangs around.
        if self._pick_mode:
            self._mouse_vp = None
            self._snap_scene = None
            self.viewport().update()
        super().leaveEvent(event)

    def _snap_now(self):
        # If a detected source sits near the cursor, the reticle snaps to
        # its gaussian centroid (the click is born centred). Slow plates
        # never stall the mouse: the search runs on a small cutout only.
        # The detector is photometry.local_sources: the global-std one was
        # blind to faint sources on structured backgrounds (a SN in its
        # galaxy) and its 5-brightest cap hid them behind the field's
        # bright stars. The snap reach is capped in plate px: at fit zoom
        # 12/scale px was a ~30 px grab and the reticle "jumped to the
        # bright stars".
        if not self._pick_mode or self._mouse_vp is None \
                or not self._state.has_image:
            return
        from ...core import photometry as _phot
        scene_pt = self.mapToScene(self._mouse_vp)
        col, row = self._state.scene_to_data(scene_pt.x(), scene_pt.y())
        data = self._state.data
        h, w = data.shape
        half = 24
        y0, y1 = max(0, int(row) - half), min(h, int(row) + half)
        x0, x1 = max(0, int(col) - half), min(w, int(col) + half)
        sub = data[y0:y1, x0:x1]
        self._snap_scene = None
        if sub.size:
            sources = _phot.local_sources(sub, k=4.0, min_sep=6,
                                          max_sources=20)
            reach = min(12.0 / max(self.current_factor(), 1e-3), 9.0)
            best, best_d = None, reach ** 2
            for sx, sy, _pk in sources:
                gx, gy = sx + x0, sy + y0
                d = (gx - col) ** 2 + (gy - row) ** 2
                if d < best_d:
                    best, best_d = (gx, gy), d
            if best is not None:
                cen = _phot.gaussian_centroid(data, best[0], best[1])
                if cen["ok"]:
                    self._snap_scene = self._state.data_to_scene(
                        cen["x"], cen["y"])
        self.viewport().update()

    def _paint_reticle(self, painter):
        # The crosshair: full-viewport lines with a central gap, white on
        # black (legible on sky, stars and cores alike). At the snapped
        # point when a source was found, else under the cursor.
        if self._snap_scene is not None:
            vp = self.mapFromScene(self._snap_scene[0], self._snap_scene[1])
        else:
            vp = self._mouse_vp
        if vp is None:
            return
        x, y = vp.x(), vp.y()
        w, h = self.viewport().width(), self.viewport().height()
        gap = 8
        for dx, dy in ((1, 1), (0, 0)):       # black shadow, then white
            color = QColor(0, 0, 0, 160) if dx else QColor(230, 235, 245)
            painter.setPen(QPen(color, 1.6 if dx else 1.0))
            painter.drawLine(x + dx, 0, x + dx, y - gap + dy)
            painter.drawLine(x + dx, y + gap + dy, x + dx, h)
            painter.drawLine(0, y + dy, x - gap + dx, y + dy)
            painter.drawLine(x + gap + dx, y + dy, w, y + dy)

    def _paint_hud(self, painter, w, h, k=1.0):
        # @args: painter - device-coords painter, w, h - surface size in
        #        device px, k - export pixel ratio (1.0 on screen)
        # The boxes paint with or without a WCS (the name and the site
        # lines do not need one); north/scale still do. With the boxes
        # on, the compass moves to the bottom centre (and gains the east
        # leg) and the scale bar to the bottom right: the report layout
        # keeps its corners free.
        if not self._state.has_image:
            return
        boxes_on = self._paint_boxes(painter, w, h, k)
        if self._state.wcs is None:
            return
        if self.show_north:
            self._paint_north(painter, w, h, k, bottom=boxes_on)
        if self.show_scale:
            self._paint_scale(painter, w, h, k, right=boxes_on)

    def _paint_boxes(self, painter, w, h, k):
        # The metadata corner boxes (ADR-046): square, dark, monospace,
        # in the spirit of the classic tracker charts. Content comes
        # from the provider (core/chart_annotate rules); a provider
        # hiccup never breaks the paint.
        # @return: True when something was drawn
        self._boxes_tl_h = 0.0
        if not self.show_boxes or self._boxes_provider is None:
            return False
        try:
            boxes = self._boxes_provider() or {}
        except Exception as err:
            logger.warning("chart boxes provider failed: %s", err)
            return False
        if not boxes:
            return False
        font = QFont("monospace")
        font.setPixelSize(max(8.0, 10.0 * k))
        painter.setFont(font)
        fm = painter.fontMetrics()
        pad, margin = 5.0 * k, 10.0 * k
        line_h = fm.height()
        for key, right, bottom in (("top_left", False, False),
                                   ("top_right", True, False),
                                   ("bottom_left", False, True)):
            lines = boxes.get(key)
            if not lines:
                continue
            bw = max(fm.horizontalAdvance(t) for t in lines) + 2 * pad
            bh = line_h * len(lines) + 2 * pad
            x = w - margin - bw if right else margin
            y = h - margin - bh if bottom else margin
            bg = QColor(palette.BG)
            bg.setAlpha(215)
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            painter.drawRect(QRectF(x, y, bw, bh))
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(palette.MUTED), max(1.0, 0.8 * k)))
            painter.drawRect(QRectF(x, y, bw, bh))
            painter.setPen(QPen(QColor(palette.FG)))
            for i, t in enumerate(lines):
                baseline = y + pad + i * line_h + fm.ascent()
                if right:
                    painter.drawText(
                        QRectF(x, y + pad + i * line_h, bw - pad, line_h),
                        Qt.AlignRight, t)
                else:
                    painter.drawText(QPointF(x + pad, baseline), t)
            if key == "top_left":
                self._boxes_tl_h = bh + margin
        return True

    def _paint_north(self, painter, w, h, k, bottom=False):
        # North arrow, rotated by the plate PA (positive = east of north,
        # clockwise; the legacy convention). Legacy spot: top-right, N
        # only. With the corner boxes on it becomes the bottom-centre
        # compass: the same arrow plus the east leg (90° anticlockwise
        # from north on screen, flipped on mirrored plates).
        pa = -self._state.wcs.rotation()
        cx, cy = (w / 2.0, h - 44 * k) if bottom else (w - 44 * k, 48 * k)
        length = 30 * k
        legs = [("N", pa)]
        if bottom:
            east = pa + 90.0 if self._state.wcs.is_mirrored() \
                else pa - 90.0
            legs.append(("E", east))
        for label, angle in legs:
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(angle)
            for color, width in ((QColor(0, 0, 0, 160), 3.6 * k),
                                 (QColor(palette.FG), 2.0 * k)):
                painter.setPen(QPen(color, width))
                painter.drawLine(QPointF(0, length / 2),
                                 QPointF(0, -length / 2))
                ah = length * 0.3
                painter.drawLine(QPointF(0, -length / 2),
                                 QPointF(-ah / 2, -length / 2 + ah))
                painter.drawLine(QPointF(0, -length / 2),
                                 QPointF(ah / 2, -length / 2 + ah))
            f = QFont()
            f.setPointSizeF(10 * k)
            painter.setFont(f)
            painter.drawText(QRectF(-14 * k, length / 2 + 2 * k,
                                    28 * k, 14 * k), Qt.AlignHCenter, label)
            painter.restore()

    def _paint_scale(self, painter, w, h, k, right=False):
        # Scale bar: a round arcsec span that lands near 90 screen px at
        # the current zoom. Legacy spot: bottom-left; with the corner
        # boxes on it moves to the bottom-right (that corner stays free).
        factor = max(self.current_factor(), 1e-6) * k
        per_px = self._state.wcs.pixel_scale() / factor   # arcsec/device px
        arcsec = _round_arcsec(90.0 * k * per_px)
        bar = min(max(arcsec / per_px, 12.0 * k), w * 0.35)
        x0 = (w - 16 * k - bar) if right else 16 * k
        y0 = h - 26 * k
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
        if right:
            painter.drawText(QRectF(x0 - 40 * k, y0 - 22 * k,
                                    bar + 40 * k, 18 * k),
                             Qt.AlignRight, f"{arcsec:g}″")
        else:
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
