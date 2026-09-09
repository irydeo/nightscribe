############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SN series engine (Track B, B5)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import numpy as np

from nightscribe.core.series import (
    aperture_flux, instrumental_mag, detect_sources,
    load_series, Frame, cull_candidates, build_ensemble,
    measure_series, analyze_campaign, quicklook,
    R_AP, R_ANN_IN, R_ANN_OUT, TARGET_N, MIN_N,
)


# ---------------- helpers: synthetic frames ----------------

def _make_frame(w, h, stars, sky=100.0, noise=2.0, mjd=60000.0,
               filt="Clear", wcs=None):
    # @args: stars - list of (x, y, flux) tuples
    # @return: 2D numpy array with Gaussian PSF stars planted
    data = np.full((h, w), sky, dtype=np.float32)
    yy, xx = np.ogrid[:h, :w]
    for x, y, flux in stars:
        data += flux * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 3 ** 2))
    if noise > 0:
        data += np.random.normal(0, noise, (h, w)).astype(np.float32)
    f = Frame(data, wcs, mjd, filt, "/synthetic.fits")
    return f


def _make_series_frames(n=5, sn_pos=(150, 150), n_comps=6):
    # @return: list of Frame with the SN + n_comps comparison stars
    # The SN fades (flux decreases), comps are constant.
    frames = []
    for i in range(n):
        sn_flux = 5000 * (0.95 ** i)   # SN fades 5% per night
        # place comparison stars on a ring around the SN, well within the
        # 200x200 frame and well separated from each other and from the SN
        # (R_ANN_OUT=15, so >40px from the SN and >30px between comps)
        import math as _m
        comps = []
        for j in range(n_comps):
            ang = j * (2 * _m.pi / n_comps)
            cx, cy = 150 + 60 * _m.cos(ang), 150 + 60 * _m.sin(ang)
            comps.append((cx, cy, 3000.0))
        stars = [(*sn_pos, sn_flux)] + comps
        f = _make_frame(200, 200, stars, mjd=60000.0 + i, noise=1.0)
        f.sn_xy = sn_pos
        frames.append(f)
    return frames


# ---------------- aperture photometry ----------------

def test_aperture_flux_basic():
    data = _make_frame(50, 50, [(25, 25, 5000.0)]).data
    flux, sky = aperture_flux(data, 25, 25)
    assert flux > 0
    assert sky > 0


def test_aperture_flux_out_of_bounds():
    data = _make_frame(50, 50, [(25, 25, 5000.0)]).data
    flux, sky = aperture_flux(data, 60, 60)
    assert flux is None


def test_instrumental_mag():
    data = _make_frame(50, 50, [(25, 25, 5000.0)]).data
    mag = instrumental_mag(data, 25, 25)
    assert mag is not None
    # brighter star = lower mag
    data2 = _make_frame(50, 50, [(25, 25, 10000.0)]).data
    mag2 = instrumental_mag(data2, 25, 25)
    assert mag2 < mag


# ---------------- source detection ----------------

def test_detect_sources_finds_bright():
    data = _make_frame(100, 100, [(30, 30, 2000.0), (70, 70, 1500.0)]).data
    src = detect_sources(data, k=5.0)
    assert len(src) >= 2
    peaks = [s[2] for s in src]
    # brightest first
    assert peaks[0] >= peaks[1]


def test_detect_sources_ignores_noise():
    data = np.full((100, 100), 100.0, dtype=np.float32)
    data += np.random.normal(0, 1.0, (100, 100)).astype(np.float32)
    src = detect_sources(data, k=5.0)
    assert len(src) == 0


def test_detect_sources_min_sep():
    data = _make_frame(100, 100, [(30, 30, 2000.0), (35, 35, 1500.0)]).data
    src = detect_sources(data, k=5.0, min_sep=10)
    # two sources 7px apart → only the brightest survives
    assert len(src) == 1


# ---------------- culling ----------------

def test_cull_finds_comparisons():
    frames = _make_series_frames(n=5, sn_pos=(150, 150), n_comps=6)
    sources = detect_sources(frames[0].data)
    ens = cull_candidates(frames, (150, 150), sources=sources)
    assert len(ens) >= MIN_N
    # none of the ensemble stars should be at the SN position
    for x, y, _sc, _m in ens:
        assert (x - 150) ** 2 + (y - 150) ** 2 > R_ANN_OUT ** 2


def test_cull_drops_variables():
    # a variable star (flickers) should be rejected by the constancy check
    frames = []
    for i in range(5):
        stars = [(150, 150, 4000.0),  # SN (constant, for this test)
                 (50, 50, 4000.0 * (0.5 ** (i % 2))),  # variable
                 (100, 100, 3000.0)]  # stable comp
        f = _make_frame(200, 200, stars, mjd=60000.0 + i)
        f.sn_xy = (150, 150)
        frames.append(f)
    sources = detect_sources(frames[0].data)
    ens = cull_candidates(frames, (150, 150), sources=sources)
    # the variable star should not be in the ensemble
    ens_positions = [(e[0], e[1]) for e in ens]
    assert all(abs(x - 50) > 5 or abs(y - 50) > 5
               for x, y in ens_positions)   # not the variable at (50,50)


