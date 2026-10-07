############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Zero point against a real catalogue (matched filter check)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The zero point against a REAL catalogue: does the matched filter calibrate
better than the aperture, with real stars of different brightness and colour?

Why this exists and why it is not a test: P4c measured the two methods against
8 injected sources of the SAME flux, which is the cleanest possible comparison
but not a realistic one (a real sequence has stars from mag 15 to mag 19, of
every colour). The catalogue has those stars already, with their magnitudes
measured by somebody else, so the honest question becomes: with the ZERO POINT
computed the way the app computes it, which method reproduces the catalogue's
own magnitudes better?

And the answer has to be measured, not argued: the filter wins on paper by
1/sqrt(n_eff/n_ap), but its shape is a GAUSSIAN of the measured seeing, and a
model that does not match the real PSF does not add noise, it adds BIAS (the
filter's flux is 2*sm^2/(sm^2+sg^2) of the truth when the real profile is sg
and the model sm). A real catalogue is the only way to find out which of the
two effects wins, and the only one that can show the bias.

What it does, in order, and always with the app's own functions:
  1. registers the visit and builds the STAR stack (the comps are points there,
     the object is the streak: that is the stack the zero point lives on),
  2. loads the field from a real catalogue (Gaia EDR3 or APASS DR9),
  3. picks comparison stars with the app's own rules: not a VSX variable,
     isolated in the catalogue, on the sensor with its sky annulus, not
     saturated, not past the linearity, and not so faint that it cannot
     calibrate,
  4. measures each one with BOTH methods from the SAME centroid and sky
     (measure_matched returns the two fluxes of one measurement, so the
     comparison measures the weighting and nothing else),
  5. calibrates the zero point with the app's own rule and compares, per
     method: the zero point, its error, the ROBUST residual scatter, and
     leave-one-out (predict each star from the zero point of the OTHERS, so
     the star does not help calibrate itself),
  6. repeats it on sub-stacks of the visit, where the stars are fainter, and
     with the comps confined to a window around the target, which is where the
     app picks them.

Why the robust statistics and not the RMS: a real catalogue has bad rows (one
of the 40 comps here is a mag-19.5 Gaia source that measures 3.5 mag brighter
than its catalogue value: a blend, or a wrong row). One of those makes the RMS
useless and the RMS is not what a run publishes: the app's own zero-point
error is a scaled MAD over the comps, and that is the number compared here.

Usage:

    python benchmarks/zp_catalog_check.py --carpeta DIR --objeto "2025 UR"
    python benchmarks/zp_catalog_check.py --carpeta DIR --ventana 150
    python benchmarks/zp_catalog_check.py --carpeta DIR --catalogo apass
