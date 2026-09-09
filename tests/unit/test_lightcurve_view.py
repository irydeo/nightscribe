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

from nightscribe.viz.lightcurve_view import draw_lightcurve


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
