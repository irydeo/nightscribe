############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: visual histogram strip (ADR-044)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Unified FITS Editor's histogram strip (ADR-044, phase B): a 256-bin
QPainter histogram of the display frame with AstroImageJ-style draggable
black/white handles, fine-DN spin boxes, a gamma box, and Auto / Invert
buttons. Everything talks to the shared UfeImageState in absolute DN; the
view re-renders through its 120 ms coalescing timer, so a handle drag
feels live without saturating the GUI thread.
"""

import logging
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QFrame,
                               QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from ...viz import palette

logger = logging.getLogger("nightscribe.gui.histogram_widget")

_NBINS = 256          # histogram resolution on the display frame
_HANDLE_TOL = 6       # px either side of a handle line that grabs it
_MARGIN_L = 8
_MARGIN_R = 8
_MARGIN_T = 6
_MARGIN_B = 16        # room for the min / mid / max DN labels


class _HistogramCanvas(QWidget):
    # The painted area: log-scaled bars, out-of-stretch shading and the
    # two draggable handles. Mouse edits go straight to the state.

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self._edges = None
        self._counts = None
        self._drag = None               # "black" | "white" while dragging
        self.setMinimumHeight(110)
        self.setMouseTracking(False)
        self.setAccessibleName(self.tr("Histogram"))
        self.setToolTip(self.tr(
            "Drag the blue (black) and orange (white) handles; a plain "
            "click moves the nearest one"))

    # ------------------------------------------------------------ data

    def set_histogram(self, edges, counts):
        # @args: edges - nbins+1 DN edges, counts - per-bin counts
        #        (both None to clear, e.g. when the plate is gone)
        self._edges = edges
        self._counts = counts
        self.update()

    # ------------------------------------------------------ dn <-> x

    def _plot_rect(self):
        # @return: (x0, y0, w, h) of the histogram plot area in widget px
        w = self.width() - _MARGIN_L - _MARGIN_R
        h = self.height() - _MARGIN_T - _MARGIN_B
        return _MARGIN_L, _MARGIN_T, max(w, 1), max(h, 1)

    def dn_to_x(self, dn):
        # @args: dn - a data value inside [d_min, d_max]
        # @return: the widget x coordinate of that value
        x0, _y0, w, _h = self._plot_rect()
        span = max(self._state.d_max - self._state.d_min, 1e-12)
        frac = (dn - self._state.d_min) / span
        return x0 + min(max(frac, 0.0), 1.0) * w

    def x_to_dn(self, x):
        # @args: x - a widget x coordinate
        # @return: the DN under that x, clamped to the data range
        x0, _y0, w, _h = self._plot_rect()
        frac = min(max((x - x0) / w, 0.0), 1.0)
        return self._state.d_min + frac * \
            (self._state.d_max - self._state.d_min)

    # ---------------------------------------------------------- paint

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(palette.BG))
        if self._edges is None or self._counts is None:
            p.setPen(QPen(QColor(palette.MUTED)))
            p.drawText(self.rect(), Qt.AlignCenter,
                       self.tr("Load a plate to see its histogram"))
            p.end()
            return
        x0, y0, w, h = self._plot_rect()
        counts = self._counts
        nbins = len(counts)
        log_max = math.log10(float(counts.max()) + 1.0) or 1.0
        pen = QPen(QColor(palette.FG))
        pen.setWidthF(1.0)
        p.setPen(pen)
        bw = w / nbins
        for i, c in enumerate(counts):
            if c <= 0:
                continue
            bh = (math.log10(c + 1.0) / log_max) * h
            p.drawLine(int(x0 + i * bw), int(y0 + h),
                       int(x0 + i * bw), int(y0 + h - bh))
        # shade what the stretch throws away: below black, above white
        bx = self.dn_to_x(self._state.black)
        wx = self.dn_to_x(self._state.white)
        shade = QColor(0, 0, 0, 110)
        p.fillRect(int(x0), int(y0), max(0, int(bx - x0)), int(h), shade)
        p.fillRect(int(wx), int(y0), max(0, int(x0 + w - wx)), int(h),
                   shade)
        # handles: blue for the black point, orange for the white one
        for x, name in ((bx, palette.ACCENT2), (wx, palette.ACCENT)):
            hp = QPen(QColor(name))
            hp.setWidthF(2.0)
            p.setPen(hp)
            p.drawLine(int(x), int(y0), int(x), int(y0 + h))
        # DN axis labels: min, mid, max of the plate
        p.setPen(QPen(QColor(palette.MUTED)))
        lo, hi = self._state.d_min, self._state.d_max
        mid = (lo + hi) / 2.0
        y_text = y0 + h + 12
        p.drawText(int(x0), int(y_text), f"{lo:.0f}")
        p.drawText(int(x0 + w / 2 - 20), int(y_text), f"{mid:.0f}")
        p.drawText(int(x0 + w - 60), int(y_text), f"{hi:.0f}")
        p.end()

    # ---------------------------------------------------------- mouse

    def mousePressEvent(self, event):
        # Grab the near handle; a plain click jumps the NEAREST handle to
        # the click and keeps dragging (AstroImageJ feel).
        if self._edges is None or event.button() != Qt.LeftButton:
            return
        x = event.position().x()
        d_black = abs(x - self.dn_to_x(self._state.black))
        d_white = abs(x - self.dn_to_x(self._state.white))
        self._drag = "black" if d_black <= d_white else "white"
        if min(d_black, d_white) > _HANDLE_TOL:
            self._apply_drag(x)   # a plain click jumps the nearest handle
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self._apply_drag(event.position().x())
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag is not None and event.button() == Qt.LeftButton:
            self._drag = None
            event.accept()

    def _apply_drag(self, x):
        # @args: x - widget x the grabbed handle follows
        dn = self.x_to_dn(x)
        if self._drag == "black":
            self._state.set_stretch(black=dn)
        else:
            self._state.set_stretch(white=dn)


class HistogramWidget(QFrame):
    # The strip the dialog docks at the bottom: the canvas on the left,
    # the fine controls on the right. Everything mirrors the state through
    # its signals, so the top-bar Invert button and this one never drift
    # apart.

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self._ui_sync = False          # guards spinboxes during mirroring
        self.setFrameShape(QFrame.StyledPanel)
        # never fixed: the controls column (black/white/gamma/buttons/keep)
        # must get its natural height in every language and font size
        self.setMinimumHeight(175)
        lay = QHBoxLayout(self)
        self.canvas = _HistogramCanvas(state)
        lay.addWidget(self.canvas, 1)
        lay.addLayout(self._build_controls())
        state.image_loaded.connect(self._on_image_loaded)
        state.stretch_changed.connect(self._sync_from_state)
        self._set_enabled(False)

    def _build_controls(self):
        # @return: the right-hand controls column (DN spins, gamma,
        #          Auto, Invert)
        col = QVBoxLayout()
        self.spn_black = self._dn_spin(self.tr("Black:"), col)
        self.spn_white = self._dn_spin(self.tr("White:"), col)
        row_g = QHBoxLayout()
        row_g.addWidget(QLabel(self.tr("Gamma:")))
        self.spn_gamma = QDoubleSpinBox()
        self.spn_gamma.setRange(0.05, 10.0)
        self.spn_gamma.setSingleStep(0.05)
        self.spn_gamma.setDecimals(2)
        self.spn_gamma.setValue(1.0)
        self.spn_gamma.valueChanged.connect(self._on_gamma_edited)
        row_g.addWidget(self.spn_gamma)
        col.addLayout(row_g)
        row_b = QHBoxLayout()
        self.btn_auto = QPushButton(self.tr("Auto"))
        self.btn_auto.setToolTip(self.tr(
            "Black and white at the 1 / 99.5 percentiles"))
        self.btn_auto.clicked.connect(lambda: self._state.auto())
        row_b.addWidget(self.btn_auto)
        self.btn_invert = QPushButton(self.tr("Invert"))
        self.btn_invert.setCheckable(True)
        self.btn_invert.toggled.connect(self._on_invert_toggled)
        row_b.addWidget(self.btn_invert)
        col.addLayout(row_b)
        self.chk_keep = QCheckBox(self.tr("Keep stretch on load"))
        self.chk_keep.setToolTip(self.tr(
            "The next plate keeps these black, white, gamma and invert "
            "values instead of the auto percentiles"))
        self.chk_keep.toggled.connect(
            lambda checked: setattr(self._state, "keep_stretch", checked))
        col.addWidget(self.chk_keep)
        return col

    def _dn_spin(self, label, col):
        # @args: label - the row caption, col - the controls column layout
        # @return: the QDoubleSpinBox, already parked and wired
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        spn = QDoubleSpinBox()
        spn.setKeyboardTracking(False)   # fire on commit, not per keystroke
        spn.setAccessibleName(label.rstrip(":"))
        row.addWidget(spn)
        col.addLayout(row)
        spn.valueChanged.connect(self._on_dn_edited)
        return spn

    # ------------------------------------------------------- state sync

    def _on_image_loaded(self):
        # A plate landed (or left): recompute the histogram and re-arm
        # the spin ranges; the controls disable themselves when empty.
        has = self._state.has_image
        self._set_enabled(has)
        if not has:
            self.canvas.set_histogram(None, None)
            return
        edges, counts = self._state.histogram(_NBINS)
        self.canvas.set_histogram(edges, counts)
        lo, hi = self._state.d_min, self._state.d_max
        span = max(hi - lo, 1e-12)
        for spn in (self.spn_black, self.spn_white):
            spn.blockSignals(True)
            spn.setRange(lo, hi)
            spn.setDecimals(2 if span >= 100 else 4)
            spn.setSingleStep(max(span / 1000.0, 1e-4))
            spn.blockSignals(False)
        self._sync_from_state()

    def _sync_from_state(self):
        # Mirrors the state's stretch into the controls and the canvas
        # (fired by stretch_changed: handle drags, spins, Auto, Invert).
        if not self._state.has_image:
            return
        self._ui_sync = True
        try:
            self.spn_black.setValue(self._state.black)
            self.spn_white.setValue(self._state.white)
            self.spn_gamma.setValue(self._state.gamma)
            self.btn_invert.setChecked(self._state.inverted)
        finally:
            self._ui_sync = False
        self.canvas.update()

    # ----------------------------------------------------------- edits

    def _on_dn_edited(self, _value):
        # A spin committed: push both DN points (the state clamps).
        if self._ui_sync:
            return
        self._state.set_stretch(black=self.spn_black.value(),
                                white=self.spn_white.value())

    def _on_gamma_edited(self, value):
        if not self._ui_sync:
            self._state.set_stretch(gamma=value)

    def _on_invert_toggled(self, checked):
        if not self._ui_sync and self._state.has_image \
                and checked != self._state.inverted:
            self._state.toggle_invert()

    def _set_enabled(self, flag):
        for w in (self.spn_black, self.spn_white, self.spn_gamma,
                  self.btn_auto, self.btn_invert):
            w.setEnabled(flag)
