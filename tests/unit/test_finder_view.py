############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: finder / comparison chart (ADR-042)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import math

import numpy as np
import pytest

from nightscribe.core import compstars
from nightscribe.core.wcs import Wcs
from nightscribe.viz import finder_view

CENTER = (291.366, 42.784)
FOV_ARCMIN = 18.0


def _star(ra, dec, mag, star_id=None):
    return {"id": star_id or f"J{ra:.4f}{dec:+.4f}", "name": None,
            "ra": ra, "dec": dec, "mag": mag, "band": "G",
            "catalog": "Gaia EDR3",
            "bands": [{"label": "G", "value": mag, "err": 0.003,
                       "derived": False}],
            "bv": 0.6, "color_origin": "estimated", "vsx": None}


def _field():
    # a small synthetic field around CENTER (no network involved)
    stars = [
        _star(291.366, 42.790, 12.0),
        _star(291.300, 42.780, 12.5),
        _star(291.320, 42.750, 13.0),
        _star(291.400, 42.800, 13.5),
        _star(291.430, 42.760, 14.0),
        _star(291.380, 42.820, 14.5),
    ]
    variables = [{"oid": "1", "name": "V0001 Cyg", "type": "EA",
                  "period_d": 2.3, "ra": 291.310, "dec": 42.795,
                  "star": None, "distance_arcsec": 99.0}]
    return {"stars": stars, "variables": variables, "catalog": "gaia",
            "catalog_name": "Gaia EDR3", "band": "G", "center": CENTER,
            "fov_arcmin": FOV_ARCMIN, "vsx_warning": False}


def _entries(field):
    seq = compstars.propose_comps(field["stars"], target_mag=14.5,
                                  target_bv=0.6, n=3)
    return seq["comps"] + ([seq["check"]] if seq["check"] else [])


def _make_wcs():
    # 0.648 arcsec/pixel -> an 18' side over 1000 px, north up, east left
    scale = FOV_ARCMIN * 60.0 / 1000.0 / 3600.0
    cd = [[-scale, 0.0], [0.0, scale]]
    return Wcs(CENTER[0], CENTER[1], 500.5, 500.5, cd, 1000, 1000)


def test_draw_catalog_mode_no_image(tmp_path):
    out = tmp_path / "finder.png"
    fig = finder_view.draw_finder(
        _field(), target={"name": "V0001 Cyg", "ra": CENTER[0],
                          "dec": CENTER[1]},
        out=out, lang="es")
    assert out.exists() and out.stat().st_size > 0
    assert fig is not None


def test_draw_sequence_mode(tmp_path):
    field = _field()
    out = tmp_path / "seq.png"
    finder_view.draw_finder(field, entries=_entries(field), out=out,
                            lang="en")
    assert out.exists() and out.stat().st_size > 0


def test_draw_with_rgb_image_and_inverted_negative(tmp_path):
    yy, xx = np.mgrid[0:1000, 0:1000]
    img = np.dstack([xx / 1000.0, yy / 1000.0,
                     np.full((1000, 1000), 0.5)]).astype(np.float32)
    out = tmp_path / "rgb.png"
    finder_view.draw_finder(_field(), image=img, inverted=True,
                            negative=True, out=out)
    assert out.exists() and out.stat().st_size > 0


def test_draw_with_user_wcs(tmp_path):
    wcs = _make_wcs()
    img = np.random.default_rng(42).normal(0.2, 0.02,
                                           (1000, 1000)).astype(np.float32)
    field = _field()
    out = tmp_path / "wcs.png"
    finder_view.draw_finder(field, target={"name": "V0001 Cyg",
                                           "ra": CENTER[0],
                                           "dec": CENTER[1]},
                            entries=_entries(field), image=img, wcs=wcs,
                            out=out, lang="en")
    assert out.exists() and out.stat().st_size > 0


def test_canvas_geo_flips_to_plot_coordinates():
    # field_math is y-down (screen); the adapter returns y-up plot coords:
    # a star north of the centre must plot ABOVE it
    geo = finder_view._CanvasGeo(CENTER, FOV_ARCMIN, False)
    _, y_north = geo.to_xy(CENTER[0], CENTER[1] + 0.05)
    _, y_center = geo.to_xy(*CENTER)
    assert y_north > y_center
    # inverted view turns it around
    geo_inv = finder_view._CanvasGeo(CENTER, FOV_ARCMIN, True)
    _, y_inv = geo_inv.to_xy(CENTER[0], CENTER[1] + 0.05)
    assert y_inv < y_center


def test_wcs_geo_projection_matches_the_frame():
    # the WCS adapter maps the field centre to the middle of the frame
    geo = finder_view._WcsGeo(_make_wcs())
    x, y = geo.to_xy(*CENTER)
    assert x == pytest.approx(500.0, abs=1.0)
    assert y == pytest.approx(500.0, abs=1.0)
    # and the frame diagonal is 18' wide
    assert geo.fov_arcmin == pytest.approx(FOV_ARCMIN, rel=0.02)


def test_label_collision_cap():
    # 100 bright stars on a tight grid: the cap and the clearance rule
    # keep the label list short and non-overlapping
    stars = []
    for i in range(10):
        for j in range(10):
            stars.append(_star(CENTER[0] - 0.06 + i * 0.012,
                               CENTER[1] - 0.06 + j * 0.012,
                               12.0 + 0.01 * (i + j)))
    geo = finder_view._CanvasGeo(CENTER, FOV_ARCMIN, False)
    labelled = finder_view._label_positions(stars, geo)
    assert 0 < len(labelled) <= finder_view.MAX_LABELS
    clear = finder_view._LABEL_CLEAR * geo.width / 1000.0
    xy = [(s["_x"], s["_y"]) for s in labelled]
    for i, a in enumerate(xy):
        for b in xy[i + 1:]:
            assert math.hypot(a[0] - b[0], a[1] - b[1]) >= clear - 1e-6
