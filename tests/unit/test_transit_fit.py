############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: transit model and fit (series plan, 7)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Transit model parity (D27) and the fitter (D28/D38). The parity test
uses batman as the reference and is skipped when it is not installed
(checklist 3 fallback). No network."""

import math

import numpy as np
import pytest

from nightscribe.core import transit_fit as tf


def test_model_matches_the_uniform_disk_limit():
    # With u1=u2=0 the model is a uniform disc; a sanity value at full
    # transit (z=0) is 1 - p^2 (the planet's area over the star's).
    p = 0.15
    fr = tf.transit_flux_ratio(np.array([0.0]), p, 0.0, 0.0)
    assert fr[0] == pytest.approx(1.0 - p ** 2, abs=1e-6)


def test_model_parity_against_batman():
    # D27: the numpy model reproduces the quadratic-limb-darkening model
    # to better than MODEL_PARITY_TOL (batman is a test-only reference).
    batman = pytest.importorskip("batman")
    u = [0.4, 0.3]
    p = 0.154
    a = 5.344
    per = 2.1500082
    params = batman.TransitParams()
    params.t0 = 0.0
    params.per = per
    params.rp = p
    params.a = a
    params.inc = 88.98
    params.ecc = 0.0
    params.w = 90.0
    params.u = u
    params.limb_dark = "quadratic"
    t = np.linspace(-0.2, 0.2, 121)
    model = batman.TransitModel(params, t)
    ref = model.light_curve(params)
    z = tf.separation(t, 0.0, a, per, 88.98)
    mine = tf.transit_flux_ratio(z, p, u[0], u[1])
    assert float(np.max(np.abs(mine - ref))) < tf.MODEL_PARITY_TOL


def test_fit_recovers_a_synthetic_transit():
    true = {"tmid": 2458107.71406, "rprs": 0.1541, "a_rs": 5.344}
    cfg = tf.TransitFitConfig(
        period_d=2.1500082, inc_deg=88.98, u1=0.4, u2=0.3,
        tmid_prior=true["tmid"] + 0.01, tmid_sigma=0.01,
        rprs_prior=0.15, a_rs_prior=5.344, detrend_policy="off")
    rng = np.random.default_rng(3)
    t = np.linspace(true["tmid"] - 0.18, true["tmid"] + 0.18, 200)
    z = tf.separation(t, true["tmid"], true["a_rs"], cfg.period_d,
                      cfg.inc_deg)
    truth = -2.5 * np.log10(tf.transit_flux_ratio(z, true["rprs"],
                                                  cfg.u1, cfg.u2))
    mags = truth + 12.5 + rng.normal(0.0, 0.002, t.size)
    fit = tf.fit_transit(t, mags, None, cfg)
    assert fit["ok"]
    assert fit["tmid"] == pytest.approx(true["tmid"], abs=0.002)
    assert fit["rprs"] == pytest.approx(true["rprs"], abs=0.005)
    assert fit["depth_mag"] == pytest.approx(truth.max(), rel=0.05)
    assert fit["chi2_red"] < 5.0


def test_fit_with_a_joint_airmass_detrend():
    # D13 reused: an airmass trend does not bias the recovered transit.
    true = {"tmid": 2458107.71406, "rprs": 0.1541, "a_rs": 5.344}
    rng = np.random.default_rng(5)
    t = np.linspace(true["tmid"] - 0.18, true["tmid"] + 0.18, 150)
    air = 1.0 + 0.4 * (t - t[0]) / (t[-1] - t[0])
    cfg = tf.TransitFitConfig(
        period_d=2.1500082, inc_deg=88.98, u1=0.4, u2=0.3,
        tmid_prior=true["tmid"] + 0.01, tmid_sigma=0.01,
        rprs_prior=0.15, a_rs_prior=5.344, detrend_policy="airmass",
        airmass=air)
    z = tf.separation(t, true["tmid"], true["a_rs"], cfg.period_d,
                      cfg.inc_deg)
    truth = -2.5 * np.log10(tf.transit_flux_ratio(z, true["rprs"],
                                                  cfg.u1, cfg.u2))
    trend = 0.08 * np.exp(-0.6 * air)
    mags = truth + 12.5 + trend + rng.normal(0.0, 0.002, t.size)
    fit = tf.fit_transit(t, mags, None, cfg)
    assert fit["ok"]
    assert fit["rprs"] == pytest.approx(true["rprs"], abs=0.006)


def test_gate_report_flags_and_never_relaxes():
    # A fit 5 % too small in Rp/Rs fails the frozen 5 % gate; a good one
    # passes. The thresholds are the module constants (D38).
    good = {"ok": True, "tmid": 2458107.7141, "tmid_err": 0.0009,
            "rprs": 0.1545, "rprs_err": 0.0030, "a_rs": 5.3, "a_rs_err": 0.1}
    rep = tf.gate_report(good, 2458107.71406, 0.00097, 0.1541, 0.0033)
    assert rep["passed"]
    bad = dict(good, rprs=0.17)
    assert not tf.gate_report(bad, 2458107.71406, 0.00097, 0.1541,
                              0.0033)["passed"]
    slow = dict(good, tmid=2458107.72)
    assert not tf.gate_report(slow, 2458107.71406, 0.00097, 0.1541,
                              0.0033)["passed"]
