############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometry engine benchmark: injection and recovery
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Would another engine measure a single star better? Ask the truth.

This puts a star of a KNOWN total flux, at a KNOWN place, on a copy of a
real frame (with its real sky, its real noise and its real neighbours) and
measures it with every engine from a click drawn around it, which is what
the observer does. The recovery error is the answer.

Two design decisions that make the numbers mean something:

* the injected flux is set to a TARGET SNR against the frame's own sky
  noise, so the comparison is not a lottery of whichever star happens to be
  bright. The sky-limited precision of an aperture is
  sigma_sky * sqrt(area) / flux, which in magnitudes is 1085.7 / SNR mmag:
  that is the IDEAL column, and the question for each engine is how close
  its rms gets to it and whether it adds a bias;
* the statistic is the RELATIVE FLUX residual, (measured - injected) /
  injected, not the magnitude difference. At SNR 3 half the measurements
  land on a negative flux and the magnitude of a negative number is not a
  number: the flux residual stays well defined and its median and its MAD
  convert to mmag for small values, which is where the comparison lives.

The injected source is a Gaussian with the SESSION's own seeing, measured
from the frame's own stars: injecting a source sharper than the night's PSF
would measure the bench and not the pipeline.

Usage:
    python tools/bench/bench_inject.py --datasets 2025FG18,HatP32
