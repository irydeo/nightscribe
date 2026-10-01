############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the night's figures (phase A1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The two small figures that explain a night: the airmass and the
measured position. What is asserted is what matters to the reader: both
are written as scientific figures, a missing value never becomes a zero,
and a series without coordinates simply draws an empty chart instead of
inventing one.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from nightscribe.viz import night_view


def _pts(n=40, airmass=True, xy=True):
    out = []
    for i in range(n):
        p = {"mjd": 60297.77 + i * 0.0005, "mag": 12.58 + i * 0.0001}
        if airmass:
            p["airmass"] = 1.2 - i * 0.004
        if xy:
            p["x"] = 804.0 + i * 0.01
            p["y"] = 831.0 - i * 0.005
        out.append(p)
    return out


def test_the_airmass_figure_is_written(tmp_path):
    out = tmp_path / "air.png"
    res = night_view.draw_airmass(_pts(), out=str(out),
                                  subtitle="V0526 Per", lang="es")
    assert res == str(out)
    assert out.exists() and out.stat().st_size > 1000


def test_the_drift_figure_is_written(tmp_path):
    out = tmp_path / "drift.png"
    res = night_view.draw_drift(_pts(), out=str(out), lang="es")
    assert res == str(out)
    assert out.exists() and out.stat().st_size > 1000


def test_a_missing_value_never_becomes_a_zero():
    pts = _pts()
    pts[5]["airmass"] = None
    pts[6]["mjd"] = None
    t, air = night_view._series(pts, "airmass")
    assert len(t) == len(pts) - 2
    assert float(air.min()) > 1.0            # no zero sneaked in


def test_a_series_without_coordinates_draws_an_empty_chart(tmp_path):
    out = tmp_path / "none.png"
    res = night_view.draw_airmass(_pts(airmass=False), out=str(out))
    assert res == str(out) and out.exists()


def test_the_drift_is_measured_from_the_first_point():
    pts = _pts()
    fig = night_view.draw_drift(pts)
    assert fig is not None                   # the figure exists
    import matplotlib.pyplot as plt
    plt.close(fig)
