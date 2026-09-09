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
                                QGraphicsSimpleTextItem)

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

# Distinct colours per filter (matching the PNG export)
_FILTER_COLOURS = {
    "Clear": palette.ACCENT, "None": palette.ACCENT,
    "V": palette.ACCENT2, "R": palette.ACCENT2,
    "B": "#6a9fd8", "I": "#d8a06a", "NIR": "#d86a9f",
}


def _filter_colour(filt):
    return QColor(_FILTER_COLOURS.get(filt or "Clear", palette.ACCENT))


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
        self._bounds = None   # (mjd_min, mjd_max, mag_min, mag_max)
        self.set_hover_probe(self._probe)

    def set_data(self, points, sn_type=None, peak_mjd=None, peak_mag=None):
        # @args: points - list of {mjd, mag, err, filter, source} dicts,
        #        sn_type - for the template overlay, peak_mjd/mag - to align it
        # Replaces the current data and rebuilds the scene.
        self._points = sorted(points, key=lambda p: p["mjd"])
        self._sn_type = sn_type
        self._peak_mjd = peak_mjd
        self._peak_mag = peak_mag
        self._compute_bounds()
        self._build_scene()
        self.fit_to_scene()

    def _compute_bounds(self):
        # Finds the data extent (mjd and mag) for the scene mapping. Falls
        # back to a small default if there's no data.
        if not self._points:
            self._bounds = (0, 1, 10, 20)
            return
        mjds = [p["mjd"] for p in self._points]
        mags = [p["mag"] for p in self._points]
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
        # template overlay
        tpl = sn_templates.template(self._sn_type) if self._sn_type else None
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
        # data points
        for p in self._points:
            x = self._map_x(p["mjd"])
            y = self._map_y(p["mag"])
            colour = _filter_colour(p.get("filter"))
            r = 6.0
            dot = QGraphicsEllipseItem(x - r, y - r, r * 2, r * 2)
            dot.setBrush(QBrush(colour))
            dot.setPen(QPen(colour, 1.5))
            is_quicklook = p.get("source") == "quicklook"
            if is_quicklook:
                dot.setBrush(QBrush(QColor(palette.BG)))
            dot.setZValue(_Z_DATA)
            self.add_item(dot)
            # error bar
            if p.get("err") is not None:
                ey = p["err"] / (b[3] - b[2]) * 2 * _HALF if b[3] != b[2] else 0
                bar = QGraphicsLineItem(x, y - ey, x, y + ey)
                bar.setPen(QPen(colour, 1.0))
                bar.setZValue(_Z_ERROR)
                self.add_item(bar)

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
            # tick label (MJD)
            mjd = b[0] + (b[1] - b[0]) * i / 5
            lbl = QGraphicsSimpleTextItem(f"{mjd:.1f}")
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
            dx = self._map_x(p["mjd"]) - sx
            dy = self._map_y(p["mag"]) - sy
            dist = dx * dx + dy * dy
            if dist < best_dist:
                best_dist = dist
                best = p
        if best is None or best_dist > 2500:   # ~25 scene units radius
            return False, None
        lines = [
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
