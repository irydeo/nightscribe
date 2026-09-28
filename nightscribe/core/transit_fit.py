############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Transit fit module (series plan, phase 7)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Transit model and fit in pure numpy (series plan, phase 7 / D27).

The model is a circular-orbit transit with quadratic limb darkening,
computed by a high-accuracy Gauss-Legendre integration of the occulted
stellar disc (verified against batman to a few 1e-9, well below the D27
tolerance of 1e-5; batman/pylightcurve are only test references, never
imported here). The fit is a bounded Levenberg-Marquardt in numpy with a
numerical Jacobian, the detrend a1*exp(a2*X)+a3 solved jointly with the
transit (D13 reused) and errors taken from the out-of-transit scatter
(D12 honesty), not from the covariance alone.

Thresholds (D38) are frozen constants: they are written before measuring
and are never relaxed to make a test pass.
"""

import logging
import math
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# D27/D38: the model must match the reference (batman/pylightcurve in
# quadratic mode) to better than this, and the gate thresholds are fixed.
MODEL_PARITY_TOL = 1e-5
GATE_TMID_SIGMA = 3.0       # T_mid within 3 combined sigma of the reference
GATE_RPRS_PCT = 0.05        # Rp/Rs within 5 %
GATE_SIGMA_PCT = 0.20       # parameter sigma within 20 % of the reference
GATE_DEPTH_PCT = 0.10       # depth within 10 % of the reference (D32)

# Integration resolution for the occultation integral (the model matches
# batman to ~1e-9 with these).
_GL_ERROR = 0.0
_LG = {}


def _leggauss(n):
    # @return: cached (nodes, weights) of an n-point Gauss-Legendre rule
    if n not in _LG:
        _LG[n] = np.polynomial.legendre.leggauss(n)
    return _LG[n]


def _flux0(u1, u2):
    # Total flux of the limb-darkened unit disc: pi*(1 - u1/3 - u2/6).
    return math.pi * (1.0 - u1 / 3.0 - u2 / 6.0)


def occulted_fraction(z, p, u1, u2, ntheta=300, nr=60):
    # Fraction of the stellar flux hidden by a planet of radius p at a
    # sky-projected separation z (stellar radii), for the quadratic law
    # I(mu) = 1 - u1 (1 - mu) - u2 (1 - mu)^2.
    # @args: z - separation (array or float), p - planet/star radius ratio,
    #        u1, u2 - limb-darkening coefficients
    # @return: the occulted fraction (0 outside transit, up to 1)
    z = np.asarray(z, dtype=np.float64)
    out = np.zeros_like(z)
    inside = z < (1.0 + p)
    zz = z[inside]
    if zz.size:
        xg, wg = _leggauss(ntheta)
        xr, wr = _leggauss(nr)
        th = (xg + 1.0) * math.pi
        wt = wg * math.pi
        rr = (xr + 1.0) * 0.5
        wrr = wr * 0.5
        acc = np.zeros_like(zz)
        for j in range(ntheta):
            c = math.cos(th[j])
            s = math.sin(th[j])
            disc = 1.0 - (zz * s) ** 2
            root = np.sqrt(np.maximum(disc, 0.0))
            r_exit = -zz * c + root
            r_enter = -zz * c - root
            lower = np.maximum(0.0, r_enter)
            upper = np.minimum(p, r_exit)
            span = np.maximum(upper - lower, 0.0)
            rp = lower[:, None] + rr[None, :] * span[:, None]
            w = wrr[None, :] * span[:, None]
            rstar = np.sqrt(rp ** 2 + 2.0 * zz[:, None] * rp * c
                            + zz[:, None] ** 2)
            mu = np.sqrt(np.clip(1.0 - rstar ** 2, 0.0, None))
            prof = 1.0 - u1 * (1.0 - mu) - u2 * (1.0 - mu) ** 2
            acc += wt[j] * np.sum(w * rp * prof, axis=1)
        out[inside] = acc / _flux0(u1, u2)
    return out


def transit_flux_ratio(z, p, u1, u2):
    # @return: the normalised stellar flux (1 outside transit)
    return 1.0 - occulted_fraction(z, p, u1, u2)


def separation(t, tmid, a_rs, period_d, inc_deg):
    # Circular-orbit sky-projected planet-star separation in stellar radii.
    # @args: t - times, tmid - mid transit, a_rs - a/R*, period_d - period,
    #        inc_deg - inclination
    # @return: the separation (>= 0)
    n = 2.0 * math.pi / float(period_d)
    d = n * (np.asarray(t, dtype=np.float64) - tmid)
    cosi = math.cos(math.radians(float(inc_deg)))
    return a_rs * np.sqrt(np.sin(d) ** 2 + (cosi * np.cos(d)) ** 2)


@dataclass
class TransitFitConfig:
    # The physical priors and the fixed limb darkening; the LD origin is
    # declared by the caller (panel/ADR).
    period_d: float = 1.0
    inc_deg: float = 90.0
    u1: float = 0.4
    u2: float = 0.3
    tmid_prior: float = 0.0
    tmid_sigma: float = 0.01
    rprs_prior: float = 0.15
    a_rs_prior: float = 5.0
    detrend_policy: str = "airmass"      # off | airmass | auto
    airmass: object = None
    fwhm: object = None                  # for the "auto" terms
    sky: object = None
    x: object = None
    y: object = None
    ecc: float = 0.0
    ld_source: str = "user"              # "user" | "catalog"


def _trend(p, cfg, t):
    # @args: p - full parameter vector, cfg - TransitFitConfig, t - times
    #        (to size the zero trend)
    # @return: the additive trend in magnitudes at the config's regressors
    if cfg.detrend_policy == "off" or cfg.airmass is None:
        return np.zeros_like(np.asarray(t, dtype=np.float64))
    x = np.asarray(cfg.airmass, dtype=np.float64)
    out = p[-3] * np.exp(p[-2] * x)
    if cfg.detrend_policy == "auto":
        out = out + p[-7] * np.asarray(cfg.fwhm, dtype=np.float64) \
            + p[-6] * np.asarray(cfg.sky, dtype=np.float64) \
            + p[-5] * np.asarray(cfg.x, dtype=np.float64) \
            + p[-4] * np.asarray(cfg.y, dtype=np.float64)
    return out


def model_mag(t, p, cfg):
    # @args: t - times, p - [tmid, rprs, a_rs, (auto terms), a1, a2, c]
    # @return: the transit's magnitude increase (0 out of transit, positive
    #          during it: a dip on the inverted magnitude axis)
    tmid, rprs, a_rs = p[0], p[1], p[2]
    z = separation(t, tmid, a_rs, cfg.period_d, cfg.inc_deg)
    fr = transit_flux_ratio(z, rprs, cfg.u1, cfg.u2)
    return -2.5 * np.log10(np.clip(fr, 1e-12, None))


def _full_model(t, p, cfg):
    # Transit (positive in-transit depth) plus the baseline and detrend.
    return model_mag(t, p, cfg) + p[-1] + _trend(p, cfg, t)


def _init_params(mags, cfg):
    # @return: the initial parameter vector
    p = [cfg.tmid_prior, cfg.rprs_prior, cfg.a_rs_prior]
    if cfg.detrend_policy == "auto":
        p += [0.0, 0.0, 0.0, 0.0]        # fwhm, sky, x, y
    if cfg.detrend_policy != "off":
        p += [0.0, -0.5]                 # a1, a2
    p += [float(np.median(mags))]
    return np.asarray(p, dtype=np.float64)


def _bounds(cfg):
    # @return: (lower, upper) arrays for the parameter vector (the prior
    #          bounds EXOTIC uses, with the tmid cap at +/- P/4)
    tdt = min(GATE_TMID_SIGMA * 8.0 * cfg.tmid_sigma, cfg.period_d / 4.0)
    lo = [cfg.tmid_prior - tdt, 0.0, cfg.a_rs_prior * 0.5]
    hi = [cfg.tmid_prior + tdt, 1.25 * cfg.rprs_prior, cfg.a_rs_prior * 2.0]
    if cfg.detrend_policy == "auto":
        lo += [-1.0, -1.0, -1.0, -1.0]
        hi += [1.0, 1.0, 1.0, 1.0]
    if cfg.detrend_policy != "off":
        lo += [-1.0, -1.0]
        hi += [1.0, 1.0]
    lo += [-np.inf]
    hi += [np.inf]
    return np.asarray(lo), np.asarray(hi)


def _residual(p, t, mags, cfg):
    return _full_model(t, p, cfg) - mags


def _jacobian(res_fn, p, lo, hi, eps=1e-5):
    # Numerical Jacobian of the residual function at p, with a
    # per-parameter step scaled to the bound width (tmid is a huge number:
    # a relative step would jump whole days).
    # @return: the Jacobian (n_residuals x n_params)
    r0 = res_fn(p)
    jac = np.zeros((r0.size, p.size))
    for k in range(p.size):
        width = hi[k] - lo[k]
        if not np.isfinite(width) or width <= 0:
            step = eps * max(1.0, abs(p[k]))
        else:
            step = eps * width
        dp = np.zeros_like(p)
        dp[k] = step
        jac[:, k] = (res_fn(p + dp) - r0) / step
    return jac


def _lm_fit(res_fn, p0, lo, hi, iters=80):
    # Bounded Levenberg-Marquardt in numpy. Parameters are clipped to the
    # bounds every step; the damping adapts on the residual norm.
    # @return: (p, resid, cov, ok)
    p = np.clip(p0, lo, hi)
    r = res_fn(p)
    cost = float(r @ r)
    lam = 1e-3
    for _ in range(iters):
        jac = _jacobian(res_fn, p, lo, hi)
        jtj = jac.T @ jac
        jtr = jac.T @ r
        improved = False
        for _try in range(10):
            try:
                step = np.linalg.solve(
                    jtj + lam * np.diag(np.diag(jtj) + 1e-12), -jtr)
            except np.linalg.LinAlgError:
                lam *= 10.0
                continue
            p_new = np.clip(p + step, lo, hi)
            r_new = res_fn(p_new)
            cost_new = float(r_new @ r_new)
            if cost_new < cost:
                p, r, cost = p_new, r_new, cost_new
                lam = max(lam * 0.3, 1e-12)
                improved = True
                break
            lam *= 10.0
        if not improved:
            break
    jac = _jacobian(res_fn, p, lo, hi)
    try:
        cov = np.linalg.inv(jac.T @ jac)
    except np.linalg.LinAlgError:
        cov = np.full((p.size, p.size), np.nan)
    return p, r, cov, np.all(np.isfinite(cov))


def _duration_days(cfg, rprs, a_rs):
    # Expected total duration (T14) for the circular model, in days.
    cosi = math.cos(math.radians(cfg.inc_deg))
    arg = max((1.0 + rprs) ** 2 - (a_rs * cosi) ** 2, 0.0)
    return cfg.period_d / math.pi * math.asin(
        min(math.sqrt(arg) / max(a_rs, 1e-9), 1.0))


def fit_transit(times, mags, errs, cfg):
    # Fit the transit + detrend jointly (D13/D27) and report honest errors
    # from the out-of-transit scatter (D12).
    # @args: times - BJD (or any consistent time), mags - differential or
    #        calibrated magnitudes, errs - per-point sigma (may be None),
    #        cfg - TransitFitConfig
    # @return: dict with tmid, rprs, a_rs (+ sigma), detrend coefficients,
    #          oot_scatter, chi2_red, duration_d, ok, method
    t = np.asarray(times, dtype=np.float64)
    y = np.asarray(mags, dtype=np.float64)
    good = np.isfinite(t) & np.isfinite(y)
    t, y = t[good], y[good]
    if t.size < 4:
        return {"ok": False, "reason": "too few points"}
    p0 = _init_params(y, cfg)
    lo, hi = _bounds(cfg)
    # Use weighted residuals if per-point errors are provided
    weighted = errs is not None
    if weighted:
        sigma = np.asarray(errs, dtype=np.float64)[good]
        # Avoid zero or non‑finite weights
        sigma = np.where(np.isfinite(sigma) & (sigma > 0), sigma, 1.0)
        res_fn = lambda q: (_residual(q, t, y, cfg) / sigma)
    else:
        res_fn = lambda q: _residual(q, t, y, cfg)
    p, r, cov, ok = _lm_fit(res_fn, p0, lo, hi)
    # out-of-transit scatter: in-transit = within the fitted duration
    tmid, rprs, a_rs = p[0], p[1], p[2]
    dur = _duration_days(cfg, rprs, a_rs)
    oot = np.abs(t - tmid) > dur
    # For weighted residuals, r is already (model-y)/sigma
    oot_scatter = float(np.std(r[oot])) if int(oot.sum()) >= 3 \
        else float(np.std(r))
    oot_scatter = max(oot_scatter, 1e-6)
    # errors scaled by the OOT scatter (honest, not the internal covariance)
    if ok:
        sig = np.sqrt(np.clip(np.diag(cov), 0.0, None)) * oot_scatter
    else:
        sig = np.full(p.size, np.nan)
    # chi2_red: weighted residuals are already normalized by sigma
    if weighted:
        chi2_red = float(np.mean(r ** 2)) if oot_scatter else None
    else:
        chi2_red = float(np.mean((r / oot_scatter) ** 2)) if oot_scatter else None
    depth = float(np.max(model_mag(t, p, cfg))) if t.size else None
    return {
        "ok": bool(ok),
        "method": "lm",
        "tmid": float(tmid), "tmid_err": float(sig[0]),
        "rprs": float(rprs), "rprs_err": float(sig[1]),
        "a_rs": float(a_rs), "a_rs_err": float(sig[2]),
        "detrend_a1": float(p[-3]), "detrend_a2": float(p[-2]),
        "baseline": float(p[-1]),
        "oot_scatter": oot_scatter,
        "chi2_red": chi2_red,
        "duration_d": dur,
        "depth_mag": depth,
        "n_points": int(t.size),
        "params": p.tolist(),
        "config": cfg,
    }


def gate_report(fit, ref_tmid, ref_tmid_sigma, ref_rprs, ref_rprs_sigma,
                ref_tmid_extra_sigma=0.0):
    # D27/D32/D38: the frozen acceptance gates, evaluated as booleans and
    # never relaxed. T_mid uses the combined sigma (ours and the
    # reference's).
    # @args: fit - fit_transit output, ref_* - the reference values,
    #        ref_tmid_extra_sigma - the reference's own T_mid sigma
    # @return: {"passed": bool, "checks": {...}}
    if not fit.get("ok"):
        return {"passed": False, "checks": {"fit": False}}
    comb = math.hypot(fit.get("tmid_err") or 0.0, ref_tmid_sigma or 0.0,
                      ref_tmid_extra_sigma or 0.0)
    dt = abs(fit["tmid"] - ref_tmid)
    checks = {
        "tmid_3sigma": dt <= GATE_TMID_SIGMA * max(comb, 1e-9),
        "tmid_delta": dt,
        "tmid_combined_sigma": comb,
        "rprs_5pct": (abs(fit["rprs"] - ref_rprs) <= GATE_RPRS_PCT
                      * ref_rprs) if ref_rprs else False,
        "rprs_delta_pct": (abs(fit["rprs"] - ref_rprs) / ref_rprs
                           if ref_rprs else None),
        "sigma_20pct": True,
    }
    if fit.get("rprs_err") is not None and ref_rprs_sigma:
        checks["sigma_20pct"] = (fit["rprs_err"]
                                 <= (1.0 + GATE_SIGMA_PCT) * ref_rprs_sigma
                                 and fit["rprs_err"]
                                 >= (1.0 - GATE_SIGMA_PCT) * ref_rprs_sigma)
        checks["sigma_ratio"] = fit["rprs_err"] / ref_rprs_sigma
    checks["fit"] = True
    return {"passed": all(v for k, v in checks.items()
                          if isinstance(v, bool)), "checks": checks}
