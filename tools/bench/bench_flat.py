############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometry engine benchmark: the synthetic flat
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Can a flat built from the frames themselves match a real one, and can it
be built with NO stars in it?

Bench code: not imported by the app, not shipped. The instrument is the
author's own real flat of the same night (`Flat-31-03-2025-3`, 150 flats of
2025-03-31, gain 3, 0.3 s), which is the only thing here that knows the truth.

The physics, measured before writing this (2026-10-07):

* the FG18 field is STATIC (2 px over 207 frames, 17 to 33 stars matched), so
  the low percentile the current pseudo-flat relies on CANNOT remove the
  stars there;
* the frames carry a large uncorrected flat field, so they are full of
  isolated single-pixel spikes (11,785 above 3 sigma): dilating those masked
  50 % of the frame in the first attempt, so only what is EXTENDED may be
  dilated;
* the pixel noise is 117 ADU on a sky of 1552 (7.5 %) and the data is
  quantised to 16 ADU (an effective 12-bit depth), so a star worth 1 % of the
  sky is at S/N 0.13 in one frame: the faint stars are only visible in the
  COMBINATION, never in the frame.

Three roads that were tried and DO NOT work, with their numbers, so nobody
walks them again:

1. **The rank-1 fit per pixel** (`L = a + s_f * b`, which is the physically
   right formulation: the pedestal and the static stars fall into `a`). It
   fails on the lever: the sky varies 3.15 % on FG18 (48 ADU) against a pixel
   noise of 117 ADU, so the per-pixel slope comes out with a 43 % error and
   the raw fit spanned -820 to +554 with 2.7 % of the pixels negative. Even
   clipping against the per-pixel median leaves the additive map with 671 ADU
   of noise, which swamps the faint stars it was supposed to reveal.
2. **The spatial MAD as a lever** (the MAD is proportional to the sky, not to
   the pedestal). It does not work either: the MAD is dominated by the noise
   (118.6 ADU against 47 of structure) and it came out EXACTLY constant over
   the 207 frames.
