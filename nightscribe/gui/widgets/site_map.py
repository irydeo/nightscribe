############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Site picker map widget (Interfaz 1.5)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Pick an observatory site on a world map.

Why a map at all: typing a latitude by hand means knowing it, and most
people know where they live, not its coordinates. The map turns "where do
you look at the sky from" into a click, and it shows the point back so a
wrong number is visible instead of silent.

What makes it useful rather than decorative:

   * the **day/night terminator** is computed live from the Sun's position
     (ephem_minor + GMST, all local, no network): the shaded half is the
     half that is in the dark right now, which is the only half that
     matters to an observer;
   * the **coordinates under the cursor** are read out while you move, so
     the click lands where you mean and the spin boxes can refine it.

The base (ocean, coastlines, borders, graticule) is rasterised once per
size and zoom into a QPixmap and blitted afterwards: a repaint is a memory
copy plus the terminator and the marker, never 8000 line segments.

Data: assets/world_map.json, Natural Earth 110m (public domain). See
assets/ATTRIBUTION.txt.
"""

import json
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import QWidget

from .. import theme

ASSET = theme.asset("world_map.json")

# Zoom limits. 1.0 is the COVER level: the map fills its box completely.
# Below 1.0 the world starts to fit inside the box and the letterbox bands
# come back, which is the price of being able to see the poles; 0.5 is far
# enough out to see the whole planet on any sane box. 16x is roughly 3 km
# per pixel on a 700 px wide map: fine enough to land on the right valley,
# and the spin boxes are what nail the point.
ZOOM_MIN = 0.5
ZOOM_MAX = 16.0

# The terminator moves about a quarter of a degree per minute: recomputing
# it every two minutes keeps it honest for free.
_TERM_MS = 120_000

_CACHE = None


def terminator_points(jd):
    # The line where the Sun sits on the horizon at Julian date jd.
    #
    # Standard spherical astronomy: for a given longitude the local hour
    # angle of the Sun is H = GMST + lon - RA, and the latitude where its
    # altitude is zero follows from tan(phi) = -cos(H) / tan(dec). Sampling
    # it every 2 degrees is plenty for a 700 px wide map.
    #
    # Pulled out of the widget and given a jd on purpose: a pure function
    # can be tested at the equinox and the solstice, where the curve is at
    # its hardest (it runs almost straight up and down), without waiting
    # six months.
    # @args: jd - Julian date
    # @return: (points, declination): [(lon, lat), ...] and the solar
    #          declination in degrees, which says WHICH pole is in the dark
    from ...core import coords, ephem_minor
    ra, dec, _r = ephem_minor.sun_ra_dec(jd)
    gmst = coords.lst_degrees(jd, 0.0)
    tan_dec = math.tan(math.radians(dec))
    if abs(tan_dec) < 1e-9:
        # the equinox: the terminator is a meridian. Without this guard the
        # division blows up exactly when the curve is most vertical.
        tan_dec = 1e-9 if tan_dec >= 0 else -1e-9
    pts = []
    for lon in range(-180, 181, 2):
        h = math.radians((gmst + lon) - ra)
        lat = math.degrees(math.atan(-math.cos(h) / tan_dec))
        pts.append((float(lon), max(-90.0, min(90.0, lat))))
    return pts, dec


def _load():
    # @return: the parsed asset, or an empty shape when it is missing (the
    #          map then draws its graticule alone instead of crashing)
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(ASSET.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {"coast": [], "border": []}
    return _CACHE


class SiteMap(QWidget):
    """An equirectangular world map you can click to place a site."""

    # picked: a click landed, with (lat, lon) in degrees
    picked = Signal(float, float)

    # @args: parent - the widget that owns it
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 150)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self._data = None
        self._lat = None            # the chosen site (None = nothing yet)
        self._lon = None
        self._name = ""
        # 1.0 is the cover level, NOT ZOOM_MIN: the map opens filling its
        # box (no side bands); zooming out from here is what reveals the
        # poles, and it is a deliberate gesture.
        self._zoom = 1.0
        self._clat = 0.0            # what the widget is looking at
        self._clon = 0.0
        self._cursor = None         # (lat, lon) under the mouse
        self._press = None          # (x, y, clat, clon) while dragging
        self._moved = False
        self._base = None           # cached raster of the world
        self._base_key = None
        self._term = None           # cached terminator polygon (lon/lat)
        self._term_key = None
        self._term_dec = 0.0        # solar declination of that polygon
        self._timer = QTimer(self)
        self._timer.setInterval(_TERM_MS)
        self._timer.timeout.connect(self._age)

    # ------------------------------------------------------------- the site

    def set_site(self, lat, lon, name=""):
        # Moves the marker. Does NOT emit picked: the caller is the one who
        # just set it (a spin box, a resolved MPC code), and echoing it back
        # would fight whatever is driving this widget.
        # @args: lat, lon - degrees (None clears the marker);
        #        name - what to print next to the marker
        try:
            self._lat, self._lon = float(lat), float(lon)
        except (TypeError, ValueError):
            self._lat = self._lon = None
        self._name = name or ""
        if self._lat is not None:
            # Follow the marker ONLY when it would fall off the view. This
            # runs on every keystroke of the spin boxes, and re-centring
            # each time would yank the map away from wherever the observer
            # had just panned it.
            x, y = self.to_px(self._lon, self._lat)
            # the WIDGET rect, not map_rect(): the latter is the whole
            # world in pixels (far bigger than the view when zoomed in), so
            # everything would look "visible" and the map would never follow
            visible = QRectF(self.rect()).adjusted(-24, -24, 24, 24)
            if not visible.contains(QPointF(x, y)):
                self._clat, self._clon = self._lat, self._lon
                self._clamp()
        self.update()

    def site(self):
        # @return: (lat, lon) or (None, None)
        return self._lat, self._lon

    def has_site(self):
        # @return: True once a point has been set
        return self._lat is not None

    # ----------------------------------------------------------- projection

    def _ppd(self):
        # @return: pixels per degree. COVER, not contain: at zoom 1 the map
        #          fills its box in both axes, so no black bands sit at the
        #          sides of the world. The price is that the box shows 360
        #          degrees of longitude by only ~130 of latitude (roughly
        #          -57..+57 on a 3:1 box): zooming out past 1.0 brings the
        #          letterbox back and with it the poles.
        return (max(self.width() / 360.0, self.height() / 180.0)
                * self._zoom)

    def _fits(self):
        # @return: True when the whole world is inside the box, which is
        #          exactly when the letterbox (and its frame) is visible
        return (360.0 * self._ppd() <= self.width() + 0.5
                and 180.0 * self._ppd() <= self.height() + 0.5)

    def _origin(self):
        # @return: the pixel of (lon = -180, lat = +90)
        ppd = self._ppd()
        return (self.width() / 2.0 - (self._clon + 180.0) * ppd,
                self.height() / 2.0 - (90.0 - self._clat) * ppd)

    def to_px(self, lon, lat):
        # @args: lon, lat - degrees
        # @return: (x, y) in widget pixels
        ppd = self._ppd()
        ox, oy = self._origin()
        return ox + (lon + 180.0) * ppd, oy + (90.0 - lat) * ppd

    def to_geo(self, x, y):
        # @args: x, y - widget pixels
        # @return: (lon, lat) in degrees
        ppd = self._ppd()
        ox, oy = self._origin()
        return (x - ox) / ppd - 180.0, 90.0 - (y - oy) / ppd

    def map_rect(self):
        # @return: the QRectF the world occupies (inside it is map, outside
        #          is "off the edge of the world" and is painted as such)
        ppd = self._ppd()
        ox, oy = self._origin()
        return QRectF(ox, oy, 360.0 * ppd, 180.0 * ppd)

    def _clamp(self):
        # Keeps the view inside the world: without this the map slides off
        # into empty space and the user cannot find it back.
        ppd = self._ppd()
        world_w, world_h = 360.0 * ppd, 180.0 * ppd
        if world_w <= self.width():
            self._clon = 0.0
        else:
            half = (self.width() / 2.0) / ppd
            self._clon = max(-180.0 + half, min(180.0 - half, self._clon))
        if world_h <= self.height():
            self._clat = 0.0
        else:
            half = (self.height() / 2.0) / ppd
            self._clat = max(-90.0 + half, min(90.0 - half, self._clat))

    # ---------------------------------------------------------- interaction

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self._press = (event.position().x(), event.position().y(),
                       self._clat, self._clon)
        self._moved = False
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        x, y = event.position().x(), event.position().y()
        if self._press is not None:
            x0, y0, clat, clon = self._press
            if abs(x - x0) + abs(y - y0) > 3:
                self._moved = True
            ppd = self._ppd()
            # dragging moves the world WITH the hand
            self._clon = clon - (x - x0) / ppd
            self._clat = clat + (y - y0) / ppd
            self._clamp()
            self._invalidate_base()
            self.update()
            return
        lon, lat = self.to_geo(x, y)
        self._cursor = (max(-90.0, min(90.0, lat)), lon)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self._press is None:
            return
        self._press = None
        self.setCursor(Qt.CrossCursor)
        if self._moved:
            return                      # that was a pan, not a click
        lon, lat = self.to_geo(event.position().x(), event.position().y())
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            return                      # outside the world: nothing to pick
        self.set_site(lat, lon, self._name)
        self.picked.emit(round(lat, 5), round(lon, 5))

    def leaveEvent(self, event):
        self._cursor = None
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if not delta:
            return
        x, y = event.position().x(), event.position().y()
        lon, lat = self.to_geo(x, y)
        factor = 1.25 if delta > 0 else 1.0 / 1.25
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._zoom * factor))
        # Keep the point under the cursor under the cursor: the centre that
        # does that falls straight out of the projection equations.
        ppd = self._ppd()
        self._clon = lon - (x - self.width() / 2.0) / ppd
        self._clat = lat + (y - self.height() / 2.0) / ppd
        self._clamp()
        self._invalidate_base()
        self.update()

    def mouseDoubleClickEvent(self, event):
        # Recentre on the site: after panning around, finding it back by
        # hand is a chore.
        if self._lat is not None:
            self._zoom = max(self._zoom, 4.0)
            self._clat, self._clon = self._lat, self._lon
            self._clamp()
            self._invalidate_base()
            self.update()

    def resizeEvent(self, event):
        self._invalidate_base()
        super().resizeEvent(event)

    def showEvent(self, event):
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _age(self):
        # The terminator crept along: rebuild and repaint.
        self._term = None
        self.update()

    def _invalidate_base(self):
        self._base = None

    # ------------------------------------------------------------- painting

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        p.fillRect(rect, QColor("#070b13"))
        self._paint_base(p)
        p.save()
        p.setClipRect(self.map_rect())
        self._paint_night(p)
        p.restore()
        if self._fits():
            # only when the world is smaller than the box: with the map
            # filling it edge to edge there is no frame to draw
            p.setPen(QPen(QColor(theme.C_EDGE), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.map_rect().adjusted(0, 0, -1, -1))
        self._paint_marker(p)
        self._paint_readout(p)
        p.end()

    def _paint_base(self, p):
        key = (self.width(), self.height(), round(self._zoom, 3),
               round(self._clon, 3), round(self._clat, 3))
        if self._base is None or self._base_key != key:
            self._base = self._render_base()
            self._base_key = key
        p.drawPixmap(0, 0, self._base)

    def _render_base(self):
        # @return: a QPixmap with the ocean, the graticule, the coastlines
        #          and the borders, at the CURRENT view. Rasterised once per
        #          view instead of stroking 8000 segments on every repaint.
        dpr = self.devicePixelRatioF() or 1.0
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor("#070b13"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        mr = self.map_rect()
        p.fillRect(mr, QColor("#0d1729"))
        # graticule every 30 degrees, with the equator and the Greenwich
        # meridian a shade brighter: they are the two lines that let you
        # place yourself at a glance
        p.setPen(QPen(QColor(60, 82, 124, 90), 1))
        for lon in range(-150, 151, 30):
            x, _ = self.to_px(lon, 0)
            p.drawLine(QPointF(x, mr.top()), QPointF(x, mr.bottom()))
        for lat in range(-60, 61, 30):
            _, y = self.to_px(0, lat)
            p.drawLine(QPointF(mr.left(), y), QPointF(mr.right(), y))
        p.setPen(QPen(QColor(86, 112, 158, 150), 1))
        _, y0 = self.to_px(0, 0)
        p.drawLine(QPointF(mr.left(), y0), QPointF(mr.right(), y0))
        x0, _ = self.to_px(0, 0)
        p.drawLine(QPointF(x0, mr.top()), QPointF(x0, mr.bottom()))
        data = self._data if self._data is not None else _load()
        self._data = data
        # borders first (dimmer) and coastlines on top: the coast is the
        # line that tells you where you are
        for layer, color, width in (("border", QColor(120, 140, 175, 80), 0.7),
                                    ("coast", QColor("#93a9d8"), 0.9)):
            p.setPen(QPen(color, width))
            for run in data.get(layer, ()):
                path = QPainterPath()
                first = True
                for i in range(0, len(run) - 1, 2):
                    x, y = self.to_px(run[i], run[i + 1])
                    if first:
                        path.moveTo(x, y)
                        first = False
                    else:
                        path.lineTo(x, y)
                p.drawPath(path)
        p.end()
        return pm

    def _terminator(self):
        # @return: [(lon, lat), ...] for RIGHT NOW, memoised in two-minute
        #          buckets (the curve is identical to the pixel within one)
        import datetime as _dt

        from ...core import coords
        jd = coords.jd_from_datetime(_dt.datetime.now(_dt.timezone.utc))
        key = int(jd * 720.0)
        if self._term is not None and self._term_key == key:
            return self._term
        pts, dec = terminator_points(jd)
        self._term = pts
        self._term_key = key
        self._term_dec = dec
        return pts

    def _paint_night(self, p):
        pts = self._terminator()
        if not pts:
            return
        # The night is the cap around the pole AWAY from the Sun, so the
        # polygon closes along that pole: with the Sun over the southern
        # hemisphere (dec < 0) the dark cap is the northern one.
        night_north = self._term_dec < 0.0
        path = QPainterPath()
        first = True
        for lon, lat in pts:
            x, y = self.to_px(lon, lat)
            if first:
                path.moveTo(x, y)
                first = False
            else:
                path.lineTo(x, y)
        edge = 90.0 if night_north else -90.0
        x1, y1 = self.to_px(180.0, edge)
        x2, y2 = self.to_px(-180.0, edge)
        path.lineTo(x1, y1)
        path.lineTo(x2, y2)
        path.closeSubpath()
        p.fillPath(path, QColor(2, 4, 11, 150))
        p.setPen(QPen(QColor(130, 165, 220, 170), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def _paint_marker(self, p):
        if self._lat is None:
            return
        x, y = self.to_px(self._lon, self._lat)
        accent = QColor(theme.C_ACCENT)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 140), 3.0))
        p.drawEllipse(QPointF(x, y), 6.0, 6.0)
        p.drawLine(QPointF(x - 11, y), QPointF(x + 11, y))
        p.drawLine(QPointF(x, y - 11), QPointF(x, y + 11))
        p.setPen(QPen(accent, 1.6))
        p.drawEllipse(QPointF(x, y), 6.0, 6.0)
        p.drawLine(QPointF(x - 11, y), QPointF(x + 11, y))
        p.drawLine(QPointF(x, y - 11), QPointF(x, y + 11))
        label = "%s  %.4f, %.4f" % (self._name, self._lat, self._lon)
        self._boxed_text(p, label, x + 14.0, y - 22.0, accent)

    def _paint_readout(self, p):
        # The coordinates under the cursor: this is what turns a decorative
        # map into a way of entering a position.
        if self._cursor is None:
            return
        lat, lon = self._cursor
        if not (-180.0 <= lon <= 180.0):
            return
        # anchored to the WIDGET, not to the world: with cover the world's
        # rect starts off screen and the readout would be clamped into a
        # corner instead of sitting where it belongs
        self._boxed_text(p, "%+.3f  %+.3f" % (lat, lon),
                         8.0, self.height() - 26.0,
                         QColor(theme.C_TEXT_DIM))

    def _boxed_text(self, p, text, x, y, color):
        # A small label with a dark plate behind it, so it stays readable
        # over land, ocean and the shaded night alike.
        font = QFont(self.font())
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1.0))
        p.setFont(font)
        metrics = p.fontMetrics()
        w = metrics.horizontalAdvance(text) + 12.0
        h = metrics.height() + 4.0
        box = QRectF(x, y, w, h)
        # keep it inside the widget
        if box.right() > self.width() - 2:
            box.moveLeft(self.width() - 2 - w)
        if box.bottom() > self.height() - 2:
            box.moveTop(self.height() - 2 - h)
        if box.left() < 2:
            box.moveLeft(2)
        if box.top() < 2:
            box.moveTop(2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(6, 10, 18, 200))
        p.drawRoundedRect(box, 4.0, 4.0)
        p.setPen(QPen(color))
        p.drawText(box.adjusted(6, 0, -6, 0),
                   Qt.AlignVCenter | Qt.AlignLeft, text)
