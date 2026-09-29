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
                                QGraphicsSimpleTextItem, QGraphicsView)

import numpy as np

from ...core import sn_templates, ticks
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

# Font sizes in PIXELS, not in scene units: the scene is fitted to the
# widget, so a size in scene units grows and shrinks with the panel and the
# labels of a maximized window come out huge. These are the sizes the
# reader actually sees, and _sync_geometry converts them.
_FONT_TICK_PX = 12
_FONT_LEGEND_PX = 11
_LEGEND_SWATCH = 24.0     # the colour line that stands for a series
_LEGEND_PITCH = 20.0      # vertical distance between legend rows

# Short month names, because strftime follows the SYSTEM locale: a chart in
# an English interface would print "dic" for December on a Spanish machine,
# and a figure that mixes languages is a figure nobody trusts.
_MONTHS = {
    "es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep",
           "oct", "nov", "dic"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
           "Oct", "Nov", "Dec"),
}

# Scene half-height: the plot's height is fixed in scene units and the data
# is mapped into the box (its width follows the WINDOW, see _sync_geometry),
# so the two axes always share one scale and an error bar stays an error bar.
_HALF = 500.0

# The room the labels need around the plot, in scene units. They are
# generous on purpose (the observer asked for the texts to breathe) and the
# bottom is the widest side, because a date like "20 Sep 2026" is a long
# label under a tick.
_PAD_LEFT = 124.0
_PAD_RIGHT = 34.0
_PAD_TOP = 66.0
_PAD_BOTTOM = 108.0

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

