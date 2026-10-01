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
its silent thumbnail: no axes, no labels, just the trend of a curve so a
follow-up project shows its series right in the hub list. Drawn straight to
a QPixmap (cheap, no widget needed).

Since 2026-10-01 the row draws the project's **latest available curve** (the
newest run, whatever measured it: the series engine or an EXOTIC reduction
imported from its CSV) and it is framed in the **chart's own magnitude
window** (`core/lightcurve_data.mag_window`), passed in as `y_window`.
Fitting the data to the box, as it used to, showed a flat curve and a
three-magnitude one exactly the same.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

_PAD = 3.0        # inner margin, px
_DOT = 2.2        # point radius, px


def sparkline_pixmap(points, width=110, height=26, color="#6ab0ff",
                     y_window=None):
    # @args: points - followup.list_points rows (dicts with mjd + mag),
    #        width/height - target size in px, color - stroke accent,
    #        y_window - the magnitude window to draw in, or None to fit the
    #        data. The project list passes the chart's own window
    #        (core/lightcurve_data.mag_window), because a thumbnail that
    #        stretches min-to-max shows a flat curve and a three-magnitude
    #        one exactly the same (measured: a real project's curve spans
    #        11.074 to 13.224 mag, one anomalous frame, while its chart's
    #        window is 11.074 to 11.241)
    # @return: QPixmap with the magnitude trend (bright = up, the inverted
    #          magnitude axis honoured), or a null QPixmap when there is
    #          nothing to draw (<2 usable points — the caller hides the
    #          label then)
    usable = sorted(
        ((p["mjd"], p["mag"]) for p in points
         if p.get("mjd") is not None and p.get("mag") is not None))
    # Nothing to draw is a NULL pixmap, as the caller's contract says: a
    # transparent-but-valid one is not null, so the row would show an empty
    # box instead of hiding the label (measured: a project with no
    # photometry kept a blank thumbnail slot).
    if len(usable) < 2:
        return QPixmap()
    pix = QPixmap(width, height)
    pix.fill(Qt.transparent)
    xs = [u[0] for u in usable]
    ys = [u[1] for u in usable]
    x0, x1 = min(xs), max(xs)
    if y_window is not None:
        y0, y1 = float(y_window[0]), float(y_window[1])
    else:
        y0, y1 = min(ys), max(ys)
    # never divide by zero: a single night (x0 == x1) or a flat series
    # still draws — spread the span a touch
    if x1 - x0 < 1e-6:
        x0, x1 = x0 - 0.5, x1 + 0.5
    if y1 - y0 < 1e-6:
        y0, y1 = y0 - 0.5, y1 + 0.5

    def _map(x, y):
        # @return: the point in the pixmap; the magnitude axis is INVERTED
        #          (the astronomical way): the brightest (the smallest
        #          number) on top, the faintest at the bottom, exactly like
        #          the big chart's _map_y.
        #
        #          This is the whole direction of the thumbnail and it was
        #          the other way round: py already puts the bright end on
        #          top and the old code returned `height - py`, which
        #          flipped it back. Measured with a star fading from 12.0 to
        #          13.0: the bright point landed at y=26 of 30 (the bottom)
        #          and the faint one at y=2 (the top), so every preview in
        #          the project list read upside down.
        px = _PAD + (x - x0) / (x1 - x0) * (width - 2 * _PAD)
        py = _PAD + (y - y0) / (y1 - y0) * (height - 2 * _PAD)
        return px, py

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
