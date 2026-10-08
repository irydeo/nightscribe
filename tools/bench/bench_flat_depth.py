############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometry engine benchmark: does the flat buy depth?
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Does the synthetic flat buy DEPTH, or only the systematic?

Bench code: not imported by the app, not shipped. It answers the one question
the flat bench left open, and it answers it in the SINGLE FRAME's units, which
is what Tycho's own zero point (MZERO 25.3195) speaks.

Two things had to be fixed before this could be measured at all, and both were
found by checking instead of trusting:

1. **The units.** Our saved stack of that visit was a MEAN when the ADR-068
   comparison was made (sky 1597.83 ADU, Tycho's 1597.0, so the comparison was
   honest) and it has since been rewritten as a SUM (sky 296,049 ADU, 190.8
   times the frame). Injecting the same ADU flux into two stacks whose units
   differ by 190x measures the units and not the depth. This bench builds its
   own mean stack from the frames, so its numbers are in the same units as the
   zero point it quotes.
2. **The field is STATIC** (measured: 2 px over 207 frames), so the frames can
   be averaged without aligning. That is what makes the whole thing cheap: one
   mean stack, and every candidate flat is applied to it (dividing is linear,
   so dividing the mean is dividing every frame).

What it measures, per candidate flat: the noise, the bias (the recovered flux
against the injected one), the DEPTH (the flux at SNR 5, interpolated in log
flux) and the SYSTEMATIC, which is the spread of the recovered flux across
positions. Those last two are different things, and telling them apart is the
point: a flat that changes the systematic and not the depth is doing its job.
"""

import argparse
import glob
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bench_depth as D                                     # noqa: E402
import harness as H                                         # noqa: E402
from nightscribe.core import calibration, photometry  # noqa: E402

LIGHTS = "/home/boreal/Develop/astronomy/dataset/2025FG18/20250331/*.fits"
FLATS_GLOB = ("/home/boreal/Develop/astronomy/dataset/"
              "Flat-31-03-2025-3/20250331/*.fits")
N_FRAMES = 60           # frames averaged: 60 x 1 s, one visit's worth
# The flux of the BRIGHT injection used to measure the systematic. The
# flat-field error is a RELATIVE effect, so it is measured where the noise
# cannot hide it: the first run of this bench measured the "systematic" at the
# faint end and reported 300 %, which was nothing but the error of the
# annulus's own sky (0.1 % of the sky over a 121-pixel aperture is 185 ADU,
# enough to swamp a 210 ADU injection).
BRIGHT_FLUX = 20000.0
# The pedestal of these 1 s twilight frames, measured with the flat bench
# (pedestal / sky = 1.25, level 1488 ADU). It is what has to come out of BOTH
# sides for the division to mean anything.
PEDESTAL_ADU = 827.0
TRIALS = 40
SNR_TARGET = 5.0


def mean_stack(paths, n, loader=None):
    # The frames of this visit are STATIC (2 px over 207 frames, measured), so
    # the mean needs no alignment: the field does not move. A running sum and
    # not a list of frames, because 60 x 2048 x 2048 x 4 B would be a
    # gigabyte for nothing.
    # @args: paths - the frames, n - how many to average, loader - callable
    #        (path, box) -> array, or None for the app's own reader
    # @return: (mean float32, seconds)
    t0 = time.time()
    loader = loader or (lambda p, box: calibration.read_image(p, box)[0])
    idx = np.linspace(0, len(paths) - 1, n).astype(int)
    total = None
    for i in idx:
        data = np.asarray(loader(paths[i], None), dtype=np.float64)
        total = data if total is None else total + data
    return (total / float(len(idx))).astype(np.float32), time.time() - t0


def flat_candidates(db=None, cfg=None, progress=True):
    # @return: [(label, flat or None), ...] with every flat NORMALISED to a
    #          median of one, so the comparison is of the shape alone
    lights = sorted(glob.glob(LIGHTS))
    if progress:
        print(f"construyendo los flats sobre {len(lights)} tomas")
    out = []
    # the library has no flat for this filter, so the app builds one; with the
    # mask turned off it is what the old engine produced
    old, _info_old = calibration.pseudo_flat(lights, mask_sigma=1e9)
    masked, info = calibration.pseudo_flat(lights)

    # the pedestal: the same flat, built from frames with the offset removed.
    # It is done with the loader, which is exactly what _OffsetSubtractor does
    # when the library has a dark/bias.
    def sub(path, box):
        # @return: the frame with the pedestal already out
        return (np.asarray(calibration.read_image(path, box)[0],
                           dtype=np.float32) - PEDESTAL_ADU)

    masked_ped, _info_ped = calibration.pseudo_flat(lights, loader=sub)
    # the truth: the author's own real flat of that same night
    master, _s = D_flat_master()
    out = [("sin flat", None), ("flat de hoy (sin mascara)", old),
           ("enmascarado", masked), ("enmasc + pedestal", masked_ped),
           ("master real", master)]
    if progress:
        print(f"  {info.get('n_sources')} fuentes enmascaradas, "
              f"{info.get('filled_pct'):.2f} % rellenado, "
              f"{info.get('hot_px')} píxeles calientes")
    return out, info


def D_flat_master():
    # The real master flat of that night, from the bench's own cache (it takes
    # 55 s to build and it is the same file every time).
    cache = os.path.join(H.results_dir(), "master_flat_20250331.npy")
    if not os.path.exists(cache):
        raise SystemExit("run tools/bench/bench_flat.py --rebuild first")
    raw = np.load(cache)
    return raw / float(np.median(raw)), None


def run_candidate(label, raw, flat, spots, pedestal=0.0, resp=None,
                  verbose=True):
    # The depth ladder of bench_depth, on the RAW stack, with the flat applied
    # AFTER the injection: `(frame + star) / flat`, which is what the app
    # does. Injecting into the already-divided stack measures nothing about
    # the flat (the source never meets it), and injecting a constant ADU flux
    # measures nothing either (a star arrives multiplied by the train's
    # response, which is `resp`).
    # @args: raw - the raw stack (single-frame units), flat - the candidate
    #        flat or None, spots - the SHARED positions, pedestal - ADU to
    #        remove BEFORE dividing (the same on both sides of the division),
    #        resp - the train's response (the real master flat)
    # @return: the report dict
    r_ap, r_in, r_out = photometry.aperture_for_fwhm(D.FWHM)
    work = np.asarray(raw, dtype=np.float64)
    finite = np.isfinite(work)
    sky = float(np.median(work[finite])) - float(pedestal)
    report = {"stack": label, "sky_adu": sky, "n_spots": len(spots),
              "levels": {}}

    def apply(inj):
        # @return: the injected stack as the app would hand it to the engine
        out = inj - float(pedestal) if pedestal else inj
        if flat is not None:
            out = out / np.asarray(flat, dtype=np.float64)
        return out

    # THE LOCAL NOISE, measured where the sources are: the median over the
    # positions of the noise in the source's own annulus. It is the number the
    # recipe uses for its SNR, and unlike a whole-frame sigma it does not care
    # how much the field varies.
    locals_ = []
    for (sx, sy) in spots:
        s = D.local_noise(apply(work), sx, sy, r_ap, r_in, r_out)
        if s:
            locals_.append(float(s))
    report["noise_adu"] = float(np.median(locals_)) if locals_ else None
    if verbose:
        print(f"  {label:26s} cielo {sky:9.1f}  ruido local "
              f"{report['noise_adu'] or float('nan'):7.2f} ADU/px  "
              f"cielo/ruido {sky / (report['noise_adu'] or 1):7.1f}")
    for flux in D.FLUXES:
        got, snrs = [], []
        for j, (sx, sy) in enumerate(spots):
            local = 1.0 if resp is None else float(resp[int(round(sy)),
                                                        int(round(sx))])
            inj, xt, yt = D.inject(work, sx, sy, flux * local, D.FWHM,
                                   seed=1000 + j)
            if inj is None:
                continue
            data = apply(inj)
            f = D.aperture_flux(data, xt, yt, r_ap, r_in, r_out)
            if f is None:
                continue
            got.append(float(f))
            s = D.local_noise(data, xt, yt, r_ap, r_in, r_out)
            if s:
                snrs.append(float(flux) / (s * math.sqrt(math.pi * r_ap ** 2)))
        n, med, scatter = H.robust_stats(got)
        _sn, snr_med, _ss = H.robust_stats(snrs)
        emp = (flux / scatter) if (scatter and scatter > 0) else None
        report["levels"][str(flux)] = {
            "mag": D.mag_of(flux), "n": n, "flux_med": med,
            "scatter_adu": scatter, "bias": ((med - flux) / flux)
            if med is not None else None,
            "snr_annulus": snr_med, "snr_empirical": emp}
        if verbose:
            b = report["levels"][str(flux)]
            print("    %6.0f ADU (mag %5.2f): n=%2d  sesgo %+7.1f %%  "
                  "SNR(anillo) %5.2f  SNR(empírico) %5.2f"
                  % (flux, b["mag"], n, 100 * (b["bias"] or 0),
                     snr_med or 0, emp or 0))
    xs, ys = [], []
    for flux in D.FLUXES:
        b = report["levels"][str(flux)]
        if b["snr_annulus"]:
            xs.append(math.log10(flux))
            ys.append(math.log10(b["snr_annulus"]))
    limit = None
    if len(xs) >= 2:
        a = np.polyfit(xs, ys, 1)
        if a[0] > 0:
            limit = 10 ** ((math.log10(SNR_TARGET) - a[1]) / a[0])
    report["limit_flux_adu"] = limit
    report["limit_mag"] = D.mag_of(limit) if limit else None

    # ---- the bright injection, POSITION BY POSITION
    # The flat-field error is a relative one, and comparing candidates AT THE
    # SAME POSITION cancels the local sky, which is what swamped the first
    # version of this measurement (its "systematic" of 300 % was the error of
    # the annulus's own sky: 0.1 % of the sky over a 121-pixel aperture is 185
    # ADU, enough to swamp a 210 ADU injection).
    bright = []
    for j, (sx, sy) in enumerate(spots):
        local = 1.0 if resp is None else float(resp[int(round(sy)),
                                                    int(round(sx))])
        inj, xt, yt = D.inject(work, sx, sy, BRIGHT_FLUX * local, D.FWHM,
                               seed=2000 + j)
        if inj is None:
            bright.append(float("nan"))
            continue
        f = D.aperture_flux(apply(inj), xt, yt, r_ap, r_in, r_out)
        bright.append(float(f) if f is not None else float("nan"))
    report["bright_fluxes"] = bright
    report["bright_injected"] = [BRIGHT_FLUX * (1.0 if resp is None else
                                                float(resp[int(round(sy)),
                                                           int(round(sx))]))
                                 for (sx, sy) in spots]
    arr = np.asarray([v for v in bright if np.isfinite(v)])
    if arr.size >= 10:
        lo, hi = np.percentile(arr, 16), np.percentile(arr, 84)
        report["bright"] = {
            "flux": BRIGHT_FLUX, "n": int(arr.size),
            "median": float(np.median(arr)),
            "spread_pct": float(100.0 * (hi - lo) / BRIGHT_FLUX)}
        if verbose:
            b = report["bright"]
            print("    BRILLANTE %6.0f ADU (modulado): n=%2d  dispersión "
                  "%5.2f %% (el flat incluido)" % (BRIGHT_FLUX, b["n"],
                                                   b["spread_pct"]))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=N_FRAMES)
    args = ap.parse_args()

    report = {}
    candidates, info = flat_candidates()
    lights = sorted(glob.glob(LIGHTS))
    stack, seconds = mean_stack(lights, args.frames)
    report["mean_seconds"] = seconds
    report["n_frames"] = args.frames
    print(f"stack medio de {args.frames} tomas: {seconds:.1f} s")
    print(f"  cielo {float(np.median(stack)):.1f} ADU (una toma: 1552, "
          f"Tycho: 1597) -> las MISMAS unidades que el cero punto")

    # THE SAME positions in every candidate, by an absolute criterion (nothing
    # brighter than 100 ADU over the sky within 20 px), which is the rule the
    # depth bench learned the hard way.
    stacks = []
    for label, flat in candidates:
        if flat is None:
            stacks.append((label, stack))
        else:
            stacks.append((label, stack / np.asarray(flat,
                                                     dtype=np.float32)))
    spots = D.common_spots(stacks, TRIALS, seed=7)
    report["n_spots"] = len(spots)
    print(f"posiciones limpias en TODOS los candidatos: {len(spots)}")

    # the train's response, for the injection: the real master flat, the only
    # thing here that knows it
    master_resp = np.asarray([f for lbl, f in candidates
                              if lbl == "master real"][0], dtype=np.float32)
    reports = {}
    for label, flat in candidates:
        print(f"[profundidad] {label} ...")
        pedestal = PEDESTAL_ADU if "pedestal" in label else 0.0
        reports[label] = run_candidate(label, stack, flat, spots,
                                       pedestal=pedestal, resp=master_resp)
    report["candidates"] = reports

    print()
    print("=" * 96)
    print("%-26s %10s %9s %13s %11s" % (
        "candidato", "ruido local", "mag lím", "sesgo(brill)", "sistemático"))
    print("%-26s %10s %9s %13s %11s" % (
        "", "ADU/px", "SNR 5", "%", "vs master"))
    master = reports["master real"]["bright_fluxes"]
    for label, _flat in candidates:
        r = reports[label]
        b = r.get("bright") or {}
        # THE SYSTEMATIC, measured the only way it is clean: the flux ratio
        # against the real flat, POSITION BY POSITION. The local sky is the
        # same in both members of each ratio, so it cancels, and what is left
        # is the flat's own error.
        sys_pct = None
        if label != "master real":
            got = r["bright_fluxes"]
            inj = r["bright_injected"]
            ratio = []
            for a, c, f in zip(got, master, inj):
                if np.isfinite(a) and np.isfinite(c) and c > 0:
                    # both members carry the same response, so the ratio is
                    # the flat's own error and nothing else
                    ratio.append((a / c))
            if len(ratio) >= 10:
                arr = np.asarray(ratio, dtype=np.float64)
                lo, hi = np.percentile(arr, 16), np.percentile(arr, 84)
                sys_pct = float(100.0 * (hi - lo))
                r["systematic_vs_master_pct"] = sys_pct
                r["ratio_median"] = float(np.median(arr))
        # the bias, against what was ACTUALLY injected at each position
        if r.get("bright") and inj:
            got = np.asarray([v for v in r["bright_fluxes"] if np.isfinite(v)])
            want = np.asarray([f for f, v in zip(inj, r["bright_fluxes"])
                               if np.isfinite(v)])
            if got.size:
                r["bright"]["bias_pct"] = float(
                    100.0 * (np.median(got) - np.median(want))
                    / np.median(want))
        print("%-26s %10.2f %9.2f %12.2f %% %10s" % (
            label, r["noise_adu"] or float("nan"),
            r["limit_mag"] or float("nan"), b.get("bias_pct") or 0,
            ("%6.2f %%" % sys_pct) if sys_pct is not None else "   (ref)"))
    print()
    print("sistemático = dispersión (p16-p84) del ratio de flujo contra el")
    print("master real, POSICIÓN A POSICIÓN: el cielo local se cancela porque")
    print("es el mismo en los dos miembros, así que lo que queda es el error")
    print("del propio flat. La profundidad usa el SNR del anillo (el ruido")
    print("local de cada posición), que es la definición de la receta.")

    out = os.path.join(H.results_dir(), "flat_depth.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print()
    print(f"informe: {out}")


if __name__ == "__main__":
    main()
