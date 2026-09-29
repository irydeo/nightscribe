############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SN light curve widget (Track B, B4, ADR-029)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from nightscribe.gui.widgets.lightcurve_widget import (
    LightCurveChart, _point_style)


_POINTS = [
    {"mjd": 60600.0, "mag": 16.0, "err": 0.02, "filter": "Clear",
     "source": "manual"},
    {"mjd": 60605.0, "mag": 16.3, "err": 0.03, "filter": "Clear",
     "source": "manual"},
    {"mjd": 60610.0, "mag": 16.6, "err": 0.02, "filter": "Clear",
     "source": "manual"},
    {"mjd": 60607.0, "mag": 15.9, "err": None, "filter": "NIR",
     "source": "quicklook"},
]


def _app():
    return QApplication.instance() or QApplication([])


def test_widget_empty():
    _app()
    chart = LightCurveChart()
    chart.set_data([])
    # scene should have no data items (just grid)
    # but should not crash
    assert chart._points == []


def test_widget_with_data():
    _app()
    chart = LightCurveChart()
    chart.set_data(_POINTS, sn_type="SN Ia")
    assert len(chart._points) == 4
    # bounds computed from the data
    assert chart._bounds is not None
    b = chart._bounds
    assert b[0] == 60600.0   # mjd_min
    assert b[1] == 60610.0   # mjd_max


def test_widget_auto_peak():
    _app()
    chart = LightCurveChart()
    chart.set_data(_POINTS, sn_type="SN Ia")
    # auto-peak = brightest point (lowest mag) = 15.9
    assert chart._peak_mag == 15.9


def test_widget_hover_probe():
    _app()
    chart = LightCurveChart()
    chart.set_data(_POINTS, sn_type="SN Ia")
    # hover near the first point
    x = chart._map_x(60600.0)
    y = chart._map_y(16.0)
    hit, text = chart._probe(x, y)
    assert hit is True
    assert "60600" in text[0]
    assert "16.00" in text[1]


def test_widget_hover_miss():
    _app()
    chart = LightCurveChart()
    chart.set_data(_POINTS)
    # hover far from any point
    hit, text = chart._probe(-9999, 9999)
    assert hit is False


def test_widget_export_png(tmp_path):
    _app()
    chart = LightCurveChart()
    chart.set_data(_POINTS, sn_type="SN Ia")
    out = tmp_path / "widget_lc.png"
    chart.export_png(out)
    assert out.exists()


def test_widget_template_overlay():
    _app()
    chart = LightCurveChart()
    chart.set_data(_POINTS, sn_type="SN Ia",
                   peak_mjd=60605.0, peak_mag=15.9)
    # the template should have been drawn (scene has template lines)
    # we check indirectly: with a template, the scene has more items than
    # without (grid + data + template)
    chart_no_tpl = LightCurveChart()
    chart_no_tpl.set_data(_POINTS)  # no sn_type
    # count items via the registered list
    assert len(chart._items_registered) > len(chart_no_tpl._items_registered)


# ---------------- B4: source styles + legend labels ----------------

def _legend_texts(chart):
    # @return: every text item's string on the scene
    from PySide6.QtWidgets import QGraphicsSimpleTextItem
    return [i.text() for i in chart._items_registered
            if isinstance(i, QGraphicsSimpleTextItem)]


def test_widget_survey_point_style():
    # survey points: grey and hollow (manual stays filled)
    s_color, s_filled = _point_style(
        {"filter": "Clear", "source": "survey:ztf"})
    assert s_color.name() == "#8a90a6"
    assert s_filled is False
    m_color, m_filled = _point_style(
        {"filter": "Clear", "source": "manual"})
    assert m_color.name() != "#8a90a6"
    assert m_filled is True


def test_widget_legend_labels():
    # Legend rows group by (filter, source) with the human labels:
    # "No filter · Survey · ALeRCE/ZTF", "… Quick-look · indicative"…
    # (English source strings — no .qm loaded in the test env, so
    # tr() passes through unchanged)
    pts = [
        {"mjd": 60600.0, "mag": 16.0, "err": 0.02, "filter": "Clear",
         "source": "survey:atlas"},
        {"mjd": 60601.0, "mag": 16.2, "err": 0.03, "filter": "Clear",
         "source": "quicklook"},
    ]
    chart = LightCurveChart()
    chart.set_data(pts)
    texts = _legend_texts(chart)
    assert "No filter · Survey · ALeRCE/ZTF" in texts
    assert "No filter · Quick-look · indicative" in texts
    # named filters keep their name
    chart3 = LightCurveChart()
    chart3.set_data([dict(pts[0], filter="V")])
    assert "V · Survey · ALeRCE/ZTF" in _legend_texts(chart3)


def test_widget_source_labels():
    # filter / source label helpers (legend + probe share them, so the
    # two renderers cannot drift into different wording)
    chart = LightCurveChart()
    assert chart.filter_label(None) == "No filter"
    assert chart.filter_label("Clear") == "No filter"
    assert chart.filter_label("None") == "No filter"
    assert chart.filter_label("V") == "V"
    assert chart.source_label(None) == "Manual entry"
    assert chart.source_label("manual") == "Manual entry"
    assert chart.source_label("paste") == "Pasted data"
    assert chart.source_label("file") == "From file"
    assert chart.source_label("quicklook") == "Quick-look · indicative"
    assert chart.source_label("survey:ztf") == "Survey · ALeRCE/ZTF"
    assert chart.source_label("survey:atlas") == "Survey · ALeRCE/ZTF"


