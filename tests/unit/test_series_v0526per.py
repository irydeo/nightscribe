############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit test: the V0526 Per series (quality plan, phase A)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Eight real frames of V0526 Per, cut to 512 x 512 around the target.

The observer's series drifts 134 arcsec in 2.9 h and the FITS carry no
WCS. Measured at fixed coordinates the star leaves the 6 px aperture
within a minute and the curve is worthless; with the D44 alignment the
same engine recovers the observer's own curve. This is the regression
that keeps the desastre from coming back: the synthetic fields the other
tests use are too kind to catch it.

The frames come from `make_fixture.py` (see that script for the
provenance and the reference WCS).
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from nightscribe.core import series_measure as sm
from nightscribe.core import wcs as wcs_mod

DATA = Path(__file__).resolve().parents[1] / "data" / "v0526per"
REF = json.loads((DATA / "reference.json").read_text(encoding="utf-8"))
CROP = REF["crop"]


def _wcs():
    w = CROP["wcs"]
    return wcs_mod.Wcs(w["crval1"], w["crval2"], w["crpix1"], w["crpix2"],
                       w["cd"], w["naxis1"], w["naxis2"])


def _config(align):
    entries = tuple(dict(name=e["name"], kind=e["kind"], star=e["star"])
                    for e in CROP["entries"])
    return sm.SeriesConfig(
        wcs=_wcs(), target_xy=tuple(CROP["target_xy"]), comp_set=entries,
        band=CROP["band"], fallback_band="Rc", align=align,
        radii=(6.0, 10.0, 15.0), site_gain=2.3, site_ron=8.0,
        site_lat=40.55, site_lon=-3.37, site_aperture_m=0.43,
        site_height_m=631.0, zp_mode="catalog")


@pytest.fixture(scope="module")
def paths():
    return [str(DATA / f"frame{n:03d}.fits") for n in CROP["frames"]]


def test_alignment_saves_the_real_series(paths):
    # the frames really drift: the engine has to say so
    res = sm.measure_series(paths, _config("coords"))
    assert len(res.points) == len(paths)
    rep = res.align_report
    assert rep is not None and rep["mode"] == "coords"
    assert rep["n_failed"] == 0
    assert rep["inherited"] == 0
    # the drift measured by hand on the real frames: (85, -21) px
    assert rep["shift_max_px"] == pytest.approx(87.6, abs=2.0)
    assert rep["shift_max_arcsec"] == pytest.approx(135.7, abs=5.0)
    # a translation, not a rotation: the star field only slides
    assert rep["angle_max_deg"] < 0.2
    # the stars verify the transform to a fraction of a pixel
    assert rep["rms_median_px"] < 0.5
    mags = [p.mag for p in res.points if p.mag is not None]
    assert len(mags) == len(paths)
    # the real light curve varies about 0.06 mag over these 2.9 h; a
    # broken alignment shows a range of a magnitude or more
    assert max(mags) - min(mags) < 0.15
    for p in res.points:
        assert "unusable" not in p.flags


def test_fixed_coordinates_lose_the_star(paths):
    # the same frames measured where the reference said: the star walks
    # out of the aperture and the curve goes (this is the bug the plan
    # exists for, kept as the failing half of the story)
    res = sm.measure_series(paths, _config("off"))
    mags = [p.mag for p in res.points if p.mag is not None]
    assert len(mags) < len(paths)
    flagged = [p for p in res.points
               if "unusable" in p.flags or "few_comps" in p.flags]
    assert flagged
    if len(mags) >= 2:
        assert max(mags) - min(mags) > 0.5


def test_alignment_report_speaks_plain_language(paths):
    res = sm.measure_series(paths, _config("coords"))
    msgs = sm.align_messages(res.align_report)
    assert msgs and all("es" in m and "en" in m for m in msgs)
    joined = " ".join(m["es"] for m in msgs)
    assert "alinea" in joined or "movió" in joined


def test_no_alignment_reports_nothing(paths):
    res = sm.measure_series(paths, _config("off"))
    assert res.align_report is None
    assert sm.align_messages(None) == []
