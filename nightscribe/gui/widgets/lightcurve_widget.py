############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - interactive SN light-curve widget (Track B, B4, ADR-029)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The vector, interactive SN light-curve chart for the GUI (ADR-029).

`LightCurveChart` composes a `ChartView` and plots magnitude vs date with
an inverted Y axis (fainter = up on screen), one series per filter, error
bars and an optional schematic template overlay. The hover probe shows the
date, magnitude, filter and source at the point under the cursor.

The data comes from `core/followup.list_points`; the template from
`core/sn_templates`. The widget and the matplotlib PNG export
(`viz/lightcurve_view.py`) share the same data model so they can never drift.
"""

import logging
import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QPen, QFont, QPolygonF)
from PySide6.QtWidgets import (QWidget, QVBoxLayout,
                                QGraphicsEllipseItem, QGraphicsLineItem,
                                QGraphicsPolygonItem, QGraphicsRectItem,
                                QGraphicsSimpleTextItem)

import numpy as np

from ...core import sn_templates
from ...viz import palette
from .base_chart import ChartView

# Scene z-order (higher = drawn on top)
_Z_GRID = 0.0
_Z_SYSTEM = 0.5
_Z_TEMPLATE = 1.0
_Z_LINK = 1.5
_Z_DATA = 2.0
_Z_ERROR = 3.0
_Z_LABEL = 4.0

# Font sizes in scene units
_FONT_TICK = 18
_FONT_LABEL = 22

# Scene half-extent: the data area is always this wide/tall, independent of
# the data's actual span. The mapping scales the data into this box.
_HALF = 500.0

# Robust window (quality plan, phase A): the magnitude scale is set by the
# CORE of the data (median ± K robust sigmas), never by min/max, so one
# anomalous frame or one badly calibrated night cannot flatten the curve
# into a line. The points outside stay on the chart, anchored to the edge.
_ROBUST_K = 6.0
_MIN_WINDOW = 0.05          # mag: never a degenerate window
_PAD = 0.10                 # 10 % of the window as air

# A bar taller than this share of the half-height carries no information at
# the plot's scale (a bad calibration says so in the legend, not by
# painting over everything) and is clipped.
_BAR_CLIP = 0.12


def _series_style(src_class):
    # @args: src_class - "manual" | "quicklook" | "survey" | "detrend"
    # @return: (colour or None for "use the filter colour", filled bool)
    if src_class == "survey":
        return "#8a90a6", False
    if src_class == "quicklook":
        return None, False
    if src_class == "detrend":
        return palette.MUTED, False
    return None, True


def _point_style(p):
    # @args: p - a photometry point dict
    # @return: (QColor, filled) for this point (B4 source styles;
    #          mirrors _series_style in viz/lightcurve_view.py)
    src = p.get("source") or "manual"
    if src.startswith("survey"):
        src_class = "survey"
    elif src == "quicklook":
        src_class = "quicklook"
    elif src == "detrend":
        src_class = "detrend"
    else:
        src_class = "manual"
    colour, filled = _series_style(src_class)
    if colour is None:
        colour = palette.ACCENT if not p.get("filter") \
            else _FILTER_COLOURS.get(p.get("filter"), palette.ACCENT)
    return QColor(colour), filled

# Quality-gate colour: a flagged point keeps its place on the curve but is
# drawn as a hollow diamond, never hidden (ADR-048, T7).
FLAG_COLOUR = "#e0a030"

# Not every flag means the same thing. A DATA flag says the point itself is
# suspect (the star saturated, a cosmic ray, the focus blew up, the frame
# could not be aligned); a CAVEAT flag says the point is fine but its
# calibration leans on few comparison stars. The chart marks the first with
# the hollow diamond and the second with a faint edge, so a series with a
# thin comp set does not read as a series with 200 bad points.
# The flag classification lives in the engine (quality plan, phase A): the
# chart and the analysis must read the same thing.
from ...core.series_measure import CAVEAT_FLAGS, DATA_FLAGS  # noqa: E402


def _flags_split(flags):
    # @args: flags - the point's flag list
    # @return: (data_flags, caveat_flags) - anything unknown counts as data
    if not flags:
        return [], []
    data = [f for f in flags if f in DATA_FLAGS]
    caveat = [f for f in flags if f in CAVEAT_FLAGS]
    other = [f for f in flags if f not in DATA_FLAGS and f not in CAVEAT_FLAGS]
    return data + other, caveat


def _fmt_tick(value, span):
    # A tick label with as many decimals as the span needs (quality plan,
    # A1): on a 0.12 mag night "12.5" five times is noise, "12.53" is a
    # reading, and the same for the MJD axis.
    # @args: value - the tick value, span - the axis span
    # @return: the formatted label
    span = abs(float(span)) if span else 0.0
    decimals = 3
    if span <= 0.0:
        decimals = 3
    elif span >= 100.0:
        decimals = 0
    elif span >= 10.0:
        decimals = 1
    elif span >= 1.0:
        decimals = 2
    elif span < 0.01:
        decimals = 4
    return f"{value:.{decimals}f}"


# Distinct colours per filter (matching the PNG export)
_FILTER_COLOURS = {
    "Clear": palette.ACCENT, "None": palette.ACCENT,
    "V": palette.ACCENT2, "R": palette.ACCENT2,
    "B": "#6a9fd8", "I": "#d8a06a", "NIR": "#d86a9f",
}


class LightCurveChart(ChartView):
    # A QGraphicsView that plots SN photometry points vs date with an
    # inverted magnitude axis, per-filter series, error bars and an
    # optional template overlay. Hover shows date/mag/filter/source.

    enlarge_requested = Signal()   # a click (or double-click) wants a big view

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []
        self._sn_type = None
        self._peak_mjd = None
        self._peak_mag = None
        self._fold_p = None      # fold period in days (None = date axis)
        self._epoch = None
        self._schematic = None
        self._bounds = None   # (x_min, x_max, mag_min, mag_max)
        self._tpl_visible = True   # template overlay: ON by default
        self._link = True          # series linking lines: ON by default
        # quality plan, phase A: the scale is robust by default, the bars
        # are the point's OWN error (the systematic goes to a band) and
        # the flagged points stay visible unless the observer hides them
        self._robust = True
        self._show_errors = True
        self._hide_flagged = False
        self._clip_note = 0        # bars clipped by _BAR_CLIP on this draw
        self.set_hover_probe(self._probe)

    def mouseDoubleClickEvent(self, event):
        # A double-click asks the host for a big view (the base has no
        # fit-on-double-click, so nothing else is lost).
        if event.button() == Qt.LeftButton:
            self.enlarge_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def filter_label(self, filt):
        # @args: filt - filter name (None/"Clear"/"None" = the generic band)
        # @return: the human band label for the legend and the probe
        if not filt or filt in ("Clear", "None"):
            return self.tr("No filter")
        return filt

    def source_label(self, source):
        # @args: source - the point's source (manual|paste|file|quicklook|
        #        survey:ztf)
        # @return: the human source label for the legend and the probe
        source = source or "manual"
        if source.startswith("survey"):
            return self.tr("Survey · ALeRCE/ZTF")
        if source == "quicklook":
            return self.tr("Quick-look · indicative")
        if source == "measure":
            return self.tr("Series · measured")
        if source == "detrend":
            return self.tr("Series · detrended")
        if source == "paste":
            return self.tr("Pasted data")
        if source == "file":
            return self.tr("From file")
        return self.tr("Manual entry")

    def set_template_visible(self, on):
        # @args: on - draw the template/schematic overlay or not
        # @return: None. The axis bounds do not move on toggle: the
        #          template is a reference, and its mags are already in
        #          the data range at draw time.
        self._tpl_visible = bool(on)
        self._build_scene()
        self.fit_to_scene()

    def set_link_lines(self, on):
        # @args: on - connect each series' points with a line or not
        self._link = bool(on)
        self._build_scene()
        self.fit_to_scene()

    def set_robust(self, on):
        # @args: on - the magnitude window follows the CORE of the data
        #        (median ± K robust sigmas) instead of min/max, so an
        #        anomalous point cannot flatten the curve. Off shows the
        #        whole spread.
        self._robust = bool(on)
        self._compute_bounds()
        self._build_scene()
        self.fit_to_scene()

    def is_robust(self):
        # @return: whether the magnitude scale is robust
        return self._robust

    def set_errors_visible(self, on):
        # @args: on - draw the points' own error bars and the calibration
        #        band. Off is for judging the SHAPE of a small-amplitude
        #        curve without the bars in the way.
        self._show_errors = bool(on)
        self._build_scene()
        self.fit_to_scene()

    def is_errors_visible(self):
        # @return: whether the error bars are drawn
        return self._show_errors

    def set_hide_flagged(self, on):
        # @args: on - hide the flagged points to judge the clean curve.
        #        The default is to SHOW them: a flag marks and never
        #        deletes (ADR-048, T7), so hiding is an explicit act.
        self._hide_flagged = bool(on)
        self._compute_bounds()
        self._build_scene()
        self.fit_to_scene()

    def is_hiding_flagged(self):
        # @return: whether the flagged points are hidden
        return self._hide_flagged

    def n_flagged(self):
        # @return: (data flags, calibration caveats) counts
        data = sum(1 for p in self._points if _flags_split(p.get("flags"))[0])
        caveat = sum(1 for p in self._points
                     if _flags_split(p.get("flags"))[1])
        return data, caveat

    def set_data(self, points, sn_type=None, peak_mjd=None, peak_mag=None,
                 fold_period_d=None, epoch_mjd=None, schematic=None):
        # @args: points - list of {mjd, mag, err, filter, source} dicts,
        #        sn_type - for the template overlay, peak_mjd/mag - to align
        #        it, fold_period_d - pulsation period in days: folds the x
        #        axis to phase 0..2 (two cycles, ADR-034; kind-agnostic so
        #        future long-period variables reuse it, H-n), epoch_mjd -
        #        phase-0 reference (default: the first point), schematic -
        #        [(phase, mag)] reference curve drawn dashed (e.g. the
        #        hads.sawtooth_template — never real data)
        # Replaces the current data and rebuilds the scene.
        self._points = sorted(points, key=lambda p: p["mjd"])
        self._sn_type = sn_type
        self._peak_mjd = peak_mjd
        self._peak_mag = peak_mag
        self._fold_p = fold_period_d
        self._epoch = epoch_mjd
        self._schematic = schematic
        if fold_period_d and self._points and self._epoch is None:
            self._epoch = self._points[0]["mjd"]
        self._compute_bounds()
        self._build_scene()
        self.fit_to_scene()

    def _phase(self, mjd):
        # @return: the 0..1 phase of an epoch in fold mode
        return ((mjd - self._epoch) / self._fold_p) % 1.0

    def _xs(self, p):
        # @args: p - a photometry point dict
        # @return: the data-x values to draw it at: one mjd normally, the
        #          phase twice (cycle 0 and cycle 1) when folding
        if self._fold_p:
            ph = self._phase(p["mjd"])
            return (ph, ph + 1.0)
        return (p["mjd"],)

    def _compute_bounds(self):
        # Finds the data extent (x and mag) for the scene mapping. The
        # magnitude window is the data's CORE (median ± K robust sigmas)
        # when the scale is robust, so an anomalous point cannot set it;
        # otherwise the plain min/max. Falls back to a small default if
        # there's no data.
        if not self._points:
            self._bounds = (0, 1, 10, 20)
            return
        mags = [p["mag"] for p in self._points if p["mag"] is not None]
        if self._schematic:
            mags += [m for _ph, m in self._schematic]
        if not mags:
            self._bounds = (0, 1, 10, 20)
            return
        lo, hi = self._mag_window(mags)
        if self._fold_p:
            self._bounds = (0.0, 2.0, lo, hi)
            return
        mjds = [p["mjd"] for p in self._points if p["mjd"] is not None]
        self._bounds = (min(mjds), max(mjds), lo, hi)
        # auto-peak: brightest point (lowest mag)
        if self._peak_mjd is None or self._peak_mag is None:
            brightest = min((p for p in self._points
                             if p["mag"] is not None),
                            key=lambda p: p["mag"])
            self._peak_mjd = self._peak_mjd or brightest["mjd"]
            self._peak_mag = self._peak_mag or brightest["mag"]

    def _mag_window(self, mags):
        # The magnitude window of the chart (quality plan, A1).
        # @args: mags - the finite magnitudes on the chart
        # @return: (lo, hi) of the window, padded
        vals = np.asarray(mags, dtype=float)
        if not self._robust:
            lo, hi = float(vals.min()), float(vals.max())
        else:
            med = float(np.median(vals))
            mad = 1.4826 * float(np.median(np.abs(vals - med)))
            if mad > 0.0:
                lo, hi = med - _ROBUST_K * mad, med + _ROBUST_K * mad
                # the core is intersected with the data: a robust window
                # cannot be WIDER than the curve itself
                lo = max(lo, float(vals.min()))
                hi = min(hi, float(vals.max()))
            else:
                lo, hi = float(vals.min()), float(vals.max())
        if hi - lo < _MIN_WINDOW:
            centre = 0.5 * (lo + hi)
            lo, hi = centre - _MIN_WINDOW / 2.0, centre + _MIN_WINDOW / 2.0
        pad = (hi - lo) * _PAD
        return lo - pad, hi + pad

    def _map_x(self, mjd):
        # @args: mjd - float
        # @return: scene x coordinate
        lo, hi, _, _ = self._bounds
        if hi == lo:
            return 0.0
        return -_HALF + (mjd - lo) / (hi - lo) * 2 * _HALF

    def _map_y(self, mag):
        # @args: mag - float
        # @return: scene y coordinate (inverted: brighter = lower y)
        _, _, lo, hi = self._bounds
        if hi == lo:
            return 0.0
        return _HALF - (mag - lo) / (hi - lo) * 2 * _HALF

    def _build_scene(self):
        self.clear()
        b = self._bounds
        self.set_scene_rect(-_HALF - 60, -_HALF - 50,
                             2 * _HALF + 120, 2 * _HALF + 100)
        # grid + axes
        self._draw_grid()
        # series linking (like the PNG export): solid line for the
        # observer's own points, dashed for quick-look and survey
        if self._link:
            self._draw_link_lines()
        # template overlay: the schematic reference curve in fold mode
        # (never real data), the SN type template otherwise. Togglable
        # from the Follow-up tab without touching the axis bounds.
        has_overlay = False
        if self._tpl_visible and self._fold_p and self._schematic:
            pen = QPen(QColor(palette.MUTED), 1.0, Qt.DashLine)
            for shift in (0.0, 1.0):
                path_pts = [(self._map_x(ph + shift), self._map_y(m))
                            for ph, m in self._schematic]
                for i in range(len(path_pts) - 1):
                    line = QGraphicsLineItem(path_pts[i][0], path_pts[i][1],
                                            path_pts[i + 1][0],
                                            path_pts[i + 1][1])
                    line.setPen(pen)
                    line.setZValue(_Z_TEMPLATE)
                    self.add_item(line)
            has_overlay = True
        if self._tpl_visible:
            tpl = None if self._fold_p else (
                sn_templates.template(
                    self._sn_type) if self._sn_type else None)
        else:
            tpl = None
        if tpl and self._peak_mjd is not None and self._peak_mag is not None:
            pen = QPen(QColor(palette.MUTED), 1.0,Qt.DashLine)
            path_pts = []
            for d, dm in tpl:
                x = self._map_x(self._peak_mjd + d)
                y = self._map_y(self._peak_mag + dm)
                path_pts.append((x, y))
            for i in range(len(path_pts) - 1):
                line = QGraphicsLineItem(path_pts[i][0], path_pts[i][1],
                                        path_pts[i + 1][0], path_pts[i + 1][1])
                line.setPen(pen)
                line.setZValue(_Z_TEMPLATE)
                self.add_item(line)
            has_overlay = True
        # data points (drawn twice in fold mode: cycle 0 and cycle 1), the
        # flagged ones as hollow diamonds, the bars clipped and the
        # calibration systematic as a band (quality plan, phase A)
        flagged_seen, caveat_seen, syst, syst_all = self._draw_points()
        # legend: one entry per (filter, source) series the data has
        self._add_legend(has_overlay, flagged_seen, syst, caveat_seen,
                         syst_all)

    def _systematic(self, p):
        # The part of a point's error that is NOT its own photons: the
        # zero point and the flat (quality plan, A3). It is common to the
        # whole night, so drawing it as N giant bars hides the curve
        # instead of informing; the chart puts it in a band.
        # @args: p - a photometry point dict
        # @return: the systematic sigma in mag, or None
        total = p.get("err")
        inner = p.get("err_internal")
        if total is None:
            return None
        if inner is None:
            return float(total)
        var = float(total) ** 2 - float(inner) ** 2
        return math.sqrt(var) if var > 0.0 else 0.0

    def _bar_error(self, p):
        # The half-height of the point's bar: its OWN error when the CCD
        # equation could be evaluated, else the total (clipped by the
        # caller).
        # @args: p - a photometry point dict
        # @return: sigma in mag, or None
        if p.get("err_internal") is not None:
            return float(p["err_internal"])
        return None if p.get("err") is None else float(p["err"])

    def _draw_systematic_bands(self):
        # One translucent band per series, centred on the series' median
        # magnitude and as tall as its systematic: the honest way to show
        # "your calibration is worth ±0.17" without 244 giant bars.
        # A band taller than half the window would fill the panel and hide
        # the very curve it belongs to, so it is NOT drawn: the legend
        # says the number instead, which is the useful part.
        # @return: (tallest_drawn, largest_seen) in mag, either may be None
        b = self._bounds
        span = b[3] - b[2]
        if span <= 0.0:
            return None, None
        by_series = {}
        for p in self._points:
            if p.get("mag") is None:
                continue
            by_series.setdefault(
                (p.get("filter"), p.get("source") or "manual"), []).append(p)
        tallest, largest = None, None
        for (_band, _src), pts in by_series.items():
            syss = [self._systematic(p) for p in pts]
            syss = [s for s in syss if s is not None]
            if not syss:
                continue
            sys = float(np.median(syss))
            if sys < 0.005:                    # nothing worth a band
                continue
            largest = sys if largest is None else max(largest, sys)
            if sys > span / 2.0:
                continue
            tallest = sys if tallest is None else max(tallest, sys)
            ys = [self._map_y(p["mag"]) for p in pts]
            top, bottom = min(ys), max(ys)
            half = sys / span * 2 * _HALF
            rect = QGraphicsRectItem(-_HALF, top - half, 2 * _HALF,
                                      (bottom - top) + 2 * half)
            fill = QColor(palette.MUTED)
            fill.setAlpha(46)
            rect.setBrush(QBrush(fill))
            rect.setPen(QPen(Qt.NoPen))
            rect.setZValue(_Z_SYSTEM)
            self.add_item(rect)
        return tallest, largest

    def _draw_points(self):
        # Every point of the curve: the ones with a DATA flag as hollow
        # diamonds (never hidden, ADR-048 T7), the ones that only carry a
        # calibration caveat with a faint amber edge, the rest plain, each
        # with its own error bar clipped to the plot and anchored to the
        # edge when it falls outside the robust window (A1/A3/A4).
        # @return: (flagged_seen, caveat_seen, tallest, largest)
        b = self._bounds
        span = b[3] - b[2]
        self._clip_note = 0
        self._over_note = 0
        tallest = largest = None
        if self._show_errors and any(self._systematic(p) is not None
                                     for p in self._points):
            tallest, largest = self._draw_systematic_bands()
        flagged_seen = caveat_seen = False
        for p in self._points:
            if p.get("mag") is None:
                continue
            data_flags, caveat = _flags_split(p.get("flags"))
            flagged = bool(data_flags)
            if flagged and self._hide_flagged:
                continue
            for xv in self._xs(p):
                x = self._map_x(xv)
                y = self._map_y(p["mag"])
                y_draw, off = (y, 0)
                if y > _HALF:
                    y_draw, off = _HALF - 10.0, 1
                elif y < -_HALF:
                    y_draw, off = -_HALF + 10.0, -1
                if off:
                    self._over_note += 1
                colour, filled = _point_style(p)
                r = 6.0
                if flagged:
                    poly = QPolygonF([
                        QPointF(x, y_draw - r), QPointF(x + r, y_draw),
                        QPointF(x, y_draw + r), QPointF(x - r, y_draw)])
                    dot = QGraphicsPolygonItem(poly)
                    dot.setBrush(QBrush(QColor(palette.BG)))
                    dot.setPen(QPen(QColor(FLAG_COLOUR), 1.8))
                    flagged_seen = True
                elif off:
                    # outside the robust window: a small caret anchored to
                    # the edge, so nothing disappears from the chart
                    poly = QPolygonF([
                        QPointF(x, y_draw + off * 10.0), QPointF(x - 7, y_draw),
                        QPointF(x + 7, y_draw)])
                    dot = QGraphicsPolygonItem(poly)
                    dot.setBrush(QBrush(palette.DANGER))
                    dot.setPen(QPen(QColor(palette.DANGER), 1.0))
                else:
                    dot = QGraphicsEllipseItem(x - r, y - r, r * 2, r * 2)
                    dot.setBrush(QBrush(colour if filled
                                        else QColor(palette.BG)))
                    pen = QPen(colour, 1.5)
                    if caveat:
                        # a caveat, not a suspect point: the marker and a
                        # faint amber edge, so the shape of the curve is
                        # not drowned in warnings
                        pen = QPen(QColor(FLAG_COLOUR), 1.0)
                        caveat_seen = True
                    dot.setPen(pen)
                dot.setZValue(_Z_DATA)
                self.add_item(dot)
                err = self._bar_error(p) if self._show_errors else None
                if err is not None and span > 0.0:
                    ey = err / span * 2 * _HALF
                    clip = _BAR_CLIP * 2 * _HALF
                    if ey > clip:
                        ey = clip
                        self._clip_note += 1
                    bar = QGraphicsLineItem(x, y_draw - ey, x, y_draw + ey)
                    bar.setPen(QPen(colour, 1.0))
                    bar.setZValue(_Z_ERROR)
                    self.add_item(bar)
        return flagged_seen, caveat_seen, tallest, largest

    def _link_pen(self, source, band):
        # @args: source - the series' source, band - the series' filter
        # @return: the QPen of the series' linking line: the series colour,
        #          dashed for quick-look and survey (mirrors the PNG)
        colour, _filled = _point_style(
            {"filter": band, "source": source, "mjd": 0, "mag": 0})
        pen = QPen(colour, 1.4)
        if (source or "manual").startswith("survey") or source == "quicklook":
            pen.setStyle(Qt.DashLine)
        return pen

    def _draw_link_lines(self):
        # Connects the points of each (filter, source) series, like the PNG
        # export. In fold mode each cycle is linked within itself, so no
        # seam-crossing artefacts.
        by_series = {}
        for p in self._points:
            by_series.setdefault(
                (p.get("filter") or "Clear", p.get("source") or "manual"),
                []).append(p)
        for (band, src), pts in by_series.items():
            if len(pts) < 2:
                continue
            pen = self._link_pen(src, band)
            copies = {}
            for p in pts:
                for k, xv in enumerate(self._xs(p)):
                    copies.setdefault(k, []).append(
                        (self._map_x(xv), self._map_y(p["mag"])))
            for seq in copies.values():
                seq.sort(key=lambda xy: xy[0])
                for i in range(len(seq) - 1):
                    line = QGraphicsLineItem(seq[i][0], seq[i][1],
                                              seq[i + 1][0], seq[i + 1][1])
                    line.setPen(pen)
                    line.setZValue(_Z_LINK)
                    self.add_item(line)

    def _add_legend(self, has_template, flagged=False, systematic=None,
                    caveat=False, systematic_all=None):
        # @args: has_template - whether the schematic overlay is drawn,
        #        flagged - whether any point carries a DATA flag,
        #        systematic - the tallest calibration band drawn (mag),
        #        caveat - whether any point leans on few comps,
        #        systematic_all - the largest systematic seen, band or not
        # Draws a compact legend in the bottom-right of the data area
        # (same corner as sky_widget); entries mirror the PNG export so
        # the two renderers cannot disagree (B4).
        from PySide6.QtGui import QFontMetricsF
        entries = []
        if has_template:
            entries.append(
                (self.tr("schematic (sawtooth)") if self._fold_p
                 else self.tr("Typical template"), QColor(palette.MUTED)))
        if flagged:
            entries.append((self.tr("flagged (quality gate)"),
                            QColor(FLAG_COLOUR)))
        if caveat:
            entries.append((self.tr("few comps (calibration leans on few)"),
                            QColor(FLAG_COLOUR)))
        if self._hide_flagged:
            entries.append((self.tr("flagged points hidden"),
                            QColor(palette.MUTED)))
        if systematic_all and not systematic:
            # the systematic is wider than the window: draw nothing (it
            # would fill the panel) and SAY it
            entries.append((self.tr("calibration ±{0:.3f} (wider than this "
                                    "window)").format(systematic_all),
                            QColor(palette.MUTED)))
        elif systematic:
            entries.append((self.tr("calibration systematic ±{0:.3f}")
                            .format(systematic), QColor(palette.MUTED)))
        if self._clip_note:
            entries.append((self.tr("{0} bars clipped (error ≫ scale)")
                            .format(self._clip_note),
                            QColor(palette.MUTED)))
        if self._over_note:
            entries.append((self.tr("{0} points off scale").format(
                self._over_note), QColor(palette.DANGER)))
        # one entry per (band, source) series: human labels, so the
        # observer sees "Pasted data", "From file", "Survey · ALeRCE/ZTF"
        seen = set()
        for p in self._points:
            src = p.get("source") or "manual"
            key = (p.get("filter"), src)
            if key in seen:
                continue
            seen.add(key)
            text = (self.filter_label(p.get("filter"))
                    + " · " + self.source_label(src))
            colour, _filled = _point_style(p)
            entries.append((text, colour))
        if not entries:
            return
        fmt = QFont(self._label_font) if hasattr(self, "_label_font") else QFont()
        if not hasattr(self, "_label_font"):
            fmt.setPointSize(_FONT_TICK)
        fm = QFontMetricsF(fmt)
        rows = [(text, color, fm.horizontalAdvance(text))
                for text, color in entries]
        text_w = max(row[2] for row in rows)
        sw = 60            # swatch length
        gap = 16           # swatch -> text gap
        pad = 16           # backdrop padding
        row_h = 44         # vertical pitch between rows
        right = _HALF - 12
        text_x = right - text_w
        sw_x = text_x - gap - sw
        top = _HALF - 12 - row_h * len(entries)
        for i, (text, color, _w) in enumerate(rows):
            cy = top + i * row_h + row_h / 2.0
            line = QGraphicsLineItem(sw_x, cy, sw_x + sw, cy)
            line.setPen(QPen(color, 1.8))
            line.setZValue(_Z_LABEL)
            self.add_item(line)
            lb = QGraphicsSimpleTextItem(text)
            lb.setBrush(QBrush(QColor(palette.FG)))
            lb.setFont(fmt)
            lb.setPos(text_x, cy - fm.height() / 2.0)
            lb.setZValue(_Z_LABEL)
            self.add_item(lb)
        # soft dark backdrop above the grid/data, below the swatches
        x0 = sw_x - pad
        y0 = top - pad
        w = (right - sw_x) + 2 * pad
        h = row_h * len(entries) + 2 * pad
        bg = QGraphicsRectItem(x0, y0, w, h)
        bg.setBrush(QBrush(QColor(11, 13, 23, 210)))
        bg.setPen(Qt.NoPen)
        bg.setZValue(_Z_LABEL - 0.5)
        self.add_item(bg)

    def _draw_grid(self):
        # Simple grid: a few date ticks on X, a few mag ticks on Y (inverted).
        # The number of decimals follows the SPAN: a 0.12 mag night needs
        # three of them, and the old fixed one decimal made every label
        # read the same ("60297.8", "12.5") on a small-amplitude curve
        # (quality plan, phase A).
        b = self._bounds
        x_span = b[1] - b[0]
        y_span = b[3] - b[2]
        pen = QPen(QColor(palette.MUTED), 0.8)
        pen.setStyle(Qt.DotLine)
        # X grid lines (5 divisions)
        for i in range(6):
            x = -_HALF + i * 2 * _HALF / 5
            line = QGraphicsLineItem(x, -_HALF, x, _HALF)
            line.setPen(pen)
            line.setZValue(_Z_GRID)
            self.add_item(line)
            # tick label (MJD, or phase 0..2 in fold mode)
            xv = b[0] + x_span * i / 5
            lbl = QGraphicsSimpleTextItem(_fmt_tick(xv, x_span))
            lbl.setPos(x - 20, _HALF + 10)
            lbl.setBrush(QBrush(QColor(palette.MUTED)))
            f = QFont(); f.setPointSize(_FONT_TICK)
            lbl.setFont(f)
            lbl.setZValue(_Z_LABEL)
            self.add_item(lbl)
        # Y grid lines (4 divisions)
        for i in range(5):
            y = _HALF - i * 2 * _HALF / 4
            line = QGraphicsLineItem(-_HALF, y, _HALF, y)
            line.setPen(pen)
            line.setZValue(_Z_GRID)
            self.add_item(line)
            mag = b[2] + y_span * i / 4
            lbl = QGraphicsSimpleTextItem(_fmt_tick(mag, y_span))
            lbl.setPos(-_HALF - 60, y - 8)
            lbl.setBrush(QBrush(QColor(palette.MUTED)))
            f = QFont(); f.setPointSize(_FONT_TICK)
            lbl.setFont(f)
            lbl.setZValue(_Z_LABEL)
            self.add_item(lbl)

    def _probe(self, sx, sy):
        # @args: sx, sy - scene coordinates
        # @return: (hit, text) for the nearest data point
        if not self._points:
            return False, None
        best = None
        best_dist = 1e9
        for p in self._points:
            if p.get("mag") is None:
                continue
            for xv in self._xs(p):
                dx = self._map_x(xv) - sx
                dy = self._map_y(p["mag"]) - sy
                dist = dx * dx + dy * dy
                if dist < best_dist:
                    best_dist = dist
                    best = p
        if best is None or best_dist > 2500:   # ~25 scene units radius
            return False, None
        lines = []
        if self._fold_p:
            lines.append(f"phase {self._phase(best['mjd']):.2f}")
        lines += [
            f"MJD {best['mjd']:.2f}",
            f"mag {best['mag']:.2f}",
            f"[{self.filter_label(best.get('filter'))}]",
        ]
        if best.get("source"):
            lines.append(f"({self.source_label(best['source'])})")
        if best.get("err") is not None:
            lines.append(f"±{best['err']:.3f}")
        if best.get("err_internal") is not None:
            lines.append(self.tr("photons ±{0:.4f}").format(
                best["err_internal"]))
            sys_err = self._systematic(best)
            if sys_err:
                lines.append(self.tr("calibration ±{0:.3f}").format(
                    sys_err))
        if best.get("n_comps") is not None:
            lines.append(self.tr("{0} comps").format(best["n_comps"]))
        if best.get("flags"):
            lines.append("⚠ " + ", ".join(best["flags"]))
        return True, lines


def make_lightcurve_widget(parent=None, points=None, sn_type=None):
    # @args: parent - QWidget parent, points/sn_type - optional initial data
    # @return: a QWidget wrapping a LightCurveChart in a layout
    w = QWidget(parent)
    w.setLayout(QVBoxLayout())
    chart = LightCurveChart()
    w.layout().addWidget(chart)
    if points:
        chart.set_data(points, sn_type=sn_type)
    w._chart = chart
    return w