def test_widget_template_toggle_keeps_bounds():
    # Toggling the template rebuilds the scene but never moves the axis:
    # the template is a reference, not data.
    _app()
    from nightscribe.core import hads
    saw = hads.sawtooth_template(12.0, 0.5, 11.55)
    chart = LightCurveChart()
    chart.set_data(_FOLD_POINTS, fold_period_d=0.5, schematic=saw)
    before = chart._bounds
    assert before is not None
    n_with = len(chart._items_registered)
    chart.set_template_visible(False)
    assert chart._bounds == before          # axis fixed
    n_without = len(chart._items_registered)
    assert n_without < n_with               # schematic lines gone
    assert chart._tpl_visible is False
    chart.set_template_visible(True)
    assert chart._bounds == before
    assert len(chart._items_registered) == n_with
    # without a template/schematic the toggle is a no-op on the scene
    chart2 = LightCurveChart()
    chart2.set_data(_POINTS, sn_type="SN Ia")
    b2 = chart2._bounds
    n2 = len(chart2._items_registered)
    chart2.set_template_visible(False)
    assert chart2._bounds == b2
    chart2.set_template_visible(True)
    assert chart2._bounds == b2
    assert len(chart2._items_registered) == n2


def test_widget_link_lines_toggle():
    # Linking lines on/off: solid for the observer's own points, dashed
    # for quick-look / survey, and it must not crash when a series has
    # 0, 1 or 2 points (a series with a single point has no neighbours
    # to connect and gets no line).
    _app()
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QPen as _QPen
    pts = [
        {"mjd": 60600.0, "mag": 16.0, "err": 0.02, "filter": "Clear",
         "source": "manual"},
        {"mjd": 60602.0, "mag": 16.3, "err": 0.02, "filter": "Clear",
         "source": "manual"},
        {"mjd": 60601.0, "mag": 15.8, "err": 0.03, "filter": "Clear",
         "source": "survey:ztf"},
    ]
    for n in (0, 1, len(pts)):
        chart = LightCurveChart()
        chart.set_data(pts[:n])
        chart.set_link_lines(False)
        linkless = len(chart._items_registered)
        chart.set_link_lines(True)
        linked = len(chart._items_registered)
        assert linked >= linkless
        if n < len(pts):
            assert linked == linkless  # every series has 1 point: no line
        else:
            # only the 2-point manual series gets a line (single survey
            # point stays unlinked)
            assert linked == linkless + 1
    # both series with 2 points: two lines
    pts2 = pts + [dict(pts[2], mjd=60603.0, source="survey:ztf")]
    chart = LightCurveChart()
    chart.set_data(pts2)
    chart.set_link_lines(False)
    linkless = len(chart._items_registered)
    chart.set_link_lines(True)
    assert len(chart._items_registered) == linkless + 2
    # pen styles: manual solid, survey dashed (mirrors the PNG export)
    solid = chart._link_pen("manual", "Clear")
    dash = chart._link_pen("survey:ztf", "Clear")
    dashed = chart._link_pen("quicklook", "Clear")
    assert isinstance(solid, _QPen)
    assert solid.style() == _Qt.SolidLine
    assert dash.style() == _Qt.DashLine
    assert dashed.style() == _Qt.DashLine


def test_widget_survey_point_not_crash():
    # a survey-catalog point must render without a QPen/colour crash
    from PySide6.QtGui import QColor
    p = {"mjd": 60600.0, "mag": 16.0, "err": 0.02,
         "filter": "Clear", "source": "survey:ztf"}
    c, filled = _point_style(p)
    assert isinstance(c, QColor)
    c2, f2 = _point_style({"mjd": 0, "mag": 1, "filter": "Clear",
                           "source": "manual"})
    assert isinstance(c2, QColor) and f2


# ---------------- phase folding (ADR-034, subplan D.4) ----------------

_FOLD_POINTS = [
    {"mjd": 60600.00, "mag": 11.8, "err": 0.02, "filter": "Clear",
     "source": "file"},
    {"mjd": 60600.25, "mag": 11.3, "err": 0.02, "filter": "Clear",
     "source": "file"},      # half a period later (P = 0.5 d)
    {"mjd": 60600.50, "mag": 11.8, "err": 0.02, "filter": "Clear",
     "source": "file"},
]


def test_widget_fold_maps_phases_and_bounds():
    _app()
    chart = LightCurveChart()
    chart.set_data(_FOLD_POINTS, fold_period_d=0.5)
    assert chart._bounds[0] == 0.0 and chart._bounds[1] == 2.0
    # epoch defaults to the first point; half a period later is phase 0.5
    assert abs(chart._phase(60600.25) - 0.5) < 1e-9
    # each point is drawn in both cycles
    assert chart._xs(_FOLD_POINTS[1]) == (0.5, 1.5)


