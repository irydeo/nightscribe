############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Chart viewer dialog (zoom, pan, export)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import re
import shutil
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QScroller, QScrollArea,
                               QVBoxLayout)

# characters that no sane file system keeps in a name (Windows + the
# control range); the export dialog suggestion is sanitised through this.
_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

# The chart viewer opens in one of two modes (ADR-029 Fase 4):
#
#   * **pixmap** — a flat PNG file (the social-media exports, the reference-
#     field cutout). Rendered through a QLabel in a scroll area: wheel zoom,
#     drag pan, a "1:1" step and a one-click file copy.
#   * **widget** — a live vector chart (OrbitChart / SkyChart / TransitChart).
#     Embedded as-is on a dark canvas that already owns its own zoom, pan and
#     hover; the toolbar's Zoom / Fit buttons simply drive the widget's
#     `view` and "Export" writes a fresh PNG of whatever is on screen.
#
# Both share the window-size memory (config, keyed per chart) so the dialog
# lands back where the user left it.

# first-open window: a sane default for the pixmap aspect; the widget mode
# has no bitmap aspect to derive from, so it reuses the same starting size.
_START = (1000, 800)
_MIN = (420, 300)
_MAX = (1920, 1080)
# zoom limits for the +/- buttons and the wheel (pixmap mode; the widget
# mode clamps through ChartView, which uses the same 0.05 / 8.0 range)
_ZOOM_MIN = 0.05
_ZOOM_MAX = 8.0
# one wheel/btn step, matching ChartView's own wheel so both modes feel alike
_WHEEL = 1.25


