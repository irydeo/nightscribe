############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Night ribbon widget (the night, drawn)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""A night, drawn: dusk, darkness, dawn, and what happens inside.

This is the Welcome hero's trick applied to ONE object (or one plan, or one
visit): the same painted sky and the same real numbers, in a band about
58 px tall (30 of sky, 16 of caption, 12 of padding). It answers the
question every project tab asks and none of them showed:

  * the Ficha  -> where is this object tonight?
  * Capture    -> does my plan fit in the dark?
  * Analysis   -> when did I actually shoot?

The band is a time axis from dusk to dawn (plus a little twilight at each
end, so the gradient has somewhere to happen). On top of it go the object's
altitude arc, the Moon at its real phase, a marker for "now" and any number
of coloured BLOCKS (a plan, a visit's frames) dropped on the timeline.

Everything is local (core/coords + core/night_brief + gui/moon_icon): no
network, no cache, and nothing here blocks the GUI thread. It is also
tolerant on purpose: no site, no coordinates, no astronomical night or an
object that never rises all draw *something* honest instead of nothing.
"""

import datetime as _dt

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF,
                           QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import theme
from ..moon_icon import moon_pixmap

# The band's own geometry, in px.
_MARGIN = 10.0          # side margins
_BAND_H = 30.0          # the ribbon itself
_CAPTION_H = 16.0       # the line of numbers under it
_PAD = 4.0              # total vertical padding
_ARC_STEP_MIN = 10      # one altitude sample every 10 minutes

# How far past the astronomical night the band reaches, so the twilight has
# somewhere to be drawn. The dark window is what matters; this is the frame.
_TWILIGHT = _dt.timedelta(minutes=50)

# The altitude ceiling the arc is drawn against. 90 would flatten every
# real arc (an object at 40 degrees would sit in the lower half).
_ALT_CEIL = 80.0

# Below this the object is technically up and practically unobservable: the
# caption says so instead of reporting "up 04:40 -> 04:40, max 0°", which is
# true and useless.
_MIN_ALT = 10.0

# The band's colours: the same night family as the Welcome hero.
_C_TWILIGHT = QColor("#2a3350")
_C_NIGHT = QColor("#0a1020")


class NightRibbon(QWidget):
    """The night as a band, with optional overlays."""

    # @args: parent - the widget that hosts it
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lat = None
        self._lon = None
        self._ra = None
        self._dec = None
        self._name = ""
        self._blocks = []
        self._brief = None
        self._arc = []
        self._span = None
        self._accent = theme.C_ACCENT
        self._note = ""
        self._note_color = None
        # A fixed height: the band is a strip of information, not a panel
        # that grows. Letting it stretch is how a 40 px ribbon becomes a
        # 200 px empty box on a tall window.
        self.setFixedHeight(int(_BAND_H + _CAPTION_H + _PAD * 2 + 4))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.refresh()

    def set_note(self, text, color=None):
        # @args: text - a sentence drawn at the RIGHT end of the caption
        #        (the plan's verdict, the visit's summary); color - its hue
        # @return: None. The band's own numbers stay on the left; this is
        #          the caller's answer, and it is what makes the band an
        #          answer instead of a decoration.
        self._note = text or ""
        self._note_color = color
        self.update()

    def set_accent(self, color):
        # @args: color - a #rrggbb hue for the arc (the object's kind colour,
        #        the plan's accent...); None keeps the app accent
        self._accent = color or theme.C_ACCENT
        self.update()

    # -------------------------------------------------------------- data

    def set_site(self, lat, lon):
        # @args: lat, lon - the observatory, in degrees (None clears it)
        try:
            self._lat, self._lon = float(lat), float(lon)
        except (TypeError, ValueError):
            self._lat = self._lon = None
        self.refresh()

    def set_object(self, ra=None, dec=None, name=""):
        # @args: ra, dec - the object, in degrees (None draws a bare night)
        #        name - the object's name, for the tooltip
        try:
            self._ra, self._dec = float(ra), float(dec)
        except (TypeError, ValueError):
            self._ra = self._dec = None
        self._name = name or ""
        self.refresh()

    def set_blocks(self, blocks):
        # @args: blocks - [{"start": datetime, "end": datetime,
        #          "label": str, "color": "#rrggbb"}]; anything missing is
        #          skipped, so a half-built plan still draws what it has.
        self._blocks = [b for b in (blocks or [])
                        if b.get("start") and b.get("end")]
        self.refresh()

    def has_night(self):
        # @return: True when there is an astronomical night to draw
        return bool(self._brief and self._brief.get("window"))

    def window(self):
        # @return: (dusk, dawn) of the astronomical night, or None. The
        #          callers that drop a block on the band (a plan, a visit)
        #          need to know where the night starts without reaching
        #          into the brief themselves.
        return (self._brief or {}).get("window")

    def refresh(self):
        # Recomputes the brief, the span and the arc. Cheap (a few dozen
        # samples) and local, so callers can run it on every entry.
        # @return: None
        from ...core import night_brief
        if self._lat is None or self._lon is None:
            self._brief = None
            self._span = None
            self._arc = []
            self.update()
            self._sync_tooltip()
            return
        self._brief = night_brief.brief(self._lat, self._lon)
        win = self._brief.get("window")
        if win is None:
            self._span = None
            self._arc = []
            self.update()
            self._sync_tooltip()
            return
        self._span = (win[0] - _TWILIGHT, win[1] + _TWILIGHT)
        self._arc = self._sample_arc()
        self.update()
        self._sync_tooltip()

    def _sync_tooltip(self):
        # @return: None. The caption is elided in a narrow column, so the
        #          tooltip carries it whole (with the object's name first):
        #          hovering the band is how you read the sentence that did
        #          not fit.
        tip = self.caption()
        if self._name:
            tip = f"{self._name}\n{tip}"
        self.setToolTip(tip)

    def _sample_arc(self):
        # @return: [(datetime, altitude), ...] across the span, or [] when
        #          there is no object to follow
        if self._ra is None or self._dec is None or self._span is None:
            return []
        from ...core import coords
        t = self._span[0]
        out = []
        step = _dt.timedelta(minutes=_ARC_STEP_MIN)
        while t <= self._span[1]:
            jd = coords.jd_from_datetime(t)
            alt, _az = coords.altaz(self._ra, self._dec, self._lat,
                                    coords.lst_degrees(jd, self._lon))
            out.append((t, alt))
            t += step
        return out

    # ------------------------------------------------------------- wording

    def caption(self):
        # @return: the line of numbers under the band (also what the tests
        #          read instead of counting pixels)
        from ...core import night_brief as nb
        if self._brief is None:
            return self.tr("Set your observatory to see your night")
        if not self.has_night():
            return nb.window_line(self._brief)
        dusk, dawn = self._brief["window"]
        hours = (dawn - dusk).total_seconds() / 3600.0
        parts = [self.tr("Dark {start} → {end} · {hours} h").format(
            start=nb.local_hhmm(dusk), end=nb.local_hhmm(dawn),
            hours=("%.1f" % hours).replace(".0", ""))]
        up = self.up_window()
        alt, when = self.peak()
        if up is None or alt is None:
            parts.append(self.tr("never rises tonight"))
        elif alt < _MIN_ALT:
            # honest, and it saves a wasted trip to the telescope
            parts.append(self.tr("max {alt}°: too low").format(
                alt=int(round(alt))))
        else:
            parts.append(self.tr("up {start} → {end}").format(
                start=nb.local_hhmm(up[0]), end=nb.local_hhmm(up[1])))
            parts.append(self.tr("max {alt}° at {time}").format(
                alt=int(round(alt)), time=nb.local_hhmm(when)))
        # The Moon goes last and only when there is room for it: in a
        # narrow column (the Analysis band is ~340 px) it was elided away
        # mid-word, which says nothing; dropping it keeps the two facts
        # that matter (when it is dark, whether the object is up) readable.
        moon = nb.moon_short(self._brief)
        if moon and self.width() >= 430:
            parts.append(moon)
        return " · ".join(parts)

    def up_window(self):
        # @return: (rise, set) of the object inside the dark window, or None
        #          when it is not up at all (or there is no arc)
        if not self._arc or not self.has_night():
            return None
        dusk, dawn = self._brief["window"]
        inside = [(t, alt) for t, alt in self._arc if dusk <= t <= dawn]
        up = [t for t, alt in inside if alt > 0.0]
        if not up:
            return None
        return up[0], up[-1]

    def peak(self):
        # @return: (max altitude, when) inside the dark window, or (None, None)
        if not self._arc or not self.has_night():
            return None, None
        dusk, dawn = self._brief["window"]
        inside = [(t, alt) for t, alt in self._arc if dusk <= t <= dawn]
        if not inside:
            return None, None
        t, alt = max(inside, key=lambda item: item[1])
        if alt <= 0.0:
            return None, None
        return alt, t

    # ------------------------------------------------------------ painting

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        band = QRectF(_MARGIN, _PAD,
                      max(10.0, rect.width() - 2 * _MARGIN), _BAND_H)
        self._paint_band(p, band)
        if self.has_night():
            self._paint_night_window(p, band)
            self._paint_arc(p, band)
            self._paint_blocks(p, band)
            self._paint_now(p, band)
        self._paint_moon(p, band)
        self._paint_caption(p, rect)
        p.end()

    def _paint_band(self, p, band):
        # The twilight → night → twilight gradient. Rounded so the band
        # reads as a strip of sky and not as a progress bar.
        g = QLinearGradient(band.left(), 0.0, band.right(), 0.0)
        g.setColorAt(0.0, _C_TWILIGHT)
        g.setColorAt(0.18, _C_NIGHT)
        g.setColorAt(0.82, _C_NIGHT)
        g.setColorAt(1.0, _C_TWILIGHT)
        path = QPainterPath()
        path.addRoundedRect(band, 7.0, 7.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawPath(path)

    def _x(self, when, band):
        # @args: when - a UTC datetime; band - the band rect
        # @return: the x for that moment
        start, end = self._span
        total = (end - start).total_seconds() or 1.0
        rel = (when - start).total_seconds() / total
        return band.left() + max(0.0, min(1.0, rel)) * band.width()

    def _paint_night_window(self, p, band):
        # The astronomical night is the DARK part; the twilight at the ends
        # is the frame. Shading the night itself would be backwards, so the
        # window gets a hairline and the ends keep the warm tone.
        dusk, dawn = self._brief["window"]
        x0, x1 = self._x(dusk, band), self._x(dawn, band)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(x0, band.top()), QPointF(x0, band.bottom()))
        p.drawLine(QPointF(x1, band.top()), QPointF(x1, band.bottom()))

    def _paint_arc(self, p, band):
        if not self._arc:
            return
        base = band.bottom() - 6.0
        path = QPainterPath()
        first = True
        for when, alt in self._arc:
            x = self._x(when, band)
            y = base - max(0.0, min(_ALT_CEIL, alt)) / _ALT_CEIL * \
                (band.height() - 12.0)
            if first:
                path.moveTo(x, y)
                first = False
            else:
                path.lineTo(x, y)
        # the caller's accent (the object's kind hue, the plan's), so the
        # band speaks the same colour language as the row that opened it
        p.setPen(QPen(QColor(self._accent), 1.8))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        # the horizon: where "up" begins
        p.setPen(QPen(QColor(255, 255, 255, 40), 1.0, Qt.DashLine))
        p.drawLine(QPointF(band.left() + 2, base), QPointF(band.right() - 2,
                                                          base))

    def _paint_blocks(self, p, band):
        # The overlays (a plan, a visit's frames): solid bars in their own
        # colour, sitting on the night they happen in.
        for block in self._blocks:
            x0 = self._x(block["start"], band)
            x1 = self._x(block["end"], band)
            if x1 - x0 < 2.0:
                x1 = x0 + 2.0
            bar = QRectF(x0, band.top() + 4.0, x1 - x0, band.height() - 8.0)
            color = QColor(block.get("color") or theme.C_ACCENT)
            p.setPen(Qt.NoPen)
            fill = QColor(color)
            fill.setAlpha(150)
            p.setBrush(QBrush(fill))
            p.drawRoundedRect(bar, 3.0, 3.0)
            label = block.get("label") or ""
            if label and bar.width() > 42.0:
                f = QFont(self.font())
                f.setPixelSize(10)
                p.setFont(f)
                p.setPen(QPen(QColor(theme.C_CHIP_TEXT_DARK)))
                p.drawText(bar.adjusted(5, 0, -5, 0),
                           Qt.AlignVCenter | Qt.AlignLeft, label)

    def _paint_now(self, p, band):
        # A hairline where we are, when we are inside the band: the one
        # reference the reader has without doing arithmetic.
        now = _dt.datetime.now(_dt.timezone.utc)
        if not (self._span[0] <= now <= self._span[1]):
            return
        x = self._x(now, band)
        p.setPen(QPen(QColor(theme.C_GOOD), 1.2))
        p.drawLine(QPointF(x, band.top() - 3), QPointF(x, band.bottom() + 3))

    def _paint_moon(self, p, band):
        # The real Moon, at its real phase, at the band's right end: it is
        # the one thing that changes what the night is worth.
        if not self.has_night():
            return
        moon = (self._brief or {}).get("moon") or {}
        if not moon:
            return
        size = 18
        # inside the band, clear of the rounded corner
        x = band.right() - size - 12
        y = band.top() + 4
        centre = QPointF(x + size / 2, y + size / 2)
        halo = QRadialGradient(centre, size * 1.4)
        halo.setColorAt(0.0, QColor(210, 226, 255, 46))
        halo.setColorAt(1.0, QColor(210, 226, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(centre, size * 1.4, size * 1.4)
        p.drawPixmap(int(x), int(y), moon_pixmap(moon.get("elong", 0.0), size))

    def _paint_caption(self, p, rect):
        f = QFont(self.font())
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QPen(QColor(theme.C_TEXT_DIM)))
        box = QRectF(_MARGIN, rect.height() - _CAPTION_H - 3,
                     rect.width() - 2 * _MARGIN, _CAPTION_H)
        # elided, never cut mid-word: the band shares its column with a
        # chart now and can be as narrow as 300 px
        note_w = 0.0
        if self._note:
            fm = QFontMetricsF(f)
            note_w = min(fm.horizontalAdvance(self._note),
                         box.width() * 0.6)
            note = fm.elidedText(self._note, Qt.ElideRight, note_w)
            p.setPen(QPen(QColor(self._note_color or theme.C_ACCENT)))
            p.drawText(QRectF(box.right() - note_w, box.top(), note_w,
                              box.height()),
                       Qt.AlignRight | Qt.AlignVCenter, note)
            p.setPen(QPen(QColor(theme.C_TEXT_DIM)))
            box = QRectF(box.left(), box.top(),
                         max(40.0, box.width() - note_w - 12), box.height())
        text = QFontMetricsF(f).elidedText(self.caption(), Qt.ElideRight,
                                           box.width())
        p.drawText(box, Qt.AlignLeft | Qt.AlignVCenter, text)