# The axis shows ONE kind of magnitude at a time, and that is not a matter
# of taste: an absolute magnitude (12.34) and a differential one (the
# detrended curve, which is "mag - trend", around 0) are DIFFERENT
# quantities. Drawing both on one axis is what produced a window of twelve
# magnitudes for a curve of tenths, with ticks reading 2, 4, 6 ... 14: the
# variation vanished into a straight line and the numbers meant nothing.
# Our group's own tool splits the two for exactly this reason.
#
#   * "calibrated": the magnitudes the calibration produced. The detrended
#     curve does NOT belong here, because it counts from another level
#     (the night's own trend), and drawing it would force the axis open;
#   * "differential": everything referred to a STATED level, so a tenth of
#     a magnitude fills the chart. Raw (mag - median) and detrended (mag -
#     trend) travel together because both are differences now.
MAG_CALIBRATED = "calibrated"
MAG_DIFFERENTIAL = "differential"


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
    point_clicked = Signal(int)    # a click ON a point picked that one

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = []
        self._sn_type = None
        self._peak_mjd = None
        self._peak_mag = None
        self._fold_p = None      # fold period in days (None = date axis)
        self._epoch = None
        self._mag_mode = MAG_CALIBRATED   # which quantity the axis shows
        self._mag_ref = None     # the level a differential axis counts
                                 # from (the measured series' robust median),
                                 # fixed when the data lands
        # The window the observer is looking at, in DATA units, or None for
        # "whatever the data wants" (see zoom_window). This is what the
        # wheel moves: not a magnifying glass over the drawing, a narrower
        # piece of the curve.
        self._window = None
        self._pan_from = None    # viewport point where the current drag began
        self._notes = []         # what the legend no longer says (see notes())
        # the plot's half-WIDTH, in scene units: it follows the shape of the
        # window (see _sync_geometry) while the height stays _HALF, and
        # _scale is how many units a pixel is worth, so the labels can be
        # sized in the pixels the reader actually sees
        self._hx = _HALF
        self._scale = 0.45
        # the window IS the pan: the base's hand-drag would also scroll the
        # view, and two pans fighting over one drag is a bug
        self.setDragMode(QGraphicsView.NoDrag)
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
        self._y_range = None       # (lo, hi) when the observer fixed it
        # the observer's decisions on the curve (phase A): what is out,
        # what is marked as an outlier and what is selected right now
        self._excluded = set()
        self._outlier_idx = set()
        self._selected = set()
        # the chart's own binning and its mean curve (presentation only)
        self._bin_mode = "off"
        self._bin_n = 5
        self._mean_window = 0
        self._has_mean = False
        self._clip_note = 0        # bars clipped by _BAR_CLIP on this draw
        self.set_hover_probe(self._probe)
        # a single left click picks a point when there is one under the
        # cursor, and asks for the big view when there is not
        self.scene_clicked.connect(self._on_scene_click)

    def mouseDoubleClickEvent(self, event):
        # A double-click frames the whole curve again: the quickest way back
        # after wandering into the zoom, and what the group's tool does. The
        # "show me this big" host signal is still emitted, because a chart
        # embedded in a page has no other way to ask for it.
        if event.button() == Qt.LeftButton:
            self.reset_view()
            self.enlarge_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        # The wheel narrows the DATA window around the cursor (V3), which is
        # not the same thing as magnifying the drawing: the labels keep
        # their size, the axis re-rounds its ticks, and a hundredth of a
        # magnitude becomes readable instead of growing into a blur.
        #
        # Shift narrows the time only and Ctrl the magnitude only: reading a
        # small-amplitude curve means asking one of the two axes a question
        # at a time. Embedded in a page the wheel belongs to the page (the
        # base's rule, kept).
        # @args: event - the QWheelEvent
        # @return: None
        if self._embedded or event.angleDelta().y() == 0:
            event.ignore()
            return
        pos = self.mapToScene(event.position().toPoint())
        x0, x1, y0, y1 = self._bounds
        # the fraction of the window under the cursor, the exact inverse of
        # _map_x/_map_y: keeping them in step is the difference between
        # zooming where the cursor is and zooming somewhere else
        fx = (pos.x() + self._hx) / (2 * self._hx) if x1 > x0 else 0.5
        fy = (pos.y() + _HALF) / (2 * _HALF) if y1 > y0 else 0.5
        axes = "both"
        if event.modifiers() & Qt.ShiftModifier:
            axes = "x"
        elif event.modifiers() & Qt.ControlModifier:
            axes = "y"
        # 1.2 per notch: the group's own feel, and it is a good one (a
        # quarter of the window per three notches, easy to land where you
        # wanted)
        factor = 1.2 if event.angleDelta().y() > 0 else 1.0 / 1.2
        self.zoom_window(factor, fx, fy, axes=axes)
        event.accept()

    def mousePressEvent(self, event):
        # The left button starts a WINDOW drag (the base's hand-drag scrolls
        # the view, which is not the same thing and would fight this one).
        #
        # A click also takes the hover tooltip away: the observer is
        # DECIDING something (selecting a point, marking it), and leaving
        # the bubble pinned over the curve makes a decision look like a
        # note that got stuck there (reported as "annotations that stack").
        if event.button() == Qt.LeftButton and not self._embedded:
            self._pan_from = event.position().toPoint()
            self._hide_tooltip()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Dragging slides the window through the data: the frame stays and
        # the curve moves under it. A press without motion is still a click
        # (the base decides that on release, by distance).
        if (self._pan_from is not None and not self._embedded
                and event.buttons() & Qt.LeftButton):
            pos = event.position().toPoint()
            dx = pos.x() - self._pan_from.x()
            dy = pos.y() - self._pan_from.y()
            if dx or dy:
                self._pan_from = pos
                self.pan_window(dx, dy)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._pan_from = None
        super().mouseReleaseEvent(event)

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

    def set_excluded(self, indexes):
        # The points the observer took out of the curve (quality plan, A).
        # They are NOT deleted and they are NOT hidden: they stay on the
        # chart as small grey crosses, so the figure says what was left
        # out. This is the same rule as the engine's flags (T7).
        # @args: indexes - iterable of indexes into the point list
        self._excluded = set(int(i) for i in (indexes or ()))
        self._compute_bounds()
        self._build_scene()
        self.fit_to_scene()

    def excluded(self):
        # @return: the sorted list of excluded indexes
        return sorted(self._excluded)

    def set_outliers(self, indexes):
        # The outlier candidates: marked in red, never removed (phase A).
        # @args: indexes - iterable of indexes into the point list
        self._outlier_idx = set(int(i) for i in (indexes or ()))
        self._build_scene()
        self.fit_to_scene()

    def outliers(self):
        # @return: the sorted list of marked candidates
        return sorted(self._outlier_idx)

    def set_selected(self, indexes):
        # @args: indexes - the points the observer clicked
        self._selected = set(int(i) for i in (indexes or ()))
        self._build_scene()
        self.fit_to_scene()

    def selected(self):
        # @return: the sorted list of selected indexes
        return sorted(self._selected)

    def toggle_selection(self, index):
        # A click on a point adds or removes it from the selection, which
        # is how the observer says "this one".
        # @args: index - the point's index
        # @return: True when it ended selected
        index = int(index)
        if index in self._selected:
            self._selected.discard(index)
            chosen = False
        else:
            self._selected.add(index)
            chosen = True
        self._build_scene()
        self.fit_to_scene()
        return chosen

    def clear_selection(self):
        # @return: None
        self._selected = set()
        self._build_scene()
        self.fit_to_scene()

    def set_bin_mode(self, mode, n=5):
        # The chart's own binning (a presentation choice, not the engine's
        # frame grouping): "off", "frames" or "minutes".
        # @args: mode - "off" | "frames" | "minutes", n - frames or minutes
        self._bin_mode = mode if mode in ("frames", "minutes") else "off"
        self._bin_n = max(1, int(n or 1))
        self._build_scene()
        self.fit_to_scene()

    def set_mean_curve(self, window):
        # @args: window - points of the moving average, or 0/None to hide it
        self._mean_window = max(0, int(window or 0))
        self._build_scene()
        self.fit_to_scene()

    def point_at(self, scene_x, scene_y, radius=25.0):
        # The point under a scene position, or None. The chart uses it to
        # know whether a click meant "this point" or "the empty space".
        # @args: scene_x/scene_y - scene coordinates, radius - hit radius
        # @return: the point's index, or None
        best, best_dist = None, radius * radius
        for idx, p in enumerate(self._points):
            value = self._plot_mag(p)
            if value is None or idx in self._excluded:
                continue
            for xv in self._xs(p):
                dx = self._map_x(xv) - scene_x
                dy = self._map_y(value) - scene_y
                dist = dx * dx + dy * dy
                if dist <= best_dist:
                    best, best_dist = idx, dist
        return best

    def _on_scene_click(self, point):
        # A single left click: on a point it selects it; anywhere else it
        # asks the host for the big view (the old behaviour, kept for the
        # empty space where there is nothing to select).
        idx = self.point_at(point.x(), point.y())
        if idx is None:
            self.enlarge_requested.emit()
            return
        self.toggle_selection(idx)
        self.point_clicked.emit(idx)

    def n_flagged(self):
        # @return: (data flags, calibration caveats) counts
        data = sum(1 for p in self._points if _flags_split(p.get("flags"))[0])
        caveat = sum(1 for p in self._points
                     if _flags_split(p.get("flags"))[1])
        return data, caveat

    def set_data(self, points, sn_type=None, peak_mjd=None, peak_mag=None,
                 fold_period_d=None, epoch_mjd=None, schematic=None,
                 mag_mode=None, keep_window=False):
        # @args: points - list of {mjd, mag, err, filter, source} dicts,
        #        sn_type - for the template overlay, peak_mjd/mag - to align
        #        it, fold_period_d - pulsation period in days: folds the x
        #        axis to phase 0..2 (two cycles, ADR-034; kind-agnostic so
        #        future long-period variables reuse it, H-n), epoch_mjd -
        #        phase-0 reference (default: the first point), schematic -
        #        [(phase, mag)] reference curve drawn dashed (e.g. the
        #        hads.sawtooth_template — never real data), mag_mode -
        #        "calibrated" | "differential" (None keeps the current one):
        #        which quantity the axis shows, see MAG_CALIBRATED above,
        #        keep_window - True keeps the zoom the observer made (a
        #        growing live curve is the same series continuing)
        # Replaces the current data and rebuilds the scene.
        self._points = sorted(points, key=lambda p: p["mjd"])
        self._sn_type = sn_type
        self._peak_mjd = peak_mjd
        self._peak_mag = peak_mag
        self._fold_p = fold_period_d
        self._epoch = epoch_mjd
        self._schematic = schematic
        if mag_mode in (MAG_CALIBRATED, MAG_DIFFERENTIAL):
            self._mag_mode = mag_mode
        if not keep_window:
            # a different series deserves a fresh look, on the whole curve
            self._window = None
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
        # the level first: a differential axis is drawn FROM it, so it has
        # to exist before any value is mapped
        self._mag_ref = self._measure_level()
        mags = [v for v in (self._plot_mag(p) for p in self._points)
                if v is not None]
        if self._schematic:
            mags += [self._axis_mag(m) for _ph, m in self._schematic]
        if not mags:
            # nothing belongs to this axis (e.g. a differential view of a
            # series that has no measured magnitudes): say it plainly
            self._bounds = (0, 1, 10, 20)
            return
        lo, hi = self._mag_window(mags)
        if self._fold_p:
            self._bounds = self._window or (0.0, 2.0, lo, hi)
            return
        mjds = [p["mjd"] for p in self._points if p["mjd"] is not None]
        self._bounds = self._window or (min(mjds), max(mjds), lo, hi)
        if self._window is not None:
            return
        # auto-peak: brightest point (lowest mag)
        if self._peak_mjd is None or self._peak_mag is None:
            brightest = min((p for p in self._points
                             if p["mag"] is not None),
                            key=lambda p: p["mag"])
            self._peak_mjd = self._peak_mjd or brightest["mjd"]
            self._peak_mag = self._peak_mag or brightest["mag"]

    def _mag_window(self, mags):
        # The magnitude window of the chart (quality plan, A1).
        #
        # Three things can decide it, in this order:
        #   1. the observer, when the manual range is on (their eye knows
        #      what they are looking for);
        #   2. the robust core (median ± K robust sigmas), which keeps one
        #      anomalous frame from flattening the whole curve;
        #   3. the plain min/max, when robust mode is off or the scatter
        #      is degenerate.
        # @args: mags - the finite magnitudes on the chart
        # @return: (lo, hi) of the window, padded
        if self._y_range is not None:
            return float(self._y_range[0]), float(self._y_range[1])
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

    def set_mag_mode(self, mode):
        # Switches what the axis shows. It is a real change of QUANTITY, so
        # the whole chart is rebuilt: the window, the ticks and the points
        # move together and the axis says which one you are reading.
        #
        # A manual range written in the old units is dropped, not silently
        # reinterpreted: "12.3 to 12.4" means nothing on a differential
        # axis, and keeping it would rescale the chart into nonsense.
        # @args: mode - "calibrated" | "differential"
        # @return: True when the mode is (now) in force
        if mode not in (MAG_CALIBRATED, MAG_DIFFERENTIAL):
            return False
        if mode == self._mag_mode:
            return True
        self._mag_mode = mode
        self._y_range = None
        self._compute_bounds()
        self._build_scene()
        self.fit_to_scene()
        return True

    def mag_mode(self):
        # @return: "calibrated" | "differential", which the axis shows now
        return self._mag_mode

    def mag_reference(self):
        # The level a differential axis counts from, so a caller (a figure,
        # a report, a label) can SAY it instead of guessing.
        # @return: the reference magnitude, or None without measurements
        return self._mag_ref

    def axis_points(self):
        # The points as THIS axis draws them, for whoever has to render the
        # same curve somewhere else (the exported figure): a copy of every
        # point with "mag" already carrying the mode's value, and without
        # the ones that do not belong to this axis.
        #
        # It exists so the exported figure cannot disagree with the screen:
        # two renderers picking their own window is exactly how a curve of
        # hundredths came out with a 2 to 14 axis.
        # @return: [dict, ...]
        out = []
        for p in self._points:
            value = self._plot_mag(p)
            if value is None:
                continue
            q = dict(p)
            q["mag"] = value
            out.append(q)
        return out

    def _is_differential(self, p):
        # @args: p - a photometry point dict
        # @return: True when its magnitude is a difference, not a measure
        return (p.get("source") or "") == "detrend"

    def _plot_mag(self, p):
        # The magnitude a point is DRAWN at, which is what the axis' mode
        # decides (see MAG_CALIBRATED above).
        #
        # Returning None is as important as returning a number: a point
        # that does not belong to this axis must not be drawn AND must not
        # drag the window with it. That single omission is the difference
        # between a curve of tenths and a twelve-magnitude line.
        # @args: p - a photometry point dict
        # @return: the value for this axis, or None when it does not belong
        if p.get("mag") is None:
            return None
        if self._mag_mode == MAG_DIFFERENTIAL:
            if self._is_differential(p):
                return float(p["mag"])        # already "mag - trend"
            if self._mag_ref is None:
                return None
            return float(p["mag"]) - self._mag_ref
        if self._is_differential(p):
            return None                       # another level: not this axis
        return float(p["mag"])

    def _axis_mag(self, absolute_mag):
        # An ABSOLUTE magnitude (the SN template, the HADS schematic) as
        # this axis shows it: on a differential axis the overlays move with
        # the data, or they would float over a curve they no longer
        # describe.
        # @return: the value for this axis
        if self._mag_mode == MAG_DIFFERENTIAL and self._mag_ref is not None:
            return float(absolute_mag) - self._mag_ref
        return float(absolute_mag)

    def _measure_level(self):
        # The level a differential axis counts from: the robust median of
        # the MEASURED series.
        #
        # Never the median of everything: the differences have a median of
        # zero by construction, so including them would drag the reference
        # to zero and turn it into a lie (that is the bug's shape: a
        # reference of zero is what made the axis read 2 to 14).
        # @return: the reference magnitude, or None without measurements
        vals = [float(p["mag"]) for p in self._points
                if p.get("mag") is not None and not self._is_differential(p)]
        if not vals:
            return None
        return float(np.median(vals))

    def set_y_range(self, lo, hi):
        # The observer fixes the magnitude axis (quality plan, A1). A range
        # with no room, or inverted, is refused: an axis is not a place to
        # be clever, and a bad range would draw an unreadable chart.
        # @args: lo, hi - magnitudes (lo brighter than hi)
        # @return: True when the range was accepted
        try:
            lo, hi = float(lo), float(hi)
        except (TypeError, ValueError):
            return False
        if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
            return False
        self._y_range = (lo, hi)
        self._compute_bounds()
        self._build_scene()
        self.fit_to_scene()
        return True

    def window(self):
        # The piece of the curve on screen, in data units
        # (x0, x1, y0, y1), or None when the chart is showing it all.
        # @return: the window or None
        return self._window

    def zoom_window(self, factor, fx=None, fy=None, axes="both"):
        # Narrows the DATA window around a point of the view.
        #
        # This is what the group's tool does, and it is not the same thing
        # as magnifying the drawing: the labels keep their size, the axis
        # re-rounds its ticks and a tenth of a magnitude can be read
        # comfortably instead of growing into a blur. The chart is a
        # measurement instrument, not a picture.
        #
        # A magnitude range fixed by hand is never zoomed away: that range
        # is the observer's decision and it must not move under their feet.
        # @args: factor - >1 zooms in (a narrower window), <1 zooms out;
        #        fx/fy - the focal point as a fraction of the window
        #        (0..1, the cursor), None = the centre; axes - "both" |
        #        "x" | "y"
        # @return: True when the window changed
        try:
            factor = float(factor)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(factor) or factor <= 0.0:
            return False
        if axes not in ("both", "x", "y"):
            return False
        x0, x1, y0, y1 = self._bounds
        fx = 0.5 if fx is None else min(max(float(fx), 0.0), 1.0)
        fy = 0.5 if fy is None else min(max(float(fy), 0.0), 1.0)
        if axes in ("both", "x"):
            span = (x1 - x0) / factor
            x0, x1 = x0 + fx * (x1 - x0) - fx * span, \
                x0 + fx * (x1 - x0) - fx * span + span
        if axes in ("both", "y") and self._y_range is None:
            span = (y1 - y0) / factor
            y0, y1 = y0 + fy * (y1 - y0) - fy * span, \
                y0 + fy * (y1 - y0) - fy * span + span
        return self._set_window(x0, x1, y0, y1)

    def pan_window(self, dx_px, dy_px):
        # Slides the window through the data, the way a drag should: the
        # frame stays put and the curve moves under it.
        # @args: dx_px/dy_px - how far the cursor travelled, in screen px
        # @return: True when the window changed
        x0, x1, y0, y1 = self._bounds
        scale = abs(self.transform().m11()) or 1.0
        dx = (dx_px / scale) / (2 * self._hx) * (x1 - x0)
        dy = (dy_px / scale) / (2 * _HALF) * (y1 - y0)
        if dx == 0.0 and dy == 0.0:
            return False
        return self._set_window(x0 - dx, x1 - dx, y0 - dy, y1 - dy)

    def _set_window(self, x0, x1, y0, y1):
        # Clamps and installs a window. The limits are generous on purpose
        # (a ten-thousandth of the data's own span, or twenty times it):
        # they exist to keep the chart alive, not to decide for the
        # observer. What the observer must be stopped from is losing the
        # curve into a window with nothing in it.
        # @return: True when the window was accepted
        data = self._data_span()
        if data is None:
            return False
        (dx, dy) = data
        if not (x1 > x0 and y1 > y0):
            return False
        span_x, span_y = x1 - x0, y1 - y0
        if (span_x < dx / 1e4 or span_x > dx * 20
                or span_y < dy / 1e4 or span_y > dy * 20):
            return False
        self._window = (float(x0), float(x1), float(y0), float(y1))
        self._compute_bounds()
        self._build_scene()
        return True

    def _data_span(self):
        # The span of the data itself (x and mag), the ruler the zoom
        # limits are measured against.
        # @return: (x_span, y_span) or None without data
        if not self._points:
            return None
        xs = [p["mjd"] for p in self._points if p["mjd"] is not None]
        mags = [v for v in (self._plot_mag(p) for p in self._points)
                if v is not None]
        if not xs or not mags:
            return None
        x_span = (max(xs) - min(xs)) or 1.0
        y_span = (max(mags) - min(mags)) or _MIN_WINDOW
        return (x_span, y_span)

    def reset_view(self):
        # Back to the whole curve (the "Fit" button, a double-click).
        # @return: None
        self._window = None
        self._compute_bounds()
        self._build_scene()
        self.fit_to_scene()

    def clear_y_range(self):
        # Back to the automatic (robust) window.
        self._y_range = None
        self._compute_bounds()
        self._build_scene()
        self.fit_to_scene()

    def is_y_range_fixed(self):
        # @return: (lo, hi) when the observer fixed it, else None
        return self._y_range

    def _sync_geometry(self):
        # The plot takes the SHAPE of the space it is given.
        #
        # It used to be a fixed square (both axes 2 * _HALF wide) fitted
        # into whatever panel it lived in: a wide panel then showed a small
        # square with two dead margins, the time axis had no room and the
        # labels were squeezed against the frame. A light curve is a
        # HORIZONTAL thing (time runs along it), so the plot stretches with
        # the window, and the width is chosen so that the scene's own
        # proportions match the viewport's: the fit then fills the panel
        # exactly, with no letterboxing and no wasted side.
        #
        # @return: True when the width changed (the scene must be rebuilt)
        vw = max(120, self.viewport().width())
        vh = max(120, self.viewport().height())
        scene_h = 2 * _HALF + _PAD_TOP + _PAD_BOTTOM
        want = ((vw / float(vh)) * scene_h - _PAD_LEFT - _PAD_RIGHT) / 2.0
        # sanity bounds: never narrower than a square, never absurdly long
        want = min(max(want, _HALF), _HALF * 8.0)
        if abs(want - self._hx) < 1.0:
            return False
        self._hx = want
        # how many SCENE UNITS one pixel is worth, for the labels: the base
        # fits the scene with a 2 % pad, so this is the honest conversion
        # from the pixel sizes the reader sees to the units the items use
        self._scale = vh / (scene_h * 1.04)
        return True

    def _do_fit(self):
        # One deferred pass per resize burst (the base's own coalescing):
        # the plot's shape is recomputed and, when it changed, the scene is
        # rebuilt BEFORE the fit, so the picture follows the window.
        # @return: None
        if self._sync_geometry():
            self._build_scene()
        super()._do_fit()

    def _map_x(self, mjd):
        # @args: mjd - float
        # @return: scene x coordinate
        lo, hi, _, _ = self._bounds
        if hi == lo:
            return 0.0
        return -self._hx + (mjd - lo) / (hi - lo) * 2 * self._hx

    def _map_y(self, mag):
        # The magnitude axis, the astronomical way: the FAINTEST (the big
        # number) at the bottom and the brightest at the top.
        #
        # The sign of this formula is the whole direction of the chart, and
        # it was the other way round: a variable star's curve read upside
        # down against every published light curve and against the group's
        # own tool, whose plotY(m) puts the bright end on top. The grid
        # used to carry its own copy of the formula, which is exactly how
        # the ticks and the points can end up disagreeing; now there is one
        # rule and everything comes through here.
        # @args: mag - the magnitude on the current axis (see _plot_mag)
        # @return: scene y coordinate
        _, _, lo, hi = self._bounds
        if hi == lo:
            return 0.0
        return -_HALF + (mag - lo) / (hi - lo) * 2 * _HALF

    def _x_tick_label(self, mjd):
        # An X tick in the units the observer lives in: the civil date and
        # time the frame was taken (UTC), not the Julian number.
        #
        # The SPAN decides the shape the same way the tick's step decides
        # its decimals: a night is read in hours, a run of nights in dates
        # and a project's curve in months. Folded charts are phases and
        # keep their plain numbers (there is no date in a phase).
        # @args: mjd - the tick's value
        # @return: the label text
        if self._fold_p:
            return "%.2f" % float(mjd)
        from ...core import coords, variables
        dt = coords.datetime_from_jd(float(mjd) + variables.MJD0)
        span = self._bounds[1] - self._bounds[0]
        if span <= 1.2:                    # one night, with slack
            return dt.strftime("%H:%M")
        if span <= 40.0:                   # a few nights
            return "{} {}".format(dt.day, self._month(dt))
        return "{} {}".format(self._month(dt), dt.year)

    def _month(self, dt):
        # @args: dt - a datetime
        # @return: its short month name in the app's language (never the
        #          system's, see _MONTHS)
        from ..pretty import ui_lang
        return _MONTHS[ui_lang()][dt.month - 1]

    def _x_axis_note(self):
        # What the X axis means, in one line under it: the civil date the
        # observation happened on and the MJD a report asks for, so nobody
        # has to convert by hand (folded charts carry no date).
        # @return: the note, or "" when there is nothing to say
        if self._fold_p or not self._points:
            return ""
        from ...core import coords, variables
        x0, x1 = float(self._bounds[0]), float(self._bounds[1])
        d0 = coords.datetime_from_jd(x0 + variables.MJD0)
        d1 = coords.datetime_from_jd(x1 + variables.MJD0)
        if (x1 - x0) <= 1.2:
            if d0.date() == d1.date():
                days = "{} {} {}".format(d0.day, self._month(d0), d0.year)
            else:
                # a night that crosses midnight says both days
                days = "{} → {} {} {}".format(d0.day, d1.day,
                                              self._month(d1), d1.year)
            return self.tr("{0} UTC · MJD {1:.2f}–{2:.2f}").format(
                days, x0, x1)
        return self.tr("UTC · MJD {0:.1f}–{1:.1f}").format(x0, x1)

    def _build_scene(self):
        self.clear()
        self._has_mean = False
        if self._bounds is None:
            # a resize can arrive before any data (the plot is rebuilt when
            # the window changes shape): the axis still has to exist
            self._compute_bounds()
        b = self._bounds
        self.set_scene_rect(-self._hx - _PAD_LEFT, -_HALF - _PAD_BOTTOM,
                            2 * self._hx + _PAD_LEFT + _PAD_RIGHT,
                            2 * _HALF + _PAD_BOTTOM + _PAD_TOP)
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
                path_pts = [(self._map_x(ph + shift),
                             self._map_y(self._axis_mag(m)))
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
                y = self._map_y(self._axis_mag(self._peak_mag + dm))
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
        # legend: one entry per (filter, source) series the data has; the
        # rest of what it used to say becomes the panel's notes
        self._add_legend(has_overlay)
        self._notes = self._build_notes(flagged_seen, caveat_seen, syst,
                                        syst_all, has_overlay)

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
            if self._plot_mag(p) is None:
                continue          # another quantity: not on this axis
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
            ys = [self._map_y(self._plot_mag(p)) for p in pts]
            top, bottom = min(ys), max(ys)
            half = sys / span * 2 * _HALF
            rect = QGraphicsRectItem(-self._hx, top - half, 2 * self._hx,
                                      (bottom - top) + 2 * half)
            fill = QColor(palette.MUTED)
            fill.setAlpha(26)
            rect.setBrush(QBrush(fill))
            rect.setPen(QPen(Qt.NoPen))
            rect.setZValue(_Z_SYSTEM)
            self.add_item(rect)
        return tallest, largest

    def _bin_groups(self):
        # The plotted points, grouped the way the chart draws them: one
        # group per (filter, source). The binning and the mean curve act
        # inside each group, because averaging a measurement with a
        # detrended guide (or with another filter) would be meaningless.
        # @return: {(band, source): [point, ...]} in time order
        groups = {}
        for idx, p in enumerate(self._points):
            if self._plot_mag(p) is None:
                continue
            key = (p.get("filter"), p.get("source") or "manual")
            groups.setdefault(key, []).append((idx, p))
        for key in groups:
            groups[key].sort(key=lambda pair: pair[1]["mjd"])
        return groups

    def _binned(self, members):
        # The mean of N frames, or of N minutes, for the CHART only (a
        # presentation choice: the engine's own grouping happens in the
        # measurement domain and is a different thing).
        #
        # The error of a binned point is the quadrature of its members
        # divided by k (noise averages down) but never smaller than their
        # standard error of the mean: a group of frames that disagree
        # among themselves is telling us something, and the error must not
        # hide it.
        # @args: members - [(index, point), ...] in time order
        # @return: [{"x", "mag", "err", "n"}] (x in the chart's units)
        if not members:
            return []
        mode, n = self._bin_mode, max(1, int(self._bin_n))
        groups = []
        if mode == "frames":
            for start in range(0, len(members), n):
                groups.append(members[start:start + n])
        elif mode == "minutes":
            width = n / 1440.0
            t0 = members[0][1]["mjd"]
            buckets = {}
            for idx, p in members:
                key = int(math.floor((p["mjd"] - t0) / width + 1e-4))
                buckets.setdefault(key, []).append((idx, p))
            groups = [buckets[k] for k in sorted(buckets)]
        else:
            return []
        out = []
        for group in groups:
            mags = [self._plot_mag(p) for _i, p in group]
            mag = float(np.mean(mags))
            errs = [p.get("err_internal") or p.get("err") for _i, p in group]
            errs = [e for e in errs if e]
            err = None
            if errs:
                err = math.sqrt(sum(e * e for e in errs)) / len(group)
            if len(group) > 1:
                spread = float(np.std(mags, ddof=1)) / math.sqrt(len(group))
                err = spread if err is None else max(err, spread)
            mjd = float(np.mean([p["mjd"] for _i, p in group]))
            out.append({"mjd": mjd, "mag": mag, "err": err, "n": len(group)})
        return out

    def _moving_average(self, series):
        # A centred moving average of the plotted series: the shape of a
        # small-amplitude curve without the noise. It is a guide for the
        # eye and the legend says so; the measurements are the points.
        # @args: series - [{"mjd", "mag"}] in time order
        # @return: [(mjd, mag)] of the smoothed curve
        win = max(2, int(self._mean_window or 0))
        if win < 2 or len(series) < 3:
            return []
        half = win // 2
        out = []
        for i, p in enumerate(series):
            lo, hi = max(0, i - half), min(len(series), i + half + 1)
            chunk = [q["mag"] for q in series[lo:hi]]
            out.append((p["mjd"], float(np.mean(chunk))))
        return out

    def _dot(self, x, y, radius, colour, filled=True, pen=None, width=1.5,
             z=_Z_DATA):
        # One data marker. Small helper so every style of point (plain,
        # flagged diamond, excluded cross, selected ring, binned dot)
        # reads the same in the code below.
        # @return: the item, already added to the scene
        item = QGraphicsEllipseItem(x - radius, y - radius,
                                    radius * 2, radius * 2)
        item.setBrush(QBrush(colour if filled else QColor(palette.BG)))
        # a filled point gets a thin dark edge: it separates it from the
        # background and from its neighbours in a dense cloud, which is
        # what makes a scatter read as measurements instead of smudges
        item.setPen(pen or QPen(QColor(palette.BG) if filled else colour,
                                width))
        item.setZValue(z)
        self.add_item(item)
        return item

    def _draw_points(self):
        # Every point of the curve, and how the chart shows what the
        # observer and the detector decided about it (quality plan, phase
        # A):
        #
        #   * a DATA flag (saturated, cosmic, focus, cloud, unaligned) is
        #     the hollow diamond; a calibration CAVEAT (few comps) is a
        #     faint amber edge;
        #   * an OUTLIER candidate is red (marked, never removed);
        #   * a point the observer EXCLUDED is a small grey cross, still
        #     visible on purpose: the curve must show what was taken out;
        #   * a SELECTED point is the same dot with a black ring;
        #   * when a binning is on, the raw points fade and the binned
        #     means take the foreground, with their own error;
        #   * a mean curve, when asked, rides on top with a white halo.
        #
        # Nothing is deleted at any step: every decision is reversible.
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
        groups = self._bin_groups()
        binned_mode = self._bin_mode in ("frames", "minutes")
        for (_band, _src), members in groups.items():
            raw = [(i, p) for i, p in members if i not in self._excluded]
            binned = self._binned(raw) if binned_mode else []
            faded = 0.35 if binned else 1.0
            # 1. the raw measurements (behind, faded when binned)
            for idx, p in members:
                excluded = idx in self._excluded
                data_flags, caveat = _flags_split(p.get("flags"))
                flagged = bool(data_flags)
                if flagged and self._hide_flagged:
                    continue
                selected = idx in self._selected
                outlier = idx in self._outlier_idx
                for xv in self._xs(p):
                    x = self._map_x(xv)
                    y = self._map_y(self._plot_mag(p))
                    y_draw, off = self._clipped_y(y)
                    if off:
                        self._over_note += 1
                    colour, filled = _point_style(p)
                    radius = 4.6
                    if excluded:
                        # out of the curve but ON the chart: a grey cross,
                        # never a silent deletion
                        self._draw_cross(x, y_draw)
                        continue
                    if outlier:
                        colour = QColor(palette.DANGER)
                    if flagged:
                        self._draw_diamond(x, y_draw, radius)
                        flagged_seen = True
                    elif off:
                        self._draw_caret(x, y_draw, off)
                    else:
                        pen = QPen(QColor(FLAG_COLOUR), 1.0) if caveat \
                            else None
                        if caveat:
                            caveat_seen = True
                        if selected:
                            pen = QPen(QColor(palette.FG), 2.0)
                            radius = 6.4
                        self._dot(x, y_draw, radius, colour,
                                  filled=filled and not selected, pen=pen,
                                  width=1.5, z=_Z_DATA)
                        if selected:
                            # the selection ring is on top of the dot, so
                            # it reads as "this is the one I picked"
                            ring = QGraphicsEllipseItem(
                                x - radius - 2, y_draw - radius - 2,
                                (radius + 2) * 2, (radius + 2) * 2)
                            ring.setBrush(QBrush(Qt.NoBrush))
                            halo = QColor(palette.ACCENT)
                            halo.setAlpha(210)
                            ring.setPen(QPen(halo, 1.4))
                            ring.setZValue(_Z_DATA + 0.1)
                            self.add_item(ring)
                    err = self._bar_error(p) if self._show_errors else None
                    if err is not None and span > 0.0:
                        self._draw_error_bar(x, y_draw, err, span, colour,
                                             alpha=faded)
            # 2. the binned means (in front, one dot per group)
            for q in binned:
                x = self._map_x(q["mjd"])
                y_draw, _off = self._clipped_y(self._map_y(q["mag"]))
                colour = _point_style({"filter": _band,
                                       "source": _src})[0]
                self._dot(x, y_draw, 3.8, colour, filled=True, width=0.8,
                          z=_Z_DATA + 0.5)
                if self._show_errors and q["err"] and span > 0.0:
                    self._draw_error_bar(x, y_draw, q["err"], span, colour,
                                         alpha=1.0)
            # 3. the mean curve (a guide for the eye, drawn last)
            if self._mean_window:
                series = [{"mjd": q["mjd"], "mag": q["mag"]}
                          for q in (binned or [p for _i, p in raw])]
                smooth = self._moving_average(series)
                self._draw_mean_curve(smooth, _band, _src)
                if smooth:
                    self._has_mean = True
        return flagged_seen, caveat_seen, tallest, largest

    def _clipped_y(self, y):
        # @args: y - the scene y of a point
        # @return: (y to draw, off) where off is -1 above the window,
        #          +1 below, 0 inside: the points outside are anchored to
        #          the edge, never hidden (A1)
        if y > _HALF:
            return _HALF - 10.0, 1
        if y < -_HALF:
            return -_HALF + 10.0, -1
        return y, 0

    def _draw_cross(self, x, y):
        # An excluded point: a small grey cross, deliberately visible.
        pen = QPen(QColor(palette.MUTED), 1.2)
        for (dx, dy) in ((-5.0, -5.0), (-5.0, 5.0)):
            line = QGraphicsLineItem(x + dx, y + dy, x - dx, y - dy)
            line.setPen(pen)
            line.setZValue(_Z_DATA)
            self.add_item(line)

    def _draw_diamond(self, x, y, radius):
        # A point whose DATA is in doubt: the hollow diamond of ADR-048.
        poly = QPolygonF([QPointF(x, y - radius), QPointF(x + radius, y),
                          QPointF(x, y + radius), QPointF(x - radius, y)])
        dot = QGraphicsPolygonItem(poly)
        dot.setBrush(QBrush(QColor(palette.BG)))
        dot.setPen(QPen(QColor(FLAG_COLOUR), 1.8))
        dot.setZValue(_Z_DATA)
        self.add_item(dot)

    def _draw_caret(self, x, y, off):
        # A point outside the window: a small triangle on the edge, so the
        # reader can see there is something beyond without it setting the
        # scale.
        poly = QPolygonF([QPointF(x, y + off * 10.0), QPointF(x - 7, y),
                          QPointF(x + 7, y)])
        dot = QGraphicsPolygonItem(poly)
        dot.setBrush(QBrush(palette.DANGER))
        dot.setPen(QPen(QColor(palette.DANGER), 1.0))
        dot.setZValue(_Z_DATA)
        self.add_item(dot)

    def _draw_error_bar(self, x, y, err, span, colour, alpha=1.0):
        # The point's OWN error, clipped when it is wider than the plot can
        # carry (the legend says how many were clipped): a 0.17 mag bar on
        # a 0.12 mag curve would paint over everything.
        ey = err / span * 2 * _HALF
        clip = _BAR_CLIP * 2 * _HALF
        if ey > clip:
            ey = clip
            self._clip_note += 1
        pen = QPen(colour, 0.8)
        pen.setColor(QColor(colour.red(), colour.green(), colour.blue(),
                            int(255 * alpha)))
        bar = QGraphicsLineItem(x, y - ey, x, y + ey)
        bar.setPen(pen)
        bar.setZValue(_Z_ERROR)
        self.add_item(bar)
        # caps: the small horizontal strokes that make an error bar a
        # measurement instead of a line
        for yy in (y - ey, y + ey):
            cap = QGraphicsLineItem(x - 2.2, yy, x + 2.2, yy)
            cap.setPen(pen)
            cap.setZValue(_Z_ERROR)
            self.add_item(cap)

    def _draw_mean_curve(self, smooth, band, src):
        # The moving average, with a white halo under it so it reads on
        # top of a dense cloud of points (the trick the Photometrica tool
        # uses; it costs one extra pass and saves the eye).
        # @args: smooth - [(mjd, mag)], band/src - the series it belongs to
        if len(smooth) < 2:
            return
        colour, _filled = _point_style({"filter": band, "source": src})
        pts = [(self._map_x(mjd), self._map_y(mag)) for mjd, mag in smooth]
        for width, pen_colour in ((3.2, QColor(palette.BG)),
                                  (1.6, colour)):
            pen = QPen(pen_colour, width)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            for i in range(len(pts) - 1):
                line = QGraphicsLineItem(pts[i][0], pts[i][1],
                                          pts[i + 1][0], pts[i + 1][1])
                line.setPen(pen)
                line.setZValue(_Z_LINK + 0.4)
                self.add_item(line)


    def _link_pen(self, source, band):
        # @args: source - the series' source, band - the series' filter
        # @return: the QPen of the series' linking line: the series colour,
        #          dashed for quick-look and survey (mirrors the PNG)
        colour, _filled = _point_style(
            {"filter": band, "source": source, "mjd": 0, "mag": 0})
        pen = QPen(colour, 1.1)
        if (source or "manual").startswith("survey") or source == "quicklook":
            pen.setStyle(Qt.DashLine)
        return pen

    def _draw_link_lines(self):
        # Connects the points of each (filter, source) series, like the PNG
        # export. In fold mode each cycle is linked within itself, so no
        # seam-crossing artefacts.
        by_series = {}
        for p in self._points:
            if self._plot_mag(p) is None:
                continue          # another quantity: not on this axis
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
                        (self._map_x(xv), self._map_y(self._plot_mag(p))))
            for seq in copies.values():
                seq.sort(key=lambda xy: xy[0])
                for i in range(len(seq) - 1):
                    line = QGraphicsLineItem(seq[i][0], seq[i][1],
                                              seq[i + 1][0], seq[i + 1][1])
                    line.setPen(pen)
                    line.setZValue(_Z_LINK)
                    self.add_item(line)

    def _add_legend(self, has_template):
        # The chart's legend, kept to the MINIMUM: one short line per
        # series drawn, plus the template when one is on screen (a dashed
        # reference curve with no label would be a curve the reader might
        # take for data).
        #
        # Everything else it used to carry (flagged counts, caveats,
        # clipped bars, points off scale, the calibration band, the hidden
        # detrended curve) is information, not a label: `notes()` hands it
        # to the panel, where a reader meets it next to the other warnings
        # instead of over the science. It is smaller and muted on purpose:
        # the curve is the subject, the legend is a footnote.
        # @args: has_template - whether a reference curve is drawn
        # @return: None
        from PySide6.QtGui import QFontMetricsF
        entries = []
        if has_template:
            entries.append(
                (self.tr("schematic (sawtooth)") if self._fold_p
                 else self.tr("Typical template"), QColor(palette.MUTED)))
        seen = set()
        for p in self._points:
            src = p.get("source") or "manual"
            key = (p.get("filter"), src)
            if self._plot_mag(p) is None:
                continue          # not on this axis: not in the legend
            if key in seen:
                continue
            seen.add(key)
            text = (self.filter_label(p.get("filter"))
                    + " · " + self.source_label(src))
            colour, _filled = _point_style(p)
            entries.append((text, colour))
        if not entries:
            return
        fmt = QFont(self._label_font) if hasattr(self, "_label_font") \
            else QFont()
        fmt.setPixelSize(self._font_px(_FONT_LEGEND_PX))
        fm = QFontMetricsF(fmt)
        rows = [(text, color, fm.horizontalAdvance(text))
                for text, color in entries]
        text_w = max(row[2] for row in rows)
        sw = _LEGEND_SWATCH          # swatch length
        gap = 8                      # swatch -> text gap
        pad = 8                      # backdrop padding
        row_h = _LEGEND_PITCH        # vertical pitch between rows
        right = self._hx - 10
        text_x = right - text_w
        sw_x = text_x - gap - sw
        top = _HALF - 10 - row_h * len(entries)
        # a very faint backdrop, only as much as keeps the text readable
        # over a dense cloud of points
        bg = QGraphicsRectItem(sw_x - pad, top - pad,
                               (right - sw_x) + 2 * pad,
                               row_h * len(entries) + 2 * pad)
        bg.setBrush(QBrush(QColor(11, 13, 23, 110)))
        bg.setPen(Qt.NoPen)
        bg.setZValue(_Z_LABEL - 0.5)
        self.add_item(bg)
        for i, (text, color, _w) in enumerate(rows):
            cy = top + i * row_h + row_h / 2.0
            line = QGraphicsLineItem(sw_x, cy, sw_x + sw, cy)
            line.setPen(QPen(color, 1.3))
            line.setZValue(_Z_LABEL)
            self.add_item(line)
            lb = QGraphicsSimpleTextItem(text)
            # muted, not foreground: the legend is a footnote to the curve
            lb.setBrush(QBrush(QColor(palette.MUTED)))
            lb.setFont(fmt)
            lb.setPos(text_x, cy - row_h * 0.42)
            lb.setZValue(_Z_LABEL)
            self.add_item(lb)

    def _build_notes(self, flagged, caveat, systematic, systematic_all,
                     has_template):
        # The chart's own caveats, in plain language, for somebody else to
        # show: everything the scene used to spell out in its corner.
        #
        # They live in the chart and not in the panel because only the
        # chart knows what it actually drew (how many bars it had to clip,
        # how many points fell outside its window, which series the axis
        # left out), and the panel should not have to re-derive it.
        # @args: what _draw_points and _build_scene counted
        # @return: [str, ...]
        out = []
        if flagged:
            out.append(self.tr("flagged points are drawn as hollow "
                               "diamonds (quality gate)"))
        if caveat:
            out.append(self.tr("some points lean on few comparison stars"))
        if self._hide_flagged:
            out.append(self.tr("flagged points are hidden"))
        if self._has_mean:
            out.append(self.tr("the mean curve is a guide for the eye"))
        if systematic_all and not systematic:
            out.append(self.tr("calibration systematic ±{0:.3f}: wider than "
                               "this window, so it is not drawn"
                               ).format(systematic_all))
        elif systematic:
            out.append(self.tr("calibration systematic ±{0:.3f} (the band)"
                               ).format(systematic))
        if self._clip_note:
            out.append(self.tr("{0} error bars clipped: they are wider than "
                               "this scale").format(self._clip_note))
        if self._over_note:
            out.append(self.tr("{0} points fall outside this window and are "
                               "anchored to the edge").format(
                                   self._over_note))
        hidden = []
        for p in self._points:
            if self._plot_mag(p) is None:
                src = p.get("source") or "manual"
                label = self.source_label(src)
                if label not in hidden:
                    hidden.append(label)
        if hidden:
            out.append(self.tr("{0}: see the Δ magnitude view").format(
                ", ".join(hidden)))
        return out

    def notes(self):
        # What the chart no longer writes over the science: the counts and
        # caveats a reader needs, in the chart's own language, for the
        # caller to show wherever a reader meets them (the panel's summary,
        # a report). They are rebuilt with the scene, so they always
        # describe what is on screen.
        # @return: [str, ...], possibly empty
        return list(self._notes)


    def _draw_grid(self):
        # The grid and its labels (quality plan, A1).
        #
        # Everything about the numbers comes from core/ticks: the ticks
        # land on round values, each label carries the decimals its step
        # needs, and when the values sit far from zero (a Julian Date, a
        # pixel position) the constant is factored out and written once,
        # the way a published figure does. Before this, a 0.12 mag night
        # printed "12.5" five times and the X axis printed "60297.8"
        # everywhere: the reader had no way to know which tick was which.
        b = self._bounds
        x_span = b[1] - b[0]
        y_span = b[3] - b[2]
        grid_pen = QPen(QColor(palette.MUTED), 0.8)
        grid_pen.setStyle(Qt.DotLine)
        faint = QColor(palette.MUTED)
        faint.setAlpha(70)
        grid_pen.setColor(faint)
        axis_pen = QPen(QColor(palette.MUTED), 1.4)
        # how many TIME labels fit: a date like "20 Sep 2026" takes twice
        # the room of a "21:30", and a tick that collides with its
        # neighbour is worse than one tick fewer (the scene units are
        # roughly the tick font's own units, so these are honest budgets)
        if self._fold_p:
            tick_budget = 90.0
        elif (b[1] - b[0]) <= 1.2:
            tick_budget = 72.0            # a night: HH:MM
        else:
            tick_budget = 150.0           # dates
        target_x = int(min(max(2 * self._hx / tick_budget, 3.0), 8.0))
        x_plan = ticks.axis_plan(b[0], b[1], target=target_x)
        y_plan = ticks.axis_plan(b[2], b[3], target=5)
        # the frame: two axes and their short marks, the way a measured
        # figure is drawn. A floating dotted grid alone made the plot read
        # as a draft: the eye needs to know where the scale starts.
        for x0, y0, x1, y1 in ((-self._hx, -_HALF, -self._hx, _HALF),
                               (-self._hx, _HALF, self._hx, _HALF)):
            line = QGraphicsLineItem(x0, y0, x1, y1)
            line.setPen(axis_pen)
            line.setZValue(_Z_GRID + 0.1)
            self.add_item(line)
        # X grid lines: the tick's own x, not an even division.
        #
        # The planner's extra "offset" entry is how a Julian number is
        # printed once ("+60297.65") instead of six times, and it is
        # pointless now: the chart writes the labels itself in civil time
        # and says the MJD in its own note. Keeping it printed "00:00"
        # twice, because that constant IS the first tick of a short span.
        if self._fold_p:
            x_pairs = list(zip(x_plan["ticks"] + [x_plan["offset"]],
                               x_plan["labels"] + [""]))
        else:
            x_pairs = [(tv, self._x_tick_label(tv))
                       for tv in x_plan["ticks"]]
        for tv, text in x_pairs:
            if x_span <= 0.0:
                break
            x = -self._hx + (tv - b[0]) / x_span * 2 * self._hx
            line = QGraphicsLineItem(x, -_HALF, x, _HALF)
            line.setPen(grid_pen)
            line.setZValue(_Z_GRID)
            self.add_item(line)
            mark = QGraphicsLineItem(x, _HALF, x, _HALF + 7)
            mark.setPen(axis_pen)
            mark.setZValue(_Z_GRID + 0.1)
            self.add_item(mark)
            if text:
                self._tick_label(text, x, _HALF + 20, align="center")
        # Y grid lines (inverted axis: brighter on top)
        for tv, label in zip(y_plan["ticks"], y_plan["labels"]):
            if y_span <= 0.0:
                break
            y = self._map_y(tv)          # one rule, never a copy
            line = QGraphicsLineItem(-self._hx, y, self._hx, y)
            line.setPen(grid_pen)
            line.setZValue(_Z_GRID)
            self.add_item(line)
            mark = QGraphicsLineItem(-self._hx - 7, y, -self._hx, y)
            mark.setPen(axis_pen)
            mark.setZValue(_Z_GRID + 0.1)
            self.add_item(mark)
            # right-aligned against the axis: a wall of numbers left of a
            # plot is exactly what "let the texts breathe" is about
            self._tick_label(label, -self._hx - 12, y - 8, align="right")
        # the factored-out constant, said once (never hidden)
        if y_plan["offset_label"]:
            self._tick_label(y_plan["offset_label"], -self._hx - 12,
                             -_HALF - 30, align="right")
        note_x = self._x_axis_note()
        if note_x:
            # the corner note: the civil date the night happened on and the
            # MJD a report would ask for. Nobody should convert by hand.
            self._tick_label(note_x, -self._hx, _HALF + 44)
        elif x_plan["offset_label"]:
            self._tick_label(x_plan["offset_label"], self._hx - 60,
                             _HALF + 44)
        # WHAT the numbers are: the mode, and on a differential axis the
        # level they count from. A reader must never have to guess whether
        # 12.34 is a star's magnitude or a difference, and an axis that
        # does not say it is an axis that lies by omission.
        if self._mag_mode == MAG_DIFFERENTIAL:
            note = (self.tr("Δ magnitude from {0:.3f}").format(self._mag_ref)
                    if self._mag_ref is not None
                    else self.tr("Δ magnitude"))
        else:
            note = self.tr("Calibrated magnitude")
        self._tick_label(note, -self._hx, -_HALF - 34)

    def _font_px(self, pixels):
        # A font size that RENDERS at `pixels` on this window: the scene is
        # fitted, so a size in scene units would grow and shrink with the
        # panel and a maximized window would show giant labels. _scale is
        # the honest conversion (see _sync_geometry).
        # @args: pixels - the size the reader should see
        # @return: the font's pixel size in the item's own units
        return max(7, int(round(pixels / max(self._scale, 1e-3))))

    def _tick_label(self, text, x, y, align="left"):
        # One small grey tick label at a scene position.
        #
        # The alignment exists so the numbers can be pushed AGAINST the
        # axis instead of floating in a column: with right-aligned
        # magnitudes and centred times, the axis is a frame and the text
        # has room, which is what the observer asked for.
        # @args: text - the label, x/y - scene coordinates (x is the edge
        #        the text is aligned to), align - "left" | "center" | "right"
        # @return: the item, already added
        from PySide6.QtGui import QFontMetricsF
        lbl = QGraphicsSimpleTextItem(text)
        f = QFont()
        f.setPixelSize(self._font_px(_FONT_TICK_PX))
        lbl.setFont(f)
        if align == "right":
            x -= QFontMetricsF(f).horizontalAdvance(text)
        elif align == "center":
            x -= QFontMetricsF(f).horizontalAdvance(text) / 2.0
        lbl.setPos(x, y)
        lbl.setBrush(QBrush(QColor(palette.MUTED)))
        lbl.setZValue(_Z_LABEL)
        self.add_item(lbl)
        return lbl

    def _probe(self, sx, sy):
        # @args: sx, sy - scene coordinates
        # @return: (hit, text) for the nearest data point
        if not self._points:
            return False, None
        best = None
        best_dist = 1e9
        for p in self._points:
            value = self._plot_mag(p)
            if value is None:
                continue
            for xv in self._xs(p):
                dx = self._map_x(xv) - sx
                dy = self._map_y(value) - sy
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
