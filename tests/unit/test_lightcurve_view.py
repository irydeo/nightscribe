############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SN light curve PNG (Track B, B4)
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

from nightscribe.viz import lightcurve_view
from nightscribe.viz.lightcurve_view import (
    draw_lightcurve, _source_class, _series_label, _series_style)


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


def test_draw_lightcurve_returns_figure(tmp_path):
    fig = draw_lightcurve(_POINTS)
    assert fig is not None


def test_draw_lightcurve_writes_png(tmp_path):
    out = tmp_path / "lc.png"
    draw_lightcurve(_POINTS, out=str(out))
    assert out.exists()
    assert out.stat().st_size > 1000


def test_draw_lightcurve_with_template(tmp_path):
    out = tmp_path / "lc_tpl.png"
    fig = draw_lightcurve(_POINTS, out=str(out), sn_type="SN Ia",
                          peak_mjd=60605.0, peak_mag=15.9)
    assert out.exists()
    # the figure should have at least 2 legend entries (Clear + template)
    leg = fig.axes[0].get_legend()
    assert leg is not None


def test_draw_lightcurve_empty_points():
    # no data — should not crash, returns a figure with defaults
    fig = draw_lightcurve([])
    assert fig is not None


def test_draw_lightcurve_auto_peak(tmp_path):
    # without explicit peak_mjd/mag, the brightest point is used
    out = tmp_path / "lc_auto.png"
    draw_lightcurve(_POINTS, out=str(out), sn_type="SN Ia")
    assert out.exists()


def test_draw_lightcurve_inverted_yaxis(tmp_path):
    # the Y axis must be inverted (fainter = up)
    fig = draw_lightcurve(_POINTS)
    ylim = fig.axes[0].get_ylim()
    # inverted means ylim[0] > ylim[1] (top > bottom in data terms)
    assert ylim[0] > ylim[1]


def test_draw_lightcurve_quicklook_open_marker(tmp_path):
    # quicklook points use a hollow marker; the figure should render
    # without error when mixed sources are present
    fig = draw_lightcurve(_POINTS, sn_type="SN Ia")
    assert fig is not None


# ---------------- B4: source styles + legend labels ----------------

def test_survey_source_classification():
    assert _source_class("survey:atlas") == "survey"
    assert _source_class("survey:ztf") == "survey"
    assert _source_class("quicklook") == "quicklook"
    assert _source_class("manual") == "manual"
    assert _source_class("paste") == "manual"
    assert _source_class(None) == "manual"


def test_survey_series_style_grey_hollow_dashed():
    colour, face, ls = _series_style("survey")
    assert colour == "#8a90a6"
    assert face == "none"     # hollow
    assert ls == "--"         # dashed
    colour, face, ls = _series_style("quicklook")
    assert colour is None and face == "none" and ls == "--"
    colour, face, ls = _series_style("manual")
    assert colour is None and face == "auto" and ls == "-"


def test_series_label_suffixes():
    assert "indicativo" in _series_label("Clear", "quicklook", "es")
    assert "indicative" in _series_label("Clear", "quicklook", "en")
    assert "catálogo" in _series_label("Clear", "survey", "es")
    assert "catalog" in _series_label("Clear", "survey", "en")
    assert "·" not in _series_label("Clear", "manual", "es")


def test_draw_lightcurve_survey_point_grey():
    # a survey-catalog point must land as a grey (hollow, dashed) series
    pts = [
        {"mjd": 60600.0, "mag": 16.0, "err": 0.02,
         "filter": "Clear", "source": "survey:atlas"},
        {"mjd": 60602.0, "mag": 16.4, "err": 0.02,
         "filter": "Clear", "source": "manual"},
    ]
    fig = draw_lightcurve(pts)
    ax = fig.axes[0]
    leg = ax.get_legend()
    labels = [t.get_text() for t in leg.get_texts()]
    assert any("catálogo" in l for l in labels)
    # the survey series handle carries the grey colour (errorbar →
    # LineCollection, so get_color() returns a list of rgba tuples)
    i = next(i for i, l in enumerate(labels) if "catálogo" in l)
    handle = leg.legend_handles[i]
    c = handle.get_color()
    if isinstance(c, (list, tuple)):
        c = c[0]
    from matplotlib.colors import to_hex
    assert to_hex(c) == "#8a90a6"


def test_draw_lightcurve_folded(tmp_path):
    # ADR-034 (D.4): the PNG export folds by the period, two cycles wide,
    # with the schematic sawtooth as the legend reference
    from nightscribe.core import hads
    out = tmp_path / "lc_fold.png"
    saw = hads.sawtooth_template(12.0, 0.5, 11.55)
    fig = draw_lightcurve(_POINTS[:3], out=str(out), fold_period_d=0.5,
                          schematic=saw)
    assert out.exists() and out.stat().st_size > 1000
    ax = fig.axes[0]
    assert ax.get_xlim() == (0.0, 2.0)
    assert ax.get_xlabel() in ("Fase", "Phase")
    leg = ax.get_legend()
    assert leg is not None
    labels = [t.get_text() for t in leg.get_texts()]
    assert any("esquemática" in l or "schematic" in l for l in labels)


def test_draw_lightcurve_unfolded_axis_unchanged(tmp_path):
    fig = draw_lightcurve(_POINTS[:3])
    ax = fig.axes[0]
    assert ax.get_xlabel() in ("Fecha (MJD)", "Date (MJD)")