def test_widget_fold_probe_reports_phase_and_mjd():
    _app()
    chart = LightCurveChart()
    chart.set_data(_FOLD_POINTS, fold_period_d=0.5)
    # hover right on the cycle-1 copy of the middle point
    x = chart._map_x(1.5)
    y = chart._map_y(11.3)
    hit, lines = chart._probe(x, y)
    assert hit
    assert lines[0].startswith("phase 0.50")
    assert any(l.startswith("MJD 60600.25") for l in lines)


def test_widget_fold_draws_schematic_and_skips_sn_template():
    _app()
    from nightscribe.core import hads
    chart = LightCurveChart()
    saw = hads.sawtooth_template(12.0, 0.5, 11.55)
    chart.set_data(_FOLD_POINTS, fold_period_d=0.5, sn_type="SN Ia",
                   schematic=saw)
    assert chart._schematic is saw
    # the SN template is skipped in fold mode (its days-from-peak
    # semantics don't fold); the legend shows the schematic entry
    texts = _legend_texts(chart)
    assert any("schematic" in t for t in texts)
    assert not any("Typical template" in t for t in texts)


def test_widget_unfolded_unchanged():
    _app()
    chart = LightCurveChart()
    chart.set_data(_POINTS, sn_type="SN Ia")
    assert chart._fold_p is None
    assert chart._xs(_POINTS[0]) == (60600.0,)


# ---------------- quality plan, phase A1: the chart's decisions --------

import math  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402

from nightscribe.gui.widgets.lightcurve_widget import _HALF  # noqa: E402


def _points(n=60, seed=5):
    rng = np.random.default_rng(seed)
    return [{"mjd": 60297.77 + i * 0.0005,
             "mag": 12.58 + 0.05 * math.sin(i / 9.0)
             + rng.normal(0, 0.004),
             "err": 0.02, "err_internal": 0.004, "filter": "V",
             "source": "measure", "flags": []}
            for i in range(n)]


def test_the_observer_can_fix_the_magnitude_axis():
    _app()
    c = LightCurveChart()
    c.set_data(_points())
    auto = c._bounds[3] - c._bounds[2]
    assert c.set_y_range(12.55, 12.60) is True
    assert c.is_y_range_fixed() == (12.55, 12.60)
    assert (c._bounds[3] - c._bounds[2]) == pytest.approx(0.05)
    assert c._bounds[3] - c._bounds[2] < auto
    # an impossible range is refused, not silently accepted
    assert c.set_y_range(12.60, 12.55) is False
    assert c.set_y_range("x", 1.0) is False
    assert c.is_y_range_fixed() == (12.55, 12.60)
    c.clear_y_range()
    assert c.is_y_range_fixed() is None


def test_a_click_on_a_point_selects_it_and_on_air_asks_for_the_big_view():
    _app()
    c = LightCurveChart()
    c.set_data(_points())
    picked, enlarged = [], []
    c.point_clicked.connect(picked.append)
    c.enlarge_requested.connect(lambda: enlarged.append(True))
    p = c._points[10]
    c._on_scene_click(QPointF(c._map_x(p["mjd"]), c._map_y(p["mag"])))
    assert picked == [10] and c.selected() == [10]
    assert enlarged == []
    # a click far from every point asks for the big view instead
    c._on_scene_click(QPointF(-_HALF + 1.0, -_HALF + 1.0))
    assert enlarged == [True]
    # and clicking the same point again unselects it
    c._on_scene_click(QPointF(c._map_x(p["mjd"]), c._map_y(p["mag"])))
    assert c.selected() == []


def test_excluded_points_are_never_hidden():
    _app()
    c = LightCurveChart()
    c.set_data(_points())
    c.set_excluded([3, 4])
    assert c.excluded() == [3, 4]
    # they stay in the chart's data: an exclusion is a decision, not a
    # deletion (ADR-048, T7)
    assert len(c._points) == 60
    c.set_excluded([])
    assert c.excluded() == []


def test_binning_and_mean_curve_are_presentation_only():
    _app()
    c = LightCurveChart()
    c.set_data(_points())
    c.set_bin_mode("frames", 5)
    series = [{"mjd": p["mjd"], "mag": p["mag"]}
              for p in c._points]
    binned = c._binned(list(enumerate(c._points)))
    assert len(binned) == 12               # 60 points / 5 per bin
    assert binned[0]["n"] == 5
    # the mean of a group is the mean of its members
    assert binned[0]["mag"] == pytest.approx(
        float(np.mean([p["mag"] for p in c._points[:5]])))
    smooth = c._moving_average(series)
    assert len(smooth) == len(series)
    # the moving average is smoother than the curve itself
    raw = np.array([p["mag"] for p in c._points])
    sm = np.array([m for _t, m in smooth])
    assert sm.std() < raw.std()
    c.set_bin_mode("minutes", 2)
    assert c._bin_mode == "minutes"
    c.set_bin_mode("nonsense")
    assert c._bin_mode == "off"


def test_the_hit_test_respects_the_exclusion():
    _app()
    c = LightCurveChart()
    c.set_data(_points())
    p = c._points[7]
    x, y = c._map_x(p["mjd"]), c._map_y(p["mag"])
    assert c.point_at(x, y) == 7
    c.set_excluded([7])
    assert c.point_at(x, y) is None


