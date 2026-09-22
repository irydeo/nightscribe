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

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPixmap, QTransform
from PySide6.QtWidgets import (QGraphicsPixmapItem, QGraphicsSimpleTextItem,
                               QGraphicsView)

from ...viz import palette
from .base_chart import ChartView

logger = logging.getLogger("nightscribe.gui.ufe_image_view")

_RENDER_COALESCE_MS = 120   # stretch drags collapse into a single render


class UfeImageView(ChartView):
    # @args: state - the shared UfeImageState; the view subscribes to its
    #        signals and renders whatever display_uint8() returns

    ZOOM_MIN = 0.05
    ZOOM_MAX = 40.0    # pixel-level inspection of subtle targets
    WHEEL_STEP = 1.5   # a bolder notch: 40x must be reachable by wheel

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self._pix_item = None       # QGraphicsPixmapItem, None when empty
        self._hint = None           # empty-state text item
        self._need_initial_fit = False

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render)

        state.image_loaded.connect(self._on_image_loaded)
        state.stretch_changed.connect(self._render_soon)
        self.set_hover_probe(state.probe_text)
        self._show_hint()

    # ------------------------------------------------------------ image

    def _on_image_loaded(self):
        # A new plate landed (or was cleared): rebuild the pixmap item and
        # fit once. The fit is deferred while the viewport is not sized.
        self.clear()
        self._pix_item = None
        self._hint = None             # clear() removed it from the scene
        if not self._state.has_image:
            self._show_hint()
            return
        w, h = self._state.plate_shape
        self.set_scene_rect(0, 0, w, h)
        self._render()
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

    def fit_to_factor(self, factor):
        # Absolute zoom presets: 1.0 shows one plate pixel per device
        # pixel. Keeps the current view centre.
        # @args: factor - absolute scale (0.5, 1, 2, 4 for the presets)
        factor = min(max(float(factor), self.ZOOM_MIN), self.ZOOM_MAX)
        centre = self.mapToScene(self.viewport().rect().center())
        self.resetTransform()
        self.scale(factor, factor)
        self.centerOn(centre)

    def current_factor(self):
        # @return: the current absolute scale (1.0 = 100 %)
        return self.transform().m11()

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
        # Drops everything but the plate pixmap (the feature tab being
        # deactivated clears its own annotations this way).
        if self._pix_item is None:
            return
        keep = self._pix_item
        for it in list(self._items_registered):
            if it is not keep:
                self.scene().removeItem(it)
                self._items_registered.remove(it)

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
