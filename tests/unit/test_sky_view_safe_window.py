############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: safe window drawn in the night sky chart (ADR-020)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from nightscribe.core import planner, horizon  # noqa: E402
from nightscribe.viz import sky_view  # noqa: E402

# same fixed site/target/date as test_horizon_safety.py: the object rises
# east, peaks ~48 deg and sets west, so it has a real safe span against the
# canonical sample horizon.
SAMPLE = "docs/limits-sample.hrz"
DATE = datetime.date(2026, 8, 28)
LAT, LON = 40.55, -3.37
RA, DEC = 45.0, 0.0


def _safe_args():
    # @return: (safe_window tuple, best_time) from the planner glue
    vis = planner._visibility(RA, DEC, LAT, LON, DATE, horizon.load(SAMPLE),
                              0.0, 3600)
    s, e = vis["safe_window"].split("|")
    sw = (datetime.datetime.fromisoformat(s), datetime.datetime.fromisoformat(e))
    bt = datetime.datetime.fromisoformat(vis["best_time"])
    return sw, bt


def test_draw_sky_safe_window_adds_artists():
    # the shaded safe span plus the start-by line are new artists on top
    # of the plain chart
    base = sky_view.draw_sky(RA, DEC, LAT, LON, "t", date=DATE)
    ax = base.axes[0]
    n_lines, n_patches = len(ax.lines), len(ax.collections)
    sw, bt = _safe_args()
    fig = sky_view.draw_sky(RA, DEC, LAT, LON, "t", date=DATE,
                            safe_window=sw, best_time=bt)
    ax = fig.axes[0]
    assert len(ax.lines) > n_lines
    assert len(ax.collections) >= n_patches
    # a legend entry for the safe window must exist
    labels = [t.get_text() for t in ax.get_legend().get_texts()] \
        if ax.get_legend() else []
    assert any("segura" in lbl for lbl in labels)
    plt.close("all")


def test_draw_sky_best_time_without_span():
    # no session planned yet: the meridian crossing is drawn as best time
    fig = sky_view.draw_sky(RA, DEC, LAT, LON, "t", date=DATE)
    ax = fig.axes[0]
    n_lines = len(ax.lines)
    fig = sky_view.draw_sky(RA, DEC, LAT, LON, "t", date=DATE,
                            best_time=datetime.datetime(2026, 8, 28, 5, 30))
    ax = fig.axes[0]
    assert len(ax.lines) > n_lines
    plt.close("all")


def test_draw_sky_plain_unchanged():
    # neither safe_window nor best_time: identical artist count to before
    fig = sky_view.draw_sky(RA, DEC, LAT, LON, "t", date=DATE)
    ax = fig.axes[0]
    fig2 = sky_view.draw_sky(RA, DEC, LAT, LON, "t", date=DATE,
                             safe_window=None, best_time=None)
    ax2 = fig2.axes[0]
    assert len(ax.lines) == len(ax2.lines)
    assert len(ax.collections) == len(ax2.collections)
    plt.close("all")


def test_draw_sky_transit_iso_strings():
    # The Exoplanet Archive's transit_times() returns t0/t1 as ISO strings
    # (enrich.py passes them through to transit["ingress"]/["egress"]).
    # draw_sky must accept both datetimes and ISO strings.
    fig = sky_view.draw_sky(RA, DEC, LAT, LON, "t", date=DATE,
                            transit={"name": "HAT-P-53b",
                                     "ingress": "2026-09-11T00:30:00+00:00",
                                     "egress": "2026-09-11T02:30:00+00:00"})
    ax = fig.axes[0]
    # the transit band is a Polygon/Patch, drawn only when ingress+egress parsed
    assert hasattr(ax, "patches") and ax.patches
    # the "tránsito" text annotation is drawn at the band mid-point
    texts = [t.get_text() for t in ax.texts]
    assert any("tránsito" in t or "transit" in t for t in texts)
    plt.close("all")