# ---------------- V1: one axis, one kind of magnitude ----------------

def _series_payload():
    # What a measured series hands the chart: the calibrated magnitudes of
    # the night plus the detrended curve, which is "mag - trend" and
    # therefore lives around ZERO. That mix is exactly what gave a curve of
    # hundredths an axis from 2 to 14.
    raw = [{"mjd": 60600.0 + 0.01 * i, "mag": 12.34 + 0.004 * i,
            "err": 0.01, "err_internal": 0.008, "filter": "V",
            "source": "measure", "flags": []} for i in range(6)]
    det = [{"mjd": 60600.0 + 0.01 * i, "mag": 0.002 * i,
            "err": 0.01, "err_internal": 0.008, "filter": "V",
            "source": "detrend", "flags": []} for i in range(6)]
    return raw + det


def test_a_measured_curve_and_a_detrended_one_never_share_the_axis():
    # The bug this fixes, as a test: absolute magnitudes (12.3x) and
    # differences (around 0) on one axis made the window 12 magnitudes
    # wide, the ticks read 2, 4, 6 ... 14, and a variation of hundredths
    # was a straight line. The calibrated axis must ignore the curve that
    # belongs to another level.
    _app()
    chart = LightCurveChart()
    chart.set_data(_series_payload())
    lo, hi = chart._bounds[2], chart._bounds[3]
    assert hi - lo < 0.2          # a curve of hundredths, not of 12 mag
    assert 12.3 < lo and hi < 12.4
    # and the detrended points are simply not on this axis
    assert all(p["source"] != "detrend" for p in chart.axis_points())
    assert len(chart.axis_points()) == 6


def test_the_differential_axis_counts_from_the_measured_level():
    # The other view: everything referred to a level that is SAID, so a
    # tenth of a magnitude fills the chart and both curves travel
    # together, because both are differences now.
    _app()
    chart = LightCurveChart()
    chart.set_data(_series_payload())
    assert chart.set_mag_mode("differential") is True
    assert chart.mag_mode() == "differential"
    lo, hi = chart._bounds[2], chart._bounds[3]
    assert hi - lo < 0.2
    assert lo < 0 < hi            # a difference axis straddles zero
    # the reference is the MEASURED series' level, never zero: a median of
    # everything would be dragged to zero by the differences themselves
    ref = chart.mag_reference()
    assert ref == pytest.approx(12.35, abs=0.01)
    # and both series are drawn now
    got = chart.axis_points()
    assert len(got) == 12
    raws = [p["mag"] for p in got if p["source"] == "measure"]
    assert max(raws) < 0.02       # a measured 12.35 shows as ~0.00


def test_the_scale_can_be_switched_both_ways():
    _app()
    chart = LightCurveChart()
    chart.set_data(_series_payload())
    assert chart.mag_mode() == "calibrated"
    chart.set_mag_mode("differential")
    assert chart.mag_mode() == "differential"
    chart.set_mag_mode("calibrated")
    assert chart.mag_mode() == "calibrated"
    # a mode the chart does not know is refused, never silently obeyed
    assert chart.set_mag_mode("absolute-ish") is False
    assert chart.mag_mode() == "calibrated"


def test_switching_the_scale_drops_a_range_written_in_the_old_units():
    # "12.3 to 12.4" means nothing on a difference axis: keeping it would
    # rescale the chart into nonsense, so it is dropped rather than
    # silently reinterpreted.
    _app()
    chart = LightCurveChart()
    chart.set_data(_series_payload())
    assert chart.set_y_range(12.33, 12.37) is True
    assert chart.is_y_range_fixed() is not None
    chart.set_mag_mode("differential")
    assert chart.is_y_range_fixed() is None


def _scene_texts(chart):
    # @return: every text drawn on the scene (the axis' own words included)
    from PySide6.QtWidgets import QGraphicsSimpleTextItem
    return [it.text() for it in chart.scene().items()
            if isinstance(it, QGraphicsSimpleTextItem)]


def test_the_axis_says_which_magnitude_it_shows():
    # A reader must never have to guess whether 12.34 is a star's
    # magnitude or a difference.
    _app()
    chart = LightCurveChart()
    chart.set_data(_series_payload())
    assert any("Calibrated" in t for t in _scene_texts(chart))
    chart.set_mag_mode("differential")
    texts = _scene_texts(chart)
    assert any("magnitude from" in t for t in texts)
    assert any("12.35" in t for t in texts)      # the level, in the figure


def test_the_legend_does_not_promise_a_series_that_is_not_drawn():
    # In calibrated mode the detrended curve is not on the axis: the legend
    # must not list it as if it were, and the chart must SAY where to find
    # it (in the notes the panel shows now, not over the curve).
    _app()
    chart = LightCurveChart()
    chart.set_data(_series_payload())
    texts = _scene_texts(chart)
    assert not any("detrended" in t.lower() for t in texts)
    assert any("Δ magnitude view" in n for n in chart.notes())
    chart.set_mag_mode("differential")
    assert not any("Δ magnitude view" in n for n in chart.notes())
    assert any("detrended" in t.lower() for t in _scene_texts(chart))


