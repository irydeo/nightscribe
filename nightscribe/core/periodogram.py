############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Period search module (series quality plan, phase C)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Find the period of a light curve and fold it.

Two classic tools, both pure numpy (ADR-004):

  * the generalised Lomb-Scargle periodogram with a floating mean
    (Zechmeister & Kürster 2009), which needs no re-centring and weights
    the points by their own errors;
  * the Phase Dispersion Minimisation of Stellingwerf (1978), which
    makes no assumption about the shape of the curve and so is the right
    cross-check for an eclipsing or a sawtooth variable.

Neither one invents a period out of a single night: what the module
always reports is how many cycles the baseline really covers, the
spectral window (the 1-day alias engine) and a false-alarm probability,
so the observer can tell a detection from an artefact. The plotting and
the folding live next door (`viz/phase_view.py`), and the honesty rules
are the ones of the plan (`docs/PLANS/series-quality.md`).
"""

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)

# Frequency grid: this many samples per peak of the spectral window, the
# usual oversampling for a Lomb-Scargle that must not miss a peak.
SAMPLES_PER_PEAK = 10
# Below this many cycles covered the period is not really constrained by
# the data (the classic one-night trap).
MIN_CYCLES = 2.0
# Bootstrap shuffles for the false-alarm probability. Cheap enough to be
# honest; the loop can be switched off for a huge series.
FAP_SHUFFLES = 120


def _as_arrays(t, y, dy=None):
    # @return: (t, y, w) float arrays with the bad points dropped, w the
    #          1/sigma^2 weights (1.0 when no errors were given)
    t = np.asarray(t, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    good = np.isfinite(t) & np.isfinite(y)
    if dy is not None:
        dy = np.asarray(dy, dtype=np.float64)
        good &= np.isfinite(dy) & (dy > 0.0)
    t, y = t[good], y[good]
    if dy is None:
        return t, y, np.ones(len(t), dtype=np.float64)
    return t, y, 1.0 / np.square(dy[good])


def baseline_days(t):
    # @return: the span of the observations in days
    t = np.asarray(t, dtype=np.float64)
    return float(np.max(t) - np.min(t)) if t.size else 0.0


def median_cadence_days(t):
    # @return: the median spacing in days, or None with fewer than 2 points
    t = np.sort(np.asarray(t, dtype=np.float64))
    if t.size < 2:
        return None
    gaps = np.diff(t)
    gaps = gaps[gaps > 0]
    return float(np.median(gaps)) if gaps.size else None


def frequency_grid(t, min_period_d=None, max_period_d=None,
                   samples_per_peak=SAMPLES_PER_PEAK):
    # The frequency grid of the search: from the shortest period the
    # cadence can resolve to the longest the baseline can hold, with
    # enough samples per peak that no peak falls between two grid points.
    # @args: t - times (days), min_period_d - shortest period to try
    #        (default: twice the median cadence), max_period_d - longest
    #        (default: the baseline itself, one cycle)
    # @return: (frequencies, min_period_d, max_period_d)
    span = baseline_days(t)
    cad = median_cadence_days(t)
    if max_period_d is None:
        max_period_d = span if span > 0.0 else 1.0
    if min_period_d is None:
        min_period_d = 2.0 * cad if cad else max_period_d / 50.0
    max_period_d = max(max_period_d, min_period_d * 1.001)
    f_min = 1.0 / max_period_d
    f_max = 1.0 / min_period_d
    df = 1.0 / (max(span, 1e-6) * max(1, int(samples_per_peak)))
    n = int(math.ceil((f_max - f_min) / df)) + 1
    n = max(n, 8)
    return np.linspace(f_min, f_max, n), min_period_d, max_period_d


def lomb_scargle(t, y, dy=None, frequencies=None, min_period_d=None,
                 max_period_d=None, samples_per_peak=SAMPLES_PER_PEAK,
                 chunk=512):
    # The generalised Lomb-Scargle periodogram with a floating mean: the
    # normalised power in 0..1, weighted by the points' own errors.
    # @args: t - times (days), y - magnitudes, dy - their errors,
    #        frequencies - the grid to evaluate (1/day), or None to build
    #        one from the baseline and the cadence, min/max_period_d and
    #        samples_per_peak - the grid parameters
    # @return: {"frequencies", "power", "min_period_d", "max_period_d"}
    t, y, w = _as_arrays(t, y, dy)
    if t.size < 4:
        return {"frequencies": np.empty(0), "power": np.empty(0),
                "min_period_d": min_period_d, "max_period_d": max_period_d}
    if frequencies is None:
        frequencies, min_period_d, max_period_d = frequency_grid(
            t, min_period_d, max_period_d, samples_per_peak)
    frequencies = np.asarray(frequencies, dtype=np.float64)
    ybar = float(np.sum(w * y) / np.sum(w))
    yc = y - ybar
    yy = float(np.sum(w * np.square(yc)))
    power = np.empty(frequencies.size, dtype=np.float64)
    for start in range(0, frequencies.size, chunk):
        block = frequencies[start:start + chunk]
        omega = 2.0 * math.pi * block
        arg2 = 2.0 * omega[:, None] * t[None, :]
        sin2 = np.sin(arg2)
        cos2 = np.cos(arg2)
        tau = np.arctan2(np.sum(w * sin2, axis=1),
                         np.sum(w * cos2, axis=1)) / (2.0 * omega)
        arg = omega[:, None] * (t[None, :] - tau[:, None])
        cos = np.cos(arg)
        sin = np.sin(arg)
        yc_c = np.sum(w * yc * cos, axis=1)
        yc_s = np.sum(w * yc * sin, axis=1)
        cc = np.sum(w * cos * cos, axis=1)
        ss = np.sum(w * sin * sin, axis=1)
        cs = np.sum(w * cos * sin, axis=1)
        det = cc * ss - cs * cs
        with np.errstate(divide="ignore", invalid="ignore"):
            fit = (yc_c * yc_c * ss + yc_s * yc_s * cc
                   - 2.0 * yc_c * yc_s * cs) / det
        fit = np.where(np.isfinite(fit), fit, 0.0)
        power[start:start + block.size] = np.clip(fit / yy, 0.0, 1.0)
    return {"frequencies": frequencies, "power": power,
            "min_period_d": min_period_d, "max_period_d": max_period_d}


def phase_dispersion(t, y, dy=None, periods=None, bins=10,
                     min_period_d=None, max_period_d=None,
                     samples_per_peak=SAMPLES_PER_PEAK):
    # Stellingwerf's Phase Dispersion Minimisation: bin the folded curve
    # and compare the scatter inside the bins with the scatter of the
    # whole set. Theta near 0 means a curve formed; it makes no
    # assumption about its shape.
    # @args: as lomb_scargle, plus bins - phase bins
    # @return: {"periods", "theta", "min_period_d", "max_period_d"}
    t, y, _w = _as_arrays(t, y, dy)
    if t.size < 4:
        return {"periods": np.empty(0), "theta": np.empty(0),
                "min_period_d": min_period_d, "max_period_d": max_period_d}
    if periods is None:
        freqs, min_period_d, max_period_d = frequency_grid(
            t, min_period_d, max_period_d, samples_per_peak)
        periods = 1.0 / freqs
    periods = np.asarray(periods, dtype=np.float64)
    var_all = float(np.sum(np.square(y - np.mean(y))))
    n = t.size
    theta = np.empty(periods.size, dtype=np.float64)
    for i, period in enumerate(periods):
        if not np.isfinite(period) or period <= 0.0:
            theta[i] = 1.0
            continue
        phase = np.mod(t / period, 1.0)
        idx = np.minimum((phase * bins).astype(np.int64), bins - 1)
        count = np.bincount(idx, minlength=bins).astype(np.float64)
        total = np.bincount(idx, weights=y, minlength=bins)
        total2 = np.bincount(idx, weights=np.square(y), minlength=bins)
        nz = count > 1
        # within-bin sum of squares, the textbook theta
        ss = float(np.sum(total2[nz] - np.square(total[nz]) / count[nz]))
        dof = float(np.sum(count[nz] - 1.0))
        theta[i] = (ss / dof) / (var_all / (n - 1)) if dof > 0.0 \
            and var_all > 0.0 else 1.0
    return {"periods": periods, "theta": theta,
            "min_period_d": min_period_d, "max_period_d": max_period_d}


def spectral_window(t, frequencies=None, samples_per_peak=SAMPLES_PER_PEAK):
    # The window function |sum exp(-2 pi i f t)|^2 / N^2: it says which
    # periods the OBSERVING PATTERN itself puts peaks at (the 1-day alias
    # of a single-site run is the classic one). A real period that sits
    # on a window peak cannot be told from the alias by this data alone.
    # @args: t - times (days), frequencies - the grid (or None)
    # @return: {"frequencies", "power"}
    t = np.asarray(t, dtype=np.float64)
    if frequencies is None:
        frequencies, _a, _b = frequency_grid(t, samples_per_peak=samples_per_peak)
    frequencies = np.asarray(frequencies, dtype=np.float64)
    power = np.empty(frequencies.size, dtype=np.float64)
    n = max(t.size, 1)
    for i, f in enumerate(frequencies):
        z = np.exp(-2.0j * math.pi * f * t)
        power[i] = float(np.abs(np.sum(z)) ** 2) / (n * n)
    return {"frequencies": frequencies, "power": power}


def _window_peaks(t, frequencies, power, n=4, min_period_d=None,
                  max_period_d=None):
    # @return: the strongest window peaks as [{"period_d", "power"}] away
    #          from the trivial f -> 0 one
    peaks = []
    for i in range(1, len(frequencies) - 1):
        if power[i] <= power[i - 1] or power[i] < power[i + 1]:
            continue
        if power[i] < 0.05:
            continue
        period = 1.0 / frequencies[i] if frequencies[i] > 0 else None
        peaks.append({"period_d": period, "frequency": float(frequencies[i]),
                      "power": float(power[i])})
    peaks.sort(key=lambda p: -p["power"])
    return peaks[:n]


def _refine(periods, power, index):
    # Parabolic refinement of a periodogram peak around a grid index.
    # @return: the refined period
    if index <= 0 or index >= len(power) - 1:
        return float(periods[index])
    y0, y1, y2 = power[index - 1], power[index], power[index + 1]
    denom = y0 - 2.0 * y1 + y2
    delta = 0.0 if abs(denom) < 1e-12 else 0.5 * (y0 - y2) / denom
    delta = float(np.clip(delta, -0.5, 0.5))
    f = 1.0 / float(periods[index])
    df = abs(1.0 / float(periods[index + 1]) - f)
    f_ref = f + delta * df
    return float(1.0 / f_ref) if f_ref > 0 else float(periods[index])


def false_alarm(power_max, t, y, dy=None, frequencies=None,
                shuffles=FAP_SHUFFLES, seed=7, chunk=512):
    # The false-alarm probability of a peak: the share of shuffled
    # versions of the SAME data whose best peak is at least as strong. It
    # only shuffles the magnitudes, so the observing pattern (and with it
    # the aliases) stays exactly as it was.
    # @args: power_max - the observed peak, the rest as lomb_scargle
    # @return: {"fap": float or None, "shuffles": n, "power_max": float}
    t, y, w = _as_arrays(t, y, dy)
    if t.size < 8 or power_max <= 0.0:
        return {"fap": None, "shuffles": 0, "power_max": float(power_max)}
    if frequencies is None:
        frequencies, _a, _b = frequency_grid(t)
    rng = np.random.default_rng(seed)
    hits = 0
    for _i in range(max(1, int(shuffles))):
        shuffled = rng.permutation(y)
        res = lomb_scargle(t, shuffled, None, frequencies=frequencies,
                           chunk=chunk)
        if res["power"].size and float(np.max(res["power"])) >= power_max:
            hits += 1
    return {"fap": (hits + 1.0) / (shuffles + 1.0), "shuffles": shuffles,
            "power_max": float(power_max)}


def find_period(t, y, dy=None, min_period_d=None, max_period_d=None,
                method="ls", samples_per_peak=SAMPLES_PER_PEAK,
                fap_shuffles=FAP_SHUFFLES):
    # Search for the period of a light curve, honestly: the peak, its
    # false-alarm probability, how many cycles the baseline really
    # covers, the window peaks and the aliases, and what the OTHER method
    # says about the same data (a detection that only one of the two sees
    # is a warning, not a period).
    #
    # @args: t - times (days, any zero point), y - magnitudes, dy - their
    #        errors, min/max_period_d - the search range, method - "ls",
    #        "pdm" or "both", samples_per_peak - grid oversampling,
    #        fap_shuffles - bootstrap shuffles (0 disables the FAP)
    # @return: {"period_d", "frequency", "power", "method", "fap",
    #          "cycles", "baseline_d", "n_points", "periodogram",
    #          "pdm", "window", "aliases", "notes", "warnings"}
    t, y, w = _as_arrays(t, y, dy)
    out = {"period_d": None, "frequency": None, "power": None,
           "method": method, "fap": None, "cycles": None,
           "baseline_d": baseline_days(t), "n_points": int(t.size),
           "periodogram": None, "pdm": None, "window": None,
           "aliases": [], "notes": [], "warnings": []}
    if t.size < 4:
        out["warnings"].append({"es": "Hacen falta al menos 4 puntos",
                                "en": "At least 4 points are needed"})
        return out
    grid, p_min, p_max = frequency_grid(t, min_period_d, max_period_d,
                                        samples_per_peak)
    ls = lomb_scargle(t, y, dy, frequencies=grid)
    pdm = phase_dispersion(t, y, dy, periods=1.0 / grid, bins=10)
    out["periodogram"] = {"frequencies": ls["frequencies"],
                          "power": ls["power"],
                          "min_period_d": p_min, "max_period_d": p_max}
    out["pdm"] = {"periods": pdm["periods"], "theta": pdm["theta"]}
    use_pdm = method in ("pdm", "both")
    if use_pdm:
        index = int(np.argmin(pdm["theta"]))
        period = float(pdm["periods"][index])
        # a minimum of theta: refine on the theta curve itself
        if 0 < index < len(pdm["theta"]) - 1:
            per = _refine(pdm["periods"], -pdm["theta"], index)
            if np.isfinite(per):
                period = per
        out["period_d"] = period
        out["power"] = float(1.0 - pdm["theta"][index])
        out["method"] = "pdm"
    else:
        index = int(np.argmax(ls["power"]))
        out["period_d"] = _refine(1.0 / ls["frequencies"], ls["power"],
                                  index)
        out["power"] = float(ls["power"][index])
    if out["period_d"]:
        out["frequency"] = 1.0 / out["period_d"]
        out["cycles"] = out["baseline_d"] / out["period_d"]
    # the false-alarm probability of the Lomb-Scargle peak (the PDM has
    # no closed form; it is reported as a cross-check instead)
    if fap_shuffles:
        ls_index = int(np.argmax(ls["power"]))
        fa = false_alarm(float(ls["power"][ls_index]), t, y, dy,
                         frequencies=grid, shuffles=fap_shuffles)
        out["fap"] = fa["fap"]
    # the observing window and the aliases it creates
    win = spectral_window(t, frequencies=grid)
    out["window"] = win
    out["aliases"] = _window_peaks(t, win["frequencies"], win["power"])
    out["notes"].extend(_notes(t, y, out, pdm, ls, use_pdm))
    return out


def _notes(t, y, out, pdm, ls, use_pdm):
    # Plain-language notes about what the search can and cannot say. The
    # ordering follows importance: what the data cannot support first.
    notes = []
    cycles = out.get("cycles")
    if cycles is not None and cycles < MIN_CYCLES:
        notes.append({
            "es": "La línea base cubre solo {:.1f} ciclos: el período no "
                  "está fijado por estos datos, solo acotado".format(cycles),
            "en": "The baseline covers only {:.1f} cycles: the period is "
                  "not fixed by this data, only bounded".format(cycles)})
    # the range ZOOMED matters as much as the peak: a search that reaches
    # periods longer than the baseline can hold invites an alias as the
    # answer, but only if the answer itself sits out there
    gram = out.get("periodogram") or {}
    longest = gram.get("max_period_d")
    baseline = out.get("baseline_d") or 0.0
    found = out.get("period_d")
    if (longest and baseline > 0.0 and found
            and longest > baseline / MIN_CYCLES
            and found > baseline / MIN_CYCLES):
        notes.append({
            "es": "El período encontrado no cabe dos veces en la línea base "
                  "({:.3f} d): el rango buscado llega a {:.3f} d y ahí "
                  "cualquier pico es un alias. Acota el rango o suma otra "
                  "noche".format(baseline, longest),
            "en": "The period found does not fit twice in the baseline "
                  "({:.3f} d): the range reaches {:.3f} d and any peak out "
                  "there is an alias. Narrow the range or add another "
                  "night.".format(baseline, longest)})
    if out.get("fap") is not None and out["fap"] > 0.01:
        notes.append({
            "es": "FAP {:.3f}: el pico puede ser ruido (por debajo de 0,01 "
                  "es una detección seria)".format(out["fap"]),
            "en": "FAP {:.3f}: the peak may be noise (below 0.01 is a "
                  "serious detection)".format(out["fap"])})
    if out.get("period_d") and use_pdm:
        index = int(np.argmax(ls["power"]))
        ls_period = 1.0 / ls["frequencies"][index]
        if abs(ls_period - out["period_d"]) / out["period_d"] > 0.02:
            notes.append({
                "es": "Lomb-Scargle y PDM no coinciden ({:.5f} d frente a "
                      "{:.5f} d): una de las dos está viendo un armónico o "
                      "un alias".format(ls_period, out["period_d"]),
                "en": "Lomb-Scargle and PDM disagree ({:.5f} d against "
                      "{:.5f} d): one of them is seeing a harmonic or an "
                      "alias".format(ls_period, out["period_d"])})
    aliases = [a for a in out.get("aliases") or []
               if a.get("period_d") and a["power"] > 0.2]
    if aliases and out.get("period_d"):
        near = [a for a in aliases
                if abs(a["period_d"] - out["period_d"]) / out["period_d"] < 0.1]
        if near:
            notes.append({
                "es": "El patrón de observación tiene un pico justo ahí: "
                      "comprueba con otra noche o con datos de la comunidad",
                "en": "The observing pattern peaks right there: check with "
                      "another night or with community data"})
    return notes


def fold(t, y, dy=None, period_d=None, epoch=None):
    # Fold a light curve at a period, in the plot's convention: phase
    # 0..1, repeated once so the eye sees a cycle whole.
    # @args: t - times (days), y - magnitudes, dy - errors, period_d - the
    #        period, epoch - the phase-0 reference (default: the first
    #        point)
    # @return: {"phase", "phase2", "mag", "err", "cycle", "period_d",
    #          "epoch"}
    t, y, w = _as_arrays(t, y, dy)
    if period_d is None or period_d <= 0.0 or t.size == 0:
        return {"phase": np.empty(0), "phase2": np.empty(0),
                "mag": np.empty(0), "err": np.empty(0),
                "cycle": np.empty(0), "period_d": period_d, "epoch": epoch}
    if epoch is None:
        epoch = float(np.min(t))
    phase = np.mod((t - epoch) / float(period_d), 1.0)
    cycle = np.floor((t - epoch) / float(period_d))
    err = np.sqrt(1.0 / w)
    return {"phase": phase, "phase2": phase + 1.0, "mag": y, "err": err,
            "cycle": cycle, "period_d": float(period_d),
            "epoch": float(epoch)}


def binned_curve(phase, mag, bins=30, phase_max=1.0):
    # The mean magnitude per phase bin: the shape without the noise, and
    # the honest way to compare two nights over the same phases.
    # @args: phase - 0..1, mag - the magnitudes, bins - how many,
    #        phase_max - the span to bin (1.0 or 2.0 for the doubled plot)
    # @return: {"phase", "mag", "n"}
    phase = np.asarray(phase, dtype=np.float64)
    mag = np.asarray(mag, dtype=np.float64)
    if phase.size == 0:
        return {"phase": np.empty(0), "mag": np.empty(0), "n": np.empty(0)}
    idx = np.minimum((phase / phase_max * bins).astype(np.int64),
                     bins - 1)
    idx = np.clip(idx, 0, bins - 1)
    count = np.bincount(idx, minlength=bins).astype(np.float64)
    total = np.bincount(idx, weights=mag, minlength=bins)
    centres = (np.arange(bins) + 0.5) * phase_max / bins
    good = count > 0
    return {"phase": centres[good], "mag": (total[good] / count[good]),
            "n": count[good]}


def phase_of_night(mjd):
    # The observing night of a point, for the fold's colouring (the
    # boundary sits at local noon, as in the series engine).
    # @return: an integer night key, or None
    if mjd is None:
        return None
    return int(math.floor(float(mjd) - 0.5))
