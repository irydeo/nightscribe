############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Stack benchmark: does the interpolation buy depth?
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""One knob, one measurement: the interpolation order of the warp.

The warp is where the frames land on the output grid, and its kernel decides
two things that pull in opposite directions:

* a LOW order (bilinear) smooths, and smoothing lowers the pixel noise (it
  correlates it, so the pixel-to-pixel difference falls without any
  information being gained);
* a HIGH order (cubic spline) keeps the resolution but its prefilter has
  negative lobes and AMPLIFIES high frequencies, which is exactly where the
  noise lives.

Measured on this same visit with 40 frames: the mean comes out at 16.8 ADU/px
with order 1 and 21.5 with order 3. But pixel noise is not depth, so this
bench builds the SAME stack at each order and runs the injection and recovery
on it: the question is the limiting magnitude, not how clean it looks.

The stack is reproduced as the app builds it (reference solved, frames
registered, the object's motion from the ephemeris the stack's own header
carries), so the only difference between the variants is the kernel.

Usage:
    python tools/bench/bench_order.py
"""

import argparse
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

FRAMES = ("/home/boreal/Develop/astronomy/dataset/2025FG18/20250331_c/*.fits")
APP_STACK = ("/home/boreal/.local/share/NightScribe/projects/117-2025_FG18/"
             "2025FG18_obs1_20250331T203044.fits")
ORDERS = (1, 3, 5)
SIZE = 2008
METHOD = "sigma"


def motion_from_header(header, t_mid):
    # The object's motion the app itself used, read back from the stack's own
    # header: NS_RA/NS_DEC is the position at the middle of the run and
    # NS_RATE (arcsec/min) with NS_PA (deg, north through east) is the
    # velocity. Building it here instead of asking an ephemeris again is what
    # makes the comparison reproducible offline and identical to the run.
    # @return: callable(jd) -> (ra_deg, dec_deg)
    ra0 = float(header["NS_RA"])
    dec0 = float(header["NS_DEC"])
    rate = float(header["NS_RATE"])
    pa = float(header["NS_PA"])
    dra = rate * math.sin(math.radians(pa))     # arcsec/min towards +RA
    ddec = rate * math.cos(math.radians(pa))    # arcsec/min towards +dec

    def motion(jd):
        dt = (jd - t_mid) * 1440.0              # minutes from the middle
        cosd = math.cos(math.radians(dec0))
        return (ra0 + dra * dt / 3600.0 / cosd, dec0 + ddec * dt / 3600.0)
    return motion


def _forced_order(order):
    # A context manager that forces the warp's interpolation order. The app
    # has it fixed at 3 (scipy's cubic spline) and this is a bench, so the
    # knob is turned from outside instead of changing production code.
    class _Forced:
        def __enter__(self):
            self._orig = ts._warp_to_box

            def patched(*a, **kw):
                kw["order"] = order
                return self._orig(*a, **kw)
            ts._warp_to_box = patched
            return self

        def __exit__(self, *exc):
            ts._warp_to_box = self._orig
            return False
    return _Forced()


def build(frames, q, box, shape, order):
    # @return: the stack (float64, NaN where no frame reached)
    with _forced_order(order):
        stack, _rep = ts.stack_group(frames, (0, len(frames)), q, METHOD,
                                     box, shape, cfg=None,
                                     loader=calibration.read_image,
                                     track=True)
    return np.asarray(stack, dtype=np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out_dir = args.out or H.results_dir()
    paths = sorted(glob.glob(FRAMES))
    if not paths:
        print("no hay frames"); return
    print(f"frames: {len(paths)}")
    frames = ts.load_sequence(paths)
    ref, w0 = ts.solve_reference(frames)
    print(f"referencia: {ref.path.split('/')[-1] if ref else None}")
    ts.register_sequence(frames, ref_index=frames.index(ref),
                         allow_rotation=False)
    ok = sum(1 for f in frames if ts.usable(f))
    print(f"frames utilizables: {ok} de {len(frames)}")
    header, _d = fits_io.read_fits(APP_STACK)
    t_mid = ts.group_mid_jd(frames, (0, len(frames)))
    motion = motion_from_header(header, t_mid)
    ts.object_positions(frames, motion)
    _t, q = ts.group_q(frames, (0, len(frames)), w0, motion)
    shape = (2048, 2048)
    box = ts.box_around(q, SIZE, shape)
    print(f"q = ({q[0]:.1f}, {q[1]:.1f})   caja = {box}")
    reports = {}
    spots = None
    for order in ORDERS:
        print(f"\n[orden {order}] apilando ...")
        stack = build(frames, q, box, shape, order)
        if spots is None:
            # the SAME positions in the three orders, and by the absolute
            # criterion (ADU above the sky, not sigmas of each variant's own
            # noise), so the kernel is the only thing that changes
            spots = D.common_spots([(f"order{order}", stack)], D.TRIALS, seed=7)
            print(f"  posiciones limpias: {len(spots)}")
        finite = np.isfinite(stack)
        noise = D.photometry.sky_sigma(stack[finite])
        print(f"  ruido por píxel: {noise:.2f} ADU/px")
        # the injection, with the SAME positions in the three orders, so the
        # only thing that changes between them is the kernel
        rep = {"order": order, "noise_adu": float(noise), "levels": {}}
        r_ap, r_in, r_out = D.photometry.aperture_for_fwhm(D.FWHM)
        for flux in D.FLUXES:
            got, snrs = [], []
            for j, (sx, sy) in enumerate(spots):
                inj, xt, yt = D.inject(stack, sx, sy, flux, D.FWHM,
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
            emp = (flux / scatter) if (scatter and scatter > 0) else None
            rep["levels"][str(flux)] = {
                "mag": D.mag_of(flux), "n": n, "scatter_adu": scatter,
                "bias": ((med - flux) / flux) if med is not None else None,
                "snr_annulus": snr_med, "snr_empirical": emp}
            print("    %6.0f ADU (mag %5.2f)  sesgo %+6.1f %%  dispersión %6.1f  "
                  "SNR(empírico) %5.2f" % (flux, D.mag_of(flux),
                                           100 * (rep["levels"][str(flux)]["bias"] or 0),
                                           scatter or 0, emp or 0))
        xs, ys = [], []
        for flux in D.FLUXES:
            b = rep["levels"][str(flux)]
            if b["snr_empirical"]:
                xs.append(math.log10(flux)); ys.append(math.log10(b["snr_empirical"]))
        if len(xs) >= 2:
            a = np.polyfit(xs, ys, 1)
            if a[0] > 0:
                lf = 10 ** ((math.log10(D.SNR_TARGET) - a[1]) / a[0])
                rep["limit_flux_adu"] = lf
                rep["limit_mag"] = D.mag_of(lf)
                print("  -> límite a SNR 5: %.0f ADU (mag %.2f)" % (lf, rep["limit_mag"]))
        reports[str(order)] = rep
    print("\n=== resumen ===")
    print("%-8s %12s %12s %12s" % ("orden", "ruido", "mag límite", "dispersión r=5"))
    for order in ORDERS:
        r = reports[str(order)]
        sc = r["levels"][str(700.0)]["scatter_adu"]
        print("%-8d %12.2f %12.2f %12.1f" % (order, r["noise_adu"],
                                             r.get("limit_mag") or float("nan"),
                                             sc or float("nan")))
    path = os.path.join(out_dir, "order.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(reports, fh, indent=1, ensure_ascii=False)
    print(f"\nJSON -> {path}")


if __name__ == "__main__":
    main()
