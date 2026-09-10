############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - transit night-plan timeline widget (Track D, subplan 2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The transit night plan as a horizontal timeline (QGraphicsView, ADR-029).

One glance answers the first-timer's only real question — "when do I press
record?" — by stacking three bands over a common time axis:

  * the **darkness** window (dusk -> dawn twilight),
  * the **safe** window (the star above the local horizon, when known),
  * the **capture** window: baseline + transit + baseline, with the
    ingress / mid / egress milestones.

A capture band poking out of the darkness band *is* the "the baseline does
not fit" warning — the picture and the chip can never disagree.
"""

import datetime

from PySide6.QtGui import QBrush, QColor, QFont, QPen, Qt
from PySide6.QtWidgets import (QGraphicsLineItem, QGraphicsRectItem,
                                QGraphicsSimpleTextItem)

from ...viz import palette
from .base_chart import ChartView

# scene geometry: x in MINUTES since the span start, y in pixels
_ROW_NIGHT = (6, 20)        # darkness band (y0, y1)
_ROW_SAFE = (24, 38)        # horizon-safe band
_ROW_CAPTURE = (46, 66)     # capture band (baseline / transit / baseline)
_TICK_TOP = 42              # milestone hairlines start above the capture band
_LBL_ROW_A = 72             # staggered milestone labels (two rows)
_LBL_ROW_B = 86
_PAD_MIN = 12               # breathing room at both ends of the span


class TransitTimeline(ChartView):
    # Horizontal timeline chart for the transit capture plan. The base
    # class owns the canvas/zoom/pan/export chrome; this subclass only
    # draws the bands and the milestone labels.
    #
    # All inputs are UTC datetimes (or None). Times are drawn as "HH:MM".

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(160)

    # ------------------------------------------------- drawing -----------

    def set_data(self, dusk=None, dawn=None, safe=None, capture_start=None,
                 capture_end=None, ingress=None, mid=None, egress=None):
        # @args: dusk/dawn - darkness window (UTC datetimes),
        #        safe - optional (start, end) horizon-safe span,
        #        capture_start/capture_end - recommended capture window,
        #        ingress/mid/egress - the transit milestones
        # Anything missing is simply not drawn (the band/labels for it
        # disappear, mirroring the ObjectPanel "no gaps" rule).
        self.clear()
        times = [t for t in (dusk, dawn, capture_start, capture_end,
                             ingress, mid, egress)
                 if isinstance(t, datetime.datetime)]
        if safe:
            times += [t for t in safe if isinstance(t, datetime.datetime)]
        if not times:
            return
        t0 = min(times) - datetime.timedelta(minutes=_PAD_MIN)
        t1 = max(times) + datetime.timedelta(minutes=_PAD_MIN)
        span = max((t1 - t0).total_seconds() / 60.0, 1.0)

        def x(dt):
            return (dt - t0).total_seconds() / 60.0

        font = QFont()
        font.setPointSize(7)
        muted = QColor(palette.MUTED)
        fg = QColor(palette.FG)
        accent = QColor(palette.ACCENT)
        accent2 = QColor(palette.ACCENT2)

        def band(x0, x1, row, colour, alpha, label=None, outline=None):
            rect = QGraphicsRectItem(x0, row[0], x1 - x0, row[1] - row[0])
            fill = QColor(colour)
            fill.setAlpha(alpha)
            rect.setBrush(QBrush(fill))
            rect.setPen(QPen(outline or Qt.NoPen))
            self.add_item(rect)
            if label:
                txt = QGraphicsSimpleTextItem(label)
                txt.setFont(font)
                txt.setBrush(QBrush(fg))
                txt.setPos(x0 + 2, row[0] - 1)
                txt.setZValue(5)
                self.add_item(txt)

        if dusk and dawn:
            band(x(dusk), x(dawn), _ROW_NIGHT, muted, 40,
                 self.tr("night"), outline=QColor(palette.MUTED))
        if safe and all(isinstance(t, datetime.datetime) for t in safe):
            band(x(safe[0]), x(safe[1]), _ROW_SAFE, accent2, 40,
                 self.tr("above horizon"), outline=accent2)
        if capture_start and capture_end:
            # baselines first (under the transit fill), then the transit,
            # then the capture outline over everything
            if ingress:
                band(x(capture_start), x(ingress), _ROW_CAPTURE,
                     muted, 70, self.tr("baseline"))
            if egress:
                band(x(egress), x(capture_end), _ROW_CAPTURE, muted, 70)
            if ingress and egress:
                band(x(ingress), x(egress), _ROW_CAPTURE, accent, 110,
                     self.tr("transit"))
            band(x(capture_start), x(capture_end), _ROW_CAPTURE,
                 accent, 0, outline=accent)

        # milestones: hairline + staggered "HH:MM" + role label
        roles = ((capture_start, self.tr("start")),
                 (ingress, self.tr("ingress")),
                 (mid, self.tr("mid")),
                 (egress, self.tr("egress")),
                 (capture_end, self.tr("end")))
        row_flip = False
        for dt, role in roles:
            if not isinstance(dt, datetime.datetime):
                continue
            xx = x(dt)
            line = QGraphicsLineItem(xx, _TICK_TOP, xx, _LBL_ROW_A - 2)
            line.setPen(QPen(muted, 0.6))
            self.add_item(line)
            hm = dt.strftime("%H:%M")
            txt = QGraphicsSimpleTextItem(f"{hm}\n{role}")
            txt.setFont(font)
            txt.setBrush(QBrush(fg if role != self.tr("mid") else accent))
            br = txt.boundingRect()
            yy = _LBL_ROW_A if not row_flip else _LBL_ROW_B
            txt.setPos(xx - br.width() / 2, yy)
            self.add_item(txt)
            row_flip = not row_flip
        if isinstance(mid, datetime.datetime):
            # mid gets a full-height accent tick through the capture band
            xx = x(mid)
            line = QGraphicsLineItem(xx, _ROW_CAPTURE[0] - 2, xx,
                                     _ROW_CAPTURE[1] + 2)
            pen = QPen(accent, 1.2)
            line.setPen(pen)
            self.add_item(line)
        self.set_scene_rect(0, 0, span, _LBL_ROW_B + 14)
        self.fit_to_scene()
