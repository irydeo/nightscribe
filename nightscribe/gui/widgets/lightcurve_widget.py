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

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (QBrush, QColor, QPen, QFont)
from PySide6.QtWidgets import (QWidget, QVBoxLayout,
                                QGraphicsEllipseItem, QGraphicsLineItem,
                                QGraphicsRectItem, QGraphicsSimpleTextItem)

from ...core import sn_templates
from ...viz import palette
from .base_chart import ChartView

# Scene z-order (higher = drawn on top)
_Z_GRID = 0.0
_Z_TEMPLATE = 1.0
_Z_DATA = 2.0
_Z_ERROR = 3.0
_Z_LABEL = 4.0

# Font sizes in scene units
_FONT_TICK = 18
_FONT_LABEL = 22

# Scene half-extent: the data area is always this wide/tall, independent of
# the data's actual span. The mapping scales the data into this box.
_HALF = 500.0


def _filter_label(filt):
    # @args: filt - filter name (None/"Clear"/"None" = the generic band)
    # @return: the display label for a legend entry
    return "Sin filtro" if not filt or filt in ("Clear", "None") else filt


def _series_style(src_class):
    # @args: src_class - "manual" | "quicklook" | "survey"
    # @return: (colour or None for "use the filter colour", filled bool)
    if src_class == "survey":
        return "#8a90a6", False
    if src_class == "quicklook":
        return None, False
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
    else:
        src_class = "manual"
    colour, filled = _series_style(src_class)
    if colour is None:
        colour = palette.ACCENT if not p.get("filter") \
            else _FILTER_COLOURS.get(p.get("filter"), palette.ACCENT)
    return QColor(colour), filled

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
        self.set_hover_probe(self._probe)

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
        # Finds the data extent (x and mag) for the scene mapping. Falls
        # back to a small default if there's no data.
        if not self._points:
            self._bounds = (0, 1, 10, 20)
            return
        mags = [p["mag"] for p in self._points]
        if self._schematic:
            mags += [m for _ph, m in self._schematic]
        if self._fold_p:
            self._bounds = (0.0, 2.0, min(mags), max(mags))
            return
        mjds = [p["mjd"] for p in self._points]
        self._bounds = (min(mjds), max(mjds), min(mags), max(mags))
        # auto-peak: brightest point (lowest mag)
        if self._peak_mjd is None or self._peak_mag is None:
            brightest = min(self._points, key=lambda p: p["mag"])
            self._peak_mjd = self._peak_mjd or brightest["mjd"]
            self._peak_mag = self._peak_mag or brightest["mag"]

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
        # template overlay: the schematic reference curve in fold mode
        # (never real data), the SN type template otherwise
        has_overlay = False
        if self._fold_p and self._schematic:
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
        tpl = None if self._fold_p else (
            sn_templates.template(self._sn_type) if self._sn_type else None)
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
        # data points (drawn twice in fold mode: cycle 0 and cycle 1)
        for p in self._points:
            for xv in self._xs(p):
                x = self._map_x(xv)
                y = self._map_y(p["mag"])
                colour, filled = _point_style(p)
                r = 6.0
                dot = QGraphicsEllipseItem(x - r, y - r, r * 2, r * 2)
                dot.setBrush(QBrush(colour if filled else QColor(palette.BG)))
                dot.setPen(QPen(colour, 1.5))
                dot.setZValue(_Z_DATA)
                self.add_item(dot)
                # error bar
                if p.get("err") is not None:
                    ey = p["err"] / (b[3] - b[2]) * 2 * _HALF \
                        if b[3] != b[2] else 0
                    bar = QGraphicsLineItem(x, y - ey, x, y + ey)
                    bar.setPen(QPen(colour, 1.0))
                    bar.setZValue(_Z_ERROR)
                    self.add_item(bar)
        # legend: one entry per (filter, source) series the data has
        self._add_legend(has_overlay)

    def _add_legend(self, has_template):
        # @args: has_template - whether the schematic overlay is drawn
        # Draws a compact legend in the bottom-right of the data area
        # (same corner as sky_widget); entries mirror the PNG export so
        # the two renderers cannot disagree (B4).
        from PySide6.QtGui import QFontMetricsF
        entries = []
        if has_template:
            entries.append(
                (self.tr("schematic (sawtooth)") if self._fold_p
                 else self.tr("Typical template"), QColor(palette.MUTED)))
        seen = set()
        for p in self._points:
            src = p.get("source") or "manual"
            if src.startswith("survey"):
                cls = "survey"
            elif src == "quicklook":
                cls = "quicklook"
            else:
                cls = "manual"
            key = (p.get("filter"), cls)
            if key in seen:
                continue
            seen.add(key)
            text = _filter_label(p.get("filter"))
            if cls == "quicklook":
                text += " · " + self.tr("indicative")
            elif cls == "survey":
                text += " · " + self.tr("catalog")
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
        b = self._bounds
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
            xv = b[0] + (b[1] - b[0]) * i / 5
            lbl = QGraphicsSimpleTextItem(f"{xv:.1f}")
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
            mag = b[2] + (b[3] - b[2]) * i / 4
            lbl = QGraphicsSimpleTextItem(f"{mag:.1f}")
            lbl.setPos(-_HALF - 50, y - 8)
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
            f"[{best.get('filter') or 'Clear'}]",
        ]
        if best.get("source"):
            lines.append(f"({best['source']})")
        if best.get("err") is not None:
            lines.append(f"±{best['err']:.3f}")
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
