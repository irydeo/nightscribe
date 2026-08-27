############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: viz style presets and size override
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from nightscribe.viz import style  # noqa: E402


def test_sizes_has_panel_preset():
    # the in-GUI overview slot is 16:9, not the social media presets
    assert style.SIZES["panel"] == (1200, 675)
    assert style.SIZES["instagram"] == (1080, 1080)


def test_new_fig_panel_preset_inches():
    # dpi 100 default: figsize in inches is the preset divided by 100
    fig, _ax = style.new_fig("panel")
    w, h = fig.get_size_inches()
    assert (w, h) == (12.0, 6.75)
    assert fig.dpi == 100
    plt.close("all")


def test_new_fig_size_override_inches():
    # the re-render mode doubles the panel preset for crispness
    fig, _ax = style.new_fig("panel", size=(2400, 1350))
    w, h = fig.get_size_inches()
    assert (w, h) == (24.0, 13.5)
    plt.close("all")


def test_panel_squeezes_default_margins():
    # the dark matplotlib border is space for nothing in a GUI slot:
    # the panel preset tightens the left/right margins so the plot owns
    # the width (the slightly taller bottom holds the watermark footer)
    pf, _ = style.new_fig("panel")
    df, _ = style.new_fig("instagram")
    assert pf.subplotpars.left < df.subplotpars.left
    assert pf.subplotpars.right > df.subplotpars.right
    plot_w_p = pf.subplotpars.right - pf.subplotpars.left
    plot_w_d = df.subplotpars.right - df.subplotpars.left
    assert plot_w_p > plot_w_d
    plt.close("all")


def test_draw_orbit_panel_figure_dimensions():
    # a chart drawn for the panel keeps the preset figure, the override
    # doubles it (the PNG itself is tight-cropped on save — style.save)
    from nightscribe.viz import orbit_view
    els = {"a": 1.350, "e": 0.400, "i": 6.2,
           "q": 0.810, "Q": 1.890, "per": 560.0}
    out = "/tmp/_panel_orbit_test.png"
    fig = orbit_view.draw_orbit(dict(els), obj_name="t", out=out,
                                fmt="panel")
    w, h = fig.get_size_inches()
    assert (w, h) == (12.0, 6.75)
    fig2 = orbit_view.draw_orbit(dict(els), obj_name="t", out=out,
                                 fmt="panel", size=(2400, 1350))
    w, h = fig2.get_size_inches()
    assert (w, h) == (24.0, 13.5)
    import os
    assert os.path.exists(out) and os.path.getsize(out) > 10000
    os.remove(out)
    plt.close("all")
