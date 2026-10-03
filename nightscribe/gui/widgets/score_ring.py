############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Tonight-score ring widget module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# The 0-100 "tonight" score as a ring (ADR-057): the number alone is easy
# to skim past, the ring makes it the first thing the eye lands on. The
# score itself is computed by core/suggest.py; this widget only draws it.

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import theme

# Ring geometry: a 5 px stroke reads at 56-72 px without turning the
# widget into a donut; the inset keeps the stroke inside the widget rect.
_STROKE = 5.0


class ScoreRing(QWidget):
    # A circular 0-100 gauge. Colours follow the same honesty rule as the
    # score itself: green when the night really favours the object, the
    # app accent in the middle, and dim grey below, because a low score
    # is not a warning (nothing is wrong), just a weak night for it.

    def __init__(self, diameter=64, parent=None):
        # @args: diameter - ring edge in px, parent - parent widget
        super().__init__(parent)
        self._score = None
        self._d = int(diameter)
        # a gauge does not stretch: the layout asks and gets exactly this
        self.setFixedSize(self._d, self._d)

    def set_score(self, score):
        # @args: score - 0..100 float, or None to paint an empty track
        self._score = None if score is None else max(0.0, min(100.0,
                                                              float(score)))
        self.update()

    def score(self):
        # @return: the current 0..100 score, or None
        return self._score

    def sizeHint(self):
        # @return: the fixed gauge size
        return QSize(self._d, self._d)

    def _color(self):
        # @return: the arc colour for the current score
        if self._score is None:
            return QColor(theme.C_LINE)
        if self._score >= 70:
            return QColor(theme.C_GOOD)
        if self._score >= 45:
            return QColor(theme.C_ACCENT)
        return QColor(theme.C_TEXT_DIM)

    def paintEvent(self, _event):
        # @return: None. Track ring, then the score arc clockwise from the
        #          top, then the number centred.
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        inset = _STROKE / 2.0 + 1.0
        rect = QRectF(inset, inset, self._d - 2 * inset, self._d - 2 * inset)
        # the track: the full circle in the border colour, so an empty or
        # partial arc still reads as a ring and not as a stray parenthesis
        pen = QPen(QColor(theme.C_LINE), _STROKE)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawEllipse(rect)
        if self._score is not None:
            pen = QPen(self._color(), _STROKE)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            # Qt arcs: 16ths of a degree, counterclockwise positive, zero
            # at 3 o'clock. Start at the top (90 deg) and sweep clockwise.
            span = -int(round(360.0 * 16 * self._score / 100.0))
            p.drawArc(rect, 90 * 16, span)
            font = QFont(self.font())
            font.setBold(True)
            font.setPixelSize(max(12, int(self._d * 0.28)))
            p.setFont(font)
            p.setPen(QColor(theme.C_TEXT))
            p.drawText(self.rect(), Qt.AlignCenter,
                       str(int(round(self._score))))
        p.end()
