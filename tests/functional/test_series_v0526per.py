############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Functional test: the V0526 Per series (quality plan,
# phase A/D2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The whole real series (244 frames, about 1 GB, outside the repo).

This is the end-to-end acceptance of the quality plan: the engine, with
the D44 alignment on, must follow the observer's own report (FotoDif)
frame by frame. The frames drift 134 arcsec and the FITS carry no WCS,
which is exactly the case that used to produce a worthless curve.

Set NIGHTSCRIBE_V0526_PER to the folder holding v526per-*Rcal.fit; the
test skips otherwise. The reference WCS, the comparison sequence and the
report are in tests/data/v0526per/.
"""

import json
import os
from pathlib import Path

import numpy as np
import pytest

from nightscribe.core import series_measure as sm
from nightscribe.core import wcs as wcs_mod

DATA = Path(__file__).resolve().parents[1] / "data" / "v0526per"
SERIES_DIR = os.environ.get("NIGHTSCRIBE_V0526_PER")
REF = json.loads((DATA / "reference.json").read_text(encoding="utf-8"))
SERIES = REF["series"]

# the acceptance numbers of the plan: the curve must follow the report
_MIN_CORR = 0.80
_MAX_RESID = 0.02


@pytest.fixture(scope="module")
def paths():
    if not SERIES_DIR:
        pytest.skip("set NIGHTSCRIBE_V0526_PER to the series folder")
    files = sorted(Path(SERIES_DIR).glob("v526per-*Rcal.fit"))
    if len(files) < 200:
        pytest.skip("the series folder does not hold the 244 frames")
    return [str(p) for p in files]


@pytest.fixture(scope="module")
def measured(paths):
    w = SERIES["wcs"]
    wcs = wcs_mod.Wcs(w["crval1"], w["crval2"], w["crpix1"], w["crpix2"],
                      w["cd"], w["naxis1"], w["naxis2"])
    entries = tuple(dict(name=e["name"], kind=e["kind"], star=e["star"])
                    for e in SERIES["entries"])
    cfg = sm.SeriesConfig(
        wcs=wcs, target_xy=tuple(SERIES["target_xy"]), comp_set=entries,
        band=SERIES["band"], fallback_band="V", align="coords",
        radii=(6.0, 10.0, 15.0), site_gain=2.3, site_ron=8.0,
        site_saturate=60000.0, site_lat=40.55, site_lon=-3.37,
        site_aperture_m=0.43, site_height_m=631.0, zp_mode="catalog")
    return sm.measure_series(paths, cfg)


def _report(path):
    # @return: (mjd, mag) of the observer's own reduction (FotoDif)
    text = Path(path).read_bytes().decode("latin-1")
    mjd, mag = [], []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("2460298."):
            try:
                mjd.append(float(parts[0]) - 2400000.5)
                mag.append(float(parts[1]))
            except ValueError:
                continue
    return np.asarray(mjd), np.asarray(mag)


def test_the_whole_series_is_measured(measured, paths):
    assert len(measured.points) == len(paths)
    mags = [p.mag for p in measured.points if p.mag is not None]
    # the measurement must survive the drift: no frame lost to the star
    # walking out of the aperture
    assert len(mags) >= 0.9 * len(paths)
    unusable = sum(1 for p in measured.points if "unusable" in p.flags)
    assert unusable == 0
    rep = measured.align_report
    assert rep and rep["n_failed"] == 0
    assert rep["shift_max_px"] > 80.0
    assert rep["rms_median_px"] < 0.5


def test_the_curve_follows_the_observer_report(measured):
    pts = [p for p in measured.points if p.mag is not None]
    t = np.asarray([p.mjd for p in pts])
    y = np.asarray([p.mag for p in pts])
    rmjd, rmag = _report(DATA / "reference_report.txt")
    assert len(rmjd) > 200
    on = np.interp(t, rmjd, rmag)
    a = y - np.median(y)
    b = on - np.median(on)
    corr = float(np.corrcoef(a, b)[0, 1])
    resid = float(np.std(a - b))
    assert corr >= _MIN_CORR, "the curve does not follow the report: r=%.3f" \
        % corr
    assert resid <= _MAX_RESID, "residual against the report: %.4f" % resid
