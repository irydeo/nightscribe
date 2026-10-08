############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Stack benchmark: the frames the registration left out
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Should the frames the registration refused be stacked anyway?

The engine refuses a frame whose transform could not be verified and counts it
instead of using it, and that rule has a measured reason (on 2025 UR, 63 of 140
frames failed and stacking them crooked took the base SNR from 15.8 to 11.4).

On 2025 FG18 the 21 refused frames are not crooked: their inherited transform
agrees with their neighbours (the field moves 4 px in the whole visit). What
they have is a much worse PSF, 8.34 px against 5.08, and a broad PSF is what
makes the registration rms too large in the first place. So the question is not
about the alignment but about the SEEING:

* adding them is 10 % more integration, which is 1.055x in noise (0.06 mag);
* but a stack is the average of its frames' point spreads, so adding 21 broad
  ones broadens the object's own profile, and a broader profile needs a bigger
  aperture, which is more noise.

The two pull in opposite directions and the answer is not obvious, so it is
measured: both stacks are built and the injection is run on each with a source
of the SAME profile the stack itself has (which is the honest way to ask "how
well would I see the object in this image").

Usage:
    python tools/bench/bench_frames.py
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
from nightscribe.core import photometry                 # noqa: E402
from nightscribe.core import register                   # noqa: E402
from nightscribe.core import track_stack as ts          # noqa: E402

FRAMES = "/home/boreal/Develop/astronomy/dataset/2025FG18/20250331_c/*.fits"
APP_STACK = ("/home/boreal/.local/share/NightScribe/projects/117-2025_FG18/"
             "2025FG18_obs1_20250331T203044.fits")
BOX = (0, 0, 2008, 2008)
METHOD = "sigma"


def effective_fwhm(fwhms):
    # A stack's point spread is the average of its frames' (the sum of two
    # gaussians is a gaussian whose variance is the average): the FWHM of the
    # mixture is the root mean square of the individual FWHMs, not their mean.
    # @args: fwhms - the FWHMs of the frames that go in, in px
    # @return: the stack's FWHM in px
    vals = [f for f in fwhms if f and f > 0]
    if not vals:
        return None
    return float(math.sqrt(sum(f * f for f in vals) / len(vals)))


def build(frames, q, usable_patch=False):
    # @args: usable_patch - True to stack EVERY frame, including the ones the
    #        registration refused (which keep their inherited transform)
    saved = ts.usable
    if usable_patch:
        ts.usable = lambda f: f.transform is not None
    try:
        stack, _rep = ts.stack_group(frames, (0, len(frames)), q, METHOD, BOX,
                                     (2048, 2048), cfg=None,
                                     loader=calibration.read_image, track=True)
    finally:
        ts.usable = saved
    return np.asarray(stack, dtype=np.float64)


def main():
    paths = sorted(glob.glob(FRAMES))
    frames = ts.load_sequence(paths, None)
    ref, w0 = ts.solve_reference(frames)
    ts.register_sequence(frames, ref_index=frames.index(ref),
                         allow_rotation=False)
    header, _app = fits_io.read_fits(APP_STACK)
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
    # the seeing of every frame, measured once
    good = [f for f in frames if ts.usable(f)]
    ref_data = calibration.read_image(ref.path)[0]
    stars = [(float(s[0]), float(s[1]))
             for s in register.detect_stars(register.source_image(ref_data))[:10]]
    fwhms = {}
    for f in frames:
        data = calibration.read_image(f.path)[0]
        fwhms[f.path] = photometry.estimate_fwhm(data, stars)
    f_good = [fwhms[f.path] for f in good]
    f_all = [fwhms[f.path] for f in frames]
    print("frames: %d buenos, %d rechazados" % (len(good), len(frames) - len(good)))
    print("FWHM: buenos %.2f px (mixtura %.2f) | los 207 %.2f px (mixtura %.2f)"
          % (np.median([x for x in f_good if x]),
             effective_fwhm(f_good),
             np.median([x for x in f_all if x]),
             effective_fwhm(f_all)))
    rows = {}
    for etiqueta, patch in (("186", False), ("207", True)):
        print(f"\n[stack de {etiqueta}] apilando ...")
        stack = build(frames, q, usable_patch=patch)
        fw = effective_fwhm(f_all if patch else f_good)
        finite = np.isfinite(stack)
        noise = photometry.sky_sigma(stack[finite])
        print("  ruido por píxel %.2f ADU/px | PSF efectiva %.2f px" % (noise, fw))
        # the injection, with a source of the SAME profile this stack has
        r_ap, r_in, r_out = photometry.aperture_for_fwhm(fw)
        spots_here = D.common_spots([(etiqueta, stack)], D.TRIALS, seed=7)
        levels = {}
        for flux in D.FLUXES:
            got, snrs = [], []
            for j, (sx, sy) in enumerate(spots_here):
                inj, xt, yt = D.inject(stack, sx, sy, flux, fw, seed=1000 + j)
                if inj is None:
                    continue
                f = D.aperture_flux(inj, xt, yt, r_ap, r_in, r_out)
                if f is None:
                    continue
                got.append(float(f))
                s = D.local_noise(inj, xt, yt, r_ap, r_in, r_out)
                if s:
                    snrs.append(float(flux)
                                / (s * math.sqrt(math.pi * r_ap ** 2)))
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
                xs.append(math.log10(flux))
                ys.append(math.log10(b["snr_empirical"]))
        limit = None
        if len(xs) >= 2:
            a = np.polyfit(xs, ys, 1)
            if a[0] > 0:
                limit = 10 ** ((math.log10(D.SNR_TARGET) - a[1]) / a[0])
        rows[etiqueta] = {"noise_adu": float(noise), "fwhm_px": fw,
                          "n_frames": len(good) if not patch else len(frames),
                          "levels": levels, "limit_flux_adu": limit,
                          "limit_mag": D.mag_of(limit) if limit else None}
        print("  -> límite a SNR 5: %s ADU (mag %.2f)"
              % (("%.0f" % limit) if limit else "-",
                 rows[etiqueta]["limit_mag"] or float("nan")))
    print("\n=== resumen ===")
    print("%-8s %8s %10s %10s %12s" % ("frames", "ruido", "PSF", "dispersión",
                                       "mag límite"))
    for k in ("186", "207"):
        r = rows[k]
        print("%-8s %8.2f %10.2f %10.1f %12.2f" % (
            k, r["noise_adu"], r["fwhm_px"],
            r["levels"]["700.0"]["scatter_adu"] or float("nan"),
            r["limit_mag"] or float("nan")))
    out = os.path.join(H.results_dir(), "frames.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)
    print(f"\nJSON -> {out}")


if __name__ == "__main__":
    main()