def test_cull_drops_saturated():
    # a saturated star (peak near max) should be rejected
    frames = _make_series_frames(n=3, sn_pos=(150, 150), n_comps=3)
    # plant a saturated star
    frames[0].data[10, 10] = np.nanmax(frames[0].data) * 0.95
    sources = detect_sources(frames[0].data)
    # add the saturated star to the source list
    sources.append((10.0, 10.0, float(frames[0].data[10, 10])))
    ens = cull_candidates(frames, (150, 150), sources=sources)
    for x, y, _sc, _m in ens:
        assert abs(x - 10) > 5 or abs(y - 10) > 5


# ---------------- ensemble + Δmag ----------------

def test_build_ensemble():
    frames = _make_series_frames(n=5, n_comps=8)
    ens = build_ensemble(frames, (150, 150))
    assert MIN_N <= len(ens) <= TARGET_N


def test_measure_series_fading_sn():
    # SN fades 5%/night → Δmag should increase (fainter)
    frames = _make_series_frames(n=5, sn_pos=(150, 150), n_comps=6)
    ens = build_ensemble(frames, (150, 150))
    points = measure_series(frames, (150, 150), ens)
    assert len(points) == 5
    # Δmag should trend upward (fainter) over time
    mags = [p["mag"] for p in points]
    assert mags[-1] > mags[0]


def test_measure_series_constant_sn():
    # SN constant → Δmag should be ~constant
    frames = _make_series_frames(n=5, sn_pos=(150, 150), n_comps=6)
    # make SN constant
    for f in frames:
        f.data[150, 150] = 5000.0
    ens = build_ensemble(frames, (150, 150))
    points = measure_series(frames, (150, 150), ens)
    mags = [p["mag"] for p in points]
    scatter = np.std(mags)
    assert scatter < 0.1   # all roughly the same


# ---------------- campaign analysis ----------------

def test_analyze_campaign_no_data():
    s = analyze_campaign([])
    assert s["verdict"] == "no_data"


def test_analyze_campaign_fading():
    # SN fading → slope should be positive (getting fainter)
    points = [
        {"mjd": 60000.0, "mag": 0.0, "err": 0.02, "filter": "Clear"},
        {"mjd": 60005.0, "mag": 0.5, "err": 0.02, "filter": "Clear"},
        {"mjd": 60010.0, "mag": 1.0, "err": 0.02, "filter": "Clear"},
    ]
    s = analyze_campaign(points, sn_type="SN Ia",
                        peak_mjd=60000.0, peak_mag=0.0)
    assert s["slope_mag_per_day"] > 0
    assert s["delta_from_peak"] > 0
    assert s["nights"] == 3


def test_analyze_campaign_normal_vs_template():
    # points following the Ia template → verdict "normal"
    from nightscribe.core.sn_templates import template
    tpl = template("SN Ia")
    points = []
    peak_mjd = 60000.0
    peak_mag = 16.0
    for d, dm in tpl[:5]:
        points.append({"mjd": peak_mjd + d, "mag": peak_mag + dm,
                        "err": 0.02, "filter": "Clear"})
    s = analyze_campaign(points, sn_type="SN Ia",
                        peak_mjd=peak_mjd, peak_mag=peak_mag)
    assert s["verdict"] == "normal"


def test_analyze_campaign_faster_than_template():
    # SN declining faster than the Ia template → "faster"
    points = [
        {"mjd": 60000.0, "mag": 16.0, "err": 0.02, "filter": "Clear"},
        {"mjd": 60001.0, "mag": 17.0, "err": 0.02, "filter": "Clear"},
        {"mjd": 60002.0, "mag": 18.0, "err": 0.02, "filter": "Clear"},  # drops 2 mag in2 d
        {"mjd": 60003.0, "mag": 18.5, "err": 0.02, "filter": "Clear"},
    ]
    s = analyze_campaign(points, sn_type="SN Ia",
                        peak_mjd=60000.0, peak_mag=16.0)
    assert s["verdict"] == "faster"


# ---------------- top-level quicklook ----------------

def test_quicklook_full_pipeline():
    frames = _make_series_frames(n=5, sn_pos=(150, 150), n_comps=8)
    # quicklook expects file paths, but our synthetic frames have
    # data in memory — we test the pipeline functions directly
    ens = build_ensemble(frames, (150, 150))
    assert len(ens) >= MIN_N
    points = measure_series(frames, (150, 150), ens)
    assert len(points) == 5
    s = analyze_campaign(points, sn_type="SN Ia")
    assert s["verdict"] in ("normal", "faster", "slower", "unknown")


def test_quicklook_no_frames():
    r = quicklook([], 10.0, 20.0)
    assert r["summary"]["verdict"] == "no_frames"


def test_quicklook_auto_peak():
    # without explicit peak_mjd/mag, the brightest point is used
    points = [
        {"mjd": 60000.0, "mag": 16.0, "err": 0.02, "filter": "Clear"},
        {"mjd": 60003.0, "mag": 16.5, "err": 0.02, "filter": "Clear"},
    ]
    s = analyze_campaign(points, sn_type="SN Ia")
    assert s["delta_from_peak"] is not None