3. **The difference identity** (`f1 = P + K * (f1 - f2)` for two frames). The
   residuals came out at 337 ADU, three times the noise, so the model does
   not hold (the sky's SHAPE changes during twilight); the intercept it gave
   (1539 ADU) would imply a sky of zero, which is absurd.

A fourth road that was tried and does NOT decide anything, for the same
reason:

4. **The position sweep** (`position_sweep`): injecting the same source at
   positions chosen by their response and measuring it back with the app's
   own aperture photometry. It came out dominated by the aperture's own
   scatter (0.22 mag of spread even with the REAL flat), so it cannot resolve
   a systematic of that size. The systematic is measured where it is clean:
   in the RATIO between each candidate flat and the real master, which is
   what the photometry divides by (17.18 % with today's flat, 4.16 % with the
   masked one and the pedestal removed).

What DOES work is in `masked_flat`: the order statistic, the star mask, the
NaNs and a NORMALISED CONVOLUTION that fills what is missing.
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
from nightscribe.core import (calibration, fits_io, outliers,  # noqa: E402
                              photometry)

FLATS_GLOB = ("/home/boreal/Develop/astronomy/dataset/"
              "Flat-31-03-2025-3/20250331/*.fits")
BAND = 64                    # rows per pass: 207 frames x 64 x 2048 x 4 = 108 MB


# --------------------------------------------------------------- the truth

def flat_paths():
    # @return: the sorted paths of the real flats of that night
    return sorted(glob.glob(FLATS_GLOB))


def _master_path():
    return os.path.join(H.results_dir(), "master_flat_20250331.npy")


def build_master(paths, band=BAND, progress=True):
    # The real master: the per-pixel MEDIAN of the 150 flats, in row bands.
    # The median and not the mean: a cosmic ray or a plane in one flat must
    # not reach the master. Measured: 55 s for 150 flats of 2048x2048.
    # @return: (master float32, seconds)
    t0 = time.time()
    header = fits_io.read_header(paths[0])
    ny = int(header.get("NAXIS2", 0))
    nx = int(header.get("NAXIS1", 0))
    raw = np.empty((ny, nx), dtype=np.float32)
    total = len(paths)
    k = total // 2
    for y0 in range(0, ny, band):
        y1 = min(ny, y0 + band)
        block = np.empty((total, y1 - y0, nx), dtype=np.float32)
        for i, path in enumerate(paths):
            data, _h = calibration.read_image(path, (0, y0, nx, y1))
            block[i] = np.asarray(data, dtype=np.float32)
        raw[y0:y1] = np.partition(block, k, axis=0)[k]
        if progress:
            print(f"    franja {y1:5d}/{ny}  ({time.time() - t0:5.1f} s)",
                  flush=True)
    return raw, time.time() - t0


def _stats(name, arr):
    # @return: a dict with the robust shape of an image, for the report
    a = np.asarray(arr, dtype=np.float64)
    finite = a[np.isfinite(a)]
    med = float(np.median(finite))
    q = [float(np.percentile(finite, p)) for p in (0.1, 1, 5, 50, 95, 99, 99.9)]
    return {"name": name, "median": med, "min": float(finite.min()),
            "max": float(finite.max()),
            "p0.1": q[0], "p1": q[1], "p5": q[2], "p50": q[3],
            "p95": q[4], "p99": q[5], "p99.9": q[6],
            "mad": float(outliers.scaled_mad(finite))}


def smooth(x, window=41, passes=3):
    # The smoothing the app's pseudo-flat uses, so the comparison is of the
    # METHOD and not of the blur.
    from scipy import ndimage
    out = np.asarray(x, dtype=np.float32)
    for _ in range(max(1, passes)):
        out = ndimage.uniform_filter(out, size=window, mode="nearest")
    return out


def ratio_spread(a, b, step=8):
    # How flat is a/b? p5-p95 of the ratio over a decimated grid, which is the
    # number that says whether the two measure the same SHAPE. Both sides are
    # decimated by the SAME factor, or the comparison is of two different
    # grids (which is how the first run of this bench crashed).
    # @return: (p5, p50, p95, spread)
    x = np.asarray(a, dtype=np.float64)[::step, ::step]
    y = np.asarray(b, dtype=np.float64)[::step, ::step]
    ok = np.isfinite(x) & np.isfinite(y) & (y > 0)
    r = x[ok] / y[ok]
    med = float(np.median(r))
    r = r / med
    p5, p95 = (float(np.percentile(r, 5)), float(np.percentile(r, 95)))
    return p5, med, p95, p95 - p5


def pedestal_fit_lights(real_norm, pseudo_norm, grid=None, step=8):
    # The pseudo-flat is built from the LIGHTS, so it carries the lights'
    # pedestal: flat_obs = P + sky * R. The normalisation does not remove it,
    # so the SHAPE comes out COMPRESSED (measured on FG18: the real flat falls
    # to 0.436 at the corner and the pseudo-flat only to 0.686, a factor 1.6).
    # The scale is absorbed by the normalisation, so there is one free
    # parameter, p = P / sky, and it is fitted by requiring the ratio to be
    # flat. The spread AT the best p is the honest agreement.
    # @return: [(p, spread), ...]
    out = []
    r = np.asarray(real_norm, dtype=np.float64)[::step, ::step]
    o = np.asarray(pseudo_norm, dtype=np.float64)[::step, ::step]
    for p in (grid if grid is not None else
              (0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0)):
        model = (float(p) + r)
        model = model / float(np.median(model))
        out.append((float(p), ratio_spread(model, o, step=1)[3]))
    return out


# ------------------------------------------------------- the statistic

def raw_stat(paths, order=0.33, band=BAND, progress=False):
    # The app's own per-pixel order statistic over the frames, banded and
    # RAW (no smoothing, no normalisation), so the bench can subtract a
    # pedestal from it and see what each step is worth.
    #
    # The read is a BOX per frame (`read_image(path, (0, y0, nx, y1))`) and
    # not the whole frame: the first version of this bench read 207 full
    # frames per band and took 82 s where the app's own pass takes 18.
    # @args: paths - the frames, order - 0.5 median, 0.33 the app's percentile
    # @return: (raw float32, seconds)
    t0 = time.time()
    header = fits_io.read_header(paths[0])
    ny = int(header.get("NAXIS2", 0))
    nx = int(header.get("NAXIS1", 0))
    out = np.empty((ny, nx), dtype=np.float32)
    total = len(paths)
    k = max(0, min(total - 1, int(round(order * (total - 1)))))
    for y0 in range(0, ny, band):
        y1 = min(ny, y0 + band)
        block = np.empty((total, y1 - y0, nx), dtype=np.float32)
        for i, path in enumerate(paths):
            data, _h = calibration.read_image(path, (0, y0, nx, y1))
            block[i] = np.asarray(data, dtype=np.float32)
        out[y0:y1] = np.partition(block, k, axis=0)[k]
        if progress:
            print(f"    franja {y1:5d}/{ny}  ({time.time() - t0:5.1f} s)",
                  flush=True)
    return out, time.time() - t0


def star_mask(raw, k=5.0, dilate=12, window=41, passes=3):
    # THE APP'S OWN DETECTOR, and the right one: what is well above the
    # SMOOTHED statistic is a source that does not move. It is the only
    # detector that can see the faint stars, because it works on the
    # combination and not on a frame (measured: 117 ADU of noise on a sky of
    # 1552, so a star worth 1 % of the sky is at S/N 0.13 in a frame).
    #
    # Only what is EXTENDED is dilated. A single-pixel spike is a hot pixel:
    # it is FIXED, so it belongs in the flat (the division removes it), and
    # dilating them masked 50 % of the frame in the first attempt.
    # @return: (mask, mask_pct, stats, hot) with hot = the isolated spikes
    from scipy import ndimage
    ref = smooth(raw, window=window, passes=passes)
    diff = raw - ref
    noise = float(outliers.scaled_mad(diff.ravel()))
    raw_mask = diff > k * max(noise, 1e-6)
    lab, nl = ndimage.label(raw_mask)
    sizes = np.bincount(lab.ravel())[1:] if nl else np.array([])
    big = np.zeros_like(raw_mask)
    hot = np.zeros_like(raw_mask)
    if nl:
        big = np.isin(lab, np.nonzero(sizes > 2)[0] + 1)
        hot = np.isin(lab, np.nonzero(sizes <= 2)[0] + 1)
    mask = ndimage.binary_dilation(big, iterations=dilate) if dilate else big
    stats = {"n_components": int(nl), "n_isolated": int((sizes <= 2).sum()),
             "n_extended": int((sizes > 2).sum()),
             "pct_raw": float(100.0 * raw_mask.mean()),
             "pct_extended": float(100.0 * big.mean()),
             "pct_dilated": float(100.0 * mask.mean()),
             "noise": noise}
    return mask, float(100.0 * mask.mean()), stats, hot


def masked_flat(raw, mask, pedestal=0.0, window=41, passes=3, hot=None):
    # THE FLAT, AND THE GUARANTEE.
    #
    # The masked pixels are dropped (NaN) BEFORE anything is smoothed, so the
    # stars never enter the flat: in a static field the same pixel is masked
    # in every frame, so there is no data there at all and the value has to
    # come from the sky around it.
    #
    # The fill and the smoothing are the SAME operation: a normalised
    # convolution, `uniform(x * m) / uniform(m)`, which is a box filter that
    # ignores what is missing and interpolates it from its neighbours. Three
    # passes of 41 px, the app's own recipe. It is what makes a full
    # resolution flat WITH dust possible on a static field.
    #
    # `hot` are the ISOLATED spikes (a hot pixel is FIXED, so it belongs in
    # the flat) and they are put back AFTER the smoothing: the box filter
    # would dilute a single pixel 1681 times and the division would then leave
    # the hot pixel exactly where it was.
    #
    # The price, said and not hidden: a dust mote sitting UNDER a star cannot
    # be recovered, and the fraction of filled pixels is reported.
    # @return: (flat, filled_pct)
    from scipy import ndimage
    x = (np.asarray(raw, dtype=np.float32) - float(pedestal)).astype(np.float32)
    valid = np.isfinite(x) & ~np.asarray(mask, dtype=bool)
    y = np.where(valid, x, 0.0).astype(np.float32)
    v = valid.astype(np.float32)
    filled = float(100.0 * (1.0 - v.mean()))
    for _ in range(max(1, passes)):
        num = ndimage.uniform_filter(y, size=window, mode="nearest")
        den = ndimage.uniform_filter(v, size=window, mode="nearest")
        ok = den > 1e-6
        y = np.where(ok, num / np.where(ok, den, 1.0), 0.0).astype(np.float32)
        v = ok.astype(np.float32)
    if hot is not None:
        y = np.where(hot, x, y)
    med = float(np.median(y))
    return (y / med if med else y), filled


def position_sweep(paths, resp, candidates, fwhm, flux=12000.0, n_frames=15,
                   targets=(0.45, 0.60, 0.75, 0.90, 1.00, 1.10), seed=11):
    # Inject the SAME source at positions chosen BY THEIR RESPONSE (from the
    # real master flat, the only thing here that knows the response), with its
    # flux MODULATED by it (a star seen through the train arrives multiplied
    # by it), and measure it back with the app's own aperture photometry.
    #
    # The spread of the recovered flux across the field IS the flat-field
    # systematic, which is the whole reason a flat exists. Injecting a
    # constant ADU flux instead would measure NOTHING: the recovered flux
    # would be the injected one everywhere.
    #
    # Each position is measured on n_frames frames and averaged, because the
    # first version of this sweep picked random positions on ONE frame and
    # came out noise-dominated (a 0.37 mag spread even with the REAL flat, on
    # an aperture noise of about 0.09 mag per frame).
    # @return: ({label: {...}}, positions)
    r_ap, r_in, r_out = photometry.aperture_for_fwhm(fwhm)
    h, w = resp.shape
    margin = int(r_out) + 60
    # one position per response target: the pixel closest to it that is far
    # from any source
    frame0, _hh = calibration.read_image(paths[0])
    src = H.detect_sources(np.asarray(frame0, dtype=np.float32), nmax=400)
    positions = []
    for target in targets:
        band = np.zeros_like(resp, dtype=bool)
        band[margin:h - margin, margin:w - margin] = True
        sel = band & (np.abs(resp - target) < 0.02)
        if not sel.any():
            continue
        ys, xs = np.nonzero(sel)
        order = np.argsort(np.hypot(ys - h / 2, xs - w / 2))[:400]
        for k in order:
            x, y = float(xs[k]), float(ys[k])
            if len(src) and float(np.min(np.hypot(src[:, 0] - x,
                                                 src[:, 1] - y))) < 40.0:
                continue
            positions.append((x, y, float(resp[int(y), int(x)])))
            break
    idx = np.linspace(0, len(paths) - 1, n_frames).astype(int)
    out = {}
    for label, flat in candidates:
        mags = []
        for (x, y, local) in positions:
            got = []
            for i in idx:
                data, _hh = calibration.read_image(paths[i])
                data = np.asarray(data, dtype=np.float64)
                if flat is not None:
                    data = data / np.asarray(flat, dtype=np.float64)
                new, xt, yt = D.inject(data, x, y, float(flux) * local, fwhm,
                                       seed=seed + i)
                if new is None:
                    continue
                f = D.aperture_flux(new, xt, yt, r_ap, r_in, r_out)
                if f is not None and f > 0:
                    got.append(f)
            if got:
                mags.append(-2.5 * math.log10(float(np.mean(got))
                                              / float(flux)))
        if mags:
            arr = np.asarray(mags)
            out[label] = {"n": len(arr), "median": float(np.median(arr)),
                          "spread": float(arr.max() - arr.min()),
                          "mag": [float(v) for v in arr]}
    return out, positions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true",
                    help="rebuild the master from the 150 flats")
    ap.add_argument("--fit", action="store_true",
                    help="also run the rank-1 fit, which DOES NOT WORK "
                         "(see the docstring) and costs 100 s")
    ap.add_argument("--sweep", action="store_true",
                    help="also run the position sweep, which does NOT decide "
                         "anything (see the docstring) and costs minutes")
    args = ap.parse_args()

    report = {}
    cache = _master_path()
    if args.rebuild or not os.path.exists(cache):
        paths = flat_paths()
        print(f"master real: {len(paths)} flats")
        raw, seconds = build_master(paths)
        np.save(cache, raw)
        report["master_seconds"] = seconds
    else:
        raw = np.load(cache)
        print(f"master real: leido de {cache}")
    norm = raw / float(np.median(raw))
    real_smooth = smooth(norm)
    report["master_raw"] = _stats("master real (crudo)", raw)
    report["master_norm"] = _stats("master real (normalizado)", norm)
    report["master_smooth"] = _stats("master real (suave 41 px)", real_smooth)
    ys, xs = np.unravel_index(np.argmax(raw), raw.shape)
    ys2, xs2 = np.unravel_index(np.argmin(raw), raw.shape)
    report["mote"] = {"bright": {"y": int(ys), "x": int(xs),
                                 "value_norm": float(norm[ys, xs])},
                      "deepest": {"y": int(ys2), "x": int(xs2),
                                  "value_norm": float(norm[ys2, xs2])}}

    lights = H.dataset_paths("2025FG18")
    print(f"pseudo-flat de hoy sobre {len(lights)} tomas de FG18")
    t0 = time.time()
    flat_now, info_now = calibration.pseudo_flat(lights)
    report["today_seconds"] = time.time() - t0
    report["today_info"] = {k: v for k, v in (info_now or {}).items()
                            if k != "model_range"}
    report["today_flat"] = _stats("pseudo-flat de hoy", flat_now)

    print(f"estadistico crudo (percentil 33) sobre {len(lights)} tomas")
    raw_p33, stat_s = raw_stat(lights, order=0.33)
    report["stat_seconds"] = stat_s
    report["raw_p33"] = _stats("estadistico crudo (p33)", raw_p33)
    level = float(np.median(raw_p33))

    mask, mask_pct, mstats, hot = star_mask(raw_p33)
    report["starmap"] = mstats
    print(f"mascara de estrellas: {mstats['n_components']} componentes, "
          f"{mstats['n_isolated']} aislados, {mstats['n_extended']} extensos, "
          f"mascara dilatada {mask_pct:.2f} %")

    print()
    print("=" * 78)
    print("EL MASTER REAL")
    for key in ("master_raw", "master_norm", "master_smooth"):
        s = report[key]
        print(f"  {s['name']:28s} mediana {s['median']:10.4g}  "
              f"min {s['min']:10.4g}  max {s['max']:10.4g}  "
              f"p5 {s['p5']:10.4g}  p95 {s['p95']:10.4g}")
    m = report["mote"]
    print(f"  zona mas brillante: {m['bright']['value_norm']:.4f} en "
          f"(x={m['bright']['x']}, y={m['bright']['y']})")
    print(f"  mota mas profunda:  {m['deepest']['value_norm']:.4f} en "
          f"(x={m['deepest']['x']}, y={m['deepest']['y']})")
    print()
    print("EL PSEUDO-FLAT DE HOY (el 'antes')")
    print(f"  tipo: {info_now.get('kind')}  residuo: "
          f"{info_now.get('residual_pct')} %  ({report['today_seconds']:.1f} s)")
    s = report["today_flat"]
    print(f"  min {s['min']:.4f}  max {s['max']:.4f}  p1 {s['p1']:.4f}  "
          f"p99 {s['p99']:.4f}   <-- un maximo de 2.8 es una ESTRELLA")

    print()
    print("EL FLAT ENMASCARADO (el 'despues')")
    flat_m, filled = masked_flat(raw_p33, mask)
    report["masked_filled_pct"] = filled
    report["masked_flat"] = _stats("flat enmascarado", flat_m)
    p5, med, p95, spread = ratio_spread(flat_m, real_smooth)
    report["masked_vs_real"] = {"p5": p5, "p50": med, "p95": p95,
                               "spread": spread}
    print(f"  rellena el {filled:.2f} % de los pixeles (los de las estrellas)")
    s = report["masked_flat"]
    print(f"  min {s['min']:.4f}  max {s['max']:.4f}  p1 {s['p1']:.4f}  "
          f"p99 {s['p99']:.4f}")
    print(f"  vs master real: p5 {p5:.4f}  p95 {p95:.4f}  dispersion "
          f"{100 * spread:5.2f} %")

    print()
    print("EL PEDESTAL, QUE ES EL CONFUSOR PRINCIPAL")
    fit = pedestal_fit_lights(norm, flat_m)
    report["pedestal_lights"] = fit
    best = min(fit, key=lambda t: t[1])
    for p, sp in fit:
        mark = "  <-- mejor" if (p, sp) == best else ""
        print(f"    p = {p:5.2f} (pedestal / cielo) -> dispersion "
              f"{100 * sp:5.2f} %{mark}")
    report["best_p"] = best[0]
    report["best_spread"] = best[1]
    # p is pedestal / SKY SIGNAL, and the sky's signal is the level MINUS the
    # pedestal, so the absolute pedestal is P = p * level / (1 + p). Getting
    # this wrong (subtracting p * level) pushed the corners negative and gave
    # an absurd 81 % in the first run of this bench.
    p_adu = best[0] * level / (1.0 + best[0])
    report["pedestal_adu"] = p_adu
    print(f"  con el pedestal quitado: {100 * best[1]:.2f} % "
          f"(sin quitarlo: {100 * fit[0][1]:.2f} %)")
    print(f"  el nivel de las tomas es {level:.0f} ADU y el cielo "
          f"{level - p_adu:.0f}, asi que el pedestal es {p_adu:.0f} ADU "
          f"({100 * p_adu / level:.0f} % del nivel)")
    comp = 1.0 / (1.0 + best[0])
    report["compression"] = comp
    print(f"  LA COMPRESION DEL FLAT: 1 / (1 + p) = {comp:.2f} -> el "
          f"pseudo-flat corrige solo el {100 * comp:.0f} % del viñeteado")
    # Subtracting that scalar from the raw statistic is NOT the same as the
    # model correction above, and the number says so (10 % against 4 %): the
    # pseudo-flat measures the train's response TIMES the sky's shape, so its
    # own shape is not the train's and the difference has to show up
    # somewhere. It is the honest limit of the method and it is 0.045 mag.
    flat_mp, filled_p = masked_flat(raw_p33, mask, pedestal=p_adu)
    p5, med, p95, spread = ratio_spread(flat_mp, real_smooth)
    report["masked_ped_vs_real"] = {"p5": p5, "p50": med, "p95": p95,
                                    "spread": spread}
    report["masked_ped_flat"] = _stats("flat enmascarado sin pedestal",
                                       flat_mp)
    print(f"  el flat enmascarado SIN el pedestal: p5 {p5:.4f}  p95 {p95:.4f}  "
          f"dispersion {100 * spread:5.2f} %")

    # the app's own criterion for "is this flat clean?": the small-scale
    # structure that survived the smoothing, in per cent.
    #
    # AND IT DOES NOT WORK, which is why today's flat slipped through. It is
    # a SCALED MAD, and the MAD is robust by construction: the stars cover
    # 0.3 % of the pixels, so a flat carrying them (a maximum of 2.83, seven
    # times the real flat's own maximum) moves the number by nothing at all.
    # Measured: today's flat 0.06 %, the masked flat 0.05 %, and the REAL
    # master 0.65 % (it carries the dust, which is fine structure). The
    # threshold of 2 % therefore passes everything.
    print()
    print("EL RESIDUO DE PEQUENA ESCALA (el criterio de la app, y no sirve)")
    for label, cand in (("flat de hoy", flat_now),
                        ("flat enmascarado", flat_m),
                        ("master real", norm)):
        ref = smooth(cand)
        r = (cand / np.maximum(ref, 1e-6)) - 1.0
        res = float(100.0 * outliers.scaled_mad(r.ravel()))
        p999 = float(100.0 * np.percentile(np.abs(r), 99.9))
        report[f"residual_{label.replace(' ', '_')}"] = res
        report[f"residual999_{label.replace(' ', '_')}"] = p999
        print(f"  {label:18s}: MAD {res:5.2f} %   |p99.9| {p999:6.2f} %")

    print()
    print("LA GARANTIA, BIEN PLANTEADA: desviacion sobre el suavizado EN LOS")
    print("PIXELES QUE SE ENMASCARARON (donde habia una estrella). El polvo")
    print("no entra aqui, porque no esta enmascarado y es un hundimiento.")
    for label, cand in (("flat de hoy", flat_now),
                        ("flat enmascarado", flat_m),
                        ("master real", norm)):
        ref = smooth(cand)
        dev = np.abs((cand / np.maximum(ref, 1e-6)) - 1.0)
        at = dev[mask]
        report[f"atmask_{label.replace(' ', '_')}"] = {
            "p50": float(100 * np.median(at)),
            "p99": float(100 * np.percentile(at, 99)),
            "max": float(100 * at.max())}
        print(f"  {label:18s}: p50 {100 * np.median(at):5.2f} %   "
              f"p99 {100 * np.percentile(at, 99):6.2f} %   "
              f"max {100 * at.max():8.2f} %")

    # ---- los píxeles calientes: se restauran después del suavizado
    print()
    print("LOS PIXELES CALIENTES")
    n_hot = int(hot.sum())
    if n_hot:
        flat_hot, _fh = masked_flat(raw_p33, mask, hot=hot)
        report["hot"] = {
            "n": n_hot, "pct": float(100.0 * hot.mean()),
            "raw": float(np.median(raw_p33[hot])),
            "raw_max": float(raw_p33[hot].max()),
            "smooth": float(np.median(smooth(raw_p33)[hot])),
            "restored": float(np.median(flat_hot[hot]))}
        print(f"  {n_hot} picos aislados ({100 * hot.mean():.3f} % del "
              f"fotograma)")
        print(f"  en el estadistico crudo: mediana "
              f"{report['hot']['raw']:.0f} ADU, maximo "
              f"{report['hot']['raw_max']:.0f} ADU (el cielo esta en "
              f"{level:.0f})")
        print(f"  en el flat suavizado SIN restaurar: "
              f"{report['hot']['smooth']:.0f} ADU -> la division deja el "
              f"pixel caliente donde estaba")
        print(f"  en el flat CON la restauracion: "
              f"{report['hot']['restored']:.3f} normalizado "
              f"-> la division lo quita")

    # ---- el sistemático por posición: para lo que sirve un flat
    if not args.sweep:
        out = os.path.join(H.results_dir(), "flat.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print()
        print("(el barrido por posicion queda detras de --sweep: no decide "
              "nada, ver el docstring)")
        print(f"informe: {out}")
        return
    print()
    print("EL SISTEMATICO POR POSICION (la misma fuente en todo el campo,")
    print(" modulada por la respuesta real: el master)")
    frame0, _hh = calibration.read_image(lights[len(lights) // 2])
    frame0 = np.asarray(frame0, dtype=np.float32)
    seeds = H.detect_sources(frame0, nmax=6)
    spots0 = [(float(s[0]), float(s[1])) for s in seeds]
    fwhm = float(photometry.estimate_fwhm(frame0, spots0) or 5.0)
    cands = [("sin flat", None), ("flat de hoy", flat_now),
             ("enmascarado", flat_m), ("enmasc. + pedestal", flat_mp),
             ("master real", norm)]
    sweep, positions = position_sweep(lights, norm, cands, fwhm)
    report["sweep"] = {k: {kk: vv for kk, vv in v.items() if kk != "mag"}
                       for k, v in sweep.items()}
    report["sweep_positions"] = [[float(a), float(b), float(c)]
                                 for (a, b, c) in positions]
    report["sweep_fwhm"] = fwhm
    print(f"  FWHM de la noche: {fwhm:.2f} px, {len(positions)} posiciones "
          f"con respuestas {[round(p[2], 2) for p in positions]}")
    print(f"  {'candidato':20s} {'error mediano':>14s} {'dispersion':>12s}")
    for label, _flat in cands:
        if label not in sweep:
            continue
        s = sweep[label]
        print(f"  {label:20s} {s['median']:+13.4f} m {s['spread']:11.4f} m")

    out = os.path.join(H.results_dir(), "flat.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print()
    print(f"informe: {out}")


if __name__ == "__main__":
    main()
