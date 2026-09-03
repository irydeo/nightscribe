############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Skeleton loading rows module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# Skeleton loading rows with a moving shimmer highlight.
#
# Each row paints three things in one pass (no child frames to style): the
# rounded background, the two fake "text" bars, and a soft highlight band
# that sweeps left-to-right. A single timer shared by all rows repaints
# them with a global clock; each row only differs in its starting offset so
# the sweep is staggered instead of all moving together.
#
# The shimmer is a translucent white wash so it stays theme-proof.

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QLinearGradient, QPaintEvent
from PySide6.QtWidgets import QWidget, QSizePolicy

from . import theme

SWEEP_S = 1.2        # one highlight pass over the row
BAND_FRACTION = 0.22  # highlight band width as a fraction of the row width
_HL = QColor(255, 255, 255)   # the shimmer wash (alpha set per band)
_STAGGER = 0.18        # phase offset added per row


class ShimmerRow(QWidget):
    # @args: index - row index (drives the stagger), total_rows - number of
    #        rows (keeps the offsets inside one 0..1 sweep cycle)
    def __init__(self, index, total_rows):
        super().__init__()
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setObjectName("skelrow")
        self._phase = ((index * _STAGGER) % 1.0) if total_rows > 1 else 0.0

    def paintEvent(self, event: QPaintEvent):
        # @args: event - the paint event (ignored; we repaint everything)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        # rounded background (same look as the former plain skeleton frame)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.C_BASE))
        p.drawRoundedRect(rect, 8, 8)
        # the two fake "text" bars (fixed sizes, left aligned)
        pad = 14
        p.setBrush(QColor(theme.C_LINE))
        p.drawRoundedRect(pad, 10, 420, 14, 4, 4)
        p.drawRoundedRect(pad, 32, 560, 10, 4, 4)
        # moving highlight band clipped to the rounded rect
        p.setClipRect(rect)
        progress = (time.time() / SWEEP_S + self._phase) % 1.0
        w = rect.width()
        band_w = max(8.0, BAND_FRACTION * w)
        x = progress * (w + band_w) - band_w   # travels fully off both edges
        grad = QLinearGradient(0, 0, band_w, 0)
        c0 = QColor(_HL); c0.setAlpha(0)
        cM = QColor(_HL); cM.setAlpha(26)
        grad.setColorAt(0.0, c0)
        grad.setColorAt(0.5, cM)
        grad.setColorAt(1.0, c0)
        p.fillRect(int(x), 0, int(band_w), rect.height(), grad)
        p.end()
