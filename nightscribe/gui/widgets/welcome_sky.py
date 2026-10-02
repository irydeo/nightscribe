############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Welcome sky hero widget
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The painted night sky at the top of the Welcome view.

Why a widget and not a plain image: the hero has to say "this app looks
at YOUR sky". The bundled vector (assets/welcome_sky.svg, our own art)
carries the stars, the Milky Way and the observatory silhouette, but the
Moon is drawn here from ephem_minor.moon(jd), so its phase is tonight's
real one, not a decorative crescent that contradicts the almanac.

Cost control (this is the first thing painted at startup):

   * the vector is rasterised ONCE per size into a QPixmap and blitted
     afterwards, so a repaint is a memory copy, not an SVG parse;
   * the twinkle only repaints the few 26x26 boxes of the glints, never
     the whole hero (a full 1400x300 repaint at 10 fps would be wasted
     work for a sparkle);
   * the timer stops whenever the widget is hidden or the user turned
     animations off (Settings > Interface).

If the asset is missing the widget paints an equivalent gradient by hand,
so the hero never comes up empty.
"""

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QWidget

from .. import theme

# Our own vector sky (see assets/ATTRIBUTION.txt). The POSIX path is
# handed to QSvgRenderer as a plain string; the loader takes a file name.
ASSET = theme.asset("welcome_sky.svg")

# The vector's own aspect ratio (viewBox 1600x560): used to cover the
# hero without squashing the stars into ellipses.
ASSET_ASPECT = 1600.0 / 560.0

# Glints: a few stars that breathe. Positions are relative to the hero so
# the sparkle lands on the same stars whatever the window size; the phase
# offsets keep them from pulsing in unison (which reads as a blinking
# screen, not as a sky).
_GLINTS = (
    (0.070, 0.24, 2.6, 0.00), (0.132, 0.62, 2.0, 0.35),
    (0.196, 0.38, 2.3, 0.72), (0.252, 0.76, 1.8, 0.15),
    (0.318, 0.20, 2.1, 0.55), (0.372, 0.58, 1.9, 0.88),
    (0.446, 0.34, 2.4, 0.28), (0.512, 0.70, 1.8, 0.63),
    (0.588, 0.26, 2.2, 0.05), (0.664, 0.60, 1.9, 0.45),
    (0.742, 0.40, 2.5, 0.80), (0.836, 0.66, 1.8, 0.20),
    (0.912, 0.30, 2.2, 0.58), (0.958, 0.72, 1.9, 0.92),
)


class WelcomeSky(QWidget):
    # @args: parent - the hero frame that owns the slot
    def __init__(self, parent=None):
        super().__init__(parent)
        # NOT opaque: the rounded clip below leaves the four corners
        # unpainted on purpose, and they must show the hero frame's own
        # fill through, not whatever was on screen before the resize.
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.setMinimumHeight(190)
        self._bg = None            # cached raster of the vector, per size
        self._bg_for = None        # the (w, h) that cache belongs to
        self._moon = None          # {"illum": 0..1, "waxing": bool}
        self._t = 0.0              # twinkle clock, in cycles
        self._animations = True
        self._timer = QTimer(self)
        self._timer.setInterval(90)          # ~11 fps: enough for a breath
        self._timer.timeout.connect(self._tick)
        self.refresh()

    # ---------------------------------------------------------------- data

    def refresh(self):
        # Re-reads tonight's Moon. Called on build and whenever the host
        # wants the hero to catch up (the phase moves slowly; once per
        # visit is plenty).
        import datetime as _dt

        from ...core import coords, ephem_minor
        jd = coords.jd_from_datetime(_dt.datetime.now(_dt.timezone.utc))
        m = ephem_minor.moon(jd)
        # elong > 0 means the Moon is east of the Sun: waxing, lit on the
        # right as seen from the northern hemisphere. The sign is what
        # decides which limb we paint, so getting it wrong mirrors the Moon.
        self._moon = {"illum": float(m["illum"]),
                      "waxing": float(m["elong_deg"]) > 0.0}
        self.update()

    def set_animations(self, on):
        # @args: on - False stops the twinkle for good (Settings >
        #        Interface); the sky stays, only the breathing stops.
        self._animations = bool(on)
        if self._animations and self.isVisible():
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def moon_info(self):
        # @return: the phase this hero is drawing, or None before the first
        #          refresh. The tests and the night panel read it from here
        #          so the painted Moon and the written Moon never disagree.
        return self._moon

    # --------------------------------------------------------------- paint

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        # Round the corners here instead of relying on the frame's QSS: the
        # widget covers the frame edge to edge, so square corners would poke
        # out of the rounded border and read as a glitch.
        clip = QPainterPath()
        clip.addRoundedRect(rect, 13.0, 13.0)
        p.setClipPath(clip)
        self._paint_background(p, rect)
        if self._moon is not None:
            self._paint_moon(p, rect)
        if self._animations:
            self._paint_glints(p, rect)
        p.end()

    def _paint_background(self, p, rect):
        # The vector, rasterised once per size and blitted after that.
        size = (int(rect.width()), int(rect.height()))
        if self._bg is None or self._bg_for != size:
            self._bg = self._render_bg(*size)
            self._bg_for = size
        p.drawPixmap(0, 0, self._bg)

    def _render_bg(self, w, h):
        # @args: w, h - the widget size in device-independent pixels
        # @return: a QPixmap of the sky, "cover" fitted (no distortion,
        #          crop the excess) or a hand-painted fallback.
        dpr = self.devicePixelRatioF() or 1.0
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor("#04060d"))
        if not ASSET.exists():
            self._paint_fallback(pm)
            return pm
        from PySide6.QtSvg import QSvgRenderer
        r = QSvgRenderer(str(ASSET))
        if not r.isValid():
            self._paint_fallback(pm)
            return pm
        # cover: match the hero's aspect by growing the shorter side, then
        # centre the overflow. A stretched sky would turn round stars into
        # dashes and the dome into an egg.
        aspect = w / float(h) if h else ASSET_ASPECT
        if aspect >= ASSET_ASPECT:
            dw, dh = float(w), w / ASSET_ASPECT
        else:
            dw, dh = h * ASSET_ASPECT, float(h)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        r.render(p, QRectF((w - dw) / 2.0, (h - dh) / 2.0, dw, dh))
        p.end()
        return pm

    def _paint_fallback(self, pm):
        # No asset, no QtSvg: the same family of colours, painted by hand,
        # so the hero still looks like a night and not like a hole.
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(pm.rect())
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0.0, QColor("#04060d"))
        g.setColorAt(0.7, QColor("#101a30"))
        g.setColorAt(1.0, QColor("#1b2942"))
        p.fillRect(r, QBrush(g))
        glow = QRadialGradient(r.width() * 0.78, r.height() * 1.3,
                               r.width() * 0.55)
        glow.setColorAt(0.0, QColor(76, 119, 159, 120))
        glow.setColorAt(1.0, QColor(76, 119, 159, 0))
        p.fillRect(r, QBrush(glow))
        p.end()

    def _paint_moon(self, p, rect):
        cx = rect.width() * 0.80
        cy = rect.height() * 0.30
        r = max(13.0, min(rect.height() * 0.115, 38.0))
        illum = self._moon["illum"]
        waxing = self._moon["waxing"]

        # A soft halo first: the Moon is the brightest thing in the frame
        # and a hard disc on the stars looks pasted on.
        halo = QRadialGradient(cx, cy, r * 0.7)
        halo.setColorAt(0.0, QColor(206, 224, 255, 58))
        halo.setColorAt(1.0, QColor(206, 224, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), r * 3.4, r * 3.4)

        # The unlit disc: barely lighter than the sky, so the dark limb is
        # still readable (that is what "earthshine" looks like).
        p.setBrush(QColor("#151d30"))
        p.drawEllipse(QPointF(cx, cy), r, r)

        lit = self._lit_path(cx, cy, r, illum, waxing)
        face = QRadialGradient(cx - r * 0.25, cy - r * 0.3, r * 1.4)
        face.setColorAt(0.0, QColor("#fffdf4"))
        face.setColorAt(1.0, QColor("#d6cfba"))
        p.setBrush(QBrush(face))
        p.drawPath(lit)

        # A few maria, clipped to the lit side: the Moon reads as the Moon
        # and not as a bright coin. Kept deliberately few and soft.
        p.setClipPath(lit)
        p.setBrush(QColor(150, 145, 130, 70))
        for ux, uy, ur in ((-0.34, -0.20, 0.30), (0.18, 0.30, 0.24),
                           (0.34, -0.34, 0.17), (-0.10, 0.46, 0.14)):
            p.drawEllipse(QPointF(cx + ux * r, cy + uy * r), ur * r, ur * r)
        p.setClipping(False)

        # The limb: one thin stroke, so the disc has an edge against the sky.
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 250, 235, 60), 0.8))
        p.drawEllipse(QPointF(cx, cy), r, r)

    def _lit_path(self, cx, cy, r, illum, waxing):
        # The lit region of a sphere seen from Earth is the outer half
        # circle on the lit side closed by an elliptical terminator whose
        # semi-axis is r*|cos(phase)| = r*|1-2*illum|.
        #   illum < 0.5 -> the terminator bulges INTO the lit half (crescent)
        #   illum > 0.5 -> it bulges AWAY (gibbous)
        # The sign of the sweep flips with the waxing/waning mirror; this
        # is the whole reason the phase looks right instead of flipped.
        sign = 1.0 if waxing else -1.0
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.arcTo(QRectF(cx - r, cy - r, 2 * r, 2 * r), 90.0, -180.0 * sign)
        rx = max(0.4, r * abs(1.0 - 2.0 * illum))
        sweep = (180.0 if illum < 0.5 else -180.0) * sign
        path.arcTo(QRectF(cx - rx, cy - r, 2 * rx, 2 * r), 270.0, sweep)
        path.closeSubpath()
        return path

    def _paint_glints(self, p, rect):
        # Small soft dots over a few fixed stars. Each one breathes with
        # its own phase: a shared phase would pulse the whole sky at once.
        import math
        p.setPen(Qt.NoPen)
        for rx, ry, size, phase in _GLINTS:
            x, y = rect.width() * rx, rect.height() * ry
            wave = 0.5 + 0.5 * math.sin(2.0 * math.pi * (self._t + phase))
            alpha = int(30 + 120 * wave)
            if alpha <= 2:
                continue
            g = QRadialGradient(x, y, size * 3.0)
            g.setColorAt(0.0, QColor(255, 255, 255, alpha))
            g.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(x, y), size * 3.0, size * 3.0)

    # -------------------------------------------------------------- events

    def resizeEvent(self, event):
        # A new size invalidates the raster; the next paint rebuilds it.
        self._bg = None
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self._animations:
            self._timer.start()

    def hideEvent(self, event):
        # Off screen is off duty: no timer burning a core behind another view.
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self):
        # Advance the twinkle and repaint ONLY the glint boxes.
        self._t += 1.0 / 34.0
        if self._t >= 1.0:
            self._t -= 1.0
        rect = self.rect()
        for rx, ry, size, _phase in _GLINTS:
            x, y = rect.width() * rx, rect.height() * ry
            box = QRectF(x - size * 3, y - size * 3, size * 6, size * 6)
            self.update(box.toAlignedRect())