def test_the_legend_is_a_footnote_and_the_caveats_go_to_the_notes():
    # The observer asked twice: the legend shouted and ate a corner of the
    # plot. It now carries one line per series (plus the template, which
    # must not be mistaken for data) and everything else is information
    # that belongs beside the other warnings, not over the science.
    _app()
    chart = LightCurveChart()
    chart.set_data(_series_payload())
    texts = _scene_texts(chart)
    # the series are still named on the chart...
    assert any("measured" in t for t in texts)
    # ...and nothing else is written over the curve
    for noise in ("flagged", "clipped", "off scale", "calibration",
                  "mean curve", "hidden"):
        assert not any(noise in t for t in texts)
    # the little font and the muted colour are the point, not decoration
    from PySide6.QtWidgets import QGraphicsSimpleTextItem
    from nightscribe.gui.widgets.lightcurve_widget import _FONT_LEGEND_PX
    legend = [it for it in chart.scene().items()
              if isinstance(it, QGraphicsSimpleTextItem)
              and "measured" in it.text()]
    assert legend
    # the font is sized so that it RENDERS at _FONT_LEGEND_PX pixels
    assert legend[0].font().pixelSize() == pytest.approx(
        _FONT_LEGEND_PX / chart._scale, rel=0.15)


# ---------------- V3: the window, the wheel and the export ----------------

def _curve(n=40, base=12.34):
    return [{"mjd": 60600.0 + 0.01 * i, "mag": base + 0.004 * i,
             "err": 0.01, "err_internal": 0.008, "filter": "V",
             "source": "measure", "flags": []} for i in range(n)]


def test_the_window_narrows_and_still_covers_the_data():
    # Zooming is a change of WHAT PIECE of the curve is on screen, not a
    # magnifying glass over the drawing: the frame and the labels stay put
    # and the axis re-rounds its ticks.
    _app()
    chart = LightCurveChart()
    chart.set_data(_curve())
    full = chart._bounds
    scale_before = chart.transform().m11()
    assert chart.zoom_window(2.0) is True
    zoomed = chart._bounds
    assert zoomed[1] - zoomed[0] < full[1] - full[0]
    assert zoomed[3] - zoomed[2] < full[3] - full[2]
    # the view is not magnified: the drawing keeps its size
    assert chart.transform().m11() == scale_before
    # the centre of the window stayed where it was (zoom about the middle)
    assert (zoomed[0] + zoomed[1]) / 2 == pytest.approx(
        (full[0] + full[1]) / 2, abs=1e-9)
    assert chart.window() is not None


def test_the_zoom_is_limited_so_the_curve_is_never_lost():
    # The limits exist to keep the chart alive, not to decide for the
    # observer: past them the window is refused and the chart stays as it
    # was, instead of showing a piece of nothing.
    _app()
    chart = LightCurveChart()
    chart.set_data(_curve())
    before = chart._bounds
    assert chart.zoom_window(1e6) is False
    assert chart._bounds == before
    assert chart.zoom_window(0.0) is False
    assert chart.zoom_window(-3.0) is False


def test_a_fixed_magnitude_range_is_never_zoomed_away():
    # The observer's own scale is a decision, not a view: the wheel takes
    # the time axis and leaves the magnitudes where they were put.
    _app()
    chart = LightCurveChart()
    chart.set_data(_curve())
    chart.set_y_range(12.34, 12.44)
    chart.zoom_window(2.0)
    assert chart._bounds[2] == pytest.approx(12.34)
    assert chart._bounds[3] == pytest.approx(12.44)
    assert chart._bounds[1] - chart._bounds[0] < 0.39      # time did zoom


def test_the_wheel_and_the_drag_move_the_window():
    # The two gestures of the group's tool: the wheel narrows around the
    # cursor, the drag slides the window under the frame.
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import Qt
    _app()
    chart = LightCurveChart()
    chart.resize(900, 500)
    chart.set_data(_curve())
    full = chart._bounds
    press = QMouseEvent(QEvent.MouseButtonPress, QPointF(400.0, 200.0),
                        QPointF(400.0, 200.0), Qt.LeftButton,
                        Qt.LeftButton, Qt.NoModifier)
    chart.mousePressEvent(press)
    move = QMouseEvent(QEvent.MouseMove, QPointF(460.0, 200.0),
                       QPointF(460.0, 200.0), Qt.NoButton,
                       Qt.LeftButton, Qt.NoModifier)
    chart.mouseMoveEvent(move)
    release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(460.0, 200.0),
                          QPointF(460.0, 200.0), Qt.LeftButton,
                          Qt.NoButton, Qt.NoModifier)
    chart.mouseReleaseEvent(release)
    assert chart.window() is not None
    # dragging right takes the window back in time
    assert chart._bounds[0] < full[0]


