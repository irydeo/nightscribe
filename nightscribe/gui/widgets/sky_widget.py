############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - interactive night-sky chart widget (ADR-029)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The vector, interactive night-sky (visibility) chart for the GUI (ADR-029).

`SkyChart` composes a `ChartView` (the generic zoom / pan / fit / hover-chrome)
and answers the hover probe for the target — giving the exact UTC time,
altitude and azimuth at the point under the cursor. It shades:

   * the **dark window** (dusk→dawn) — the soft blue band;
   * the **safe window** (ADR-020) — the run of the night where the planned
     session still clears the local horizon. A left-click inside it fires
     `best_time_clicked`, so the GUI can snap the almanac to the start-by time;
   * the **best time** — the "start by" moment drawn as a dashed vertical line
     with a label;
   * the **local horizon** limit as a dashed line (flat 30° or the
     `horizon.alt_at(az)` per-azimuth curve);
   * the **Moon** altitude as a dotted grey line.

`TransitChart` is a subclass that adds the transit's ingress/egress shaded
band on top of the same sky chart, so the user can see the transit window
against the actual sky visibility of the star.

All the data comes from `core/sky_math` (the same sampler `viz/sky_view.py`
uses for the PNG exports — ADR-029), so the widget and the matplotlib chart
can never drift apart.
"""

import datetime as _dt

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPen, QBrush, QColor, QPainterPath
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QSizePolicy,
                               QGraphicsSimpleTextItem)

from ...core import sky_math
from ...viz import palette
from .base_chart import ChartView


# The scene works in a *normalised* coordinate system: the framed half-extent
# is always _HALF scene units on each axis, independent of the night's span
# in hours. That keeps the fonts and line widths scale-independent (a
# QGraphicsScene font is in scene units and quantises to whole pixels, so it
# would dwarf a short night or dwarf the labels of a long one otherwise).
# Same convention as orbit_widget.py.
_HALF = 500.0

# Scene z-order (higher is drawn on top) so labels never hide under a band.
_Z_DARK = 0.0
_Z_GRID = 1.0
_Z_HORIZON = 2.0
_Z_MOON = 3.0
_Z_TARGET = 4.0
_Z_SAFE = 5.0
_Z_TRANSIT = 6.0
_Z_BEST = 7.0
_Z_LABEL = 8.0

# A cursor within this fraction of _HALF of the target curve counts as
# "on the curve", so the hover probe fires without pixel-snapping.
# 8% (same as orbit_widget._HIT_TOL) — forgiving to the eye, precise enough
# to be useful (the curve is 10-min sampled).
_HIT_TOL = 0.08

# Font sizes in scene units (kept the same order of magnitude as
# orbit_widget, which also draws tick/labels in scene space).
_FONT_TICK = 20
_FONT_LABEL = 26

# A thin, dashed pen for the horizon limit.
_DASH = [6, 6]
_DOTTED = [2, 4]


def _utc(dt):
    # @args: dt - datetime (aware or naive)
    # @return: the aware-UTC equivalent (naive inputs assumed to be UTC).
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_dt.timezone.utc)
    return dt.astimezone(_dt.timezone.utc)


def _hex_alpha(hex_, alpha):
    # @args: hex_ — a "#rrggbb" string; alpha — 0..255
    # @return: a QColor with the requested alpha (a QColor(name, alpha) is
    #          not supported by this Qt build, so we set it after the fact).
    c = QColor(hex_)
    c.setAlpha(alpha)
    return c


class SkyChart(QWidget):
    """A vector, interactive night-sky chart (see module docstring).

    Signal:
        best_time_clicked(dt: object) — a left-click lands inside the
            safe-window band. `dt` is the stored `best_time` (a datetime,
            or None if the chart has no start-by moment set).
    """

    best_time_clicked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.view = ChartView()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.view)

        # -- state ------------------------------------------------------------
        self._samples = None       # the dict from core/sky_math.sample_night
        self._obj_name = ""
        self._span_h = 2.0         # framed span in hours (end-start)
        self._cx_h = 0.0           # frame center in hours (rel to dusk)
        self._scale_x = _HALF      # scene units per rel-hour
        self._scale_y = _HALF      # scene units per altitude degree
        self._target_pts = []      # (sx, sy) of the sampled target curve
        self._safe_rect = None     # QRectF (scene) of the safe window, or None
        self._transit_rect = None  # QRectF (scene) of the transit band, or None
        self._best_time = None     # the stored best_time (datetime or None)
        self._label_font = self.view.font()

        # -- hover + click ----------------------------------------------------
        self.view.set_hover_probe(self._hover)
        self.view.scene_clicked.connect(self._on_scene_clicked)

    # ------------------------------------------------- public API ---------

    def set_target(self, ra, dec, lat, lon, date,
                   obj_name="", safe_window=None, best_time=None,
                   horizon=None, transit=None, margin=0.0, step_min=10):
        # @args: ra, dec       - target (deg); lat, lon - site (deg);
        #        date           - datetime.date ("tonight");
        #        obj_name       - label shown in the legend/labels;
        #        safe_window    - (t0, t1) datetimes (or ISO strings);
        #        best_time      - datetime (or ISO string) to label "start by";
        #        horizon        - optional alt_at(az) callable (ADR-020);
        #        transit        - optional dict {ingress, egress, ...};
        #        margin         - safety margin (deg) on the horizon limit;
        #        step_min       - sampling resolution (min, default 10).
        # Rebuilds the canvas for a new target/night.
        self._obj_name = obj_name or ""
        self._samples = sky_math.sample_night(
            ra, dec, lat, lon, date,
            horizon=horizon, margin=margin, step_min=step_min)
        self._safe_window = tuple(
            self._as_dt(x) for x in safe_window) if safe_window else None
        self._best_time = self._as_dt(best_time)

        if not self._samples:
            self._span_h = 2.0
            self._cx_h = 0.0
            self._scale_x = _HALF
            self._scale_y = _HALF
            self._target_pts = []
            self._safe_rect = None
            self._transit_rect = None
            self._transit = None
            self._build_scene()
            self.view.fit_to_scene()
            return

        span_h = (self._samples["end"] - self._samples["start"]).total_seconds() / 3600.0
        self._span_h = span_h
        # the frame covers [-1, span+1] in rel-hours and [0, 90] in altitude;
        # the whole scene is [-HALF, +HALF] on each axis — so the per-unit
        # scales are (scene span) / (data span):
        self._scale_x = (2.0 * _HALF) / max(1e-9, span_h + 2.0)
        self._scale_y = (2.0 * _HALF) / 90.0
        # the scene is centred on (span/2, 45°) in data space, so a rel-hour
        # `r` of 0 maps to a scene-x that is *not* -HALF but (−1 → −HALF)
        # through a linear map with _cx_h = span/2 as the axis centre.
        self._cx_h = span_h / 2.0
        self._target_pts = [self._to_scene(r, a)
                            for r, a in zip(self._samples["rel"], self._samples["alt"])]

        # Transit band (optional); stored for a subclass (TransitChart) to read.
        tg = transit if transit else None
        if tg and tg.get("ingress") and tg.get("egress"):
            self._transit = tg
        else:
            self._transit = None

        self._build_scene()
        self.view.fit_to_scene()

    def target(self):
        # @return: the stored sample_night dict (or None if there is no night).
        return self._samples

    def best_time(self):
        # @return: the stored best_time (datetime or None).
        return self._best_time

    def export_png(self, path, dpi=100):
        # @return: the Path written (delegates to the canvas, so it captures
        #          exactly what is on screen, zoom included).
        return self.view.export_png(path, dpi=dpi)

    def fit(self):
        # Refits the canvas to the scene.
        self.view.fit_to_scene()

    def clear(self):
        # Drops the current chart (also hides any stale hover tooltip).
        self._samples = None
        self._safe_window = None
        self._best_time = None
        self._transit = None
        self._target_pts = []
        self._safe_rect = None
        self._transit_rect = None
        self.view.clear()

    # ------------------------------------------------- geometry -----------

    def _to_scene(self, rel_h, alt_deg):
        # @args: rel_h   - hours from astronomical dusk (negative = before);
        #        alt_deg - altitude in degrees.
        # @return: scene (sx, sy) in the normalised scene (frame = +/-_HALF).
        sx = (rel_h - self._cx_h) * self._scale_x
        sy = -((alt_deg - 45.0) * self._scale_y)
        return (sx, sy)

    def _to_data(self, sx, sy):
        # @args: sx, sy - scene coords
        # @return: (rel_h, alt_deg) — the inverse of _to_scene (hover probe).
        rel_h = sx / self._scale_x + self._cx_h
        alt_deg = -(sy / self._scale_y) + 45.0
        return (rel_h, alt_deg)

    # ------------------------------------------------- scene --------------

    def _build_scene(self):
        # Draws the grid, the target curve, the Moon, the local horizon
        # limit, the dark-window shading, the safe-window band and the
        # best-time marker (and, for TransitChart, the transit band).
        self.view.clear()
        self.view.set_scene_rect(-_HALF, -_HALF, 2.0 * _HALF, 2.0 * _HALF)

        # --- grid: hour + altitude ticks (drawn first, so they sit behind) --
        span = self._span_h
        # altitude ticks at 15°, 30°, 45°, 60°, 75°, 90° (a horizontal line at
        # each degree, plus a small degree label to the left)
        for a in (15, 30, 45, 60, 75, 90):
            x0, y0 = self._to_scene(-1.0, a)
            x1, y1 = self._to_scene(-1.0 + span + 2.0, a)
            self._add_grid_line(x0, y0, x1, y1)
            self._add_tick_label(f"{a}°", x0 + 2, y0 + _FONT_TICK / 2,
                                 QColor(palette.MUTED), bold=False)
        # hour labels at every integer boundary (including the 1 h of margin
        # on either side) so the axis never shows "26/28"
        if self._samples:
            start = self._samples["start"]
        else:
            start = None
        if start is not None:
            for i in range(-1, int(span) + 2):
                p = float(i)
                sx0, sy0 = self._to_scene(p, 0.0)
                sx1, sy1 = self._to_scene(p, 90.0)
                self._add_grid_line(sx0, sy0, sx1, sy1)
                label = f"{(start + _dt.timedelta(hours=i)):%H:%M}Z"
                self._add_tick_label(label, sx0 - _FONT_TICK / 2,
                                     sy1 + _FONT_TICK / 2 + 2,
                                     QColor(palette.MUTED), bold=False)
        self._add_axis_caption_alt()
        self._add_axis_caption_time()

        if not self._samples:
            # no astronomical night: a single centered notice, nothing else
            it = QGraphicsSimpleTextItem(
                self.tr("Sin noche astronómica"))
            it.setBrush(QBrush(QColor(palette.FG)))
            f = self._label_font
            f.setPixelSize(_FONT_LABEL + 6)
            it.setFont(f)
            it.setPos(-140, -8)
            it.setZValue(_Z_LABEL)
            self.view.scene().addItem(it)
            self.view._items_registered.append(it)
            return

        # --- dark window (soft blue shading 0..span, full altitude) ---------
        if self._samples:
            span = self._span_h
            x0, y0 = self._to_scene(0.0, 0.0)
            x1, y1 = self._to_scene(span, 90.0)
            # y grows downward (Qt) — the top of the dark band in scene is y1
            r = self.view.scene().addRect(min(x0, x1), min(y0, y1),
                                          abs(x1 - x0), abs(y1 - y0))
            r.setBrush(QBrush(_hex_alpha(palette.ACCENT2, 28)))
            r.setPen(Qt.NoPen)
            r.setZValue(_Z_DARK)
            self.view._items_registered.append(r)

        # --- local horizon limit ------------------------------------------
        if self._samples:
            rel0 = self._samples["rel"][0]
            relN = self._samples["rel"][-1]
            # flat (30°) or per-azimuth curve; a straight line when uniform
            first = self._samples["horizon"][0]
            flat = all(abs(h - first) < 1e-6 for h in self._samples["horizon"])
            if flat:
                ax0, ay0 = self._to_scene(rel0, first)
                ax1, ay1 = self._to_scene(relN, first)
                self._add_dashed_line(ax0, ay0, ax1, ay1,
                                      QColor(palette.MUTED), 1.0, _DASH, _Z_HORIZON)
            else:
                self._add_poly(self._samples["rel"], self._samples["horizon"],
                               QColor(palette.MUTED), 1.0, _DASH, _Z_HORIZON)

        # --- Moon altitude (dotted grey) -----------------------------------
        self._add_poly(self._samples["rel"], self._samples["moon"],
                       QColor("#c9c9c9"), 1.2, _DOTTED, _Z_MOON)

        # --- the target curve ----------------------------------------------
        self._add_poly(self._samples["rel"], self._samples["alt"],
                       QColor(palette.ACCENT), 1.8, [], _Z_TARGET)

        # --- safe window (ADR-020) -----------------------------------------
        if self._safe_window:
            t0, t1 = (_utc(self._safe_window[0]), _utc(self._safe_window[1]))
            if t0 is not None and t1 is not None:
                start = _utc(self._samples["start"])
                span = self._span_h
                p0 = (t0 - start).total_seconds() / 3600.0
                p1 = (t1 - start).total_seconds() / 3600.0
                if p1 < p0:
                    p1 += 24 * 3600.0 / 3600.0
                x0, y0 = self._to_scene(p0, 0.0)
                x1, y1 = self._to_scene(p1, 90.0)
                self._safe_rect = self._add_band(
                    min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0),
                    _hex_alpha(palette.ACCENT2, 38), "safe", _Z_SAFE)
                # best time (start-by marker)
                if self._best_time is not None:
                    bt = _utc(self._best_time)
                    if bt is not None:
                        bp = (bt - start).total_seconds() / 3600.0
                        bx0, by0 = self._to_scene(bp, 0.0)
                        bx1, by1 = self._to_scene(bp, 90.0)
                        self._add_dashed_line(bx0, by0, bx1, by1,
                                              QColor(palette.ACCENT), 1.2,
                                              _DASH, _Z_BEST)
                        self._add_band_label(
                            self.tr("empezar hasta {t}").format(
                                t=f"{bt:%H:%M}Z"),
                            (bx0 + bx1) / 2.0, by1 + _FONT_LABEL)

        elif self._best_time is not None:
            bt = _utc(self._best_time)
            if bt is not None:
                start = _utc(self._samples["start"])
                bp = (bt - start).total_seconds() / 3600.0
                bx0, by0 = self._to_scene(bp, 0.0)
                bx1, by1 = self._to_scene(bp, 90.0)
                self._add_dashed_line(bx0, by0, bx1, by1,
                                      QColor(palette.ACCENT), 1.2,
                                      _DASH, _Z_BEST)
                self._add_band_label(
                    self.tr("mejor hora {t}").format(t=f"{bt:%H:%M}Z"),
                    (bx0 + bx1) / 2.0, by1 + _FONT_LABEL)

        # the concrete chart may add a transit band on top (TransitChart)
        self._draw_transit()

    # ------------------------------------------------- scene helpers ------

    def _add_grid_line(self, x0, y0, x1, y1):
        it = self.view.scene().addLine(x0, y0, x1, y1)
        pen = QPen(QColor(palette.MUTED), 0.6)
        pen.setCosmetic(True)
        it.setPen(pen)
        it.setZValue(_Z_GRID)
        self.view._items_registered.append(it)
        return it

    def _add_tick_label(self, text, x, y, color, bold):
        it = QGraphicsSimpleTextItem(text)
        it.setBrush(QBrush(color))
        f = self._label_font
        f.setPixelSize(_FONT_TICK)
        if bold:
            f.setBold(True)
        it.setFont(f)
        it.setPos(x, y)
        it.setZValue(_Z_LABEL)
        self.view.scene().addItem(it)
        self.view._items_registered.append(it)
        return it

    def _add_axis_caption_alt(self):
        # A short axis label ("Alt (°)") on the left, "h →" at the top.
        it = QGraphicsSimpleTextItem(self.tr("Alt (°)"))
        it.setBrush(QBrush(QColor(palette.FG)))
        f = self._label_font
        f.setPixelSize(_FONT_LABEL)
        it.setFont(f)
        it.setPos(-_HALF + 6, -_HALF - 2)
        it.setZValue(_Z_LABEL)
        self.view.scene().addItem(it)
        self.view._items_registered.append(it)

    def _add_axis_caption_time(self):
        it = QGraphicsSimpleTextItem(self.tr("UTC (h desde anochecer)"))
        it.setBrush(QBrush(QColor(palette.FG)))
        f = self._label_font
        f.setPixelSize(_FONT_LABEL)
        it.setFont(f)
        it.setPos(_HALF - 260, _HALF - _FONT_LABEL - 4)
        it.setZValue(_Z_LABEL)
        self.view.scene().addItem(it)
        self.view._items_registered.append(it)

    def _add_poly(self, rel, alt, color, width, dash, z):
        # @args: rel, alt - parallel arrays (hours from start, degrees);
        #        color    - QColor; width - px; dash - pen dash list ([] = solid);
        #        z        - z order.
        if not rel:
            return None
        pp = QPainterPath()
        x0, y0 = self._to_scene(rel[0], alt[0])
        pp.moveTo(x0, y0)
        for i in range(1, len(rel)):
            xi, yi = self._to_scene(rel[i], alt[i])
            pp.lineTo(xi, yi)
        item = self.view.scene().addPath(pp)
        pen = QPen(color, width)
        pen.setCosmetic(True)
        if dash:
            pen.setStyle(Qt.DashLine)
            pen.setDashPattern(dash)
        item.setPen(pen)
        item.setBrush(Qt.NoBrush)
        item.setZValue(z)
        self.view._items_registered.append(item)
        return item

    def _add_dashed_line(self, x0, y0, x1, y1, color, width, dash, z):
        it = self.view.scene().addLine(x0, y0, x1, y1)
        pen = QPen(color, width)
        pen.setCosmetic(True)
        pen.setStyle(Qt.DashLine)
        pen.setDashPattern(dash)
        it.setPen(pen)
        it.setZValue(z)
        self.view._items_registered.append(it)
        return it

    def _add_band(self, x, y, w, h, brush_color, tag, z):
        # @args: x, y, w, h - the band's QRectF in scene units;
        #        brush_color - a semi-transparent QColor; tag — a string
        #        identifier stored on the band (for testing / introspection);
        #        z           - z order.
        r = self.view.scene().addRect(x, y, w, h)
        r.setBrush(QBrush(brush_color))
        r.setPen(Qt.NoPen)
        r.setZValue(z)
        r.setData(0, tag)
        self.view._items_registered.append(r)
        return r

    def _add_band_label(self, text, x, y):
        it = QGraphicsSimpleTextItem(text)
        it.setBrush(QBrush(QColor(palette.ACCENT)))
        f = self._label_font
        f.setPixelSize(_FONT_LABEL)
        it.setFont(f)
        it.setPos(x - 90, y)
        it.setZValue(_Z_LABEL)
        self.view.scene().addItem(it)
        self.view._items_registered.append(it)
        return it

    # ------------------------------------------------- hooks --------------

    def _as_dt(self, x):
        # @args: x - a datetime or an ISO string
        # @return: an aware-UTC datetime (or None).
        if x is None:
            return None
        if isinstance(x, _dt.datetime):
            return _utc(x)
        if isinstance(x, str):
            try:
                return _utc(_dt.datetime.fromisoformat(x))
            except ValueError:
                return None
        return None

    def _draw_transit(self):
        # Draws the ingress/egress shaded band when the transit was set.
        # A plain SkyChart leaves it as no-op; TransitChart adds the band +
        # label on top of the sky, so the transit window reads against the
        # star's actual visibility rather than an abstract light curve.
        if not self._transit:
            self._transit_rect = None
            return
        t_ing = self._as_dt(self._transit.get("ingress"))
        t_egr = self._as_dt(self._transit.get("egress"))
        if t_ing is None or t_egr is None:
            self._transit_rect = None
            return
        start = _utc(self._samples["start"])
        p_ing = (t_ing - start).total_seconds() / 3600.0
        p_egr = (t_egr - start).total_seconds() / 3600.0
        if p_ing > p_egr:
            p_ing, p_egr = p_egr, p_ing
        x0, y0 = self._to_scene(p_ing, 0.0)
        x1, y1 = self._to_scene(p_egr, 90.0)
        self._transit_rect = self._add_band(
            min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0),
            _hex_alpha(palette.ACCENT, 46), "transit", _Z_TRANSIT)
        self._add_band_label(self.tr("tránsito"),
                             (x0 + x1) / 2.0, y1 + _FONT_LABEL)

    # ------------------------------------------------- hover --------------

    def _hover(self, sx, sy):
        # The canvas calls this with scene coords. We answer:
        #   * "on the target curve" -> "HH:MM UTC · alt NN° · az MM°"
        #   * "inside the safe band"-> "de HH:MM a HH:MM · empezar hasta HH:MM"
        # and None (hit=False) elsewhere.
        if not self._samples or not self._target_pts:
            return (False, None)
        rel, alt = self._to_data(sx, sy)
        # nearest index on the curve (rel is strictly increasing) — a binary
        # search would be nicer but the sample count is small (~60 typical)
        best = None
        for i, (r, a) in enumerate(zip(self._samples["rel"], self._samples["alt"])):
            if best is None or abs(r - rel) < abs(best[0] - rel):
                best = (r, a, i)
        if best is None:
            return (False, None)
        br, ba, bi = best
        # distance from the cursor to the nearest curve sample, in scene units
        p_scene = self._to_scene(br, ba)
        d2 = (p_scene[0] - sx) * (p_scene[0] - sx) + (p_scene[1] - sy) * (p_scene[1] - sy)
        tol = _HALF * _HIT_TOL
        # if the cursor is inside the safe band, prefer that reading (a
        # session-planning tooltip beats the raw-curve reading at the same spot)
        if self._safe_rect is not None:
            if self._safe_rect.rect().contains(QPointF(sx, sy)):
                t0, t1 = self._safe_window
                bt = self._best_time
                tail = (self.tr(" · empezar hasta {t}").format(
                    t=f"{bt:%H:%M}Z") if bt else "")
                txt = (self.tr("de {a} a {b}").format(
                    a=f"{t0:%H:%M}", b=f"{t1:%H:%M}") + tail)
                return (True, txt)
        if d2 > tol * tol:
            return (False, None)
        t = self._samples["time"][bi]
        adeg = self._samples["alt"][bi]
        azdg = self._samples["azim"][bi]
        head = f"{self._obj_name}: " if self._obj_name else ""
        txt = (f"{head}{t:%H:%M} UTC · "
               f"alt {adeg:.1f}° · az {azdg:.0f}°")
        return (True, txt)

    # ------------------------------------------------- click --------------

    def _on_scene_clicked(self, sc):
        # The canvas has decided this was a click (not a drag) and hands us
        # the scene coords. If that point fell inside the safe-window band
        # we fire best_time_clicked, so the GUI can snap to the start-by time.
        # @args: sc - QPointF in scene coordinates (ChartView scene_clicked).
        if self._safe_rect is None:
            return
        if self._safe_rect.rect().contains(sc):
            self.best_time_clicked.emit(self._best_time)


class TransitChart(SkyChart):
    """A SkyChart that additionally shades the transit window.

    The parent SkyChart already exposes the same API (set_target(…,
    transit={…})) and draws the band in _draw_transit(); this subclass just
    exists as the concrete name the GUI/panel wants to instantiate when the
    object is an exoplanet.
    """
