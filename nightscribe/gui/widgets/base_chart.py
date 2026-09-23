############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - base chart view (zoom / pan / fit / hover / export)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QPen, QPixmap,
                            QPainter, QFontMetricsF)
from PySide6.QtWidgets import (QGraphicsRectItem, QGraphicsScene,
                                QGraphicsSimpleTextItem, QGraphicsView)

from ...viz import palette

# Base class for the vector, interactive charts that replace the old
# QPixmap slots in the GUI (ADR-029). A subclass (OrbitChart, SkyChart, …)
# adds its items into the scene and installs a hover callback that says
# what to show at each scene coordinate. This layer owns only the
# generic chrome — the dark canvas, the zoom and pan, the fit-to-parent
# rule, the hover tooltip, the bottom-right watermark and the PNG export —
# and deliberately knows nothing about the concrete chart.

# The tooltip box is a semi-transparent panel with a 1px border; it follows
# the cursor while the hover probe answers "yes". The font size is a SCREEN
# size: the tooltip is a scene item, so _show_tooltip compensates by the
# current view scale (a fixed scene size read tiny at fit and huge zoomed in).
_TT_PAD = 6            # px
_TT_BG = QColor(0, 0, 0, 170)
_TT_BORDER = QColor("#2a2f42")
_TT_TEXT = QColor(palette.FG)
_TT_FONT_PT = 13.0     # screen points (≈17 px), constant at any zoom

# wheel zoom: one step = this many percent, capped by setZoomLimits(0.05, 8).
_WHEEL = 1.25
_ZOOM_MIN = 0.05
_ZOOM_MAX = 8.0

# Bottom-right watermark: same muted, low-opacity small text the matplotlib
# exports stamp on their PNGs (viz/style.watermark). Drawn in *viewport*
# space so it stays corner-anchored while the user zooms/pans.
_WM_TEXT = "NightScribe"
_WM_FONT_PT = 8
_WM_MARGIN = 10          # px from the bottom-right corner
_WM_ALPHA = 0.8


