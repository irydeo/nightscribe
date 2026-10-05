############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Injection and recovery module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Injection and recovery: the only honest way to say how faint we reach.

Everything else in the SNR campaign is a claim ("the matched filter gains
1.6x", "the second run is worth stacking"). This module is the instrument
that measures the claim END TO END: it puts a source of a KNOWN flux, at a
KNOWN place, moving at a KNOWN rate, into copies of the real frames, runs
the real chain on them, and asks whether it came back and how far off it
landed.

Two things make it honest:

* the truth travels IN THE FILE. Every injected copy carries `NS_INJ`,
  `NS_INJX` and `NS_INJY` in its header, so a run can be verified from the
  copies alone, months later, without trusting a variable that lived in
  somebody's session.
* the USER'S DATA IS NEVER TOUCHED. The injection writes new files into a
  folder of its own; the originals are only ever read.

What it measures, and what it does not:

* it measures the DETECTION (does the gate see it), the POSITION (how far
  from the truth) and the SIGNAL-TO-NOISE of the stacked source;
* it does NOT measure the magnitude, because that needs the comparison
  stars' catalogue, and it does NOT measure the plate solve, because the
  reference WCS is handed to the chain (the solve is a separate, already
  validated step: ADR-051).

So a completeness curve from here answers "how faint can this pipeline go
on these frames, at this motion", which is the question the observer
actually has.
"""

import logging
import math
import shutil
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# The header cards the truth travels in. Named NS_* like the rest of the
# astrometry products, and long enough to be unambiguous.
INJ_FLUX = "NS_INJ"       # ADU above the sky of the injected source
INJ_X = "NS_INJX"         # its position in THIS frame, in pixels
INJ_Y = "NS_INJY"


def inject_sequence(paths, flux_adu, rate_px=1.5, pa_deg=90.0, psf_fwhm=4.0,
                    out_dir=None, start=None, seed=0, ref_wcs=None,
                    progress=None, cancel=None):
    # @args: paths - the real frames (read only), flux_adu - the source's
    #        total flux above the sky, in ADU, rate_px - how far it moves
    #        between consecutive frames, pa_deg - the direction of that
    #        motion (0 = +x, 90 = +y), psf_fwhm - the injected point spread,
    #        out_dir - where the copies go (a folder of its own is created
    #        when None), start - where the source starts, in pixels (the
    #        frame's centre by default), seed - for a reproducible sub-pixel
    #        phase, ref_wcs - the reference frame's astropy WCS, when the
    #        caller has one: with it the injection also returns the motion
    #        in the sky (see _motion_from_truth), progress - callable(done,
    #        total), cancel - callable()
    # @return: {"paths": [the copies], "truth": [(path, x, y)], "motion":
    #          callable(jd) -> (ra, dec), "out_dir": Path}
    #
    # The source is a Gaussian of the given FWHM, which is what a star is,
    # and it moves in a straight line: exactly the shape a real NEO has over
    # a short visit (the curvature shows up over hours, not minutes). The
    # motion is returned as a callable in RA/Dec so the SAME chain the
    # observer runs can be driven with the truth's own motion, which is what
    # makes the comparison a comparison.
    from . import calibration
    from . import track_stack

    paths = [str(p) for p in paths]
    if not paths:
        raise ValueError("no frames to inject into")
    if out_dir is None:
        base = Path(paths[0]).parent
        out_dir = base / "inyectadas"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    frames = track_stack.load_sequence(paths)
    if ref_wcs is not None and frames:
        # the caller's reference WCS: with it the injection can also hand
        # back the motion in the sky, which is what the chain needs
        frames[0].wcs = ref_wcs
    shape = None
    try:
        header = calibration.read_header(paths[0])
        shape = (int(header.get("NAXIS2", 0)), int(header.get("NAXIS1", 0)))
    except Exception:
        shape = None
    if not shape or min(shape) <= 0:
        raise ValueError("the first frame does not say its size")
    half = int(math.ceil(2.5 * float(psf_fwhm)))
    if start is None:
        # off the exact centre: a source sitting on a pixel centre is a
        # special case of the centroid, and the interesting one is between
        # pixels
        start = (shape[1] / 2.0 + 0.37, shape[0] / 2.0 + 0.21)
    sigma = float(psf_fwhm) / 2.3548200450309493
    ang = math.radians(float(pa_deg))
    step = (float(rate_px) * math.cos(ang), float(rate_px) * math.sin(ang))
    truth = []
    out_paths = []
    total = len(frames)
    for index, frame in enumerate(frames):
        if cancel is not None and cancel():
            break
        data, header = calibration.read_image(frame.path)
        x = float(start[0]) + step[0] * index
        y = float(start[1]) + step[1] * index
        # the sub-pixel phase: two sources of the same flux must not land on
        # the same fraction of a pixel every time, or the recovery would be
        # measuring that fraction and not the pipeline
        fx = float(rng.uniform(-0.5, 0.5))
        fy = float(rng.uniform(-0.5, 0.5))
        x0 = int(math.floor(x + fx)) - half
        y0 = int(math.floor(y + fy)) - half
        size = 2 * half + 1
        if x0 < 0 or y0 < 0 or x0 + size > shape[1] or y0 + size > shape[0]:
            # the source walked off the frame: the injection stops there and
            # the truth says which frames carry it
            continue
        yy, xx = np.mgrid[0:size, 0:size]
        cx = (x + fx) - x0
        cy = (y + fy) - y0
        spot = np.exp(-0.5 * (((xx - cx) ** 2 + (yy - cy) ** 2) / sigma ** 2))
        spot_sum = float(spot.sum())
        if spot_sum <= 0:
            continue
        # normalised to the requested TOTAL flux: a source of 500 ADU is 500
        # ADU however broad its PSF is, which is what makes the SNR of two
        # injections comparable
        data = data.copy()
        data[y0:y0 + size, x0:x0 + size] += (float(flux_adu) / spot_sum) * spot
        header = dict(header)
        header[INJ_FLUX] = float(flux_adu)
        header[INJ_X] = float(x + fx)
        header[INJ_Y] = float(y + fy)
        dest = out_dir / Path(frame.path).name
        _write(dest, data, header)
        truth.append((str(dest), float(x + fx), float(y + fy)))
        out_paths.append(str(dest))
        if progress is not None:
            progress(index + 1, total)
    motion = _motion_from_truth(truth, frames, shape)
    # The truth AT AN INSTANT, in pixels. A measurement is taken at the
    # group's own T_mid and not at the first frame, so comparing it with
    # truth[0] reads a whole walk of error (measured: 11.3 px on a source
    # moving 1.5 px per frame with the group's middle seven frames away).
    # This closes that gap without the caller having to know how the groups
    # were cut.
    jds = [float(f.t_mid_jd) for f in frames if f.t_mid_jd is not None]
    xs = [t[1] for t in truth]
    ys = [t[2] for t in truth]
    if len(jds) == len(xs) and len(jds) >= 2:
        def truth_at(jd):
            return (float(np.interp(float(jd), jds, xs)),
                    float(np.interp(float(jd), jds, ys)))
    else:
        truth_at = None
    return {"paths": out_paths, "truth": truth, "motion": motion,
            "truth_at": truth_at, "out_dir": out_dir}


def _write(path, data, header):
    # @args: path - where the copy goes, data - the pixels (float32, ADU),
    #        header - the original header plus the truth
    # @return: None
    # The copy is written as float32 and keeps the original cards: the
    # pipeline reads it exactly as it reads a real frame, which is the point
    # of the whole exercise.
    from astropy.io import fits
    hdu = fits.PrimaryHDU(np.asarray(data, dtype=np.float32))
    for key, value in (header or {}).items():
        if key in ("SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2", "EXTEND",
                   "BSCALE", "BZERO"):
            continue
        try:
            hdu.header[key] = value
        except (ValueError, TypeError):
            continue
    hdu.writeto(str(path), overwrite=True)


def _motion_from_truth(truth, frames, shape):
    # @args: truth - [(path, x, y)], frames - the frames the injection
    #        walked, shape - (ny, nx)
    # @return: callable(jd) -> (ra, dec), or None when there is no reference
    #          WCS to speak in
    # The truth's motion, expressed in the sky, so the SAME chain the
    # observer runs can be driven with it. It is built from the frames' own
    # reference WCS when there is one: the first frame's pixels to the sky,
    # plus the motion's direction in pixel space, converted through the
    # plate scale. Without a WCS the caller drives the chain itself.
    if not truth:
        return None
    ref = frames[0] if frames else None
    wcs = getattr(ref, "wcs", None) if ref is not None else None
    if wcs is None:
        return None
    x0, y0 = truth[0][1], truth[0][2]
    x1, y1 = truth[-1][1], truth[-1][2]
    try:
        ra0, dec0 = wcs.all_pix2world([[x0, y0]], 0)[0]
        ra1, dec1 = wcs.all_pix2world([[x1, y1]], 0)[0]
    except Exception:
        return None
    jd0 = getattr(ref, "t_mid_jd", None)
    jd1 = getattr(frames[len(truth) - 1] if frames else ref, "t_mid_jd", None)
    if jd0 is None or jd1 is None or jd1 <= jd0:
        return None
    dra = (float(ra1) - float(ra0)) / (jd1 - jd0)
    ddec = (float(dec1) - float(dec0)) / (jd1 - jd0)

    def motion(jd):
        dt = float(jd) - float(jd0)
        return (float(ra0) + dra * dt, float(dec0) + ddec * dt)
    return motion


def truth_of(paths):
    # @args: paths - the injected copies (or any frames)
    # @return: [(path, x, y)] for the ones that carry the truth, in the
    #          order given. The truth is read FROM THE FILES, so a recovery
    #          can be verified without trusting anything that lived in a
    #          session.
    from . import calibration
    out = []
    for path in paths:
        try:
            header = calibration.read_header(path)
        except Exception:
            continue
        if INJ_X in header and INJ_Y in header:
            out.append((str(path), float(header[INJ_X]),
                        float(header[INJ_Y])))
    return out


def recover(paths, motion, ref_wcs, cfg=None, n_obs=1, method="sigma",
            cancel=None, progress=None):
    # @args: paths - the frames to measure (the injected copies), motion -
    #        callable(jd) -> (ra, dec) (the truth's own motion), ref_wcs -
    #        the reference frame's astropy WCS (the solve is NOT part of what
    #        is being measured, see the module docstring), cfg - Config,
    #        n_obs - how many observations to split into, method - the
    #        combination, cancel/progress - as usual
    # @return: {"detected", "snr", "x", "y", "n_frames", "note"}
    # The real chain, minus the plate solve: register, place the object with
    # the ephemeris, stack along the motion, and ask the detection gate.
    from . import track_stack
    frames = track_stack.load_sequence(paths, cfg)
    frames[0].wcs = ref_wcs
    track_stack.register_sequence(frames, cancel=cancel)
    track_stack.object_positions(frames, motion)
    shape = (int(frames[0].header.get("NAXIS1", 1)),
             int(frames[0].header.get("NAXIS2", 1)))
    t_all, q_all = track_stack.group_q(frames, (0, len(frames)), ref_wcs,
                                       motion)
    if q_all is None:
        return {"detected": False, "snr": None, "x": None, "y": None,
                "n_frames": 0, "note": "the object does not fall on the plate"}
    groups = track_stack.split_groups(frames, max(1, int(n_obs)))
    boxes = [track_stack.box_around(q, 0, shape) for q in
             [track_stack.group_q(frames, g, ref_wcs, motion)[1]
              for g in groups]]
    stacks = track_stack.stack_groups(frames, groups,
                                      [track_stack.group_q(frames, g,
                                                           ref_wcs, motion)[1]
                                       for g in groups],
                                      method, boxes, shape, cfg=cfg,
                                      cancel=cancel)
    det = None
    used_box = None
    used_jd = None
    for index, (stack, _rep) in enumerate(stacks):
        if stack is None:
            continue
        box = boxes[index]
        t_mid, q = track_stack.group_q(frames, groups[index], ref_wcs, motion)
        q_box = (q[0] - box[0], q[1] - box[1])
        det = track_stack.detect(stack, q_box, cfg)
        used_box = box
        used_jd = t_mid
        if det is not None and det.detected:
            break
    if det is None:
        return {"detected": False, "snr": None, "x": None, "y": None,
                "n_frames": sum(1 for f in frames if track_stack.usable(f)),
                "note": "no stack could be built"}
    # the detection speaks in the STACK's own pixels (a box), and the truth
    # lives in the reference frame's: the box's origin is what joins them.
    # Comparing the two without it is comparing two different rulers, which
    # is what the first version of this test did (it read 11 px of error
    # where there was a fraction of a pixel).
    box = used_box or (0, 0, 0, 0)
    return {"detected": bool(det.detected), "snr": float(det.snr or 0.0),
            "x": float(det.x) + float(box[0]),
            "y": float(det.y) + float(box[1]),
            "t_mid_jd": used_jd,
            "n_frames": sum(1 for f in frames if track_stack.usable(f)),
            "note": (det.notes or None) if not det.detected else None}


def completeness(paths, fluxes, ref_wcs, motion=None, trials=3, cfg=None,
                 out_root=None, cancel=None, progress=None):
    # @args: paths - the real frames, fluxes - the ADU above the sky to try,
    #        ref_wcs - the reference WCS (see recover), motion - the motion
    #        to inject with (a straight line when None), trials - how many
    #        independent injections per flux (each with its own sub-pixel
    #        phase), cfg - Config, out_root - where the copies go,
    #        cancel/progress - as usual
    # @return: [{"flux", "detected", "trials", "rate", "snr_median",
    #           "err_px_median", "err_px_max"}]
    # The curve that answers the question. Each row is a flux and how many
    # of its trials came back, with the SNR and the position error of the
    # ones that did. A flux whose rate is 0 and whose neighbours are 1 is
    # where the pipeline's reach is; a rate of 1 at a flux where the
    # position error explodes is a detection you should not report, which is
    # why the error is in the table and not just the count.
    out = []
    root = Path(out_root) if out_root else None
    for flux in fluxes:
        rows = []
        for trial in range(max(1, int(trials))):
            if cancel is not None and cancel():
                return out
            folder = (root / f"flux{int(flux)}_t{trial}") if root else None
            got = inject_sequence(paths, flux, out_dir=folder,
                                  seed=1000 + trial, ref_wcs=ref_wcs,
                                  progress=progress, cancel=cancel)
            if not got["paths"]:
                continue
            res = recover(got["paths"], got["motion"] or motion, ref_wcs,
                          cfg=cfg, cancel=cancel)
            err = None
            if res["detected"] and res["x"] is not None:
                # the truth AT THE INSTANT the measurement was taken (the
                # group's T_mid): comparing with the first frame would read
                # a whole walk of error
                at = got.get("truth_at")
                if at is not None and res.get("t_mid_jd") is not None:
                    tx, ty = at(res["t_mid_jd"])
                    err = math.hypot(res["x"] - tx, res["y"] - ty)
            rows.append({"detected": bool(res["detected"]),
                         "snr": res["snr"], "err_px": err,
                         "note": res.get("note")})
            if folder is not None and folder.exists():
                shutil.rmtree(folder, ignore_errors=True)
        hits = [r for r in rows if r["detected"]]
        errs = [r["err_px"] for r in hits if r["err_px"] is not None]
        out.append({
            "flux": float(flux), "detected": len(hits), "trials": len(rows),
            "rate": (len(hits) / len(rows)) if rows else 0.0,
            "snr_median": (float(np.median([r["snr"] for r in hits]))
                           if hits else None),
            "err_px_median": (float(np.median(errs)) if errs else None),
            "err_px_max": (float(max(errs)) if errs else None)})
    return out
