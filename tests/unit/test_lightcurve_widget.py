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


def test_widget_legend_suffixes():
    # legend rows carry the "indicative" / "catalog" suffixes (English
    # source strings — no .qm loaded in the test env, tr() passes through)
    pts = [
        {"mjd": 60600.0, "mag": 16.0, "err": 0.02, "filter": "Clear",
         "source": "survey:atlas"},
        {"mjd": 60601.0, "mag": 16.2, "err": 0.03, "filter": "Clear",
         "source": "quicklook"},
    ]
    chart = LightCurveChart()
    chart.set_data(pts)
    texts = _legend_texts(chart)
    assert any("catalog" in t for t in texts)
    assert any("indicative" in t for t in texts)
    # a manual-only set has no suffix at all
    chart2 = LightCurveChart()
    chart2.set_data([dict(pts[0], source="manual")])
    assert not any("·" in t for t in _legend_texts(chart2))


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
