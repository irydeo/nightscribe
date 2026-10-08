############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Stack benchmark: the combination, head to head
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Four stacks of the same 207 frames, one injection test, one verdict.

The question this answers: how much depth is lost by combining the frames with
the MEDIAN instead of the sigma-clipped mean, and where does that leave us
against Tycho-Tracker?

    app      the stack the application saved (median, 9.40 ADU/px)
    ours-s   the same frames and the same engine, sigma-clipped (7.73)
    ours-m   the same, median (9.38)
    tycho    Tycho-Tracker's own stack

All four are measured with the SAME positions (chosen by an absolute criterion
in ADU, valid in every one of them) and the same aperture, so the only thing
that changes between rows is the image.

Usage:
    python tools/bench/bench_combine.py
"""

import glob
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bench_depth as D                                 # noqa: E402
import harness as H                                     # noqa: E402
from nightscribe.core import calibration, fits_io       # noqa: E402
from nightscribe.core import track_stack as ts          # noqa: E402

FRAMES = "/home/boreal/Develop/astronomy/dataset/2025FG18/20250331_c/*.fits"
APP = ("/home/boreal/.local/share/NightScribe/projects/117-2025_FG18/"
       "2025FG18_obs1_20250331T203044.fits")
TYCHO = "/home/boreal/Develop/astronomy/dataset/2025FG18/tycho_result.fit"
BOX = (0, 0, 2008, 2008)


def build(frames, q, method):
    stack, _rep = ts.stack_group(frames, (0, len(frames)), q, method, BOX,
                                 (2048, 2048), cfg=None,
                                 loader=calibration.read_image, track=True)
    return np.asarray(stack, dtype=np.float64)


def main():
    paths = sorted(glob.glob(FRAMES))
    frames = ts.load_sequence(paths, None)
    ref, w0 = ts.solve_reference(frames)
    ts.register_sequence(frames, ref_index=frames.index(ref),
                         allow_rotation=False)
    header, app = fits_io.read_fits(APP)
    app = np.asarray(app, dtype=np.float64)
    t_mid = ts.group_mid_jd(frames, (0, len(frames)))
    ra0, dec0 = float(header["NS_RA"]), float(header["NS_DEC"])
    rate, pa = float(header["NS_RATE"]), float(header["NS_PA"])
    dra = rate * math.sin(math.radians(pa))
    ddec = rate * math.cos(math.radians(pa))

    def motion(jd):
        dt = (jd - t_mid) * 1440.0
        c = math.cos(math.radians(dec0))
        return (ra0 + dra * dt / 3600.0 / c, dec0 + ddec * dt / 3600.0)
    ts.object_positions(frames, motion)
    _t, q = ts.group_q(frames, (0, len(frames)), w0, motion)
    stacks = {"app": app}
    for method in ("sigma", "median"):
        print(f"apilando con {method} ...")
        stacks["ours-" + method[0]] = build(frames, q, method)
    stacks["tycho"] = np.asarray(fits_io.read_fits(TYCHO)[1], dtype=np.float64)
    # las posiciones, validas en LOS CUATRO
    spots = D.common_spots([(k, v) for k, v in stacks.items()], D.TRIALS,
                           seed=7)
    print(f"posiciones limpias en los cuatro: {len(spots)}\n")
    r_ap, r_in, r_out = D.photometry.aperture_for_fwhm(D.FWHM)
    rows = {}
    for name, data in stacks.items():
        finite = np.isfinite(data)
        noise = D.photometry.sky_sigma(data[finite])
        levels = {}
        for flux in D.FLUXES:
            got, snrs = [], []
            for j, (sx, sy) in enumerate(spots):
                inj, xt, yt = D.inject(data, sx, sy, flux, D.FWHM,
                                       seed=1000 + j)
                if inj is None:
                    continue
                f = D.aperture_flux(inj, xt, yt, r_ap, r_in, r_out)
                if f is None:
                    continue
                got.append(float(f))
                s = D.local_noise(inj, xt, yt, r_ap, r_in, r_out)
                if s:
                    snrs.append(float(flux) / (s * math.sqrt(math.pi * r_ap ** 2)))
            n, med, scatter = H.robust_stats(got)
            _sn, snr_med, _ss = H.robust_stats(snrs)
            levels[str(flux)] = {
                "scatter_adu": scatter,
                "bias": ((med - flux) / flux) if med is not None else None,
                "snr_annulus": snr_med,
                "snr_empirical": (flux / scatter) if scatter else None}
        xs, ys = [], []
        for flux in D.FLUXES:
            b = levels[str(flux)]
            if b["snr_empirical"]:
                xs.append(math.log10(flux)); ys.append(math.log10(b["snr_empirical"]))
        limit = None
        if len(xs) >= 2:
            a = np.polyfit(xs, ys, 1)
            if a[0] > 0:
                limit = 10 ** ((math.log10(D.SNR_TARGET) - a[1]) / a[0])
        rows[name] = {"noise_adu": float(noise), "levels": levels,
                      "limit_flux_adu": limit,
                      "limit_mag": D.mag_of(limit) if limit else None}
    print("%-10s %10s %12s %12s %12s" % ("stack", "ruido", "mag límite",
                                         "dispersión", "sesgo @700"))
    for name in ("app", "ours-s", "ours-m", "tycho"):
        r = rows[name]
        lv = r["levels"]["700.0"]
        print("%-10s %10.2f %12.2f %12.1f %11.1f %%" % (
            name, r["noise_adu"], r["limit_mag"] or float("nan"),
            lv["scatter_adu"] or float("nan"), 100 * (lv["bias"] or 0)))
    out = os.path.join(H.results_dir(), "combine.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)
    print(f"\nJSON -> {out}")


if __name__ == "__main__":
    main()