"""

import argparse
import json
import logging
import math
import os
import sys
import time
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engines as E                                    # noqa: E402
import harness as H                                    # noqa: E402
from nightscribe.core import photometry                # noqa: E402

# The SNR ladder: 3 is "we can barely see it", 100 is a comfortable series
# point. A transit needs 30 to 100 per point to reach mmag per binned point.
SNR_LEVELS = (3.0, 10.0, 30.0, 100.0)

ENGINES = ("ours", "ours_refined", "ours_none", "ours_pu_cen", "pu_cen_ours",
           "pu")

# 1085.7 = 2.5 / ln(10) * 1000: the mmag of a unit relative flux change.
MMAG = 2.5 / math.log(10.0) * 1000.0


def frame_sky_noise(data, sources, fwhm):
    # The frame's own sky noise per pixel, from empty sky (the app's own
    # estimator: pixel-to-pixel differences, so a smooth gradient barely
    # moves it).
    # @return: sigma in ADU per pixel
    h, w = data.shape
    rng = np.random.default_rng(7)
    vals = []
    for _ in range(12):
        x = int(rng.uniform(80, w - 80))
        y = int(rng.uniform(80, h - 80))
        if sources is not None and len(sources):
            if float(np.min(np.hypot(sources[:, 0] - x, sources[:, 1] - y))) \
                    < 30.0:
                continue
        s = photometry.sky_sigma(
            np.asarray(data[y - 20:y + 20, x - 20:x + 20], dtype=np.float64))
        if s:
            vals.append(float(s))
    return float(np.median(vals)) if vals else 1.0


def aperture_floor(data, spots, r_ap, r_in, r_out, sigma_clip=True):
    # The frame's noise floor, measured on empty sky with the arithmetic
    # itself and NOT through an engine.
    #
    # It has to be done this way: an engine reports flux <= 0 as "no
    # measurable signal", so measuring the floor by asking an engine for
    # "ok" measurements keeps only the POSITIVE half of a distribution that
    # is centred on zero, and the floor comes out ~25 % low (measured on a
    # synthetic frame: 105 of 200 empty apertures survived the cut, median
    # +1330 ADU, rms 1049 instead of 1238). The first version of this bench
    # did exactly that, and it is the kind of bias that makes a benchmark
    # lie without anyone noticing.
    # @args: data - the frame, spots - empty positions, r_ap/r_in/r_out -
    #        the aperture, sigma_clip - as the engine uses it
    # @return: the rms of the net flux in ADU, or None
    vals = []
    for (x, y) in spots:
        h, w = data.shape
        if min(x, y, w - x, h - y) < r_out:
            continue
        pad = int(math.ceil(max(r_out, r_ap))) + 2
        py0 = max(0, int(math.floor(y)) - pad)
        py1 = min(h, int(math.ceil(y)) + pad + 1)
        px0 = max(0, int(math.floor(x)) - pad)
        px1 = min(w, int(math.ceil(x)) + pad + 1)
        sub = np.asarray(data[py0:py1, px0:px1], dtype=np.float64)
        yy, xx = np.mgrid[py0:py1, px0:px1]
        r2 = (xx - x) ** 2 + (yy - y) ** 2
        cover, cy0, cx0 = photometry.pixel_coverage(data.shape, x, y, r_ap)
        weights = np.zeros(sub.shape, dtype=np.float64)
        if cover.size:
            weights[cy0 - py0:cy0 - py0 + cover.shape[0],
                    cx0 - px0:cx0 - px0 + cover.shape[1]] = cover
        usable = weights > 0.0
        if not np.any(usable):
            continue
        area = float(weights[usable].sum())
        total = float((sub[usable] * weights[usable]).sum())
        ann = sub[(r2 >= r_in ** 2) & (r2 <= r_out ** 2)]
        if ann.size == 0:
            continue
        sky, _kept = photometry._sigma_clipped_median(
            ann, iters=(photometry.SIG_ITERS if sigma_clip else 0))
        if sky is None:
            continue
        vals.append(total - sky * area)
    if len(vals) < 5:
        return None
    _n, _med, sig = H.robust_stats(vals)
    return sig


def noise_floor(data, spots, kw, engines):
    # The noise floor of an engine on THIS frame, measured the only honest
    # way: measuring empty sky at the same places, with the same aperture.
    # It is not the textbook sigma_sky * sqrt(area): the sky level comes from
    # the star's own annulus (which has its own noise) and the pixel noise of
    # a real frame is not always white (measured on 2025 FG18: the empty
    # aperture scatters 2.4x the textbook figure, so scaling the injected
    # flux by the textbook one would call SNR 10 what is really SNR 4).
    # @return: {engine: rms of the empty-aperture flux in ADU}
    out = {}
    for eng in engines:
        vals = []
        for (sx, sy) in spots:
            try:
                r = E.measure_with(eng, data, sx, sy, **kw)
            except Exception:                              # noqa: BLE001
                continue
            if r.get("ok") and r.get("flux") is not None:
                vals.append(float(r["flux"]))
        if len(vals) >= 5:
            n, med, sig = H.robust_stats(vals)
            out[eng] = sig
        else:
            out[eng] = None
    return out


def run_dataset(name, n_spots=40, n_frames=3, seed=1234, verbose=True):
    # @args: name - a key of harness.DATASETS, n_spots - injections per
    #        level, n_frames - how many frames of the visit to use,
    #        seed - reproducibility
    # @return: a report dict (see main)
    paths = H.dataset_paths(name)
    if not paths:
        return None
    step = max(1, len(paths) // n_frames)
    frames = paths[::step][:n_frames]
    rel = {e: {s: [] for s in SNR_LEVELS} for e in ENGINES}
    pos = {e: {s: [] for s in SNR_LEVELS} for e in ENGINES}
    snrs = {e: {s: [] for s in SNR_LEVELS} for e in ENGINES}
    per_frame = []
    floors = {e: [] for e in ENGINES}
    for fi, path in enumerate(frames):
        header, data = H.load(path)
        src = H.detect_sources(data)
        fwhm = H.seeing_of(data, src)
        sig_pp = frame_sky_noise(data, src, fwhm)
        spots = H.empty_spots(data, src, n_spots, seed=seed + fi)
        r_ap, r_in, r_out = photometry.aperture_for_fwhm(fwhm)
        area = math.pi * float(r_ap) ** 2
        kw = dict(r_ap=r_ap, r_ann_in=r_in, r_ann_out=r_out, fwhm=fwhm)
        # the frame's real noise floor: measured on empty sky at the very
        # places the sources will be injected, with the arithmetic and not
        # through an engine (see aperture_floor: the engines' "ok" cut keeps
        # only the positive half and would understate it by a quarter)
        ref_floor = aperture_floor(data, spots, r_ap, r_in, r_out)
        floor = noise_floor(data, spots, kw, ENGINES)
        for eng, val in floor.items():
            if val:
                floors[eng].append(float(val))
        if ref_floor is None:
            ref_floor = float(np.median([v for v in floor.values() if v]))
        rng = np.random.default_rng(seed + 100 * fi)
        for snr in SNR_LEVELS:
            # the nominal SNR is against the frame's REAL floor, so "SNR 10"
            # means what it says
            flux = float(snr) * ref_floor
            for j, (sx, sy) in enumerate(spots):
                inj, xt, yt = H.inject(data, sx, sy, flux, fwhm,
                                       seed=seed + 1000 * fi + j)
                if inj is None:
                    continue
                cx, cy = H.click_off(xt, yt, rng)
                for eng in ENGINES:
                    try:
                        r = E.measure_with(eng, inj, cx, cy, **kw)
                    except Exception as err:               # noqa: BLE001
                        r = {"ok": False, "reason": {"en": str(err)}}
                    if not r.get("ok") or r.get("flux") is None:
                        rel[eng][snr].append(None)
                        pos[eng][snr].append(None)
                        snrs[eng][snr].append(None)
                        continue
                    rel[eng][snr].append(
                        (float(r["flux"]) - flux) / flux)
                    pos[eng][snr].append(
                        float(np.hypot(r["x"] - xt, r["y"] - yt)))
                    snrs[eng][snr].append(r.get("snr"))
        per_frame.append({"frame": os.path.basename(path), "fwhm_px": fwhm,
                          "sigma_sky_pp": sig_pp,
                          "sky_adu": float(np.median(data)),
                          "r_ap_px": float(r_ap), "area_px": area,
                          "ref_floor_adu": ref_floor,
                          "floor_adu": {k: v for k, v in floor.items()}})
        if verbose:
            print(f"  {name}: frame {fi + 1}/{len(frames)} "
                  f"(fwhm {fwhm:.2f} px, sigma_cielo {sig_pp:.1f} ADU/px, "
                  f"suelo {ref_floor:.0f} ADU)", flush=True)
    report = {"dataset": name, "frames": per_frame, "engines": {},
              "floor_adu_med": {e: (float(np.median(v)) if v else None)
                                for e, v in floors.items()}}
    for eng in ENGINES:
        block = {}
        for snr in SNR_LEVELS:
            n, bias, sig = H.robust_stats(rel[eng][snr])
            npn, pmed, psig = H.robust_stats(pos[eng][snr])
            sn, smed, _ = H.robust_stats(snrs[eng][snr])
            n_fail = sum(1 for v in rel[eng][snr] if v is None)
            # the standard error of a MAD-based sigma over n samples: the
            # difference between two engines only means something when it
            # clears this
            se = (sig / math.sqrt(2.0 * n) * MMAG) if (sig and n) else None
            block[str(snr)] = {
                "n": n, "n_failed": n_fail,
                "bias_mmag": (bias * MMAG) if bias is not None else None,
                "rms_mmag": (sig * MMAG) if sig is not None else None,
                "rms_se_mmag": se,
                "ideal_mmag": MMAG / float(snr),
                "pos_med_px": pmed, "pos_rms_px": psig, "pos_n": npn,
                "snr_med": smed, "snr_n": sn,
            }
        report["engines"][eng] = block
    return report


def print_table(report):
    print(f"\n=== {report['dataset']} ===")
    for fr in report["frames"]:
        print(f"  {fr['frame']}: fwhm {fr['fwhm_px']:.2f} px, "
              f"sigma_cielo {fr['sigma_sky_pp']:.1f} ADU/px, "
              f"r_ap {fr['r_ap_px']:.2f} px, area {fr['area_px']:.0f} px, "
              f"suelo {fr['ref_floor_adu']:.0f} ADU")
    print("  suelo de ruido por motor (ADU, mediana): "
          + ", ".join(f"{e}={v:.0f}" for e, v in
                      report["floor_adu_med"].items() if v))
    print(f"\n{'motor':14s} {'SNR':>5s} {'ideal':>8s} {'sesgo':>9s} "
          f"{'rms':>9s} {'+-se':>7s} {'rms/ideal':>10s} {'pos_rms':>8s} "
          f"{'n':>4s} {'fall':>5s}")
    for eng in ENGINES:
        for snr in SNR_LEVELS:
            b = report["engines"][eng][str(snr)]
            if b["rms_mmag"] is None:
                print(f"{eng:14s} {snr:5.0f} {b['ideal_mmag']:8.1f} "
                      f"{'-':>9s} {'-':>9s} {'-':>7s} {'-':>10s} {'-':>8s} "
                      f"{b['n']:4d} {b['n_failed']:5d}")
                continue
            ratio = b["rms_mmag"] / b["ideal_mmag"] if b["ideal_mmag"] else None
            print(f"{eng:14s} {snr:5.0f} {b['ideal_mmag']:8.1f} "
                  f"{b['bias_mmag']:+9.2f} {b['rms_mmag']:9.2f} "
                  f"{(b['rms_se_mmag'] or 0):7.2f} "
                  f"{ratio:10.3f} {(b['pos_rms_px'] or 0):8.3f} "
                  f"{b['n']:4d} {b['n_failed']:5d}")
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default="2025FG18,HatP32")
    ap.add_argument("--spots", type=int, default=40)
    ap.add_argument("--frames", type=int, default=3)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    logging.disable(logging.WARNING)
    warnings.filterwarnings("ignore")
    out_dir = args.out or H.results_dir()
    all_reports = []
    for name in [d.strip() for d in args.datasets.split(",") if d.strip()]:
        print(f"[inyección] {name} ...", flush=True)
        t0 = time.time()
        rep = run_dataset(name, n_spots=args.spots, n_frames=args.frames)
        if rep is None:
            print(f"  {name}: sin ficheros, se salta")
            continue
        rep["seconds"] = round(time.time() - t0, 1)
        all_reports.append(rep)
        print_table(rep)
    path = os.path.join(out_dir, "inject.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(all_reports, fh, indent=1, ensure_ascii=False)
    print(f"\nJSON -> {path}")


if __name__ == "__main__":
    main()
