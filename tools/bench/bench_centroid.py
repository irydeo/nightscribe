############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometry engine benchmark: the centroid, isolated
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""What does the centroid cost, and what does it buy? Synthetic truth.

The series A/B on real frames says the difference between engines lives in
the CENTROID (swapping the arithmetic alone changes nothing: the two
arithmetic paths agree to a few ppm). This isolates it: a synthetic frame
with the sky and the noise of a real one, a Gaussian of known flux at a
known place, and every centroid asked for the same thing.

Two clicks are used, because they answer different questions:

* an EXACT click (where the star really is): the centroid has nothing to
  fix, so whatever it changes is what it costs;
* a REALISTIC click (the observer's hand): the centroid has something to
  fix, so what it recovers is what it buys.

Two decisions keep this honest, and both were learned the hard way here:

* a FRESH noise realisation per trial. Reusing one frame measures the
  sensitivity to the sub-pixel phase, not the photometric scatter (the
  first version reported 9.5 mmag where the aperture's own noise is 43);
* a DETERMINISTIC click pattern and enough trials. With 150 random clicks
  the MAD-based sigma moved 20 % between runs, which is not a measurement:
  it is a coin toss with a decimal point.

The noise is drawn to match the 2025 FG18 visit (sky 1552 ADU, 118 ADU/px,
FWHM 4.6 px), the worst of the corpus.

Usage:
    python tools/bench/bench_centroid.py [--trials 600]
"""

import argparse
import math
import os
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engines as E                                    # noqa: E402
import harness as H                                    # noqa: E402
from nightscribe.core import photometry                # noqa: E402

MMAG = 2.5 / math.log(10.0) * 1000.0

SKY = 1552.0
SIGMA_SKY = 118.0
FWHM = 4.6
SIZE = 300

MODES = (
    ("sin centroide (posicion exacta)", "ours_none"),
    ("momentos (refined)", "ours_refined"),
    ("matched filter nuestro (robust)", "ours"),
    ("matched filter nuestro (no robust)", "ours_norobust"),
    ("photutils centroid_2dg", "pu"),
    ("photutils centroid_quadratic", "pu"),
)


def click_pattern(n, spread):
    # A deterministic grid of click offsets over the window the observer's
    # hand really covers: the same pattern for every engine and every run,
    # so two runs of this bench are two runs of the SAME experiment.
    # @return: [(dx, dy), ...] of length n
    if spread <= 0:
        return [(0.0, 0.0)] * n
    side = int(math.ceil(math.sqrt(n)))
    out = []
    for iy in range(side):
        for ix in range(side):
            fx = (ix + 0.5) / side * 2.0 - 1.0
            fy = (iy + 0.5) / side * 2.0 - 1.0
            out.append((fx * spread, fy * spread))
    return out[:n]


def run(fluxes, trials, click_spread, verbose=True):
    rng = np.random.default_rng(20261007)
    r_ap, r_in, r_out = photometry.aperture_for_fwhm(FWHM)
    kw = dict(r_ap=r_ap, r_ann_in=r_in, r_ann_out=r_out, fwhm=FWHM)
    clicks = click_pattern(trials, click_spread)
    out = {}
    for flux in fluxes:
        rows = {}
        for label, eng in MODES:
            rel, perr = [], []
            extra = {"centroid_func": "quadratic"} if "quadratic" in label \
                else {}
            for i, (dx, dy) in enumerate(clicks):
                base = SKY + rng.normal(0.0, SIGMA_SKY, (SIZE, SIZE))
                inj, xt, yt = H.inject(base, 150.0, 150.0, flux, FWHM,
                                       seed=1000 + i)
                if inj is None:
                    continue
                r = E.measure_with(eng, inj, xt + dx, yt + dy, **kw, **extra)
                if not r.get("ok") or not r.get("flux"):
                    continue
                rel.append((float(r["flux"]) - flux) / flux)
                perr.append(math.hypot(r["x"] - xt, r["y"] - yt))
            n, bias, sd = H.robust_stats(rel)
            _pn, _pm, psd = H.robust_stats(perr)
            se = (sd / math.sqrt(2.0 * n) * MMAG) if (sd and n) else None
            rows[label] = {"n": n,
                           "bias_mmag": bias * MMAG if bias is not None else None,
                           "rms_mmag": sd * MMAG if sd is not None else None,
                           "rms_se_mmag": se, "pos_rms_px": psd}
        out[flux] = rows
        if verbose:
            snr = flux / (SIGMA_SKY * math.sqrt(math.pi * r_ap ** 2))
            print(f"\nflujo {flux:.0f} ADU  (SNR de apertura {snr:.1f}, "
                  f"click {'exacto' if click_spread <= 0 else '+-%.1f px' % click_spread})")
            print(f"  {'centroide':34s} {'sesgo':>8s} {'rms':>8s} {'+-se':>6s} "
                  f"{'pos_rms':>8s} {'n':>4s}")
            for label, _eng in MODES:
                r = rows[label]
                if r["rms_mmag"] is None:
                    continue
                print(f"  {label:34s} {r['bias_mmag']:+8.2f} "
                      f"{r['rms_mmag']:8.2f} {(r['rms_se_mmag'] or 0):6.2f} "
                      f"{(r['pos_rms_px'] or 0):8.3f} {r['n']:4d}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=600)
    args = ap.parse_args()
    warnings.filterwarnings("ignore")
    print("=" * 78)
    print("CONTROL SINTETICO: cielo %.0f ADU, ruido %.0f ADU/px, FWHM %.1f px, "
          "%d pruebas" % (SKY, SIGMA_SKY, FWHM, args.trials))
    print("=" * 78)
    print("\n--- click EXACTO (el centroide no tiene nada que arreglar) ---")
    run((30000.0,), args.trials, 0.0)
    print("\n--- click REALISTA (uniforme +-1.5 px) ---")
    run((3000.0, 30000.0, 100000.0), args.trials, 1.5)


if __name__ == "__main__":
    main()
