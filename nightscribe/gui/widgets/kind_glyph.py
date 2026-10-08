############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Kind glyph painter module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# The little geometric icon per object kind, shared by the Tonight rows,
# the project masthead and (since ADR-057) the object card's hero. It
# used to live as a MainWindow method, which made it unavailable to any
# widget that is not the main window; pulling it here keeps ONE painter
# for one grammar of shapes.
#
# The shapes are tuned on a 28 px canvas (their original size); bigger
# renditions just scale the painter, so the 44 px hero glyph is the same
# drawing, not a re-tuned copy.

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen,
                           QPixmap)

from .. import theme

# The canvas the shapes were drawn for; every other size scales from it.
_BASE = 28.0


def _draw(p, kind, color, size=_BASE):
    # @args: p - QPainter (already antialiased), kind - kind id,
    #        color - QColor of the kind, size - canvas edge in px
    # @return: None
    cx = cy = size / 2.0
    if kind == "sn":
        # 4-point star (spark burst)
        p.setBrush(QBrush(color))
        path = QPainterPath()
        path.moveTo(QPointF(cx, 2))
        path.lineTo(QPointF(cx + 4, cy - 4))
        path.lineTo(QPointF(size - 2, cy))
        path.lineTo(QPointF(cx + 4, cy + 4))
        path.lineTo(QPointF(cx, size - 2))
        path.lineTo(QPointF(cx - 4, cy + 4))
        path.lineTo(QPointF(2, cy))
        path.lineTo(QPointF(cx - 4, cy - 4))
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "neo":
        # small ellipse (asteroid body)
        p.setBrush(QBrush(color))
        p.drawEllipse(QRectF(cx - 7, cy - 4, 14, 8))
    elif kind == "comet":
        # nucleus + tail
        p.setBrush(QBrush(color))
        p.drawEllipse(QRectF(cx - 4, cy - 4, 8, 8))
        p.setPen(QPen(color, 1.5))
        p.drawLine(QPointF(cx + 3, cy), QPointF(size - 2, cy + 4))
        p.drawLine(QPointF(cx + 3, cy + 1), QPointF(size - 3, cy + 5))
    elif kind == "pccp":
        # dashed circle (uncertain identity)
        pen = QPen(color, 2)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(cx - 8, cy - 8, 16, 16))
    elif kind == "transit":
        # light curve with a dip
        p.setPen(QPen(color, 2))
        p.drawLine(QPointF(2, cy), QPointF(cx - 6, cy))
        p.drawArc(QRectF(cx - 6, cy - 6, 12, 12), 0, -180 * 16)
        p.drawLine(QPointF(cx + 6, cy), QPointF(size - 2, cy))
    elif kind == "alert":
        # warning triangle
        p.setBrush(QBrush(color))
        path = QPainterPath()
        path.moveTo(QPointF(cx, 3))
        path.lineTo(QPointF(size - 2, size - 3))
        path.lineTo(QPointF(2, size - 3))
        path.closeSubpath()
        p.drawPath(path)
        p.setPen(QPen(QColor("#e8eaf2"), 1.5))
        p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, "!")
    elif kind in ("hads", "variable"):
        # pulsating / long-period variable: 4-point star + a wave
        # underneath (quick for HADS, slow for variables)
        p.setBrush(QBrush(color))
        path = QPainterPath()
        path.moveTo(QPointF(cx, 4))
        path.lineTo(QPointF(cx + 3, cy - 5))
        path.lineTo(QPointF(size - 4, cy - 5))
        path.lineTo(QPointF(cx + 3, cy - 5 + 3))
        path.lineTo(QPointF(cx, cy + 1))
        path.lineTo(QPointF(cx - 3, cy - 2))
        path.lineTo(QPointF(4, cy - 5))
        path.lineTo(QPointF(cx - 3, cy - 5))
        path.closeSubpath()
        p.drawPath(path)
        p.setPen(QPen(color, 1.5))
        wave = QPainterPath()
        if kind == "hads":
            wave.moveTo(QPointF(3, size - 6))
            wave.cubicTo(QPointF(cx - 4, size - 6),
                         QPointF(cx - 6, size - 11),
                         QPointF(cx, size - 11))
            wave.cubicTo(QPointF(cx + 6, size - 11),
                         QPointF(cx + 4, size - 6),
                         QPointF(size - 3, size - 6))
        else:
            wave.moveTo(QPointF(3, size - 8))
            wave.cubicTo(QPointF(cx - 2, size - 2),
                         QPointF(cx + 2, size - 12),
                         QPointF(size - 3, size - 7))
        p.drawPath(wave)


def kind_glyph_pixmap(kind, size=28, color=None):
    # @args: kind - object kind id ("neo", "sn", ...), size - edge in px,
    #        color - a hex string for the glyph, or None for the kind's own
    #        hue. The hero button draws it ON a surface of that same hue, so
    #        there the glyph has to wear the button's text colour instead.
    # @return: a QPixmap with the kind's glyph on a transparent
    #          background; an unknown kind paints an empty pixmap (the
    #          caller decides whether a missing glyph matters)
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    if size != int(_BASE):
        p.scale(size / _BASE, size / _BASE)
    paint = QColor(color) if color else QColor(
        theme.KIND_COLORS.get(kind, "#888888"))
    _draw(p, kind, paint)
    p.end()
    return pix