def test_a_double_click_frames_the_whole_curve_again():
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    _app()
    chart = LightCurveChart()
    chart.resize(900, 500)
    chart.set_data(_curve())
    full = chart._bounds
    chart.zoom_window(3.0)
    assert chart.window() is not None
    event = QMouseEvent(QEvent.MouseButtonDblClick, QPointF(450.0, 250.0),
                        QPointF(450.0, 250.0), Qt.LeftButton,
                        Qt.LeftButton, Qt.NoModifier)
    chart.mouseDoubleClickEvent(event)
    assert chart.window() is None
    assert chart._bounds == full


def test_a_new_series_gets_a_fresh_window_and_a_live_one_keeps_it():
    # A different series deserves a fresh look; the live curve growing is
    # the SAME series continuing, and resetting the zoom at every batch
    # would take the observer's place away once a minute.
    _app()
    chart = LightCurveChart()
    chart.set_data(_curve())
    chart.zoom_window(2.0)
    win = chart.window()
    assert win is not None
    chart.set_data(_curve(45), keep_window=True)
    assert chart.window() == win
    chart.set_data(_curve(50))
    assert chart.window() is None


def test_the_export_carries_the_window_you_framed(tmp_path):
    # "Save what you see" has to be true even zoomed in: the file is the
    # chart's own visible view, marks and fixed range included.
    _app()
    chart = LightCurveChart()
    chart.resize(900, 500)
    chart.set_data(_curve())
    whole = chart.export_png(tmp_path / "whole.png")
    assert chart.zoom_window(4.0) is True
    framed = chart.export_png(tmp_path / "framed.png")
    assert whole.read_bytes() != framed.read_bytes()
    # the axis in the file belongs to the FRAMED window: its ticks are the
    # ones that window calls for, not the whole curve's. The expected ones
    # come from the same planner the chart uses, so this checks that the
    # export and the screen agree, not that a string looks a given way
    # (values far from zero have their constant factored out and written
    # once, which is the didactic style of core/ticks).
    from PySide6.QtWidgets import QGraphicsSimpleTextItem
    from nightscribe.core import ticks as ticks_mod
    win = chart.window()
    assert win[3] - win[2] < 0.05          # a four-times zoom of 0.14 mag
    plan = ticks_mod.axis_plan(win[2], win[3], target=5)
    labels = [it.text() for it in chart.scene().items()
              if isinstance(it, QGraphicsSimpleTextItem)]
    assert plan["labels"]
    for lbl in plan["labels"]:
        assert lbl in labels


def test_the_magnitude_axis_is_the_astronomical_way_up():
    # The faintest at the BOTTOM, the brightest at the top: the convention
    # of every published light curve and of the group's own tool. The sign
    # of _map_y is the whole direction of the chart, and it was backwards
    # (a curve of a variable star read upside down).
    _app()
    chart = LightCurveChart()
    bright, faint = 12.50, 12.63
    chart.set_data([
        {"mjd": 60600.0, "mag": bright, "err": 0.01, "filter": "V",
         "source": "measure", "flags": []},
        {"mjd": 60600.5, "mag": faint, "err": 0.01, "filter": "V",
         "source": "measure", "flags": []}])
    y_bright = chart._map_y(bright)
    y_faint = chart._map_y(faint)
    assert y_bright < y_faint          # smaller scene y is higher up
    # and the axis' own ticks follow the same rule: the brightest value of
    # the window is labelled at the top
    labels = _scene_texts(chart)
    from nightscribe.core import ticks as ticks_mod
    plan = ticks_mod.axis_plan(*chart._bounds[2:], target=5)
    assert plan["labels"]
    # the first label of the plan is the smallest magnitude: it must sit
    # above the last one on screen
    first = plan["labels"][0]
    last = plan["labels"][-1]
    from PySide6.QtWidgets import QGraphicsSimpleTextItem
    pos = {}
    for it in chart.scene().items():
        if isinstance(it, QGraphicsSimpleTextItem) and it.text() in (first,
                                                                    last):
            pos[it.text()] = it.pos().y()
    assert pos[first] < pos[last]
    assert labels                     # the labels are there at all


def test_the_wheel_zooms_around_the_cursor_the_same_way_up_or_down():
    # The inverse mapping must follow the axis: a wheel over the top of the
    # plot narrows towards the bright end, and over the bottom towards the
    # faint end. Getting this wrong zooms somewhere else entirely.
    from PySide6.QtCore import QEvent, QPointF, QPoint, Qt
    from PySide6.QtGui import QWheelEvent
    _app()
    chart = LightCurveChart()
    chart.resize(900, 500)
    chart.set_data(_curve())
    chart.fit_to_scene()
    vp = chart.viewport().rect()
    # a point near the top of the plot and one near the bottom
    top = chart.mapFromScene(QPointF(0.0, -_scene_half()))
    bottom = chart.mapFromScene(QPointF(0.0, _scene_half()))
    before = chart._bounds
    wheel = QWheelEvent(QPointF(float(top.x()), float(top.y())),
                        QPointF(0.0, 0.0), QPoint(0, 0), QPoint(0, 120),
                        Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False)
    chart.wheelEvent(wheel)
    after_top = chart._bounds
    # the window got narrower towards the TOP of the screen, which on this
    # axis is the bright end (smaller magnitudes)
    assert after_top[3] - after_top[2] < before[3] - before[2]
    chart.reset_view()
    wheel2 = QWheelEvent(QPointF(float(bottom.x()), float(bottom.y())),
                         QPointF(0.0, 0.0), QPoint(0, 0), QPoint(0, 120),
                         Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False)
    chart.wheelEvent(wheel2)
    after_bottom = chart._bounds
    # zooming at the bottom keeps more of the bright end than zooming at
    # the top does: the two windows are genuinely different pieces
    assert abs(after_top[2] - after_bottom[2]) > 1e-4
    assert vp.width() > 0