class ChartViewer(QDialog):
    # Viewer for a chart. Opens fitted to the window (no scrolling needed),
    # remembers the last window size per chart, zooms with the wheel or the
    # toolbar, pans by drag, and exports one click away. Two payload kinds:
    # a flat PNG file (`png_path`) or a live vector chart widget (`widget`).
    # @args: png_path - chart file (pixmap mode);
    #        widget   - a chart widget with a `view` (widget mode);
    #        title    - window title, parent - widget;
    #        obj_name - display name of the astronomical object;
    #        chart_key - "orbit"|"sky"|"approach"|... (for the export
    #                     default file name)
    def __init__(self, png_path=None, widget=None, title="", obj_name="",
                 chart_key="", parent=None):
        super().__init__(parent)
        self._mode = "pixmap" if png_path is not None else "widget"
        self._widget = widget
        self._obj_name = obj_name
        self._chart_key = chart_key

        if self._mode == "pixmap":
            self._path = Path(png_path)
            self._pix = QPixmap(str(self._path))
            self._key = title or self._path.name
            self.setWindowTitle(title or self._path.name)
        else:
            self._path = None
            self._pix = QPixmap()
            # the widget's interactive canvas (ChartView) — the thing the
            # toolbar's Zoom / Fit buttons drive.
            self._view = getattr(widget, "view", None)
            self._key = title or type(widget).__name__
            self.setWindowTitle(title or type(widget).__name__)

        self._zoom = 1.0

        # the last window size the user left (config, keyed by chart)
        rem = None
        try:
            from ..config import config
            rem = (config.get("chart_viewer_sizes") or {}).get(self._key)
        except Exception:
            rem = None
        if rem and len(rem) == 2:
            self.resize(max(int(rem[0]), _MIN[0]),
                        max(int(rem[1]), _MIN[1]))
        else:
            self.resize(*self._fit_window())

        # ---- toolbar -------------------------------------------------------
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        buttons = ((self.tr("Zoom −"), self._zoom_out),
                   (self.tr("Zoom +"), self._zoom_in),
                   (self.tr("Fit"), self._zoom_fit))
        if self._mode == "pixmap":
            # 1:1 is only meaningful for a bitmap (scene units in widget mode
            # have no pixel meaning); the widget's "Fit" is its 1:1.
            buttons += ((self.tr("1:1"), self._zoom_11),)
        buttons += ((self.tr("Export PNG…"), self._export),)
        for text, slot in buttons:
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch()
        layout.addLayout(bar)

        # ---- payload -------------------------------------------------------
        if self._mode == "pixmap":
            self._label = QLabel()
            self._label.setAlignment(Qt.AlignCenter)
            self._label.setMinimumSize(1, 1)
            self._scroll = QScrollArea()
            self._scroll.setWidget(self._label)
            self._scroll.setWidgetResizable(False)
            layout.addWidget(self._scroll, stretch=1)
            # drag with the mouse to pan (native Qt scroller gesture)
            QScroller.grabGesture(self._scroll.viewport(),
                                  QScroller.LeftMouseButtonGesture)
            self._label.setToolTip(self.tr("Wheel: zoom · drag: pan"))
            # fit the image to the window now (tests, no event loop yet) and
            # again once the window manager has granted the real geometry
            self._zoom_fit()
            QTimer.singleShot(0, self._zoom_fit)
        else:
            self._label = None
            self._scroll = None
            # adding to the layout reparents the widget to this dialog
            layout.addWidget(widget, stretch=1)
            widget.setToolTip(
                self.tr("Wheel: zoom · drag: pan · hover: inspect"))
            # the widget fits itself to the viewport on resize (ChartView's
            # resizeEvent); nudge it once now and once when the real
            # geometry lands.
            self._zoom_fit()
            QTimer.singleShot(0, self._zoom_fit)

    # ---- fit / zoom ------------------------------------------------------

    def _fit_window(self):
        # @return: (w, h) for the first open. Pixmap: the image's aspect, so
        #          the default view fills the window. Widget: a fixed, sane
        #          default (there is no bitmap aspect to derive it from).
        if self._mode == "pixmap":
            w, h = self._pix.width(), self._pix.height()
            if not w or not h:
                return _START
            return (max(_MIN[0], min(int(w * 1.18 + 40), _MAX[0])),
                    max(_MIN[1], min(int(h * 1.18 + 90), _MAX[1])))
        return _START

    def _zoom_fit(self):
        # Fit the payload to the current window: the "default view" the user
        # asked for — big enough to read, no scrollbars (pixmap) / the scene
        # fitted to the canvas (widget).
        if self._mode == "widget":
            if self._view is not None:
                self._view.fit_to_scene()
            return
        if self._pix.isNull():
            return
        vw = self._scroll.viewport().width()
        vh = self._scroll.viewport().height()
        if vw < 20 or vh < 20:
            # geometry not granted yet (offscreen / pre-show): fall back to
            # the window size minus the toolbar chrome
            vw = max(self.width() - 40, 20)
            vh = max(self.height() - 80, 20)
        self._zoom = min(vw / self._pix.width(), vh / self._pix.height())
        self._apply()

    def _apply(self):
        # Re-renders the label at the current zoom factor (pixmap mode only).
        w = max(1, int(self._pix.width() * self._zoom))
        h = max(1, int(self._pix.height() * self._zoom))
        self._label.setPixmap(self._pix.scaled(w, h, Qt.KeepAspectRatio,
                                               Qt.SmoothTransformation))
        self._label.resize(w, h)

    def _zoom_in(self):
        if self._mode == "widget":
            if self._view is not None:
                self._view._zoom_by(_WHEEL)
            return
        self._zoom = min(self._zoom * _WHEEL, _ZOOM_MAX)
        self._apply()

    def _zoom_out(self):
        if self._mode == "widget":
            if self._view is not None:
                self._view._zoom_by(1.0 / _WHEEL)
            return
        self._zoom = max(self._zoom / _WHEEL, _ZOOM_MIN)
        self._apply()

    def _zoom_11(self):
        # Pixel-exact 1:1 — meaningful for a bitmap only.
        if self._mode == "widget":
            self._zoom_fit()
            return
        self._zoom = 1.0
        self._apply()

    def wheelEvent(self, event):
        # Pixmap mode: the dialog zooms. Widget mode: the ChartView handles
        # its own wheel (under the cursor) — do not double-act on it.
        if self._mode != "pixmap":
            event.ignore()
            return
        if event.angleDelta().y() > 0:
            self._zoom_in()
        else:
            self._zoom_out()
        event.accept()

    # ---- window size memory ----------------------------------------------

    def _save_size(self):
        # Store the window size the user left, so the next open lands the
        # same place (dragged corners, or the fitted window as they gave it —
        # either is "their" size for this chart).
        try:
            from ..config import config
            sizes = dict(config.get("chart_viewer_sizes") or {})
            sizes[self._key] = [self.width(), self.height()]
            config.set("chart_viewer_sizes", sizes)
        except Exception:
            pass

    def closeEvent(self, event):
        # Remember the size on the way out, then clean up.
        self._save_size()
        super().closeEvent(event)

    # ---- suggested export name -------------------------------------------

    @staticmethod
    def _safe_name(text):
        # @return: text fit for a file name (illegal chars and whitespace
        #          runs become "_", leading/trailing underscores stripped)
        if not text:
            return ""
        text = _ILLEGAL.sub("_", str(text))
        text = re.sub(r"\s+", "_", text).strip("_")
        return text

    def _suggested_name(self):
        # @return: default file name for the export dialog.
        #   With obj_name → <object>_<chart>.png (no "overview_" prefix).
        #   Without it: historical defaults (png name / chart title + .png)
        tag = self._chart_key or self._safe_name(self._key)
        if self._obj_name:
            return f"{self._safe_name(self._obj_name)}_{self._safe_name(tag)}.png"
        if self._mode == "pixmap":
            return self._path.name
        return f"{self._safe_name(self._key)}.png"

    # ---- export ---------------------------------------------------------

    def _export(self):
        # Pixmap mode: the chart already lives on disk — a plain file copy.
        # Widget mode: render whatever is on the canvas to a fresh PNG
        # (zoom included), via the widget's own export.
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export chart"),
            str(Path.home() / self._suggested_name()),
            "PNG (*.png);;All files (*)")
        if not out:
            return
        if self._mode == "pixmap":
            shutil.copyfile(self._path, out)
        else:
            self._widget.export_png(out)
        self.setWindowTitle(f"{self.windowTitle()} — {self.tr('exported')}")


def open_chart(parent, png_path, title="", obj_name="", chart_key=""):
    # Convenience: opens the viewer for a chart PNG file.
    # @args: parent - widget, png_path - chart PNG, title - window title,
    #        obj_name - object display name, chart_key - "orbit"|"sky"|...
    dlg = ChartViewer(png_path, title=title, obj_name=obj_name,
                      chart_key=chart_key, parent=parent)
    dlg.exec()


def open_chart_widget(parent, widget, title="", obj_name="", chart_key=""):
    # Convenience: opens the viewer around a live vector chart widget.
    # @args: parent - widget, widget - a chart widget (OrbitChart, etc.),
    #        title - window title, obj_name - object display name,
    #        chart_key - "orbit"|"sky"|"approach"|...
    dlg = ChartViewer(widget=widget, title=title, obj_name=obj_name,
                      chart_key=chart_key, parent=parent)
    dlg.exec()
