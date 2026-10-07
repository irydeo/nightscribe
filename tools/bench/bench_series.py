############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometry engine benchmark: the series A/B
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Does another engine give a flatter light curve? Run the real series twice.

The whole app runs, unmodified, on top of whichever engine is installed in
`photometry.measure_point` (that is the seam the series engine already has:
`measure_plate` calls it as a module global). The frames, the comparison
stars, the targets, the apertures, the alignment and the zero point are
IDENTICAL between runs: the only thing that changes is the measurement of
one star on one frame.

The metric is the scatter of each star's differential light curve, in
millagitudes, which is exactly what a transit's detectability is made of.
Every detected star is used as a target and the brightest isolated ones as
the ensemble, so the answer comes as a curve against brightness and not as
one lucky star's number.

Usage:
    python tools/bench/bench_series.py --datasets 2025FG18,HatP32
"""

import argparse
import json
import math
import os
import sys
import time
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engines as E                                    # noqa: E402
import harness as H                                    # noqa: E402
from nightscribe.core import photometry, series_measure as sm   # noqa: E402

MMAG = 2.5 / math.log(10.0) * 1000.0


def choose_stars(data, wcs, sources, fwhm, n_comps=8, n_targets=20,
                 margin=None, min_sep=20.0, sat_adu=None):
    # The ensemble and the targets, from the frame's own stars. The comps are
    # the brightest isolated ones (a good ensemble is what sets the zero
    # point); the targets are the rest, which is where the faint end of the
    # precision curve comes from.
    #
    # @args: data - the reference frame, wcs - to get each star's sky
    #        position, sources - (N, 3) from the detector, fwhm - seeing,
    #        margin - px to keep off the edge (the annulus has to fit)
    # @return: (comps, targets) as [{"name", "star"}], [(label, x, y)]
    h, w = data.shape
    r_ap, _r_in, r_out = photometry.aperture_for_fwhm(fwhm)
    if margin is None:
        margin = float(r_out) + 12.0
    ceil = float(sat_adu) if sat_adu else None
    keep = []
    for s in sources:
        x, y, pk = float(s[0]), float(s[1]), float(s[2])
        if not (margin <= x <= w - margin and margin <= y <= h - margin):
            continue
        if ceil is not None and pk >= 0.85 * ceil:
            continue
        keep.append((x, y, pk))
    if len(keep) < n_comps + n_targets:
        n_targets = max(1, len(keep) - n_comps)
    if len(keep) < n_comps + 1:
        return [], []
    # isolation: a comp whose neighbour is inside its own annulus is not a
    # comp, it is two stars
    isolated = []
    arr = np.asarray([(k[0], k[1]) for k in keep], dtype=np.float64)
    for x, y, pk in keep:
        d = np.hypot(arr[:, 0] - x, arr[:, 1] - y)
        d = d[d > 0]
        if d.size and float(np.min(d)) < min_sep:
            continue
        isolated.append((x, y, pk))
    if len(isolated) < n_comps + 1:
        isolated = keep
    isolated.sort(key=lambda k: -k[2])
    comps, targets = [], []
    for i, (x, y, pk) in enumerate(isolated[:n_comps]):
        try:
            ra, dec = wcs.pixel_to_sky(x, y)
        except Exception:                                  # noqa: BLE001
            continue
        comps.append({"kind": "comp", "name": f"C{i + 1}",
                      "star": {"ra": float(ra), "dec": float(dec),
                               "id": f"C{i + 1}", "mag": None, "band": None,
                               "bands": []}})
    for j, (x, y, pk) in enumerate(isolated[n_comps:n_comps + n_targets]):
        targets.append((f"T{j + 1}", float(x), float(y)))
    return comps, targets


def build_cfg(name, header, wcs, fwhm, comps, targets, radii, config,
              sat=None, seeing_aperture=False):
    # The run's own recipe. zp_mode="relative" (differential against the
    # ensemble) is deliberate: it needs no catalogue, so the benchmark is
    # network-free and reproducible, and it is exactly the quantity a transit
    # is measured with.
    #
    # The ceilings are the plate's OWN (harness.saturation_hint), not the
    # user's camera settings: the benchmark measures the engine, and a wrong
    # ceiling would reject or accept stars for a reason that belongs to the
    # settings file.
    linear = config.get("cam_linearity_adu")
    if sat is not None and linear is not None and linear > sat:
        linear = sat
    # The METHOD is pinned here on purpose (matched=False): this bench measures
    # the ENGINE and the centroid, and the app's default is the matched filter,
    # which calls measure_point inside and reports ITS flux. Leaving it to the
    # default would mean benchmarking whatever the default happens to be, and
    # since 2026-10-07 the recipe always gets a FWHM, so the default would have
    # silently switched every run to the filter.
    return sm.SeriesConfig(
        wcs=wcs, target_xy=(targets[0][1], targets[0][2]) if targets
        else (0.0, 0.0),
        targets=tuple(targets), comp_set=tuple(comps),
        zp_mode="relative", radii=tuple(radii), sigmaclip=True,
        sky_mode="median", align="auto", seeing_aperture=seeing_aperture,
        matched=False,
        site_saturate=sat,
        site_linear=linear,
        site_gain=config.get("cam_gain"), site_ron=config.get("cam_ron"),
        group_n=1,
    )


def curve_stats(result):
    # The scatter of one curve, plus its brightness. The rms is computed on
    # the differential magnitude with the same 3-sigma clip for every engine,
    # so the comparison is of the measurement and not of the cleaning.
    # @args: result - a SeriesResult
    # @return: {n, rms_mmag, mag_med, err_med_mmag, flags}
    mags = [p.mag for p in result.points if p.mag is not None]
    errs = [p.err for p in result.points if p.err is not None]
    n, _med, rms = H.rms_of(mags)
    inst = [p.inst for p in result.points if p.inst is not None]
    return {"n": n, "n_points": len(result.points),
            "rms_mmag": (rms * 1000.0) if rms is not None else None,
            "mag_med": (float(np.median(inst)) if inst else None),
            "err_med_mmag": (float(np.median(errs)) * 1000.0 if errs
                             else None),
            "flags": sum(len(p.flags) for p in result.points)}


def run_dataset(name, engines, limit=None, n_comps=8, n_targets=20,
                verbose=True, seeing_aperture=False):
    paths = H.dataset_paths(name, limit=limit)
    if not paths:
        return None
    header, data = H.load(paths[0])
    wcs = H.build_wcs(header, name)
    if wcs is None:
        print(f"  {name}: sin WCS utilizable, se salta")
        return None
    src = H.detect_sources(data)
    fwhm = H.seeing_of(data, src)
    radii = photometry.aperture_for_fwhm(fwhm)
    from nightscribe.config import config
    sat = H.saturation_hint(header, data)
    # the ceiling the ENGINE will enforce is the lower of the two (ADR-066):
    # choosing comps by saturation alone picked, on 2026 PY9, eight stars all
    # above the camera's linearity, every one of them was refused and the
    # whole run came back with no magnitude at all. The bench has to choose
    # stars the engine would accept, or it measures its own mistake.
    lin = config.get("cam_linearity_adu")
    pick_ceiling = sat
    if lin is not None:
        pick_ceiling = min(sat, lin) if sat is not None else lin
    comps, targets = choose_stars(data, wcs, src, fwhm, n_comps=n_comps,
                                  n_targets=n_targets, sat_adu=pick_ceiling)
    if not comps or not targets:
        print(f"  {name}: no hay estrellas suficientes, se salta")
        return None
    if verbose:
        print(f"  {name}: {len(paths)} frames, fwhm {fwhm:.2f} px, "
              f"radios {[round(r, 2) for r in radii]}, "
              f"techo {sat}, "
              f"{len(comps)} comps, {len(targets)} objetivos", flush=True)
    out = {"dataset": name, "n_frames": len(paths), "fwhm_px": fwhm,
           "radii_px": [float(r) for r in radii], "sat_adu": sat,
           "n_comps": len(comps), "n_targets": len(targets),
           "engines": {}}
    for eng in engines:
        cfg = build_cfg(name, header, wcs, fwhm, comps, targets, radii,
                        config, sat, seeing_aperture=seeing_aperture)
        t0 = time.time()
        with E.use_engine(eng):
            res = sm.measure_pass(paths, cfg, targets=cfg.targets)
        dt = time.time() - t0
        curves = {}
        for t in res.targets:
            curves[t["label"]] = curve_stats(t["result"])
        first = res.targets[0]["result"]
        out["engines"][eng] = {
            "seconds": round(dt, 1),
            "ms_per_frame": round(dt / max(1, len(paths)) * 1000.0, 1),
            "align": (first.align_report or {}).get("aligned"),
            "align_mode": (first.align_report or {}).get("mode"),
            "status": res.status,
            "n_errors": len(res.errors),
            "curves": curves,
        }
        if verbose:
            rms = [c["rms_mmag"] for c in curves.values()
                   if c["rms_mmag"] is not None]
            print(f"    {eng:14s} {dt:6.1f} s ({out['engines'][eng]['ms_per_frame']:6.1f} "
                  f"ms/frame)  rms mediano "
                  f"{(np.median(rms) if rms else float('nan')):7.2f} mmag  "
                  f"alineados {out['engines'][eng]['align']}", flush=True)
    return out


def print_table(report):
    print(f"\n=== {report['dataset']} ===")
    print(f"  {report['n_frames']} frames, fwhm {report['fwhm_px']:.2f} px, "
          f"radios {[round(r, 2) for r in report['radii_px']]}, "
          f"{report['n_comps']} comps, {report['n_targets']} objetivos")
    labels = list(report["engines"][list(report["engines"])[0]]["curves"])
    engines = list(report["engines"])
    print(f"\n{'objetivo':10s} {'mag_inst':>9s} "
          + " ".join(f"{e:>12s}" for e in engines) + f" {'err_med':>8s}")
    for lab in labels:
        row = [f"{lab:10s}"]
        mag = None
        for e in engines:
            c = report["engines"][e]["curves"].get(lab, {})
            if mag is None:
                mag = c.get("mag_med")
            r = c.get("rms_mmag")
            row.append(f"{(r if r is not None else float('nan')):12.2f}")
        err = report["engines"][engines[0]]["curves"].get(lab, {})
        row.append(f"{(err.get('err_med_mmag') or float('nan')):8.2f}")
        print(f"{row[0]} {(mag if mag is not None else float('nan')):9.3f} "
              + " ".join(row[1:]))
    print(f"\n{'motor':14s} {'s':>8s} {'ms/frame':>9s} {'rms_med':>9s} "
          f"{'rms_min':>9s} {'err_med':>9s} {'puntos':>7s} {'alineados':>10s}")
    for e in engines:
        blk = report["engines"][e]
        rms = [c["rms_mmag"] for c in blk["curves"].values()
               if c["rms_mmag"] is not None]
        errs = [c["err_med_mmag"] for c in blk["curves"].values()
                if c["err_med_mmag"] is not None]
        ns = [c["n"] for c in blk["curves"].values() if c["n"]]
        print(f"{e:14s} {blk['seconds']:8.1f} {blk['ms_per_frame']:9.1f} "
              f"{(np.median(rms) if rms else float('nan')):9.2f} "
              f"{(min(rms) if rms else float('nan')):9.2f} "
              f"{(np.median(errs) if errs else float('nan')):9.2f} "
              f"{(int(np.median(ns)) if ns else 0):7d} "
              f"{str(blk['align']):>10s}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", default="2025FG18,HatP32")
    ap.add_argument("--engines", default="ours,pu")
    ap.add_argument("--frames", type=int, default=0)
    ap.add_argument("--comps", type=int, default=8)
    ap.add_argument("--targets", type=int, default=20)
    ap.add_argument("--out", default=None)
    ap.add_argument("--seeing-aperture", action="store_true",
                    help="H3 on: the aperture follows each frame's seeing and "
                         "the plate recipe gets the frame's FWHM (the app's "
                         "recommended path for a series)")
    args = ap.parse_args()
    warnings.filterwarnings("ignore")
    out_dir = args.out or H.results_dir()
    engines = [e.strip() for e in args.engines.split(",") if e.strip()]
    reports = []
    for name in [d.strip() for d in args.datasets.split(",") if d.strip()]:
        print(f"[serie] {name} ...", flush=True)
        rep = run_dataset(name, engines, limit=(args.frames or None),
                          n_comps=args.comps, n_targets=args.targets,
                          seeing_aperture=args.seeing_aperture)
        if rep is None:
            continue
        reports.append(rep)
        print_table(rep)
    suffix = "_seeing" if args.seeing_aperture else ""
    path = os.path.join(out_dir, f"series{suffix}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(reports, fh, indent=1, ensure_ascii=False)
    print(f"\nJSON -> {path}")


if __name__ == "__main__":
    main()
