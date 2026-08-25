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

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QScroller, QScrollArea, QVBoxLayout)

# Every chart the app renders lands as a PNG on disk; this dialog opens one
# full-size, with wheel zoom, drag panning and a one-click export so the
# charts can be attached to reports or social posts (ADR-023 follow-up).


class ChartViewer(QDialog):
    # Full-size viewer for one chart PNG: wheel zoom, drag to pan, export.
    # @args: png_path - chart file, title - window title, parent - widget
    def __init__(self, png_path, title="", parent=None):
        super().__init__(parent)
        self._path = Path(png_path)
        self._pix = QPixmap(str(self._path))
        self._zoom = 1.0
        self.setWindowTitle(title or self._path.name)
        self.resize(1000, 800)
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
        self._zoom_fit()
        self._label.setToolTip(self.tr("Wheel: zoom · drag: pan"))

    # ---- zoom -----------------------------------------------------------

    def _apply(self):
        # Re-renders the label at the current zoom factor.
        w = max(1, int(self._pix.width() * self._zoom))
        h = max(1, int(self._pix.height() * self._zoom))
        self._label.setPixmap(self._pix.scaled(w, h, Qt.KeepAspectRatio,
                                               Qt.SmoothTransformation))
        self._label.resize(w, h)

    def _zoom_in(self):
        self._zoom = min(self._zoom * 1.25, 8.0)
        self._apply()

    def _zoom_out(self):
        self._zoom = max(self._zoom / 1.25, 0.05)
        self._apply()

    def _zoom_11(self):
        self._zoom = 1.0
        self._apply()

    def _zoom_fit(self):
        if self._pix.isNull():
            return
        vw = self._scroll.viewport().width() - 20
        vh = self._scroll.viewport().height() - 20
        self._zoom = min(vw / self._pix.width(), vh / self._pix.height())
        self._apply()

    def wheelEvent(self, event):
        # Wheel anywhere in the dialog zooms around the current view.
        if event.angleDelta().y() > 0:
            self._zoom_in()
        else:
            self._zoom_out()
        event.accept()

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