class ChartView(QGraphicsView):
    # A QGraphicsView with a dark background, mouse zoom under the cursor,
    # drag pan, fit-to-parent, a single hover tooltip and a PNG export of
    # the visible scene (not of a frozen pixmap — the export is whatever the
    # user left on screen). set_embedded(True) turns it into a passive
    # preview for embedding inside a scrolling page (wheel/drag scroll the
    # page; hover and click keep working — see set_embedded).
    #
    # Contract for subclasses (see ADR-029):
    #   * add items to `self.scene()` — the base already owns it;
    #   * install a hover probe with `set_hover_probe(fn)`, where
    #     fn(scene_x, scene_y) -> (hit: bool, text: str | list[str]);
    #   * either call `set_scene_rect(x, y, w, h)` so fit_to_scene() has a
    #     stable reference (recommended) or rely on the items' bounding
    #     boxes (sceneRectHint()).
    #
    # The two `Signal`s below exist so a parent window can react to the
    # user picking a moment (e.g. SkyChart's "best time" click). The base
    # itself does nothing with them.
    hover_changed = Signal(bool)        # True while the tooltip is on screen
    scene_clicked = Signal(QPointF)    # left-mouse release on the scene (no
                                       # drag); the QPointF is in *scene*
                                       # coordinates so a subclass can hit-test
                                       # it (e.g. SkyChart's safe-window band).

    # Zoom limits as class attributes so a subclass can retune them (the
    # finder chart needs pixel-level zoom, the orbit chart does not).
    # WHEEL_STEP is one wheel notch's factor for the same reason.
    ZOOM_MIN = _ZOOM_MIN
    ZOOM_MAX = _ZOOM_MAX
    WHEEL_STEP = _WHEEL

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._items_registered = []     # items added via add_item() (clear() drops them)
        self._hover_probe = None
        self._tooltip = None            # QGraphicsSimpleTextItem
        self._tip_panel = None          # QGraphicsRectItem behind the tooltip
        self._tip_emitted = False       # has hover_changed(True) fired since last hide?
        self._scene_rect_hint = None    # QRectF set by set_scene_rect, or None
        self._drag_start = None         # viewport point where the current pan started
        self._fit_pending = False       # a resize fit is queued, not yet run
        self._watermark = _WM_TEXT      # bottom-right signature
        self._wm_font = QFont()
        self._wm_font.setPointSize(_WM_FONT_PT)
        self._embedded = False          # passive preview in a scrolling page

        # --- chrome (view-level, not scene-level) -----------------------
        self.setBackgroundBrush(QBrush(QColor(palette.BG)))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setMouseTracking(True)     # mouseMoveEvent without a button down
        # zoom is clamped manually in _zoom_by (this Qt build has no
        # setZoomLimits; the limits are _ZOOM_MIN / _ZOOM_MAX)

    # ------------------------------------------------- items -------------

    def add_item(self, item):
        # @args: item - a QGraphicsItem
        # @return: the item; also registered for later clear().
        self._scene.addItem(item)
        self._items_registered.append(item)
        return item

    def clear(self):
        # Drops every item added via add_item() (subclasses use this when
        # the object under view changes — no stale rings or labels left).
        # The scene owns its items; removeItem() is enough (no deleteLater
        # on QGraphicsItem in this Qt build).
        for it in reversed(self._items_registered):
            self._scene.removeItem(it)
        self._items_registered = []
        self._tooltip = None
        self._tip_panel = None
        self._scene_rect_hint = None

    def scene(self):
        # @return: the QGraphicsScene (exposed for subclasses).
        return self._scene

    def scene_rect_hint(self):
        # @args: none
        # @return: the QRectF the subclass fixed with set_scene_rect, else
        #          the scene's own itemsBoundingRect (the union of the
        #          current items). This is the stable reference used by
        #          fit_to_scene().
        if self._scene_rect_hint is not None:
            return self._scene_rect_hint
        r = self._scene.itemsBoundingRect()
        if r.isEmpty():
            r = QRectF(-10, -10, 20, 20)
        return QRectF(r)

    def set_scene_rect(self, x, y, w, h):
        # @args: x, y, w, h — scene rect (same units as the items)
        self._scene_rect_hint = QRectF(x, y, w, h)

    # ------------------------------------------------- fit / zoom --------

    def fit_to_scene(self, pad=0.02):
        # Fits the visible rect to the scene's items (or fixed hint),
        # with a small padding so the content does not kiss the frame.
        # @args: pad — fraction of each side to pad (default 2%)
        r = self.scene_rect_hint()
        if r.isEmpty() or r.width() <= 0 or r.height() <= 0:
            return
        w, h = self.viewport().size().width(), self.viewport().size().height()
        if w < 4 or h < 4:
            # viewport not sized yet (offscreen / pre-show); do nothing —
            # the resizeEvent / the caller's explicit fit will handle it.
            return
        r = r.adjusted(-r.width() * pad, -r.height() * pad,
                       r.width() * pad, r.height() * pad)
        # Pin the scene rect to the padded frame before fitting. QGraphicsView
        # auto-grows its sceneRect to enclose every item, so a stray out-of-
        # frame item (e.g. a safe/transit band for a session that falls outside
        # the night, or a best-time marker) would otherwise pull fitInView off
        # centre and clip the chart. Anchoring it here keeps the fit exactly on
        # the chart's own frame, for every chart built on this base.
        self.setSceneRect(r)
        self._apply_fit(r)

    def _apply_fit(self, r):
        # How the (already padded) scene rect fills the current viewport.
        # Default: uniform-scale fitInView (KeepAspectRatio) — correct for
        # charts with a natural aspect (orbit, sky, approach, …).
        #
        # A chart whose x span keeps growing (the transit timeline: 400-900
        # scene units of night at a fixed ~114 of y) would letterbox into a
        # thin, dead-margin strip under KeepAspectRatio at every panel
        # width, so it overrides this method to fill the frame instead and
        # re-font its own text so nothing ends up stretched.
        # @args: r - the (already padded) scene rect to fit the viewport on
        self.fitInView(r, Qt.KeepAspectRatio)

    def reset_view(self):
        # Back to the fit. Called by the "Fit" / "1:1" buttons of the
        # enclosing widget, or by a double-click on the scene (a subclass
        # may wire that; the base does not).
        self.fit_to_scene()

    def set_embedded(self, flag=True):
        # Toggle "embedded preview" mode: the chart sits inside a scrolling
        # page (QScrollArea). There, the wheel and the drag belong to the
        # page (the wheel scrolls, no inline pan) while hover inspection
        # and clicking (which opens the dedicated ChartViewer for zoom,
        # pan and export) keep working.
        # @args: flag - True to embed (default is the full, interactive view)
        self._embedded = bool(flag)
        if self._embedded:
            self.setDragMode(QGraphicsView.NoDrag)
        else:
            self.setDragMode(QGraphicsView.ScrollHandDrag)

    # ------------------------------------------------- watermark ----------

    def set_watermark(self, text):
        # @args: text — the bottom-right signature (e.g. "NightScribe"),
        #        or "" / None to drop it. Mirrors the matplotlib exports'
        #        watermark param (viz/style.watermark).
        self._watermark = text or ""

    def _paint_watermark(self, painter, w, h):
        # @args: painter - a QPainter in DEVICE coordinates (viewport or
        #        pixmap), w, h - the painted surface size in device units.
        # Draws the bottom-right signature, same small font / muted colour /
        #        alpha as the matplotlib exports.
        text = self._watermark
        if not text:
            return
        painter.save()
        painter.setFont(self._wm_font)
        painter.setPen(QPen(QColor(palette.MUTED)))
        painter.setOpacity(_WM_ALPHA)
        tw = QFontMetricsF(self._wm_font).horizontalAdvance(text)
        painter.drawText(w - tw - _WM_MARGIN, h - _WM_MARGIN, text)
        painter.restore()

    def drawForeground(self, painter, rect):
        # Annotates the chart with the bottom-right watermark, painted in
        # viewport space so it stays corner-anchored while the user
        # zooms/pans (scene items would drift with the transform).
        super().drawForeground(painter, rect)
        if not self._watermark:
            return
        painter.save()
        painter.resetTransform()
        self._paint_watermark(painter, self.viewport().width(),
                              self.viewport().height())
        painter.restore()

    def _zoom_by(self, factor):
        # @args: factor — a positive number; applied to the current scale
        old = self.transform().m11()
        new = old * factor
        if new < self.ZOOM_MIN or new > self.ZOOM_MAX:
            return
        super().scale(factor, factor)

    def wheelEvent(self, event):
        # Wheel zooms centred on the cursor (setTransformationAnchor above);
        # in embedded preview mode the wheel belongs to the page, so pass
        # it through (the enclosing scroll area scrolls instead).
        if self._embedded or event.angleDelta().y() == 0:
            event.ignore()
            return
        step = self.WHEEL_STEP
        self._zoom_by(step if event.angleDelta().y() > 0 else 1.0 / step)
        event.accept()

    def mousePressEvent(self, event):
        # Left-click starts a pan (ScrollHandDrag handles the motion part
        # automatically, but we also record where the press was, so a click
        # without motion — a plain left release — can fire scene_clicked).
        if event.button() == Qt.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # A left release with no meaningful motion is a "click on the scene"
        # (the subclass may react: e.g. SkyChart picking a time). The QPointF
        # is in *scene* coordinates so the hit-test is unambiguous.
        if event.button() == Qt.LeftButton and self._drag_start is not None:
            moved = (event.position().toPoint() - self._drag_start).manhattanLength()
            if moved < 4:
                sc = self.mapToScene(event.position().toPoint())
                self.scene_clicked.emit(QPointF(sc.x(), sc.y()))
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        # The parent gave us a new size: keep the scene fitted to it so the
        # chart never letterboxes (that was the old QPixmap problem).
        #
        # A window drag queues dozens of configure events per frame; each
        # one used to force a full antialiased fitInView (a synchronous
        # scene re-render). On a slow raster path that saturates the GUI
        # thread and reads as a hard freeze. We coalesce: at most one
        # fit runs per event-loop turn regardless of how many resizes are
        # queued (_fit_pending guard + 0 ms singleShot).
        super().resizeEvent(event)
        if not self._fit_pending:
            self._fit_pending = True
            QTimer.singleShot(0, self._do_fit)

    def _do_fit(self):
        # One deferred fit per queued resize burst (see resizeEvent).
        self._fit_pending = False
        self.fit_to_scene()

    # ------------------------------------------------- hover -------------

    def set_hover_probe(self, fn):
        # @args: fn - callable(scene_x, scene_y) -> (hit, text). `text`
        #          may be a str or a list[str] (multi-line). `hit=False`
        #          hides the tooltip. `None` removes the probe entirely.
        self._hover_probe = fn
        if fn is None:
            self._hide_tooltip()

    def _probe_active(self):
        # @return: True when a hover probe is installed.
        return self._hover_probe is not None

    def mouseMoveEvent(self, event):
        # Moves the tooltip along with the cursor while the probe answers
        # "yes" at that scene point.
        pos = event.position()
        scene_pt = self.mapToScene(pos.toPoint())
        hit, text = False, None
        if self._probe_active():
            try:
                hit, text = self._hover_probe(scene_pt.x(), scene_pt.y())
            except Exception:
                hit, text = False, None
        if hit and text:
            self._show_tooltip(pos, text)
        else:
            self._hide_tooltip()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        # The cursor left the widget: the tooltip is stale.
        self._hide_tooltip()
        super().leaveEvent(event)

    def _show_tooltip(self, viewport_pos, text):
        # @args: viewport_pos - QPoint in this widget's viewport,
        #        text         - str or list[str]
        lines = text if isinstance(text, (list, tuple)) else [text]
        join = "\n".join(str(x) for x in lines)
        if self._tooltip is None:
            self._tooltip = QGraphicsSimpleTextItem()
            self._tooltip.setBrush(QBrush(_TT_TEXT))
            self._tooltip.setZValue(100)
            self._scene.addItem(self._tooltip)
        if self._tip_panel is None:
            self._tip_panel = QGraphicsRectItem()
            self._tip_panel.setBrush(QBrush(_TT_BG))
            self._tip_panel.setPen(QPen(_TT_BORDER, 1))
            self._tip_panel.setZValue(99)
            self._scene.addItem(self._tip_panel)
        # constant screen size at any zoom: the tooltip is a scene item,
        # so font, gaps and padding are divided by the view scale
        scale = max(self.transform().m11(), 1e-3)
        f = QFont()
        f.setPointSizeF(max(0.5, _TT_FONT_PT / scale))
        self._tooltip.setFont(f)
        self._tooltip.setText(join)
        br = self._tooltip.boundingRect()
        x, y = self._tooltip_anchor_pos(viewport_pos, br)
        self._tooltip.setPos(x, y)
        pad = _TT_PAD / scale
        self._tip_panel.setRect(
            br.adjusted(-pad, -pad, pad, pad).translated(x, y))
        if not self._tip_emitted:
            self._tip_emitted = True
            self.hover_changed.emit(True)

    def _tooltip_anchor_pos(self, viewport_pos, br):
        # Where the tooltip's top-left corner goes, in scene coords.
        # Default: a short offset from the cursor, flipping sides near the
        # edges of the visible scene (so it never trails off-view). A
        # subclass may pin it elsewhere (the UFE view anchors it to a
        # viewport corner while picking, so it never covers the star being
        # marked).
        # @args: viewport_pos - cursor position in viewport px,
        #        br - the tooltip text bounding rect in scene units
        # @return: (x, y) scene coordinates
        scale = max(self.transform().m11(), 1e-3)
        cursor = self.mapToScene(viewport_pos.toPoint())
        # approximate the visible scene width to decide the flip
        edge = self.mapToScene(self.viewport().width(), 0).x()
        gap = 14.0 / scale
        if cursor.x() + gap + br.width() > edge:
            x = cursor.x() - br.width() - gap
        else:
            x = cursor.x() + gap
        y = cursor.y() - br.height() - 8.0 / scale
        top = self.mapToScene(0, 0).y()
        if y < top:
            y = cursor.y() + gap
        return x, y

    def _hide_tooltip(self):
        # Removes both the text and the panel (they are paired).
        if self._tooltip is not None:
            self._scene.removeItem(self._tooltip)
            self._tooltip = None
        if self._tip_panel is not None:
            self._scene.removeItem(self._tip_panel)
            self._tip_panel = None
        if self._tip_emitted:
            self._tip_emitted = False
            self.hover_changed.emit(False)

    # ------------------------------------------------- export ------------

    def export_png(self, path, dpi=100, bg=palette.BG):
        # Renders the current visible scene to a PNG.
        # @args:  path — output file; dpi — output dots per point (default
        #           100 matches the old matplotlib preset; the pixmap keeps
        #           the widget's aspect, so portrait or landscape is both
        #           fine); bg — background hex (default the palette's BG, so
        #           the chart's empty margin matches the app).
        # @return: the Path written.
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        vw, vh = self.viewport().size().width(), self.viewport().size().height()
        if vw < 2 or vh < 2:
            # offscreen without a show(): fall back to a 16:9 default
            vw, vh = 800, 450
        scale = dpi / 96.0          # Qt points are 72 dpi, but a DPI of 96
                                    # is our practical target (matches the
                                    # old "1200 px wide" figure on screen)
        pw = max(1, int(vw * scale))
        ph = max(1, int(vh * scale))
        pix = QPixmap(pw, ph)
        pix.fill(QColor(bg))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        # sceneRect: the visible rect (the union of what's on screen).
        # Using scene().itemsBoundingRect() would export "everything" —
        # including zoomed-out content the user has scrolled away from.
        left, top = self.mapToScene(0, 0).toPoint().x(), self.mapToScene(0, 0).toPoint().y()
        w = self.mapToScene(vw, 0).x() - left
        h = self.mapToScene(0, vh).y() - top
        # target:  the destination rect in the pixmap (0,0,pw,ph)
        # source:  the scene rect to render (what the user was looking at)
        # Passing only one rect to QGraphicsScene.render() treats it as the
        # *target*; the source defaults to the full itemsBoundingRect, which
        # was producing a dark / empty PNG whenever the viewport was zoomed.
        painter.save()
        self._scene.render(painter, target=QRectF(0, 0, pw, ph),
                           source=QRectF(left, top, w, h))
        painter.restore()
        # QGraphicsScene.render() paints only the scene items — the view's
        # drawForeground watermark is not drawn into the pixmap, so stamp it
        # again here (same device-space signature, bottom-right).
        self._paint_watermark(painter, pw, ph)
        painter.end()
        pix.save(str(path))
        return path

    # ------------------------------------------------- misc --------------

    def color(self, name):
        # @args: name — a colour key from viz.palette
        # @return: a QColor
        return palette.color(name)
