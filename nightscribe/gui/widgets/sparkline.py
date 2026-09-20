############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Sparkline pixmap module (Track UX-PC, U2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Tiny light-curve sparklines for list rows (Track UX-PC, U2).

A `LightCurveChart` (ADR-029) is the full interactive chart; a sparkline is
its silent thumbnail — no axes, no labels, just the trend of YOUR
measurements so a follow-up project shows its growing series right in the
hub list. Drawn straight to a QPixmap (cheap, no widget needed); the data
model is the same `core/followup.list_points` the big chart reads.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

_PAD = 3.0        # inner margin, px
_DOT = 2.2        # point radius, px


def sparkline_pixmap(points, width=110, height=26, color="#6ab0ff"):
    # @args: points - followup.list_points rows (dicts with mjd + mag),
    #        width/height - target size in px, color - stroke accent
    # @return: QPixmap with the magnitude trend (bright = up, the inverted
    #          magnitude axis honoured), or a null QPixmap when there is
    #          nothing to draw (<2 usable points — the caller hides the
    #          label then)
    usable = sorted(
        ((p["mjd"], p["mag"]) for p in points
         if p.get("mjd") is not None and p.get("mag") is not None))
    pix = QPixmap(width, height)
    pix.fill(Qt.transparent)
    if len(usable) < 2:
        return pix
    xs = [u[0] for u in usable]
    ys = [u[1] for u in usable]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    # never divide by zero: a single night (x0 == x1) or a flat series
    # still draws — spread the span a touch
    if x1 - x0 < 1e-6:
        x0, x1 = x0 - 0.5, x1 + 0.5
    if y1 - y0 < 1e-6:
        y0, y1 = y0 - 0.5, y1 + 0.5

    def _map(x, y):
        # @return: scene point; fainter mag -> lower on screen (inverted Y)
        px = _PAD + (x - x0) / (x1 - x0) * (width - 2 * _PAD)
        py = _PAD + (y - y0) / (y1 - y0) * (height - 2 * _PAD)
        return px, height - py

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    path = QPainterPath()
    for i, (x, y) in enumerate(usable):
        px, py = _map(x, y)
        path.moveTo(px, py) if i == 0 else path.lineTo(px, py)
    pen = QPen(c)
    pen.setWidthF(1.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawPath(path)
    # dots on the points, the latest one a touch bigger — that's tonight's
    painter.setBrush(c)
    painter.setPen(Qt.NoPen)
    for i, (x, y) in enumerate(usable):
        px, py = _map(x, y)
        r = _DOT if i < len(usable) - 1 else _DOT * 1.4
        painter.drawEllipse(int(px - r), int(py - r), int(2 * r),
                            int(2 * r))
    painter.end()
    return pix
