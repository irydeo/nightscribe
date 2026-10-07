############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the matched filter and the trail (P2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The best linear filter for a known shape, and the shape itself.

With a known PSF m (summing to one) and white noise sigma per pixel, the
best estimate of a star's flux is A = sum(m (p - sky)) / sum(m^2), and its
signal-to-noise is A sqrt(sum(m^2)) / sigma. That is not an opinion: it is
what Cauchy-Schwarz says about linear filters, and an aperture is the
special case m = 1 inside the circle, which gives the noisy wings the same
weight as the core.

These tests check it against the formula, not against a remembered number:
Monte Carlo over fresh noise, so the measured gain has to land on
sqrt(n_ap / n_eff), which is what the theory promises. And the trail: a
line smears a PSF into a Gaussian whose long axis carries the extra
variance L^2/12, so the elongation can be turned back into a length in
pixels, which is a number the observer can act on.
"""

import math
from pathlib import Path

import numpy as np
import pytest

from nightscribe.core import photometry as ph

SIZE = 81
FWHM = 3.5
SIGMA = 5.0
SKY = 1000.0


def _frame_with_star(rng, flux, x, y, psf, fwhm=FWHM):
    # @return: (frame, the exact position used). The star is rendered from
    #          the SAME PSF the measurement will be given, at a random
    #          sub-pixel position: the filter has to place it there.
    data = rng.normal(SKY, SIGMA, (SIZE, SIZE))
    if flux:
        fx, fy = x - math.floor(x), y - math.floor(y)
        m = ph._shift_psf(psf, fx, fy)
        mh = (m.shape[0] - 1) // 2
        ix, iy = int(math.floor(x)) - mh, int(math.floor(y)) - mh
        data[iy:iy + m.shape[0], ix:ix + m.shape[1]] += flux * m
    return data


def _measure(data, x, y, psf):
    # the aperture the APP would use for this seeing, so the comparison is
    # against the real choice and not against a straw man
    r_ap, r_in, r_out = ph.aperture_for_fwhm(FWHM)
    return ph.measure_matched(data, x, y, psf, r_ap=r_ap,
                              r_ann_in=r_in, r_ann_out=r_out, fwhm=FWHM)


def _moments(arr):
    # @return: (the variance along x, along y) of a normalised PSF
    n = arr.shape[0]
    c = (n - 1) / 2.0
    yy, xx = np.mgrid[0:n, 0:n]
    tot = arr.sum()
    return ((arr * (xx - c) ** 2).sum() / tot,
            (arr * (yy - c) ** 2).sum() / tot)


def test_the_psf_sums_to_one_and_carries_the_trail():
    psf = ph.gaussian_psf(FWHM)
    assert psf.sum() == pytest.approx(1.0)
    # a trailed PSF moves the light without adding any: the area is kept
    trailed = ph.gaussian_psf(FWHM, ratio=0.5, pa_deg=0.0)
    assert trailed.sum() == pytest.approx(1.0)
    # and it is wider ALONG the position angle than across it (0 = x), with
    # the area kept: a Gaussian's peak does not move, its shape does
    vx, vy = _moments(trailed)
    assert vx > 2.0 * vy
    vx0, vy0 = _moments(psf)
    assert vx0 == pytest.approx(vy0, rel=0.01)


def test_the_gain_is_what_the_theory_promises():
    # Monte Carlo: the same faint star in fresh noise, two hundred times.
    # The measured ratio of the two SNRs has to land on sqrt(n_ap/n_eff),
    # which is the formula's own prediction, so the test cannot drift from
    # the arithmetic it claims.
    rng = np.random.default_rng(21)
    psf = ph.gaussian_psf(FWHM)
    x, y = 40.3, 40.6
    ratios, flux_mf, flux_ap = [], [], []
    predicted = None
    # 400 ADU of flux is ~10 sigma on this sky: bright enough that the
    # aperture path always answers (a 3-sigma star is often not measurable
    # at all, which is a different question from this one)
    for _ in range(200):
        data = _frame_with_star(rng, 400.0, x, y, psf)
        res = _measure(data, x, y, psf)
        assert res["ok"], res.get("reason")
        ratios.append(res["snr"] / res["snr_ap"])
        predicted = math.sqrt(res["n_pix"] / res["n_eff"])
        flux_mf.append(res["flux"])
        flux_ap.append(res["flux_ap"])
    assert float(np.mean(ratios)) == pytest.approx(predicted, rel=0.05)
    # and it is a real gain, not a rounding: the effective area of the
    # filter is smaller than the aperture it replaces
    assert predicted > 1.2
    # the flux it returns is the star's, with less scatter than the
    # aperture's (the same noise, the same sky, the same centre)
    assert float(np.std(flux_mf)) < float(np.std(flux_ap))


def test_the_matched_flux_recovers_the_injected_flux():
    rng = np.random.default_rng(3)
    psf = ph.gaussian_psf(FWHM)
    got = []
    for _ in range(60):
        data = _frame_with_star(rng, 500.0, 40.5, 40.5, psf)
        got.append(_measure(data, 40.5, 40.5, psf)["flux"])
    assert float(np.mean(got)) == pytest.approx(500.0, rel=0.02)


def test_a_bright_star_and_an_aperture_agree():
    # At high SNR the two must agree: the filter is not a different
    # measurement, it is a better weighting of the same one. A disagreement
    # here would mean the filter is measuring something else.
    rng = np.random.default_rng(5)
    psf = ph.gaussian_psf(FWHM)
    res = _measure(_frame_with_star(rng, 20000.0, 40.5, 40.5, psf),
                   40.5, 40.5, psf)
    assert res["flux"] == pytest.approx(res["flux_ap"], rel=0.02)


def test_a_saturated_star_is_refused_by_both():
    # A clipped core is not a measurement, and the matched path must
    # inherit that verdict: it is measure_point's check, reused, not a
    # second opinion that could disagree.
    rng = np.random.default_rng(7)
    psf = ph.gaussian_psf(FWHM)
    data = _frame_with_star(rng, 4_000_000.0, 40.5, 40.5, psf)
    data = np.clip(data, None, 60000.0)          # the detector's ceiling
    r, ri, ro = ph.aperture_for_fwhm(FWHM)
    res = ph.measure_matched(data, 40.5, 40.5, psf, r_ap=r, r_ann_in=ri,
                             r_ann_out=ro, sat_adu=60000.0, fwhm=FWHM)
    assert res["ok"] is False


# ------------------------------------------------------------- the trail

def _trailed_psf(length_px, pa_deg=0.0, half=20):
    # A round PSF smeared by a uniform line of `length_px`: the convolution
    # sampled as a sum of shifted copies, which is what a trail IS, and it
    # reuses the same sub-pixel shift the filter will use.
    psf = ph.gaussian_psf(FWHM, half=half)
    if length_px <= 0:
        return psf
    acc = np.zeros_like(psf)
    steps = max(2, int(round(length_px)) * 4)
    ang = math.radians(pa_deg)
    for i in range(steps + 1):
        t = -length_px / 2.0 + length_px * i / steps
        acc += ph._shift_psf(psf, t * math.cos(ang), t * math.sin(ang))
    return acc / acc.sum()


def _trailed(rng, length_px, flux=20000.0, pa_deg=0.0):
    # @return: a frame with the trailed star in it, in fresh noise. The
    #          flux is high on purpose: the moment inversion is a shape
    #          measurement, and it needs the object to be there.
    psf = _trailed_psf(length_px, pa_deg=pa_deg)
    data = rng.normal(SKY, SIGMA, (SIZE, SIZE))
    x, y = 40.0, 40.0
    mh = (psf.shape[0] - 1) // 2
    data[int(y) - mh:int(y) - mh + psf.shape[0],
         int(x) - mh:int(x) - mh + psf.shape[1]] += flux * psf
    return data


@pytest.mark.parametrize("length_px", [3.0, 6.0, 10.0])
def test_the_trail_comes_back_in_pixels(length_px):
    # The moment inversion: a line of length L gives sigma_long^2 =
    # sigma^2 + L^2/12, so the measured extra variance has to give the
    # injected length back. Tolerance of 1 px, which is the discretisation
    # of the rendering plus the noise on ten realisations.
    vals = []
    for seed in range(10):
        el = ph.psf_elongation(_trailed(np.random.default_rng(200 + seed),
                                        length_px), 40.0, 40.0,
                               fwhm_px=FWHM)
        assert el["ok"], el.get("reason")
        assert el["significant"] is True
        vals.append(el["trail_px"])
    assert float(np.mean(vals)) == pytest.approx(length_px, abs=1.0)


def test_the_trail_angle_is_the_one_of_the_motion():
    # A trail along +y has to come back as the position angle 90, not as
    # 0: the observer uses this number to compare it with the ephemeris.
    vals = []
    for seed in range(10):
        el = ph.psf_elongation(_trailed(np.random.default_rng(300 + seed),
                                        8.0, pa_deg=90.0), 40.0, 40.0,
                               fwhm_px=FWHM)
        vals.append(el["pa_deg"])
    assert float(np.mean(vals)) == pytest.approx(90.0, abs=8.0)


def test_a_round_star_is_not_called_trailed():
    # Measured: a round star reads up to 1.45 px of trail at SNR ~20,
    # because the second moments of a noisy image are not exactly
    # isotropic. Calling that a trail would send the observer to shorten
    # an exposure that was already fine.
    for seed in range(10):
        rng = np.random.default_rng(400 + seed)
        data = _frame_with_star(rng, 20000.0, 40.0, 40.0,
                                ph.gaussian_psf(FWHM))
        el = ph.psf_elongation(data, 40.0, 40.0, fwhm_px=FWHM)
        assert el["ok"]
        assert el["significant"] is False, el["trail_px"]
        assert el["ratio"] == pytest.approx(1.0, abs=0.15)


def test_the_empirical_psf_ignores_one_bad_star():
    # The MEDIAN of the patches, so a cosmic ray in one star cannot become
    # part of the shape.
    rng = np.random.default_rng(19)
    clean = ph.gaussian_psf(FWHM, half=6)
    base = clean * 1000.0
    cutouts = [base + rng.normal(0, 2.0, base.shape) for _ in range(9)]
    cutouts[4][6, 6] = 50000.0        # the cosmic ray
    psf = ph.empirical_psf(cutouts)
    assert psf is not None
    assert psf.sum() == pytest.approx(1.0)
    # the spike did not survive: the centre holds the star's own value
    assert psf[6, 6] == pytest.approx(clean[6, 6], rel=0.25)


def _plate_with_known_flux(rng, flux=8000.0, n=8, fwhm=3.5):
    # @return: (image, entries, positions) a plate with n stars of the SAME
    #          known flux, which is what makes the zero point's error
    #          measurable: the catalogue IS the truth and the ZP absorbs any
    #          constant bias, so what is compared is the scatter.
    from nightscribe.core import photometry as _ph
    size = 400
    img = rng.normal(1000.0, 6.0, (size, size))
    entries, pos = [], []
    psf = _ph.gaussian_psf(fwhm, half=12)
    mh = (psf.shape[0] - 1) // 2
    # the TARGET too, at (200, 200): a plate whose target is not there has
    # nothing to calibrate and the comparison would measure that instead
    for k, (x, y) in enumerate([(200.0, 200.0)] + [
            (60.0 + 40.0 * j + 0.3, 60.0 + 37.0 * (j % 4) * 2 + 0.2)
            for j in range(n)]):
        ix, iy = int(x) - mh, int(y) - mh
        img[iy:iy + psf.shape[0], ix:ix + psf.shape[1]] += flux * psf
        if k == 0:
            continue                      # the target is not a comparison
        entries.append({"kind": "comp",
                        "star": {"ra": 0.0, "dec": 0.0, "name": f"c{k}",
                                 # the band list is where band_of reads the
                                 # value: a comp without it is skipped with
                                 # the reason "band" and there is no zero
                                 # point to compare
                                 "bands": [{"label": "G", "value":
                                            -2.5 * math.log10(flux)}]}})
        pos.append((x, y))
    return img, entries, pos


def test_the_zero_point_can_be_measured_with_the_filter(qapp=None):
    # P3 of the SNR campaign: the zero point has to come from the SAME method
    # as the target, or the difference between the two methods goes straight
    # into the magnitude. Measured on 8 injected stars of identical flux, the
    # filter's zero-point error is 2.6x smaller (0.035 against 0.092 mag).
    from nightscribe.core import photometry as _ph
    rng = np.random.default_rng(11)
    img, entries, pos = _plate_with_known_flux(rng)
    fwhm = 3.5
    radii = _ph.aperture_for_fwhm(fwhm)
    # each comp carries its own window with its position in it (the same
    # shape the astrometry run uses for the star stack's comps), so the test
    # needs no WCS: the recipe is what is being compared, not the mapping
    comps = [(img, x, y) for x, y in pos]
    # the ceiling explicitly: an empty header makes the app INFER it from the
    # plate, and on a synthetic plate that inference is what fails first
    base = dict(target_xy=(200.0, 200.0), entries=entries, radii=radii,
                fwhm=fwhm, require_catalog=True, comp_images=comps,
                site_saturate=50000.0)
    # the method is pinned on BOTH sides: the filter is the default now, and
    # a test that compares two methods has to say which one each call is
    ap = _ph.measure_plate(img, _ph.PlateConfig(matched=False, **base))
    mf = _ph.measure_plate(img, _ph.PlateConfig(matched=True, **base))
    assert ap.ok and mf.ok
    assert ap.zp["zp_err"] is not None and mf.zp["zp_err"] is not None
    assert mf.zp["zp_err"] < ap.zp["zp_err"]
    # both measure the SAME comps: the flag changes how, not which
    assert ap.zp["n"] == mf.zp["n"]


def test_the_matched_filter_is_the_app_default():
    # A MEASURED decision, not a taste: on real data the filter reaches 1.55
    # to 1.63x the aperture's SNR, its zero-point error is 2.6x smaller and
    # the brightness bias at low SNR is halved, for +3 % of runtime. The
    # default lives in the config, so every caller that does not say
    # otherwise measures with it, and the checkbox that turns it off starts
    # ticked.
    from nightscribe.core import photometry as _ph
    assert _ph.PlateConfig().matched is True
    # and the switch that turns it off is in the PANEL, one click away from
    # the measurement, not inside Advanced…: reported by the author on
    # 2026-10-07, who looked for it and did not find it there
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui.main_window import _load_ui
    dlg = _load_ui("ufe_measure_tab")
    assert dlg.chk_matched.isChecked() is True
    # the tooltip has to say what it is, what it produces AND the risks:
    # a figure or a switch without its meaning is what ADR-058 forbids. Since
    # 2026-10-07 it says it in WORDS and not with the figures of the case it
    # was measured on: those live in ADR-067 and in the code, and a help that
    # cites one visit ages badly (AGENTS.md, and the guard in
    # tests/unit/test_help_texts.py).
    tip = dlg.chk_matched.toolTip()
    assert "best linear estimator" in tip
    assert "about half as much again" in tip
    assert "two and a half times smaller" in tip
    assert "a few hundredths of a magnitude" in tip
    assert "1.55 to 1.63" not in tip
    assert "2025 UR" not in tip
    assert "RISKS" in tip
    # and the risks have to carry the measurement that was made, including
    # the one that goes AGAINST the filter (its flux follows the PSF, and
    # the aperture's does not)
    assert "its flux follows the shape of the star" in tip
    assert "measured against a real catalogue" in tip
    assert "UNDERESTIMATES the faint stars" in tip
    dlg.deleteLater()


def test_the_plate_says_whether_the_filter_was_actually_used():
    # The filter needs a seeing. With no FWHM (the comps could not be
    # measured on this stack) the APERTURE measures, and the caller that
    # reported the recipe's flag said "measured with the matched filter"
    # while the aperture had done it: the plate result has to say what
    # happened, not what was asked for.
    from nightscribe.core import photometry as _ph
    rng = np.random.default_rng(23)
    img, entries, pos = _plate_with_known_flux(rng)
    radii = _ph.aperture_for_fwhm(3.5)
    comps = [(img, x, y) for x, y in pos]
    base = dict(target_xy=(200.0, 200.0), entries=entries, radii=radii,
                require_catalog=True, comp_images=comps,
                site_saturate=50000.0)
    # with the seeing: the filter measures
    res = _ph.measure_plate(img, _ph.PlateConfig(matched=True, fwhm=3.5,
                                                 **base))
    assert res.ok and res.matched_used is True
    # without it: the aperture does, and the result says so
    res = _ph.measure_plate(img, _ph.PlateConfig(matched=True, **base))
    assert res.ok and res.matched_used is False
    # and with the filter off it is False too (nothing was asked)
    res = _ph.measure_plate(img, _ph.PlateConfig(matched=False, fwhm=3.5,
                                                 **base))
    assert res.ok and res.matched_used is False


# --------- the negative flux that killed a real run (2026-10-07) ----------

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_a_negative_matched_flux_comes_back_as_a_failure():
    # THE REAL CRASH. The filter correlates a PSF with the data, and on noise
    # that correlation comes out negative as often as positive. It used to be
    # returned with ok=True, and the callers take -2.5*log10(flux) with a
    # truthiness guard that a negative number passes: on the real 2025 FG18
    # visit (frame 15, target T18 at 306,1669) the filter said -845.6 ADU with
    # snr -0.97, and the whole 207-frame series died with "math domain error"
    # instead of marking one point as unmeasurable.
    #
    # The position below is a fixed one on the real AT2026acka plate where the
    # filter comes out negative while the APERTURE measures 662 ADU: the two
    # methods disagree, and that disagreement is exactly the case. Nothing
    # here is random.
    from nightscribe.core import fits_io
    _header, data = fits_io.read_fits(str(FIXTURES / "AT2026acka.fit"))
    fwhm = 4.5
    psf = ph.gaussian_psf(fwhm)
    r_ap, r_in, r_out = ph.aperture_for_fwhm(fwhm)
    r = ph.measure_matched(data, 403.4, 200.3, psf, r_ap=r_ap,
                           r_ann_in=r_in, r_ann_out=r_out, fwhm=fwhm)
    assert r["ok"] is False
    assert r["flux"] is None
    assert r["reason"]["es"] and r["reason"]["en"]
    # the aperture measured the same sky and it does have something to say:
    # that value is KEPT, because it is a different measurement of the same
    # star and the observer is entitled to see it
    assert (r["flux_ap"] or 0.0) > 0.0


def test_the_filter_never_says_ok_with_a_non_positive_flux():
    # The invariant the fix buys, over fresh noise: whatever the noise says,
    # ok=True means a POSITIVE flux. Before the fix this failed on empty-sky
    # realisations like these, and every one of those was a log10(negative)
    # waiting for a caller.
    rng = np.random.default_rng(4)
    psf = ph.gaussian_psf(FWHM)
    r_ap, r_in, r_out = ph.aperture_for_fwhm(FWHM)
    guarded = 0
    for _ in range(60):
        data = _frame_with_star(rng, 0.0, 40.0, 40.0, psf)      # empty sky
        ap = ph.measure_point(data, 40.0, 40.0, r_ap=r_ap,
                              r_ann_in=r_in, r_ann_out=r_out, fwhm=FWHM)
        r = ph.measure_matched(data, 40.0, 40.0, psf, r_ap=r_ap,
                               r_ann_in=r_in, r_ann_out=r_out, fwhm=FWHM)
        assert not (r["ok"] and (r.get("flux") or 0.0) <= 0.0)
        if not r["ok"]:
            assert r["flux"] is None and r["reason"]
            if ap["ok"] and (ap.get("flux") or 0.0) > 0.0:
                # the aperture HAD a measurement and the filter did not: the
                # exact shape of the crash, and it has to be reachable here or
                # the test is not testing the guard at all
                guarded += 1
    assert guarded > 0, "el camino del flujo negativo no se ha ejercitado"
