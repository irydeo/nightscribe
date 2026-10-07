############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Stack benchmark: depth by injection and recovery
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""How deep does a stack really go? Ask it, do not look at it.

A cleaner image is not a deeper one: interpolating lowers the pixel noise
WITHOUT adding information, and the noise that matters for a source is the
one inside its aperture. The only measurement that cannot be fooled is to put
a source of a KNOWN flux, at a KNOWN place, on a copy of the stack, measure it
back with the same recipe, and see what comes out.

Two stacks of the SAME 207 frames are compared (2025 FG18, object-tracked, the
object frozen and the stars as trails):

    ours    the app's own stack, built from Tycho's calibrated frames
    tycho   Tycho-Tracker's stack

The flux is in ADU on the same scale (same sky, same exposure, same frames),
so the curves are directly comparable; the zero point only appears to write
the answer in magnitudes.

The injected source is a POINT: in an object-tracked stack the object is a
point and the stars are the trails, so a point is what the observer is looking
for.

Usage:
    python tools/bench/bench_depth.py
"""

import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness as H                                    # noqa: E402
from nightscribe.core import fits_io, photometry       # noqa: E402

MMAG = 2.5 / math.log(10.0) * 1000.0

STACKS = {
    "ours": ("/home/boreal/.local/share/NightScribe/projects/117-2025_FG18/"
             "2025FG18_obs1_20250331T203044.fits"),
    "tycho": ("/home/boreal/Develop/astronomy/dataset/2025FG18/"
              "tycho_result.fit"),
}

# The ladder, in ADU of total flux above the sky. With the zero point below it
# spans magnitude 18.4 to 21.2, which is where this object lives.
FLUXES = (40.0, 60.0, 90.0, 140.0, 210.0, 320.0, 480.0, 700.0)
ZP = 25.3195          # Tycho's own zero point, only to say the answer in mag
FWHM = 4.6            # the frame's seeing: in a tracked stack the object is a
                      # point with the SINGLE frame's profile
TRIALS = 40           # positions per flux level
MARGIN = 90.0         # px from the edge
SNR_TARGET = 5.0


def mag_of(flux, zp=ZP):
    # @args: flux - ADU above the sky, zp - the zero point
    # @return: the magnitude, or None when the flux is not positive
    if not flux or flux <= 0:
        return None
    return zp - 2.5 * math.log10(flux)


def common_spots(stacks, n, seed=7, radius=20.0, bright_adu=100.0):
    # Positions that are CLEAN IN EVERY STACK, by a criterion that does not
    # depend on each stack's own noise: no pixel more than `bright_adu` above
    # the sky within `radius`. This is the honest way to share positions
    # between two images whose noise differs (and it differs by a lot here:
    # 5.9 against 10.2 ADU/px).
    #
    # Why it matters, measured: choosing the spots from each stack's OWN
    # noise test moved the answer by more than the effect being measured. The
    # first version gave "Tycho 0.19 mag deeper"; sharing the positions gave
    # "ours 0.29 mag deeper". A criterion in ADU is the same ruler for both.
    # @args: stacks - [(name, data), ...], n - how many positions, radius -
    #        px around the position that must be empty, bright_adu - what
    #        counts as "something is there" above the sky
    # @return: [(x, y), ...]
    if not stacks:
        return []
    h, w = stacks[0][1].shape
    r = int(math.ceil(radius))
    rng = np.random.default_rng(seed)
    out = []
    tries = 0
    while len(out) < n and tries < 40000:
        tries += 1
        x = float(rng.uniform(MARGIN, w - MARGIN))
        y = float(rng.uniform(MARGIN, h - MARGIN))
        xi, yi = int(round(x)), int(round(y))
        ok = True
        for _name, data in stacks:
            if data.shape != (h, w):
                continue
            sub = data[yi - r:yi + r + 1, xi - r:xi + r + 1]
            if sub.size == 0 or not np.all(np.isfinite(sub)):
                ok = False
                break
            sky = float(np.median(sub))
            if float(np.max(np.abs(sub - sky))) > bright_adu:
                ok = False
                break
        if not ok:
            continue
        if any(math.hypot(px - x, py - y) < 2.0 * radius for px, py in out):
            continue
        out.append((x, y))
    return out


def inject(data, x, y, flux, fwhm, seed):
    # A star of a KNOWN total flux at a KNOWN place, on a copy of the stack.
    # The sub-pixel phase is drawn at random on purpose: two sources of the
    # same flux must not land on the same fraction of a pixel every time.
    # @return: (new_data, x_true, y_true) or (None, None, None)
    rng = np.random.default_rng(seed)
    xt = x + float(rng.uniform(-0.5, 0.5))
    yt = y + float(rng.uniform(-0.5, 0.5))
    sigma = float(fwhm) / 2.3548200450309493
    half = int(math.ceil(2.5 * sigma)) + 1
    x0 = int(math.floor(xt)) - half
    y0 = int(math.floor(yt)) - half
    size = 2 * half + 1
    h, w = data.shape
    if x0 < 0 or y0 < 0 or x0 + size > w or y0 + size > h:
        return None, None, None
    yy, xx = np.mgrid[0:size, 0:size]
    spot = np.exp(-0.5 * (((xx - (xt - x0)) ** 2 + (yy - (yt - y0)) ** 2)
                          / sigma ** 2))
    spot *= float(flux) / float(spot.sum())
    out = np.array(data, dtype=np.float64, copy=True)
    out[y0:y0 + size, x0:x0 + size] += spot
    return out, xt, yt


def aperture_flux(data, x, y, r_ap, r_in, r_out):
    # The aperture sum with its own local sky, WITHOUT any guard: the point of
    # the bench is to see what comes back for EVERY injected source, and an
    # engine that refuses a negative flux (photometry.measure_point does, and
    # it is right to) would leave only the positive half of the distribution
    # and turn the bias and the scatter into fiction. Measured on the first
    # version of this bench: a +222 % bias at 40 ADU that was nothing but the
    # positivity cut.
    # @return: the net flux in ADU, or None when the aperture does not fit
    h, w = data.shape
    if min(x, y, w - x, h - y) < r_out:
        return None
    pad = int(math.ceil(max(r_out, r_ap))) + 2
    py0 = max(0, int(math.floor(y)) - pad)
    py1 = min(h, int(math.ceil(y)) + pad + 1)
    px0 = max(0, int(math.floor(x)) - pad)
    px1 = min(w, int(math.ceil(x)) + pad + 1)
    sub = np.asarray(data[py0:py1, px0:px1], dtype=np.float64)
    if sub.size == 0 or not np.all(np.isfinite(sub)):
        return None
    yy, xx = np.mgrid[py0:py1, px0:px1]
    r2 = (xx - x) ** 2 + (yy - y) ** 2
    cover, cy0, cx0 = photometry.pixel_coverage(data.shape, x, y, r_ap)
    weights = np.zeros(sub.shape, dtype=np.float64)
    if cover.size:
        weights[cy0 - py0:cy0 - py0 + cover.shape[0],
                cx0 - px0:cx0 - px0 + cover.shape[1]] = cover
    usable = weights > 0.0
    if not np.any(usable):
        return None
    area = float(weights[usable].sum())
    total = float((sub[usable] * weights[usable]).sum())
    ann = sub[(r2 >= r_in ** 2) & (r2 <= r_out ** 2)]
    if ann.size < 10:
        return None
    sky, _kept = photometry._sigma_clipped_median(ann)
    if sky is None:
        return None
    return total - sky * area


def local_noise(data, x, y, r_ap, r_in, r_out):
    # The noise per pixel of the source's OWN annulus: it is the denominator
    # the recipe reports for its SNR, and it is measured on the same pixels
    # photometry.sky_sigma uses.
    # @return: sigma in ADU, or None
    h, w = data.shape
    pad = int(math.ceil(max(r_out, r_ap))) + 2
    py0 = max(0, int(math.floor(y)) - pad)
    py1 = min(h, int(math.ceil(y)) + pad + 1)
    px0 = max(0, int(math.floor(x)) - pad)
    px1 = min(w, int(math.ceil(x)) + pad + 1)
    sub = np.asarray(data[py0:py1, px0:px1], dtype=np.float64)
    if sub.size == 0 or not np.all(np.isfinite(sub)):
        return None
    yy, xx = np.mgrid[py0:py1, px0:px1]
    r2 = (xx - x) ** 2 + (yy - y) ** 2
    ann = sub[(r2 >= r_in ** 2) & (r2 <= r_out ** 2)]
    if ann.size < 10:
        return None
    return photometry.sky_sigma(ann)


def run_stack(name, path, verbose=True, spots=None):
    # @args: spots - the positions to use, or None to look for clean ones in
    #        THIS stack. The comparison between two stacks must pass the SAME
    #        positions: a spot that is clean in one and sits on a source in
    #        the other measures the neighbour and not the pipeline (measured
    #        on the first version of this bench: 17.90 against 18.13 between
    #        two runs of the same test with different spots).
    # @return: the report dict for one stack
    header, data = fits_io.read_fits(path)
    data = np.asarray(data, dtype=np.float64)
    r_ap, r_in, r_out = photometry.aperture_for_fwhm(FWHM)
    if spots is None:
        spots = common_spots([(name, data)], TRIALS, seed=7)
    finite = np.isfinite(data)
    sky = float(np.median(data[finite]))
    sig = photometry.sky_sigma(data[finite])
    if verbose:
        print(f"  {name}: {data.shape}, cielo {sky:.1f} ADU, ruido "
              f"{sig:.2f} ADU/px, {len(spots)} posiciones limpias")
    report = {"stack": name, "shape": list(data.shape), "sky_adu": sky,
              "noise_adu": sig, "n_spots": len(spots),
              "r_ap": float(r_ap), "fwhm": FWHM, "levels": {}}
    for flux in FLUXES:
        got, snrs, fails = [], [], 0
        for j, (sx, sy) in enumerate(spots):
            inj, xt, yt = inject(data, sx, sy, flux, FWHM, seed=1000 + j)
            if inj is None:
                continue
            f = aperture_flux(inj, xt, yt, r_ap, r_in, r_out)
            if f is None:
                fails += 1
                continue
            got.append(float(f))
            # the local noise of the SAME annulus, for the SNR of the aperture
            s = local_noise(inj, xt, yt, r_ap, r_in, r_out)
            if s:
                snrs.append(float(flux) / (s * math.sqrt(math.pi * r_ap ** 2)))
        n, med, scatter = H.robust_stats(got)
        _sn, snr_med, _ss = H.robust_stats(snrs)
        # THE two numbers, and they are not the same thing:
        #   SNR (annulus) - the injected flux over the noise of its own
        #                   annulus, which is what the recipe reports;
        #   SNR (empirical) - the injected flux over the SCATTER of the
        #                   recovered flux, which is what actually comes out.
        emp = (flux / scatter) if (scatter and scatter > 0) else None
        report["levels"][str(flux)] = {
            "mag": mag_of(flux), "n": n, "fails": fails,
            "flux_med": med, "scatter_adu": scatter,
            "bias": ((med - flux) / flux) if med is not None else None,
            "snr_annulus": snr_med, "snr_empirical": emp,
        }
        if verbose:
            b = report["levels"][str(flux)]
            print("    %6.0f ADU (mag %5.2f): n=%2d  sesgo %+7.1f %%  "
                  "dispersión %6.1f ADU  SNR(anillo) %5.2f  SNR(empírico) %5.2f"
                  % (flux, b["mag"], n, 100 * (b["bias"] or 0),
                     scatter or 0, snr_med or 0, emp or 0))
    # the limiting flux at SNR_TARGET, interpolated in log flux
    xs, ys = [], []
    for flux in FLUXES:
        b = report["levels"][str(flux)]
        if b["snr_empirical"]:
            xs.append(math.log10(flux))
            ys.append(math.log10(b["snr_empirical"]))
    limit_flux = None
    if len(xs) >= 2:
        a = np.polyfit(xs, ys, 1)
        if a[0] > 0:
            limit_flux = 10 ** ((math.log10(SNR_TARGET) - a[1]) / a[0])
    report["limit_flux_adu"] = limit_flux
    report["limit_mag"] = mag_of(limit_flux) if limit_flux else None
    report["slope"] = float(a[0]) if len(xs) >= 2 else None
    if verbose and limit_flux:
        print(f"    -> límite a SNR {SNR_TARGET:.0f}: {limit_flux:.0f} ADU "
              f"(magnitud {report['limit_mag']:.2f}), pendiente "
              f"{report['slope']:.2f}")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out_dir = args.out or H.results_dir()
    # the positions are chosen ONCE, on the stack that is cleanest, and then
    # checked in the other: the same sky for both or the comparison is not one
    loaded = []
    for name, path in STACKS.items():
        if os.path.exists(path):
            loaded.append((name, np.asarray(fits_io.read_fits(path)[1],
                                           dtype=np.float64)))
    spots = common_spots(loaded, TRIALS, seed=7)
    print(f"posiciones limpias en los DOS stacks (criterio absoluto): {len(spots)}")
    reports = {}
    for name, path in STACKS.items():
        if not os.path.exists(path):
            print(f"  {name}: no existe {path}")
            continue
        print(f"[profundidad] {name} ...")
        reports[name] = run_stack(name, path, spots=spots)
    if len(reports) == 2:
        a, b = reports["ours"], reports["tycho"]
        print("\n=== comparación ===")
        print("%-24s %14s %14s" % ("", "nuestro", "Tycho"))
        print("%-24s %14.2f %14.2f" % ("ruido (ADU/px)",
                                       a["noise_adu"], b["noise_adu"]))
        print("%-24s %14.2f %14.2f" % ("magnitud límite (SNR 5)",
                                       a["limit_mag"] or float("nan"),
                                       b["limit_mag"] or float("nan")))
        print("%-24s %14s %14s" % ("ventaja en profundidad", "",
                                   "%.2fx" % ((a["limit_flux_adu"]
                                               / b["limit_flux_adu"])
                                              if (a["limit_flux_adu"]
                                                  and b["limit_flux_adu"])
                                              else float("nan"))))
        print("\nSNR empírico por nivel:")
        print("%-10s %-8s %14s %14s" % ("flujo", "mag", "nuestro", "Tycho"))
        for flux in FLUXES:
            x = a["levels"][str(flux)]["snr_empirical"]
            y = b["levels"][str(flux)]["snr_empirical"]
            print("%-10.0f %-8.2f %14.2f %14.2f" % (
                flux, mag_of(flux), x or float("nan"), y or float("nan")))
    path = os.path.join(out_dir, "depth.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(reports, fh, indent=1, ensure_ascii=False)
    print(f"\nJSON -> {path}")


if __name__ == "__main__":
    main()
