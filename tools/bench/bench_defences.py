############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometry engine benchmark: what the defences buy
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The centroid's two defences, measured in the case they were built for.

`gaussian_centroid(robust=True)` does two extra things, and both came from the
Photometrica tool of the group:

* DEBLENDING: it finds the other significant sources in the window, clamps the
  window by how close the nearest one is, and masks out the pixels that are
  closer to the neighbour than to the star;
* the CORE CAP: it clips a pixel that is brighter than the star's own core,
  because no real point spread function carries more light than its centre.

They cost real time (measured on the 2025 FG18 series: about 40 % of the
frame) and they buy about 1 % of scatter on a field of ISOLATED stars, which
is not the case they exist for. This bench puts them where they were born: a
target at a known distance from a brighter neighbour, which is what a
supernova next to a foreground star looks like (the 2026-09 AT2026acka case).

Two things are measured, because the defences live in the CENTROID and not in
the aperture:

* the POSITION error of the centroid (the direct effect), and
* the flux the observer ends up with (the effect they actually see),
plus the cost per call, measured on a star bright enough for the deblending to
run at all (a faint star has no locked peak and the defence never fires, which
is how the first version of this bench measured 0 ms of difference).

Usage:
    python tools/bench/bench_defences.py
"""

import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness as H                                    # noqa: E402
from nightscribe.core import photometry                # noqa: E402

MMAG = 2.5 / math.log(10.0) * 1000.0

# The synthetic frame: the sky, the noise and the seeing of the 2025 FG18
# visit, which is the worst of the corpus.
SKY = 1552.0
SIGMA_SKY = 118.0
FWHM = 4.6
SIZE = 160
NEIGHBOUR_FLUX = 60000.0
TARGET_FLUX = 40000.0
SEPARATIONS = (5.0, 6.0, 7.0, 9.0, 12.0, 16.0, 25.0)
TRIALS = 200


def _gauss(yy, xx, cx, cy, flux, fwhm):
    s = fwhm / 2.3548200450309493
    g = np.exp(-0.5 * (((xx - cx) ** 2 + (yy - cy) ** 2) / s ** 2))
    return g * (flux / g.sum())


def run(verbose=True):
    rng = np.random.default_rng(20261007)
    r_ap, r_in, r_out = photometry.aperture_for_fwhm(FWHM)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    cx, cy = SIZE / 2.0 + 0.37, SIZE / 2.0 + 0.21
    out = {}
    for sep in SEPARATIONS:
        nx, ny = cx + sep, cy
        rows = {"robust": [], "plain": [], "robust_pos": [], "plain_pos": [],
                "robust_fail": 0, "plain_fail": 0}
        for i in range(TRIALS):
            data = SKY + rng.normal(0.0, SIGMA_SKY, (SIZE, SIZE))
            data += _gauss(yy, xx, nx, ny, NEIGHBOUR_FLUX, FWHM)
            data += _gauss(yy, xx, cx, cy, TARGET_FLUX, FWHM)
            # the observer clicks the target: the click is not exact, and the
            # defences have to work from a realistic starting point
            click = (cx + rng.uniform(-1.0, 1.0), cy + rng.uniform(-1.0, 1.0))
            for label, robust in (("robust", True), ("plain", False)):
                r = photometry.measure_point(
                    data, click[0], click[1], r_ap=r_ap, r_ann_in=r_in,
                    r_ann_out=r_out, fwhm=FWHM, robust=robust)
                if not r.get("ok") or not r.get("flux"):
                    rows[label + "_fail"] += 1
                    continue
                rows[label].append((r["flux"] - TARGET_FLUX) / TARGET_FLUX)
                rows[label + "_pos"].append(
                    math.hypot(r["x"] - cx, r["y"] - cy))
        entry = {}
        for label in ("robust", "plain"):
            n, bias, sig = H.robust_stats(rows[label])
            _pn, _pm, psig = H.robust_stats(rows[label + "_pos"])
            entry[label] = {"n": n, "failed": rows[label + "_fail"],
                            "bias_mmag": (bias * MMAG if bias is not None
                                          else None),
                            "rms_mmag": (sig * MMAG if sig is not None
                                         else None),
                            "pos_rms_px": psig}
        out[sep] = entry
    if verbose:
        print(f"objetivo {TARGET_FLUX:.0f} ADU, vecino {NEIGHBOUR_FLUX:.0f} ADU "
              f"({NEIGHBOUR_FLUX / TARGET_FLUX:.1f}x), FWHM {FWHM} px, "
              f"{TRIALS} pruebas\n")
        print(f"{'separacion':>10s} | {'con defensas':>30s} | "
              f"{'sin defensas':>30s}")
        print(f"{'':>10s} | {'pos_rms':>8s} {'sesgo':>8s} {'rms':>7s} "
              f"{'fallos':>5s} | {'pos_rms':>8s} {'sesgo':>8s} {'rms':>7s} "
              f"{'fallos':>5s}")
        for sep in SEPARATIONS:
            a, b = out[sep]["robust"], out[sep]["plain"]
            print(f"{sep:9.0f}px | {a['pos_rms_px']:8.3f} {a['bias_mmag']:+8.1f} "
                  f"{a['rms_mmag']:7.1f} {a['failed']:5d} | "
                  f"{b['pos_rms_px']:8.3f} {b['bias_mmag']:+8.1f} "
                  f"{b['rms_mmag']:7.1f} {b['failed']:5d}")

    # the price: measured on a star BRIGHT enough for the deblending to run
    # (a faint one has no locked peak and the defence never fires)
    data = SKY + rng.normal(0.0, SIGMA_SKY, (SIZE, SIZE))
    data += _gauss(yy, xx, cx + 9.0, cy, NEIGHBOUR_FLUX, FWHM)
    data += _gauss(yy, xx, cx, cy, 300000.0, FWHM)

    def bench(robust, n=80):
        for _ in range(5):
            photometry.measure_point(data, cx, cy, r_ap=r_ap, r_ann_in=r_in,
                                     r_ann_out=r_out, fwhm=FWHM, robust=robust)
        t0 = time.perf_counter()
        for _ in range(n):
            photometry.measure_point(data, cx, cy, r_ap=r_ap, r_ann_in=r_in,
                                     r_ann_out=r_out, fwhm=FWHM, robust=robust)
        return (time.perf_counter() - t0) / n * 1000.0

    a, b = bench(True), bench(False)
    if verbose:
        print("\ncoste por medida (estrella brillante, el desmezclado SI corre):")
        print(f"  con defensas {a:.2f} ms | sin ellas {b:.2f} ms | "
              f"el desmezclado cuesta {a - b:.2f} ms ({a / b:.2f}x)")
    return out


def main():
    run()


if __name__ == "__main__":
    main()
