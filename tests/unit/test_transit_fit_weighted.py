############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - test_transit_fit_weighted module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import numpy as np

from nightscribe.core.transit_fit import fit_transit, TransitFitConfig, model_mag


def test_fit_transit_weighted_improves_accuracy():
    # Synthetic transit with heteroscedastic errors
    np.random.seed(0)
    cfg = TransitFitConfig(
        period_d=1.0,
        inc_deg=90.0,
        u1=0.4,
        u2=0.3,
        tmid_prior=0.0,
        tmid_sigma=0.01,
        rprs_prior=0.1,
        a_rs_prior=10.0,
        detrend_policy="off",
        airmass=None,
    )
    true_tmid = 0.0
    true_rprs = 0.1
    true_a_rs = 10.0
    # times spanning 0.4 days around transit
    times = np.linspace(-0.2, 0.2, 60)
    # model magnitudes (no baseline offset)
    true_params = np.array([true_tmid, true_rprs, true_a_rs])
    mags = model_mag(times, true_params, cfg)
    # heteroscedastic uncertainties: small for even indices, large for odd
    sigma = np.where(np.arange(times.size) % 2 == 0, 0.005, 0.05)
    noise = np.random.normal(0.0, sigma)
    noisy = mags + noise
    # Weighted fit uses sigma, unweighted ignores it
    fit_weighted = fit_transit(times, noisy, sigma, cfg)
    fit_unweighted = fit_transit(times, noisy, None, cfg)
    # True depth (maximum magnitude increase during transit)
    true_depth = np.max(mags)
    # Weighted fit should yield a smaller error on the planet/star radius ratio (rprs)
    err_w = abs(fit_weighted["rprs"] - true_rprs)
    err_u = abs(fit_unweighted["rprs"] - true_rprs)
    assert err_w <= err_u, "Weighted fit did not improve rprs accuracy"
    # Chi-squared reduced for weighted fit should be near 1 (within 0.2)
    chi2 = fit_weighted.get("chi2_red")
    assert chi2 is not None
    assert abs(chi2 - 1.0) < 0.2, f"Weighted chi2_red out of expected range: {chi2}"