"""

import argparse
import collections
import glob
import logging
import math
import time
from pathlib import Path

import numpy as np

from nightscribe.config import config
from nightscribe.core import compstars, outliers, photometry, track_stack
from nightscribe.core import wcs as wcs_mod

logger = logging.getLogger("zp_catalog_check")


# ------------------------------ the visit -------------------------------

def load_visit(folder, objeto, mpc, half_box):
    # @args: folder - the visit's FITS folder, objeto - designation for the
    #        ephemeris ("" skips it), mpc - MPC code of the site, half_box -
    #        half side of the measured box, in pixels
    # @return: (frames, ref, w0, box, shape, motion)
    # The box is a cutout of the reference grid: the comps have to sit where
    # the stack is, and a 1200 px box around the field centre fits the RAM
    # budget of the warp (a full 2048 px sequence would stream for minutes to
    # measure stars at the frame's edge, which is not what is being checked).
    paths = sorted(glob.glob(str(Path(folder) / "*.fit*")))
    if not paths:
        raise SystemExit(f"no frames in {folder}")
    frames = track_stack.load_sequence(paths, config)
    print(f"{len(paths)} frames, {len(frames)} readable")
    ref, w0 = track_stack.solve_reference(frames)
    if w0 is None:
        raise SystemExit("the reference frame could not be solved")
    print("reference:", Path(ref.path).name)
    t0 = time.time()
    track_stack.register_sequence(frames)
    rep = track_stack.registration_report(frames)
    print("registration: %.1fs, %d of %d usable, rms %.2f px%s"
          % (time.time() - t0, rep["n_ok"], rep["n_total"], rep["rms_median"],
             " (two runs)" if rep["multi_run"] else ""))
    motion = None
    if objeto:
        lat = float(ref.header.get("SITELAT", 0.0))
        lon = float(ref.header.get("SITELONG", 0.0))
        eph = track_stack.sequence_ephemeris(frames, objeto, site=mpc,
                                             lat=lat, lon=lon)
        print("ephemeris:", eph["source"] or "-", "|", eph["reason"] or "",
              "| mag", eph["mag"], eph["band"] or "")
        motion = eph["motion"]
        if motion is not None:
            track_stack.object_positions(frames, motion)
        _report_motion(frames, motion)
    else:
        # the comps do not care where the object is, but the stacker asks
        # (`inside_frame`): the centre of the frame is the honest "I do not
        # know", and it keeps every frame of a visit that does not drift
        shape = (int(ref.header["NAXIS1"]), int(ref.header["NAXIS2"]))
        for frame in frames:
            frame.object_xy = (shape[0] / 2.0, shape[1] / 2.0)
    shape = (int(ref.header["NAXIS1"]), int(ref.header["NAXIS2"]))
    box = (shape[0] // 2 - half_box, shape[1] // 2 - half_box,
           shape[0] // 2 + half_box, shape[1] // 2 + half_box)
    return frames, ref, w0, box, shape, motion


def _report_motion(frames, motion):
    # @args: frames - the visit, motion - the ephemeris' callable (or None)
    # @return: nothing; prints how far the object walks, which is what decides
    #          whether the comps on the OBJECT's stack are streaks
    if motion is None:
        return
    stamps = [f.t_mid_jd for f in frames if f.t_mid_jd is not None]
    if len(stamps) < 2:
        return
    ra0, dec0 = motion(min(stamps))
    ra1, dec1 = motion(max(stamps))
    sep = math.hypot((ra1 - ra0) * math.cos(math.radians(dec0)),
                     dec1 - dec0) * 3600.0
    minutes = (max(stamps) - min(stamps)) * 1440.0
    print("object: %.1f arcsec in %.1f min (%.2f arcsec/min)"
          % (sep, minutes, sep / minutes))


# ------------------------------- the field -------------------------------

def load_field(w0, shape, catalogo, half_box, margin_arcsec=90.0):
    # @args: w0 - the reference WCS, shape - the frame size, catalogo -
    #        "gaia"|"apass", half_box - the measured box's half side,
    #        margin_arcsec - the safety ring no comp may sit inside
    # @return: the compstars.load_field dict
    # The query radius covers the box the comps live in, and the ring keeps
    # the candidates away from the box's edge: a star whose sky annulus falls
    # off the cutout cannot be measured, and `validate_on_plate` would say so
    # one by one.
    scale = math.sqrt(abs(np.linalg.det(w0.wcs.cd))) * 3600.0
    fov = (2.0 * half_box * scale) / 60.0
    ra, dec = w0.wcs.crval
    print("field: %.3f %.3f, box %.1f arcmin, catalogue %s"
          % (ra, dec, fov, catalogo))
    field = compstars.load_field(catalogo, ra, dec, fov, naxis=shape,
                                 margin_arcsec=margin_arcsec)
    if field is None:
        raise SystemExit("the catalogue did not answer")
    print("catalogue: %d stars, band %s, VSX %d"
          % (len(field["stars"]), field["band"], len(field["variables"])))
    return field


def pick_comps(field, stack, wbox, radii, mag_min, mag_max, sat_adu,
               linear_adu, gain, ron, margin_px, n_max, ventana_px=None):
    # @args: field - the loaded field, stack - the star stack, wbox - its
    #        Wcs, radii - the aperture triple, mag_min/mag_max - the catalogue
    #        range to look at, sat_adu/linear_adu/gain/ron - the detector's
    #        facts, margin_px - the ring kept clear at the edges, n_max - how
    #        many comps to keep at most, ventana_px - keep the comps within
    #        this radius of the box's centre (None = the whole box), which is
    #        where the app picks them: the filter's flux follows the PSF, so
    #        the distance to the target is not cosmetic
    # @return: (comps, rejected) with comps the star dicts that passed
    # The rules are the app's own, applied by the app's own functions: a VSX
    # variable never enters a zero point, an isolated star is a star whose sky
    # is sky, and `validate_on_plate` is the observer's plate saying whether
    # the catalogue's star is measurable HERE (saturated, past the linearity,
    # too faint, off the sensor).
    h, w = stack.shape
    centre = (w / 2.0, h / 2.0)
    inside = []
    for star in field["stars"]:
        if not (mag_min <= float(star["mag"]) <= mag_max):
            continue
        if star.get("vsx") is not None:
            continue
        try:
            x, y = wbox.sky_to_pixel(star["ra"], star["dec"])
        except Exception:
            continue
        if not (margin_px <= x < w - margin_px
                and margin_px <= y < h - margin_px):
            continue
        if ventana_px and math.hypot(x - centre[0],
                                     y - centre[1]) > ventana_px:
            continue
        inside.append(star)
    isolated = _isolated(field["stars"], inside)
    kept, rejected = [], []
    for star in isolated:
        verdict = compstars.validate_on_plate(
            star, stack, wbox, radii=radii, sat_adu=sat_adu,
            linear_adu=linear_adu, gain=gain, ron=ron, shape=stack.shape,
            margin_px=margin_px)
        if verdict is None:
            kept.append(star)
        else:
            rejected.append((star, verdict["key"]))
    # spread over the magnitude range: the check wants the faint end as much
    # as the bright one, and the catalogue's own order would give a clump
    kept.sort(key=lambda s: s["mag"])
    if n_max and len(kept) > n_max:
        idx = np.linspace(0, len(kept) - 1, n_max).round().astype(int)
        kept = [kept[i] for i in sorted(set(idx.tolist()))]
    return kept, rejected


def _isolated(stars, candidates, tol_arcsec=compstars.ISOLATION_ARCSEC):
    # @args: stars - every catalogue star in the field, candidates - the ones
    #        to test, tol_arcsec - how close a neighbour has to be to spoil it
    # @return: the candidates with no neighbour inside tol_arcsec
    # Pairwise on purpose: the field is a couple of thousand stars, so the
    # whole matrix is a few megabytes and the answer is exact (the app's grid
    # exists for the interactive case, where the field is bigger and the check
    # runs on every keystroke).
    if not candidates:
        return []
    ra = np.radians(np.array([float(s["ra"]) for s in stars]))
    dec = np.radians(np.array([float(s["dec"]) for s in stars]))
    sin = np.sin(dec)
    cos = np.cos(dec)
    # arcseconds, and the conversion is the whole point: a tolerance fed to
    # math.radians as if it were degrees is a 10 DEGREE window, and with one
    # of those every star has a neighbour and none is isolated (measured: it
    # returned 0 of 197 candidates and the field looked empty)
    tol = math.radians(float(tol_arcsec) / 3600.0)
    keep = []
    for star in candidates:
        r = math.radians(float(star["ra"]))
        d = math.radians(float(star["dec"]))
        cossep = np.sin(d) * sin + np.cos(d) * cos * np.cos(r - ra)
        sep = np.arccos(np.clip(cossep, -1.0, 1.0))
        # itself is at zero distance, so the test is "no OTHER star"
        if int((sep < tol).sum()) <= 1:
            keep.append(star)
    return keep


# ---------------------------- the measurement ----------------------------

def measure_comps(comps, stack, wbox, fwhm, radii):
    # @args: comps - the stars, stack - the image to measure on, wbox - its
    #        Wcs, fwhm - the seeing, radii - the aperture triple
    # @return: a list of dicts, one per comp, with both methods' flux
    # ONE call per star gives BOTH numbers: `measure_matched` measures the
    # aperture first and then re-weights the same pixels with the same
    # centroid and the same sky, so `flux_ap` and `flux` differ ONLY in the
    # weighting. That is what makes the comparison a comparison (and it is
    # exactly what the app does when the filter is on: the dispatcher sends
    # the target and the comps through the same function).
    psf = photometry.gaussian_psf(fwhm)
    out = []
    for star in comps:
        try:
            x, y = wbox.sky_to_pixel(star["ra"], star["dec"])
        except Exception:
            continue
        res = photometry.measure_matched(
            stack, x, y, psf, r_ap=radii[0], r_ann_in=radii[1],
            r_ann_out=radii[2], fwhm=fwhm)
        if not res.get("ok"):
            continue
        out.append({"star": star, "x": float(res["x"]), "y": float(res["y"]),
                    "flux": float(res["flux"]),
                    "flux_ap": float(res["flux_ap"]),
                    "snr": float(res.get("snr") or 0.0),
                    "snr_ap": float(res.get("snr_ap") or 0.0),
                    "peak": float(res.get("peak") or 0.0)})
    return out


def _inst(flux):
    # @args: flux - ADU
    # @return: the instrumental magnitude, or None
    if flux is None or flux <= 0:
        return None
    return -2.5 * math.log10(float(flux))


def compare(rows, label, band):
    # @args: rows - the measured comps, label - what to print in the title,
    #        band - the catalogue band
    # @return: a dict with both methods' numbers
    # The statistics, and why each one:
    #  - the zero point and its error, from the app's own calibration, is what
    #    a run would publish (the error is a scaled MAD over the comps);
    #  - the residual scatter is how well a constant fits the stars, colour
    #    included, and it is reported as a scaled MAD because a real catalogue
    #    carries bad rows (see the module docstring);
    #  - leave-one-out is the honest per-star accuracy: each star is predicted
    #    from the zero point of the OTHERS, so it cannot pull its own answer,
    #    and its scaled MAD is the number to compare;
    #  - the paired difference (filter minus aperture, per star) says whether
    #    the two methods agree in the mean and how much they scatter around
    #    each other: it is the only statistic that cancels the catalogue and
    #    the sky, because both methods measured the same pixels;
    #  - the median SNR says at what signal-to-noise all of the above was
    #    measured, which is the only way to compare a group against a stack.
    inst = [_inst(r["flux"]) for r in rows]
    inst_ap = [_inst(r["flux_ap"]) for r in rows]
    cat = [float(r["star"]["mag"]) for r in rows]
    bvs = [r["star"].get("bv") for r in rows]
    xs = np.array([r["x"] for r in rows])
    out = {"label": label, "n": len(rows), "band": band}
    for key, values in (("mf", inst), ("ap", inst_ap)):
        plain = photometry.calibrate_zero_point(values, cat)
        out[key] = {"zp": plain["zp"], "zp_err": plain["zp_err"],
                    "n": plain["n"]}
        resid = np.array([c - i - plain["zp"] for i, c in zip(values, cat)
                          if i is not None and c is not None])
        out[key]["scatter"] = float(outliers.scaled_mad(resid))
        out[key]["outliers"] = int((np.abs(resid) > 0.5).sum())
        out[key]["loo"] = _loo(values, cat)
        snrs = [r["snr"] if key == "mf" else r["snr_ap"] for r in rows]
        out[key]["snr"] = float(np.median(snrs))
        out[key]["snr_lo"] = float(np.percentile(snrs, 20))
        # the colour term: a Clear plate against Gaia G carries the stars'
        # colour, and that mismatch is in BOTH methods. Removing it leaves the
        # method's own noise, which is the number the filter's Gaussian
        # assumption has to survive.
        fit = photometry.calibrate_with_color(values, cat, bvs)
        out[key]["color_used"] = bool(fit.get("color_used"))
        out[key]["k"] = fit.get("k")
        out[key]["scatter_color"] = (float(outliers.scaled_mad(
            np.array(fit["residuals"]))) if fit.get("residuals") else None)
    # the paired difference: what the filter reads minus what the aperture
    # reads, on the same star, in magnitudes. Its median is the systematic
    # (the zero point absorbs it when the comps share the target's PSF) and
    # its scatter is how much the two disagree from star to star.
    d = np.array([i - j for i, j in zip(inst, inst_ap)
                  if i is not None and j is not None])
    out["pair"] = {"median": float(np.median(d)),
                   "mad": float(outliers.scaled_mad(d)),
                   "corr_x": float(np.corrcoef(xs[:len(d)], d)[0, 1])}
    # the brightness split: the filter's gain is a weighting, so it has to be
    # worth MORE on the fainter half. If it is worth the same on both, the
    # difference is not the weighting.
    order = sorted(range(len(rows)), key=lambda i: cat[i])
    half = len(order) // 2
    for key, values in (("mf", inst), ("ap", inst_ap)):
        for name, idx in (("bright", order[:half]), ("faint", order[half:])):
            out[key]["loo_" + name] = _loo([values[i] for i in idx],
                                           [cat[i] for i in idx])
    # THE BIAS AT LOW SIGNAL, which is the sharpest thing a catalogue can
    # show: the zero point is fitted on the stars that are BRIGHT enough to
    # be right (the top half by signal-to-noise), and then the residuals of
    # the faint half are read. If a method underestimates a faint star, the
    # catalogue minus the measurement comes out positive, and no zero point
    # can hide it because that zero point was not fitted on them. It is P4c's
    # measurement (the injection bench said the aperture biases +0.54 mag at
    # SNR 9 and the filter +0.23) asked of real stars this time.
    by_snr = sorted(range(len(rows)),
                    key=lambda i: (rows[i]["snr_ap"]
                                   if rows[i]["snr_ap"] else 0.0))
    half_s = max(1, len(by_snr) // 2)
    bright_s, faint_s = by_snr[half_s:], by_snr[:half_s]
    for key, values in (("mf", inst), ("ap", inst_ap)):
        zp_hi = photometry.calibrate_zero_point(
            [values[i] for i in bright_s], [cat[i] for i in bright_s])["zp"]
        for name, idx in (("hi", bright_s), ("lo", faint_s)):
            res = [cat[i] - values[i] - zp_hi for i in idx
                   if values[i] is not None]
            out[key]["bias_" + name] = float(np.median(res)) if res else None
        out[key]["snr_lo_med"] = float(np.median(
            [rows[i]["snr_ap"] if key == "ap" else rows[i]["snr"]
             for i in faint_s]))
    return out


def _loo(values, cat):
    # @args: values - instrumental magnitudes, cat - catalogue magnitudes
    # @return: the scaled MAD of (predicted - catalogue), each star predicted
    #          from the zero point of the others
    pairs = [(i, c) for i, c in zip(values, cat)
             if i is not None and c is not None]
    if len(pairs) < 4:
        return None
    inst = np.array([p[0] for p in pairs])
    cats = np.array([p[1] for p in pairs])
    n = len(pairs)
    total = float((cats - inst).sum())
    pred = inst + (total - (cats - inst)) / (n - 1)
    return float(outliers.scaled_mad(pred - cats))


def print_table(results):
    # @args: results - the list of compare() dicts
    # @return: nothing; prints the tables
    print()
    print("%-26s %4s %7s %7s %8s %8s %8s %8s"
          % ("", "n", "SNR", "ratio", "ZP err", "scatter", "LOO", "colour"))
    for res in results:
        ratio = (res["mf"]["snr"] / res["ap"]["snr"] if res["ap"]["snr"]
                 else float("nan"))
        for key, name in (("ap", "aperture"), ("mf", "matched filter")):
            d = res[key]
            print("%-26s %4d %7.1f %7s %8.4f %8.4f %8s %8s"
                  % (f"{res['label']} · {name}", d["n"], d["snr"],
                     "%.2f" % ratio if key == "mf" else "",
                     d["zp_err"] if d["zp_err"] is not None else float("nan"),
                     d["scatter"],
                     "%.4f" % d["loo"] if d["loo"] is not None else "-",
                     "%.4f" % d["scatter_color"]
                     if d["scatter_color"] is not None else "-"))
        print("%-26s %4s %7s %7s %7s %7s %7s %7s"
              % ("  paired mf-ap", "", "", "",
                 "med %+.3f" % res["pair"]["median"],
                 "mad %.3f" % res["pair"]["mad"],
                 "corr x %+.2f" % res["pair"]["corr_x"], ""))
    print()
    print("%-26s %11s %11s %11s" % ("", "LOO bright", "LOO faint",
                                    "faint/bright"))
    for res in results:
        for key, name in (("ap", "aperture"), ("mf", "matched filter")):
            d = res[key]
            b, f = d.get("loo_bright"), d.get("loo_faint")
            print("%-26s %11s %11s %11s"
                  % (f"{res['label']} · {name}",
                     "%.4f" % b if b else "-", "%.4f" % f if f else "-",
                     "%.2f" % (f / b) if (b and f) else "-"))
    # the bias at low signal: the zero point is fitted on the bright half and
    # the faint half is then read against it, so an underestimation shows up
    # as a positive residual that no zero point can absorb
    print()
    print("%-26s %11s %11s %11s" % ("", "bias bright", "bias faint",
                                    "SNR faint"))
    for res in results:
        for key, name in (("ap", "aperture"), ("mf", "matched filter")):
            d = res[key]
            print("%-26s %+11.3f %+11.3f %11.1f"
                  % (f"{res['label']} · {name}",
                     d.get("bias_hi") if d.get("bias_hi") is not None else 0.0,
                     d.get("bias_lo") if d.get("bias_lo") is not None else 0.0,
                     d.get("snr_lo_med") or 0.0))


# --------------------------------- main ---------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carpeta", required=True, help="visit folder")
    parser.add_argument("--objeto", default="", help="designation (ephemeris)")
    parser.add_argument("--mpc", default="", help="MPC code of the site")
    parser.add_argument("--catalogo", default="gaia",
                        choices=["gaia", "apass"])
    parser.add_argument("--caja", type=int, default=600,
                        help="half side of the measured box, px")
    parser.add_argument("--ventana", type=int, default=0,
                        help="keep the comps within this radius of the centre "
                             "(0 = the whole box, which is a worst case for "
                             "the filter: the app picks them near the target)")
    parser.add_argument("--mag-min", type=float, default=13.0)
    parser.add_argument("--mag-max", type=float, default=19.5)
    parser.add_argument("--max-comps", type=int, default=40)
    parser.add_argument("--detalle", action="store_true",
                        help="one line per comparison star")
    parser.add_argument("--grupos", type=int, default=5,
                        help="sub-stacks for the low signal-to-noise part")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    frames, ref, w0, box, shape, motion = load_visit(
        args.carpeta, args.objeto, args.mpc, args.caja)
    wbox = _shift_wcs(w0, box)
    # --- the star stack: the comps are points here and nowhere else
    t0 = time.time()
    stack, _rep = track_stack.stack_group(
        frames, (0, len(frames)), (shape[0] / 2.0, shape[1] / 2.0), "sigma",
        box, shape, cfg=config, track=False)
    if stack is None:
        raise SystemExit("the star stack could not be built")
    print("star stack: %.1fs, noise %.1f ADU" % (time.time() - t0,
                                                 _noise(stack)))

    field = load_field(w0, shape, args.catalogo, args.caja)
    sat = photometry.saturation_ceiling(ref.header, config)
    print("saturation ceiling: %s ADU, linearity %s ADU"
          % (sat, config.get("cam_linearity_adu")))
    # the seeing is measured on the field's own stars, the app's rule
    spots = []
    for star in field["stars"][:200]:
        try:
            spots.append(wbox.sky_to_pixel(star["ra"], star["dec"]))
        except Exception:
            continue
    fwhm = photometry.estimate_fwhm(stack, spots) or 5.0
    radii = photometry.aperture_for_fwhm(fwhm)
    print("seeing on the stack: %.2f px, apertures %s" % (fwhm, radii))

    comps, rejected = pick_comps(
        field, stack, wbox, radii, args.mag_min, args.mag_max, sat,
        config.get("cam_linearity_adu"), config.get("ccd_gain"),
        config.get("ccd_read_noise"), 30, args.max_comps,
        ventana_px=(args.ventana or None))
    counts = collections.Counter(key for _s, key in rejected)
    print("comps: %d kept, %d rejected %s"
          % (len(comps), len(rejected), dict(counts) if rejected else ""))
    if len(comps) < 4:
        raise SystemExit("not enough comps to calibrate")

    # --- the full sequence: the zero point at the best signal-to-noise
    rows = measure_comps(comps, stack, wbox, fwhm, radii)
    results = [compare(rows, "whole visit", field["band"])]
    print("measured %d of %d comps on the whole visit" % (len(rows),
                                                          len(comps)))

    # --- and the same on sub-stacks: the filter has to be worth MORE as the
    #     signal-to-noise falls, and that is half the argument for it
    if args.grupos and args.grupos > 1:
        groups = track_stack.split_groups(frames, args.grupos)
        for index, group in enumerate(groups):
            g_stack, _r = track_stack.stack_group(
                frames, group, (shape[0] / 2.0, shape[1] / 2.0), "sigma",
                box, shape, cfg=config, track=False)
            if g_stack is None:
                continue
            # the seeing of THIS stack, as the app measures it per group
            g_fwhm = photometry.estimate_fwhm(g_stack, spots) or fwhm
            g_rows = measure_comps(comps, g_stack, wbox, g_fwhm, radii)
            if len(g_rows) < 4:
                continue
            label = "group %d/%d (%d frames)" % (index + 1, len(groups),
                                                 group[1] - group[0])
            results.append(compare(g_rows, label, field["band"]))
    print_table(results)
    if args.detalle:
        _detail(rows, field["band"])

    # --- the object itself, on its own stack, with both methods
    _object_magnitude(frames, box, shape, w0, args, fwhm, radii, results,
                      motion)


def _detail(rows, band):
    # @args: rows - the measured comps, band - the catalogue band
    # @return: nothing; prints one line per comp
    # The table the summary hides: what each star measured, how bright the
    # catalogue says it is, and what the two methods disagree by. It is what
    # turns "the filter is 0.07 mag brighter here" into a fact somebody can
    # check against the catalogue.
    print()
    print("%8s %6s %8s %8s %8s %9s %8s %8s"
          % ("mag " + band, "B-V", "SNR ap", "SNR mf", "ratio", "d(mf-ap)",
             "peak", "x"))
    for r in sorted(rows, key=lambda r: float(r["star"]["mag"])):
        bv = r["star"].get("bv")
        d = _inst(r["flux"]) - _inst(r["flux_ap"])
        print("%8.3f %6s %8.1f %8.1f %8.2f %+9.3f %8.0f %8.1f"
              % (float(r["star"]["mag"]),
                 "%.2f" % bv if bv is not None else "-", r["snr_ap"], r["snr"],
                 r["snr"] / r["snr_ap"] if r["snr_ap"] else float("nan"), d,
                 r["peak"], r["x"]))


def _object_magnitude(frames, box, shape, w0, args, fwhm, radii, results,
                      motion=None):
    # @args: frames, box, shape, w0, args, fwhm, radii - the visit, results -
    #        the table built so far (the zero points come from it), motion -
    #        the ephemeris' callable (or None)
    # @return: nothing; prints the object's magnitude with both methods
    # It is the number a report publishes, and the two methods disagree on it
    # by the ratio of their fluxes: the zero point is the SAME one (measured
    # with the same method as the target, by construction), so this is the
    # difference the observer would see in the curve.
    #
    # The position comes from `group_q` and NOT from the middle frame's
    # object_xy: that one is in ITS OWN frame's pixels, and the stack is on
    # the reference frame's grid. Measuring at the wrong frame's coordinates
    # reads sky (measured: flux 203 ADU where the object is, SNR 0.7, which
    # is how this line was found).
    if not frames or motion is None:
        return
    _t_mid, q = track_stack.group_q(frames, (0, len(frames)), w0, motion)
    if q is None:
        return
    stack, _r = track_stack.stack_group(
        frames, (0, len(frames)), q, "sigma", box, shape, cfg=config,
        track=True)
    if stack is None:
        return
    centre = (q[0] - box[0], q[1] - box[1])
    if not (0 <= centre[0] < stack.shape[1]
            and 0 <= centre[1] < stack.shape[0]):
        print("the object is outside the measured box")
        return
    psf = photometry.gaussian_psf(fwhm)
    res = photometry.measure_matched(stack, centre[0], centre[1], psf,
                                     r_ap=radii[0], r_ann_in=radii[1],
                                     r_ann_out=radii[2], fwhm=fwhm)
    if not res.get("ok"):
        print("the object could not be measured on its own stack")
        return
    first = results[0]
    print()
    print("the object on its own stack (ephemeris position, not a detection):")
    for key, name, flux, snr in (("ap", "aperture", res["flux_ap"],
                                  res.get("snr_ap")),
                                 ("mf", "matched filter", res["flux"],
                                  res.get("snr"))):
        zp = first[key]["zp"]
        mag = _inst(flux)
        print("  %-15s flux %10.0f ADU  SNR %6.1f  mag %s"
              % (name, flux, snr or 0.0,
                 "%.3f" % (mag + zp) if mag is not None and zp is not None
                 else "-"))


def _noise(image):
    # @args: image - the stack
    # @return: its robust noise in ADU (the same estimator the engine uses)
    return float(outliers.scaled_mad(np.diff(image[::4, ::4], axis=1).ravel())
                 / math.sqrt(2.0))


def _shift_wcs(w0, box):
    # @args: w0 - the reference astropy WCS, box - the cutout
    # @return: a wcs.Wcs for the cutout's own pixel grid (the same shift the
    #          engine's stacks are measured with)
    w = wcs_mod.Wcs.from_astropy(w0)
    return wcs_mod.Wcs(w.crval1, w.crval2, w.crpix1 - box[0],
                       w.crpix2 - box[1], w.cd, w.naxis1, w.naxis2)


if __name__ == "__main__":
    main()