def _scene_half():
    from nightscribe.gui.widgets.lightcurve_widget import _HALF
    return _HALF * 0.6


# ---------------- A3: the axis in the observer's units, and the look ----

def test_the_x_axis_speaks_in_civil_time_for_one_night():
    # A night is read in hours and a campaign's curve in dates: the span
    # decides the shape, the same way the tick's step decides its decimals.
    _app()
    chart = LightCurveChart()
    chart.set_data([{"mjd": 60297.63 + 0.004 * i, "mag": 12.35,
                     "err": 0.01, "filter": "V", "source": "measure",
                     "flags": []} for i in range(20)])
    texts = _scene_texts(chart)
    ticks_txt = [t for t in texts if len(t) == 5 and t[2] == ":"]
    assert len(ticks_txt) >= 2                 # HH:MM on the axis
    note = [t for t in texts if "MJD" in t]
    assert note and "UTC" in note[0]
    # the note carries the civil date AND the Julian number a report wants
    assert "60297.6" in note[0]


def test_the_x_axis_speaks_in_dates_when_the_curve_spans_months():
    _app()
    chart = LightCurveChart()
    chart.set_data([{"mjd": 60297.6 + 40.0 * i, "mag": 12.35,
                     "err": 0.01, "filter": "V", "source": "measure",
                     "flags": []} for i in range(20)])
    texts = _scene_texts(chart)
    # months and years, never a bare Julian number
    assert any(t.endswith("2024") or t.endswith("2025") for t in texts)
    assert not any(len(t) == 5 and t[2] == ":" for t in texts)


def test_the_month_name_follows_the_application_language(monkeypatch):
    # strftime follows the SYSTEM locale: a Spanish machine would print
    # "dic" inside an English interface, and a figure that mixes languages
    # is a figure nobody trusts.
    _app()
    import nightscribe.gui.pretty as pretty
    for lang, expected in (("es", "dic"), ("en", "Dec")):
        monkeypatch.setattr(pretty, "ui_lang", lambda lang=lang: lang)
        chart = LightCurveChart()
        chart.set_data([{"mjd": 60297.63, "mag": 12.35, "err": 0.01,
                         "filter": "V", "source": "measure",
                         "flags": []}])
        assert any(expected in t for t in _scene_texts(chart))


def test_the_plot_has_a_frame_and_not_just_a_floating_grid():
    # A measured figure says where its scale starts: two axis lines with
    # their short marks, over a fainter grid.
    _app()
    from PySide6.QtWidgets import QGraphicsLineItem
    chart = LightCurveChart()
    chart.set_data(_curve())
    lines = [it for it in chart.scene().items()
             if isinstance(it, QGraphicsLineItem)]
    # the two axes run the whole frame, and there are mark strokes
    long_h = [l for l in lines
              if abs(l.line().x2() - l.line().x1()) > 900]
    long_v = [l for l in lines
              if abs(l.line().y2() - l.line().y1()) > 900]
    short = [l for l in lines
             if 5.0 <= max(abs(l.line().x2() - l.line().x1()),
                           abs(l.line().y2() - l.line().y1())) <= 8.0]
    assert long_h and long_v and len(short) >= 3


# ---------------- the plot takes the shape of its window (A4) ----------

def _shown(width=1200, height=520):
    # A chart with a REAL viewport: the plot's shape follows the window, so
    # a test without one would measure the default 640x480 stand-in.
    _app()
    chart = LightCurveChart()
    chart.show()
    chart.resize(width, height)
    QApplication.processEvents()
    chart._do_fit()
    return chart


def test_the_plot_is_not_a_square_in_a_wide_window():
    # The observer's ask, and the reason the time axis had no room: a fixed
    # square fitted into a wide panel leaves two dead margins and squeezes
    # the labels. A light curve is horizontal; the plot stretches with it.
    chart = _shown(1200, 520)
    from nightscribe.gui.widgets.lightcurve_widget import _HALF
    assert chart._hx > 1.5 * _HALF          # clearly wider than tall
    # and the whole scene takes the window's proportions, so the fit FILLS
    # the panel instead of letterboxing
    r = chart.sceneRect()
    vp = chart.viewport()
    assert (r.width() / r.height()) == pytest.approx(
        vp.width() / float(vp.height()), rel=0.02)


def test_a_narrow_window_gets_a_narrow_plot_but_never_a_square():
    # Never narrower than a square: a tall, narrow panel would otherwise
    # ask for a plot with no width at all.
    chart = _shown(360, 700)
    from nightscribe.gui.widgets.lightcurve_widget import _HALF
    assert chart._hx == pytest.approx(_HALF)


