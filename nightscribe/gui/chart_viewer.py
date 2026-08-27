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

import shutil
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QScroller, QScrollArea, QVBoxLayout)

# Every chart the app renders lands as a PNG on disk; this dialog opens one
# fitted to the window by default (no scrolling needed), with wheel zoom,
# drag panning and a one-click export so the charts can be attached to
# reports or social posts (ADR-023 follow-up).

# first-open window: the image's aspect, kept within sane bounds and with
# room for the toolbar + window chrome + breathing around the bitmap
_START = (1000, 800)
_MIN = (420, 300)
_MAX = (1920, 1080)
# zoom limits for the +/- buttons and the wheel
_ZOOM_MIN = 0.05
_ZOOM_MAX = 8.0


class ChartViewer(QDialog):
    # Viewer for one chart PNG. Opens fitted to the window (the default
    # needs no scrolling); the last window size the user left is
    # remembered per chart, wheel zooms, drag pans, one-click export.
    # @args: png_path - chart file, title - window title, parent - widget
    def __init__(self, png_path, title="", parent=None):
        super().__init__(parent)
        self._path = Path(png_path)
        self._pix = QPixmap(str(self._path))
        self._zoom = 1.0
        self.setWindowTitle(title or self._path.name)

        # the last window size the user left (config, keyed by chart name)
        rem = None
        try:
            from ..config import config
            rem = (config.get("chart_viewer_sizes") or
                   {}).get(self._path.name)
        except Exception:
            rem = None
        if rem and len(rem) == 2:
            self.resize(max(int(rem[0]), _MIN[0]),
                        max(int(rem[1]), _MIN[1]))
        else:
            self.resize(*self._fit_window())

        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        for text, slot in ((self.tr("Zoom −"), self._zoom_out),
                           (self.tr("Zoom +"), self._zoom_in),
                           (self.tr("Fit"), self._zoom_fit),
                           (self.tr("1:1"), self._zoom_11),
                           (self.tr("Export PNG…"), self._export)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch()
        layout.addLayout(bar)

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

    # ---- fit / zoom ------------------------------------------------------

    def _fit_window(self):
        # @return: (w, h) for the first open — the image's aspect, so the
        #          default view fills the window without scrolling
        w, h = self._pix.width(), self._pix.height()
        if not w or not h:
            return _START
        sw = max(_MIN[0], min(int(w * 1.18 + 40), _MAX[0]))
        sh = max(_MIN[1], min(int(h * 1.18 + 90), _MAX[1]))
        return sw, sh

    def _zoom_fit(self):
        # Fit the image to the current window: this is the "default view"
        # the user asked for — big enough to read, no scrollbars.
        if self._pix.isNull():
            return
        vw = self._scroll.viewport().width()
        vh = self._scroll.viewport().height()
        if vw < 20 or vh < 20:
            # geometry not granted yet (offscreen / pre-show): fall back
            # to the window size minus the toolbar chrome
            vw = max(self.width() - 40, 20)
            vh = max(self.height() - 80, 20)
        self._zoom = min(vw / self._pix.width(),
                         vh / self._pix.height())
        self._apply()

    def _apply(self):
        # Re-renders the label at the current zoom factor.
        w = max(1, int(self._pix.width() * self._zoom))
        h = max(1, int(self._pix.height() * self._zoom))
        self._label.setPixmap(self._pix.scaled(w, h, Qt.KeepAspectRatio,
                                               Qt.SmoothTransformation))
        self._label.resize(w, h)

    def _zoom_in(self):
        self._zoom = min(self._zoom * 1.25, _ZOOM_MAX)
        self._apply()

    def _zoom_out(self):
        self._zoom = max(self._zoom / 1.25, _ZOOM_MIN)
        self._apply()

    def _zoom_11(self):
        self._zoom = 1.0
        self._apply()

    def wheelEvent(self, event):
        # Wheel anywhere in the dialog zooms around the current view.
        if event.angleDelta().y() > 0:
            self._zoom_in()
        else:
            self._zoom_out()
        event.accept()

    # ---- window size memory ----------------------------------------------

    def _save_size(self):
        # Store the window size the user left, so the next open lands the
        # same place (dragged corners, or the fitted window as they gave
        # it — either is "their" size for this chart).
        try:
            from ..config import config
            sizes = dict(config.get("chart_viewer_sizes") or {})
            sizes[self._path.name] = [self.width(), self.height()]
            config.set("chart_viewer_sizes", sizes)
        except Exception:
            pass

    def closeEvent(self, event):
        # Remember the size on the way out, then clean up.
        self._save_size()
        super().closeEvent(event)

    # ---- export ---------------------------------------------------------

    def _export(self):
        # The chart already lives on disk: export is a plain file copy.
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export chart"),
            str(Path.home() / self._path.name),
            "PNG (*.png);;All files (*)")
        if not out:
            return
        shutil.copyfile(self._path, out)
        self.setWindowTitle(f"{self.windowTitle()} — {self.tr('exported')}")


def open_chart(parent, png_path, title=""):
    # Convenience: opens the viewer for a chart path.
    # @args: parent - widget, png_path - chart PNG, title - window title
    dlg = ChartViewer(png_path, title=title, parent=parent)
    dlg.exec()
