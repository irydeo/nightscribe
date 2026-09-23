############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: calibrated single-plate photometry (UFE, G1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""G1 acceptance tests: every item in the plan checklist, plus the
degraded paths. All plates are synthetic gaussians with a fixed seed
(the unseeded helper in test_series flaked once on a tight bound: we
keep the tight bounds, but with a deterministic seed)."""

import math

import numpy as np
import pytest

from nightscribe.core import photometry as phot

# same synthetic PSF as the series test suite
PSF_SIGMA = 3.0


def _plate(w, h, stars, sky=100.0, noise=0.0, seed=42):
    # @args: stars - list of (x, y, peak_amplitude)
    # @return: 2D float64 array with gaussian PSFs planted on a flat sky
    data = np.full((h, w), sky, dtype=np.float64)
    yy, xx = np.ogrid[:h, :w]
    for sx, sy, amp in stars:
        data += amp * np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2)
                             / (2 * PSF_SIGMA ** 2))
    if noise > 0.0:
        rng = np.random.default_rng(seed)
        data = data + rng.normal(0.0, noise, (h, w))
    return data


# ---------------- measure_point ----------------

def test_measure_point_recovers_centroid_and_flux():
    # @args: click slightly off the star position. The moment centroid
    # has an inherent window bias for an off-centre star, so the flux
    # here is checked with a generous 2 %; the tight lattice check is
    # its own test below (dead-centre click, no bias).
    plate = _plate(200, 200, [(102.4, 97.6, 8000.0)], noise=1.0)
    r = phot.measure_point(plate, 101.0, 98.0)
    assert r["ok"]
    assert r["reason"] is None
    # centroid lands near the true position, closer than the raw click
    assert abs(r["x"] - 102.4) < 0.5
    assert abs(r["y"] - 97.6) < 0.5
    assert (r["x"] - 102.4) ** 2 + (r["y"] - 97.6) ** 2 \
        < (101.0 - 102.4) ** 2 + (98.0 - 97.6) ** 2
    # net flux is the gaussian aperture fraction, sky gone
    expected = 8000.0 * 2 * math.pi * PSF_SIGMA ** 2 * (1 - math.exp(-2.0))
    assert r["flux"] == pytest.approx(expected, rel=2e-2)
    # sky estimate recovers the flat level; the aperture is the r=6 disc
    assert r["sky_pp"] == pytest.approx(100.0, abs=2.0)
    assert 100 <= r["n_pix"] <= 130
    assert 7000.0 < r["peak"] < 8200.0
    assert r["saturated"] is False


def test_measure_point_flux_is_the_aperture_net():
    # @args: star dead-centre on the click (symmetric window -> unbiased
    # centroid) and no noise: the net flux must hold the gaussian's
    # aperture fraction with the sky removed, and a bright unclipped
    # gaussian is a normal star, never "saturated".
    amp = 8000.0
    plate = _plate(200, 200, [(100.0, 100.0, amp)], noise=0.0)
    r = phot.measure_point(plate, 100.0, 100.0)
    assert r["ok"] and r["saturated"] is False
    expected = amp * 2 * math.pi * PSF_SIGMA ** 2 * (1 - math.exp(-2.0))
    assert r["flux"] == pytest.approx(expected, rel=1e-2)
    assert (r["x"] - 100.0) ** 2 + (r["y"] - 100.0) ** 2 < 1e-6
    assert r["sky_pp"] == pytest.approx(100.0, abs=1.0)
    assert 105 <= r["n_pix"] <= 120


def test_measure_point_guards_are_honest():
    # each guard says what is wrong, in both languages, without raising
    empty = _plate(200, 200, [], noise=0.0)
    out = phot.measure_point(empty, 100.0, 100.0)
    assert not out["ok"]
    assert set(out["reason"]) == {"es", "en"}

    # clipped star: the core is stuck at the ceiling, a plateau of
    # equal maxima (the honest signature of saturation on a plate)
    sat = _plate(200, 200, [(100, 100, 60000.0)], noise=0.0)
    sat = np.minimum(sat, 30000.0)
    r = phot.measure_point(sat, 100.0, 100.0)
    assert not r["ok"] and r["saturated"]
    assert r["peak"] is not None and r["n_pix"] > 0
    assert r["reason"]["en"] == "saturated"

    # known ceiling (settings or header): a high peak near it is refused
    # even without a plateau; well below it, the same star is fine
    bright = _plate(200, 200, [(100, 100, 8000.0)], noise=0.0)
    assert not phot.measure_point(bright, 100.0, 100.0,
                                  sat_adu=9000.0)["ok"]
    assert phot.measure_point(bright, 100.0, 100.0,
                              sat_adu=16000.0)["ok"]

    edge = _plate(200, 200, [(12, 100, 5000.0)])
    r = phot.measure_point(edge, 12.0, 100.0)
    assert not r["ok"] and not r["saturated"]
    assert r["reason"]["en"] == "too close to the edge"

    assert not phot.measure_point(empty, 250.0, 100.0)["ok"]
    assert not phot.measure_point(None, 50.0, 50.0)["ok"]


def test_frame_ceiling_reads_the_clipping_signature():
    # Dozens of pixels pinned at the frame maximum: the maximum is a
    # clipping level. One honest star's apex (a pixel or two) is not.
    clipped = _plate(200, 200, [(100, 100, 60000.0)])
    clipped = np.minimum(clipped, 30000.0)          # flat top at 30000
    assert phot.frame_ceiling(clipped) == 30000.0
    honest = _plate(200, 200, [(100, 100, 8000.0)])
    assert phot.frame_ceiling(honest) is None


def test_measure_point_rejects_soft_clipped_cores_without_a_card():
    # The 2026-09 field case: a CMOS plate with no SATURATE anywhere and
    # a soft roll-off (cores reach the ceiling in a pixel or two, never
    # the 25-px plateau). The frame's own clipping signature condemns
    # any peak next to it; far below it the same star is a normal read.
    plate = _plate(200, 200, [(100.0, 100.0, 8500.0)])
    plate[5:10, 5:35] = 9000.0      # 150 px pinned: the clipping level
    r = phot.measure_point(plate, 100.0, 100.0)
    assert not r["ok"] and r["saturated"]
    assert "clipped" in r["reason"]["en"]
    assert "9000" in r["reason"]["en"]
    low = _plate(200, 200, [(100.0, 100.0, 3000.0)])
    low[5:10, 5:35] = 9000.0
    assert phot.measure_point(low, 100.0, 100.0)["ok"]


# ---------------- sigma-clip on the sky annulus ----------------

def test_sigma_clipped_median_removes_hot_pixels():
    rng = np.random.default_rng(7)
    sky = rng.normal(200.0, 10.0, 400)
    hot = np.concatenate([sky, np.full(6, 5000.0)])
    med, kept = phot._sigma_clipped_median(hot)
    assert 190.0 < med < 210.0
    assert kept < hot.size               # the six hot pixels are gone
    assert kept >= 390                   # ...but the good sky survives
    # clip off: every sample stays in (the median is robust either way)
    med0, kept0 = phot._sigma_clipped_median(hot, iters=0)
    assert kept0 == hot.size
    assert 190.0 < med0 < 210.0
    # empty annulus degrades, does not raise
    assert phot._sigma_clipped_median(np.array([])) == (None, 0)


def test_measure_point_hot_pixel_in_annulus_is_ignored():
    plate = _plate(200, 200, [(100, 100, 8000.0)], noise=1.0)
    dirty = _plate(200, 200, [(100, 100, 8000.0)], noise=1.0)
    dirty[100, 113] = 9000.0             # hot pixel on the sky annulus
    clean = phot.measure_point(plate, 100.0, 100.0, sigma_clip=True)
    no_clip = phot.measure_point(dirty, 100.0, 100.0, sigma_clip=False)
    assert clean["ok"] and no_clip["ok"]
    assert abs(clean["flux"] - no_clip["flux"]) < 50.0


# ---------------- error: CCD equation (D2) ----------------

def test_ccd_flux_error_equation():
    g, ron, n, sky = 2.0, 5.0, 100, 10.0
    flux = 5000.0
    full = phot.ccd_flux_error(flux, sky, n, gain=g, ron=ron)
    expected = math.sqrt(flux / g + n * sky / g + n * ron ** 2 / g ** 2)
    assert full == pytest.approx(expected, rel=1e-9)
    # RON is optional; without a gain there is no equation at all
    two_terms = phot.ccd_flux_error(flux, sky, n, gain=g)
    assert two_terms == pytest.approx(
        math.sqrt(flux / g + n * sky / g), rel=1e-9)
    assert phot.ccd_flux_error(flux, sky, n) is None
    assert phot.ccd_flux_error(flux, sky, n, gain=0.0) is None
    # exptime is reserved for the dark current: it must not change the result
    assert phot.ccd_flux_error(flux, sky, n, gain=g, ron=ron, exptime=600.0) \
        == pytest.approx(full, rel=1e-12)


def test_mag_error():
    flux, ferr = 1000.0, 10.0
    assert phot.mag_error(flux, ferr) == pytest.approx(0.01086, rel=1e-9)
    assert phot.mag_error(0.0, ferr) is None
    assert phot.mag_error(flux, None) is None


# ---------------- zero-point calibration (D1: native catalog band) --------

def _plate_with_zp(n_comps=5, target_amp=7000.0, comp_amp=10000.0):
    # Synthetic plate: target at (120,120), comps on a 60 px ring (well
    # inside the frame, well separated: the r_out=15 annulus clears them).
    # The "catalog" magnitudes the test builds are an independent list
    # with a realistic spread, exactly like real catalog rows (D1: the
    # band is the catalog's native one; the core does not care which).
    # @return: (plate, target_result, comp_results, target inst mag)
    stars = [(120, 120, target_amp)]
    comp_pos = []
    for j in range(n_comps):
        ang = j * (2 * math.pi / n_comps)
        comp_pos.append((120 + 60 * math.cos(ang), 120 + 60 * math.sin(ang)))
        stars.append((comp_pos[-1][0], comp_pos[-1][1], comp_amp))
    plate = _plate(240, 240, stars, noise=1.0)
    target = phot.measure_point(plate, 119.0, 121.0)
    assert target["ok"]
    inst_target = -2.5 * math.log10(target["flux"])
    comp_results = []
    for sx, sy in comp_pos:
        r = phot.measure_point(plate, sx, sy)
        assert r["ok"], r
        comp_results.append(r)
    return plate, target, comp_results, inst_target


def test_zero_point_recovery_and_intrinsic_error():
    # @args: no external data; this is the acceptance test of the phase.
    # Each comp gets its OWN catalog offset (independent of the measured
    # flux, like real catalogue rows with a realistic 0.01-0.02 spread):
    # the pipeline must recover the median offset as the ZP, quote the
    # offsets' own spread as the error, and the residuals must be that
    # spread and nothing more.
    offsets = [22.30, 22.29, 22.33, 22.31, 22.32]
    _p, target, comps, inst_t = _plate_with_zp()
    inst = [-2.5 * math.log10(r["flux"]) for r in comps]
    cat = [im + off for im, off in zip(inst, offsets)]

    zp = phot.calibrate_zero_point(inst, cat)
    assert zp["n"] == 5
    assert zp["used"] == [0, 1, 2, 3, 4]
    # recovery: the inst terms cancel star by star, so the ZP is the
    # median offset, to float precision
    assert zp["zp"] == pytest.approx(22.31, abs=1e-4)
    # the residuals are exactly the offsets' own spread, per star
    got = sorted(round(res, 9) for res in zp["residuals"])
    assert got == pytest.approx(sorted(o - 22.31 for o in offsets),
                                abs=1e-6)
    # the quoted error is the honest 1.4826 * MAD / sqrt(n) of that spread
    zp_err = 1.4826 * 0.01 / math.sqrt(5)
    assert zp["zp_err"] == pytest.approx(zp_err, rel=1e-6)

    # the target in catalog magnitudes: inst + recovered ZP, same error
    mag, err = phot.calibrated_mag(inst_t, zp["zp"], zp["zp_err"], None)
    assert mag == pytest.approx(inst_t + 22.31, abs=1e-4)
    assert err == pytest.approx(zp_err, rel=1e-9)


def test_error_increases_with_ccd_equation():
    # with a gain, the quoted error also carries the photon noise
    _p, target, _comps, _inst_t = _plate_with_zp()
    flux_e, sky_adu, n = target["flux"], target["sky_pp"], target["n_pix"]
    g, ron = 2.0, 5.0
    full_err = math.hypot(
        phot.mag_error(flux_e,
                       phot.ccd_flux_error(flux_e, sky_adu, n,
                                           gain=g, ron=ron)),
        0.01)   # a small zp scatter as a stand-in
    assert full_err > 0.01            # the photon term adds, it does not cancel


def test_calibrate_zero_point_degenerate_cases():
    # nothing usable: None out, no raise
    zp = phot.calibrate_zero_point([None, None], [19.0, 19.0])
    assert zp["zp"] is None and zp["n"] == 0 and zp["residuals"] == []
    # one comp: it works, but the error is the honest generous floor
    one = phot.calibrate_zero_point([17.5], [20.0])
    assert one["zp"] == pytest.approx(2.5, rel=1e-9)
    assert one["zp_err"] == pytest.approx(phot.SINGLE_COMP_ZP_ERR)
    assert one["residuals"] == [0.0] and one["used"] == [0]
    # mixed: Nones and non-finite values are skipped, order is kept
    mixed = phot.calibrate_zero_point([17.5, float("nan"), None, 17.6],
                                      [20.0, 20.0, None, 20.2])
    assert mixed["n"] == 2 and mixed["used"] == [0, 3]
    assert mixed["zp"] == pytest.approx(
        (20.0 - 17.5 + 20.2 - 17.6) / 2.0, rel=1e-9)


# ---------------- calibrated_mag ----------------

def test_calibrated_mag():
    assert phot.calibrated_mag(18.4, None) == (None, None)
    mag, err = phot.calibrated_mag(18.4, 22.4)
    assert mag == pytest.approx(40.8, rel=1e-9)
    assert err == 0.0               # no error supplied: nothing added
    mag, err = phot.calibrated_mag(18.4, 22.4, 0.05, 0.03)
    assert mag == pytest.approx(40.8, rel=1e-9)
    assert err == pytest.approx(math.hypot(0.05, 0.03), rel=1e-9)


# ---------------- header_instrument (D2) ----------------

def test_header_instrument():
    hdr = {"GAIN": 1.5, "RDNOISE": 5.2, "EXPTIME": 180,
           "OBJECT": "M31", "WCSAXES": 2}
    out = phot.header_instrument(hdr)
    assert out == {"gain": 1.5, "ron": 5.2, "exptime": 180.0}
    # keyword case is irrelevant (fits_io lowercases; be robust anyway)
    out = phot.header_instrument({"gain": 2, "rdnoise": "4.0"})
    assert out["gain"] == 2.0 and out["ron"] == 4.0 and out["exptime"] is None
    # a string with units is not a number: degrade, do not guess
    out = phot.header_instrument({"GAIN": "1.5 e-/ADU"})
    assert out["gain"] is None
    # boolean cards and empty headers are not instrument numbers
    assert phot.header_instrument({"GAIN": True})["gain"] is None
    assert phot.header_instrument(None) == {"gain": None, "ron": None,
                                            "exptime": None}
    assert phot.header_instrument({}) == {"gain": None, "ron": None,
                                          "exptime": None}


# ---------------- phase H: quality pieces ----------------


def test_sky_plane_beats_the_median_on_a_ramp():
    # A tilted sky (galactic core): the plane fit is far less biased
    rng = np.random.default_rng(1)
    yy, xx = np.ogrid[:100, :100]
    ramp = 1000 + 25.0 * (xx - 50)         # 500 ADU across the ring
    data = ramp + rng.normal(0, 3, (100, 100))
    amp = 20000.0
    data = data + amp * np.exp(-((xx - 50.0) ** 2 + (yy - 50.0) ** 2)
                             / (2 * PSF_SIGMA ** 2))
    truth = amp * 2 * math.pi * PSF_SIGMA ** 2 * (1 - math.exp(-2.0))
    med = phot.measure_point(data, 50, 50, sky_mode="median")
    pla = phot.measure_point(data, 50, 50, sky_mode="plane")
    assert abs(pla["flux"] - truth) < abs(med["flux"] - truth)
    assert abs(pla["flux"] - truth) / truth < 0.02


def test_estimate_fwhm_and_aperture_scaling():
    plate = _plate(200, 200, [(100, 100, 9000.0), (60, 60, 7000.0)],
                   noise=0.5)
    fwhm = phot.estimate_fwhm(plate, [(100, 100), (60, 60)])
    assert fwhm == pytest.approx(2.3548 * PSF_SIGMA, rel=0.2)
    r_ap, r_in, r_out = phot.aperture_for_fwhm(fwhm)
    assert r_ap == pytest.approx(1.35 * fwhm, rel=1e-6)
    assert r_in > r_ap and r_out > r_in
    # absurd or missing seeing falls back to the series defaults
    assert phot.aperture_for_fwhm(None) == (phot.R_AP, phot.R_ANN_IN,
                                            phot.R_ANN_OUT)
    assert phot.aperture_for_fwhm(500.0) == (phot.R_AP, phot.R_ANN_IN,
                                             phot.R_ANN_OUT)
    # saturated stars are skipped
    hot = np.minimum(_plate(200, 200, [(100, 100, 60000.0)]), 30000.0)
    assert phot.estimate_fwhm(hot, [(100, 100)], sat_adu=30000.0) is None


def test_calibrate_with_color_recovers_slope():
    inst = [14.0, 14.1, 13.9, 14.05, 13.95, 14.02, 14.07]
    bvs = [0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5]
    k_true, zp_true = -0.08, 22.3
    cat = [i + zp_true + k_true * b for i, b in zip(inst, bvs)]
    out = phot.calibrate_with_color(inst, cat, bvs, target_bv=0.8)
    assert out["color_used"]
    assert out["zp"] == pytest.approx(zp_true, abs=1e-6)
    assert out["k"] == pytest.approx(k_true, abs=1e-6)
    assert out["n"] == 7 and out["used"] == list(range(7))
    # target far from the comps' mean colour carries colour uncertainty
    far = phot.calibrate_with_color(inst, cat, bvs, target_bv=2.5)
    assert far["target_color_err"] is not None
    near = phot.calibrate_with_color(inst, cat, bvs, target_bv=0.9)
    assert near["target_color_err"] <= far["target_color_err"]


def test_calibrate_with_color_clips_a_corrupt_comp():
    inst = [14.0, 14.1, 13.9, 14.05, 13.95, 14.02, 14.07]
    bvs = [0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5]
    k_true, zp_true = -0.08, 22.3
    cat = [i + zp_true + k_true * b for i, b in zip(inst, bvs)]
    cat[3] += 0.5                          # a corrupted comp (0.5 mag off)
    out = phot.calibrate_with_color(inst, cat, bvs)
    assert out["color_used"] and out["n"] == 6
    assert 3 not in out["used"]
    assert out["zp"] == pytest.approx(zp_true, abs=0.01)


def test_calibrate_with_color_falls_back_without_spread():
    inst = [14.0, 14.1, 13.9, 14.05]
    cat = [i + 22.3 for i in inst]
    out = phot.calibrate_with_color(inst, cat, [0.7] * 4)
    assert not out["color_used"] and out["k"] is None
    assert out["zp"] == pytest.approx(22.3, abs=1e-9)
    assert out["used"] == [0, 1, 2, 3]     # caller's indexes, not filtered


def test_saturation_ceiling_priority():
    cfg = type("C", (), {"get": lambda self, k, d=None:
                         {"ccd_saturate": 50000.0}.get(k, d)})()
    assert phot.saturation_ceiling({"SATURATE": 54000}, cfg) == 54000.0
    assert phot.saturation_ceiling({}, cfg) == 50000.0
    assert phot.saturation_ceiling({}, None) is None
    assert phot.saturation_ceiling({"SATURATE": "lots"}, None) is None


def test_scintillation_formula():
    # Young (1967): 0.064 * D^-2/3 * X^1.75 * (2t)^-1/2 * exp(-h/8000)
    s = phot.scintillation_mag(45.0, 60.0, 0.25, 600.0)
    x = phot.airmass_from_alt(45.0)
    expected = 1.086 * 0.064 * 0.25 ** (-2 / 3) * x ** 1.75 \
        * (120.0) ** -0.5 * math.exp(-600.0 / 8000.0)
    assert s == pytest.approx(expected, rel=1e-9)
    # shorter exposure -> more noise; higher site -> less
    assert phot.scintillation_mag(45.0, 10.0, 0.25, 600.0) > s
    assert phot.scintillation_mag(45.0, 60.0, 0.25, 2200.0) < s
    assert phot.scintillation_mag(45.0, None, 0.25, 600.0) is None
    # airmass clamped: horizon nonsense never explodes
    assert phot.airmass_from_alt(0.0) == pytest.approx(6.0, abs=0.01)
    assert phot.airmass_from_alt(90.0) == pytest.approx(1.0)


def test_combine_errors():
    assert phot.combine_errors(0.03, 0.04) == pytest.approx(0.05)
    assert phot.combine_errors(0.03, None, 0.04) == pytest.approx(0.05)
    assert phot.combine_errors(None, None) is None


# ---------------- phase I: refined centroid + suggested apertures -----


def test_refined_centroid_exact_on_a_clean_gaussian():
    plate = _plate(200, 200, [(100.4, 99.6, 9000.0)], noise=0.0)
    out = phot.refined_centroid(plate, 100, 100)
    assert out["ok"] and out["moved"]
    assert out["x"] == pytest.approx(100.4, abs=0.05)
    assert out["y"] == pytest.approx(99.6, abs=0.05)


def test_refined_centroid_beats_raw_on_a_faint_star_over_a_gradient():
    rng = np.random.default_rng(5)
    yy, xx = np.ogrid[:200, :200]
    data = 800 + 3.0 * (xx - 100) + rng.normal(0, 8, (200, 200))
    data = data + 250 * np.exp(-((xx - 103.7) ** 2 + (yy - 96.2) ** 2)
                               / (2 * 2.2 ** 2))
    ref = phot.refined_centroid(data, 104, 96)
    d_ref = math.hypot(ref["x"] - 103.7, ref["y"] - 96.2)
    raw = phot.measure_point(data, 104, 96, centroid_mode="raw")
    d_raw = math.hypot(raw["x"] - 103.7, raw["y"] - 96.2)
    assert d_ref < d_raw                    # the sky pull is gone
    assert d_ref < 0.1


def test_refined_centroid_guards_are_honest():
    empty = np.full((100, 100), 800.0)     # nothing to centre on
    out = phot.refined_centroid(empty, 50, 50)
    assert not out["ok"] and not out["moved"]
    assert out["x"] == 50.0 and out["y"] == 50.0
    assert phot.refined_centroid(empty, 500, 50)["ok"] is False


def test_measure_point_refined_is_the_default_and_raw_survives():
    plate = _plate(200, 200, [(100.4, 99.6, 9000.0)], noise=0.5)
    r = phot.measure_point(plate, 100, 100)
    assert r["ok"] and abs(r["x"] - 100.4) < 0.1
    raw = phot.measure_point(plate, 100, 100, centroid_mode="raw")
    assert raw["ok"]


def test_suggest_apertures_bright_isolated():
    rng = np.random.default_rng(3)
    plate = np.full((200, 200), 800.0) + rng.normal(0, 2, (200, 200))
    plate += 30000 * np.exp(-((xx := np.arange(200)[None, :]) - 100) ** 2
                            / (2 * 3.0 ** 2)
                            + -((yy := np.arange(200)[:, None]) - 100) ** 2
                            / (2 * 3.0 ** 2))
    s = phot.suggest_apertures(plate, 100, 100)
    assert 7.0 <= s["r_ap"] <= 12.0        # the 99 % plateau of a 3-sigma PSF
    assert s["r_ann_out"] > s["r_ann_in"] > s["r_ap"]
    assert any("99 %" in r["en"] for r in s["reasons"])
    assert all(set(r) == {"es", "en"} for r in s["reasons"])


def test_suggest_apertures_faint_picks_the_snr_peak():
    rng = np.random.default_rng(7)
    plate = 800 + rng.normal(0, 8, (200, 200))
    yy, xx = np.ogrid[:200, :200]
    plate = plate + 220 * np.exp(-((xx - 100.0) ** 2 + (yy - 100.0) ** 2)
                                 / (2 * 2.2 ** 2))
    s = phot.suggest_apertures(plate, 100, 100)
    assert s["r_ap"] <= 6.0                # small SNR-optimal aperture
    assert any("SNR" in r["en"] for r in s["reasons"])


def test_suggest_apertures_runaway_growth_falls_back_to_seeing():
    # The review case: a star whose local sky sits in a dip (the annulus
    # under-reads it) has a growth curve that never flattens, and the
    # 99 %-plateau rule inflated the aperture to the scan cap. The
    # suggestion must refuse the runaway and fall back to the seeing
    # aperture, saying why.
    rng = np.random.default_rng(9)
    yy, xx = np.ogrid[:200, :200]
    rr = np.sqrt((xx - 100.0) ** 2 + (yy - 100.0) ** 2)
    plate = 800.0 - 60.0 * np.exp(-((rr - 12.5) ** 2) / 8.0) \
        + rng.normal(0, 1.5, (200, 200))
    plate += 30000 * np.exp(-(rr ** 2) / (2 * 1.5 ** 2))
    s = phot.suggest_apertures(plate, 100, 100)
    fwhm = s["diag"]["fwhm"]
    assert s["r_ap"] <= phot._PLATEAU_MAX_FWHM * fwhm
    assert any("never flattens" in r["en"] for r in s["reasons"])
    assert all(set(r) == {"es", "en"} for r in s["reasons"])
    # and the healthy bright star keeps the plateau rule
    plate2 = 800.0 + rng.normal(0, 1.5, (200, 200))
    plate2 += 30000 * np.exp(-(rr ** 2) / (2 * 1.5 ** 2))
    s2 = phot.suggest_apertures(plate2, 100, 100)
    assert any("99 %" in r["en"] for r in s2["reasons"])


def test_suggest_apertures_neighbour_pulls_in():
    rng = np.random.default_rng(11)
    plate = np.full((200, 200), 800.0) + rng.normal(0, 2, (200, 200))
    yy, xx = np.ogrid[:200, :200]
    plate += 30000 * np.exp(-((xx - 100.0) ** 2 + (yy - 100.0) ** 2)
                            / (2 * 3.0 ** 2))
    plate += 20000 * np.exp(-((xx - 130.0) ** 2 + (yy - 100.0) ** 2)
                            / (2 * 3.0 ** 2))   # a neighbour 30 px away
    s = phot.suggest_apertures(plate, 100, 100)
    assert s["diag"]["nearest"] == pytest.approx(30.0, abs=3.0)
    assert s["r_ann_out"] < 30.0           # the annulus never touches it
    assert any("neighbour" in r["en"] for r in s["reasons"])


def test_suggest_apertures_flags_the_core_gradient():
    rng = np.random.default_rng(5)
    yy, xx = np.ogrid[:200, :200]
    data = 800 + 3.0 * (xx - 100) + rng.normal(0, 8, (200, 200))
    data = data + 250 * np.exp(-((xx - 100.0) ** 2 + (yy - 100.0) ** 2)
                               / (2 * 2.2 ** 2))
    s = phot.suggest_apertures(data, 100, 100)
    assert any("core" in r["en"] for r in s["reasons"])


# ---------------- phase I.5: the gaussian (matched-filter) centroid ---


def _noisy_star(snr, seed=3, sky=800.0, sig=8.0, pos=(103.7, 96.2)):
    rng = np.random.default_rng(seed)
    data = sky + rng.normal(0, sig, (200, 200))
    yy, xx = np.ogrid[:200, :200]
    amp = snr * sig * math.sqrt(2 * math.pi * 2.2 ** 2)
    data = data + amp * np.exp(-((xx - pos[0]) ** 2 + (yy - pos[1]) ** 2)
                               / (2 * 2.2 ** 2))
    return data


def test_gaussian_centroid_accuracy_by_snr():
    for snr, tol in ((100, 0.01), (10, 0.05)):
        d = _noisy_star(snr)
        g = phot.gaussian_centroid(d, 104, 96, fwhm=2.3548 * 2.2,
                                   sky_pp=800.0)
        assert g["ok"]
        assert math.hypot(g["x"] - 103.7, g["y"] - 96.2) < tol
        assert g["snr"] > 4


def test_gaussian_centroid_guards_are_honest():
    rng = np.random.default_rng(3)
    empty = 800 + rng.normal(0, 8, (200, 200))
    out = phot.gaussian_centroid(empty, 100, 100)
    assert not out["ok"] and not out["moved"]
    assert out["x"] == 100.0 and out["y"] == 100.0
    assert set(out["reason"]) == {"es", "en"}
    assert not phot.gaussian_centroid(empty, 500, 50)["ok"]
    # a single hot pixel has no gaussian correlation: refused
    weak = empty.copy()
    weak[96, 104] += 30.0
    assert not phot.gaussian_centroid(weak, 104, 96)["ok"]


def test_measure_point_gaussian_is_the_default():
    plate = _plate(200, 200, [(100.4, 99.6, 9000.0)], noise=0.5)
    r = phot.measure_point(plate, 100, 100)
    assert r["ok"]
    assert abs(r["x"] - 100.4) < 0.05
    # the alternatives stay available for the tests and odd cases
    assert phot.measure_point(plate, 100, 100,
                              centroid_mode="refined")["ok"]
    assert phot.measure_point(plate, 100, 100, centroid_mode="raw")["ok"]