def test_the_time_axis_can_be_zoomed_on_its_own():
    # "the X axis should be zoomable too": the wheel zooms both, Shift the
    # time only and Ctrl the magnitudes only.
    chart = _shown()
    chart.set_data(_curve(40))
    before = chart._bounds
    assert chart.zoom_window(2.0, axes="x") is True
    after = chart._bounds
    assert after[1] - after[0] < before[1] - before[0]      # time narrowed
    assert after[3] - after[2] == pytest.approx(before[3] - before[2])
    # and the other way round
    chart.reset_view()
    before = chart._bounds
    chart.zoom_window(2.0, axes="y")
    after = chart._bounds
    assert after[1] - after[0] == pytest.approx(before[1] - before[0])
    assert after[3] - after[2] < before[3] - before[2]


def test_the_labels_are_sized_in_pixels_and_do_not_grow_with_the_window():
    # A size in scene units grows and shrinks with the panel: a maximized
    # window would come out with giant labels. The reader's own size is in
    # pixels, and the conversion is exactly this.
    small = _shown(700, 380)
    big = _shown(1600, 900)
    assert small._scale != big._scale
    from PySide6.QtWidgets import QGraphicsSimpleTextItem
    for chart in (small, big):
        texts = [it for it in chart.scene().items()
                 if isinstance(it, QGraphicsSimpleTextItem)]
        assert texts
        for item in texts:
            rendered = item.font().pixelSize() * chart._scale
            # every label renders at its own size, within a pixel
            assert 9.0 <= rendered <= 14.0


def test_the_time_labels_get_room_to_breathe():
    # A date like "20 Sep 2026" takes twice the room of a "21:30", so the
    # axis asks for fewer ticks instead of letting them collide. The scene
    # units are roughly the tick font's own units, so this is an honest
    # measure of what the reader sees.
    from PySide6.QtWidgets import QGraphicsSimpleTextItem
    from PySide6.QtGui import QFontMetricsF
    chart = _shown(1200, 520)
    chart.set_data(_curve(40))                      # a night: 0.39 d
    items = [it for it in chart.scene().items()
             if isinstance(it, QGraphicsSimpleTextItem)
             and len(it.text()) == 5 and it.text()[2] == ":"]
    assert len(items) >= 3
    widths = [QFontMetricsF(it.font()).horizontalAdvance(it.text())
              for it in items]
    gaps = sorted(i.pos().x() for i in items)
    spacing = [b - a for a, b in zip(gaps, gaps[1:])]
    if spacing:
        assert min(spacing) > max(widths)      # never overlapping


# ---------------- the tooltip must not be left behind (report) --------

def _tooltip_items(chart):
    # @return: the hover bubbles still in the scene. They are the only
    #          MULTI-LINE text items on the chart (the axis note also says
    #          "MJD", so the line break is what tells them apart).
    from PySide6.QtWidgets import QGraphicsSimpleTextItem
    return [it for it in chart.scene().items()
            if isinstance(it, QGraphicsSimpleTextItem)
            and "\n" in it.text() and "MJD" in it.text()]


def test_a_clicking_session_never_leaves_bubbles_behind():
    # Reported: "if I click a point an annotation with its MJD and mag gets
    # pinned, and clicking again piles another one up, with no way to remove
    # them". It was the hover bubble: `clear()` (which runs on EVERY rebuild,
    # i.e. on every click) dropped its reference without taking it out of
    # the scene, because the bubble is added straight to the scene and not
    # through the registered add_item. Measured before the fix: one orphan
    # per click (1 -> 2 -> 3 -> 4).
    _app()
    chart = LightCurveChart()
    chart.resize(900, 500)
    chart.set_data(_curve(30))
    for n in range(4):
        chart._show_tooltip(QPointF(200.0, 200.0),
                            ["MJD 60600.%02d · mag 12.34" % n, "V · Series"])
        chart._build_scene()             # what a click does
    assert _tooltip_items(chart) == []   # nothing was left behind


def test_a_click_takes_the_bubble_away():
    # A click is a DECISION (select this point); leaving the bubble pinned
    # over the curve makes a decision look like a note stuck there.
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QMouseEvent
    _app()
    chart = LightCurveChart()
    chart.resize(900, 500)
    chart.set_data(_curve(30))
    chart._show_tooltip(QPointF(150.0, 150.0), ["MJD 60600.01 · mag 12.34"])
    assert chart._tooltip is not None
    press = QMouseEvent(QEvent.MouseButtonPress, QPointF(400.0, 200.0),
                        QPointF(400.0, 200.0), Qt.LeftButton,
                        Qt.LeftButton, Qt.NoModifier)
    chart.mousePressEvent(press)
    assert chart._tooltip is None
    assert _tooltip_items(chart) == []


def test_clearing_a_chart_takes_the_bubble_out_of_the_scene():
    # The base class contract: clear() leaves no item behind, registered or
    # not.
    _app()
    chart = LightCurveChart()
    chart.resize(900, 500)
    chart.set_data(_curve(5))
    chart._show_tooltip(QPointF(100.0, 100.0), ["MJD 1 · mag 2"])
    assert chart._tooltip is not None
    chart.clear()
    assert chart._tooltip is None
    assert chart._tip_panel is None
    assert _tooltip_items(chart) == []
