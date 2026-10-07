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


def inject_sequence(paths, flux_adu, rate_px_min=1.5, pa_deg=90.0,
                    psf_fwhm=None,
                    out_dir=None, start=None, seed=0, ref_wcs=None,
                    progress=None, cancel=None):
    # @args: paths - the real frames (read only), flux_adu - the source's
    #        total flux above the sky, in ADU, rate_px_min - how far it
    #        moves PER MINUTE (see below), pa_deg - the direction of that
    #        motion (0 = +x, 90 = +y), psf_fwhm - the injected point spread
    #        (None measures the SESSION's own seeing from the frames, which
    #        is what makes the injection realistic: a source sharper than the
    #        night's PSF is a source whose wings the aperture cannot lose,
    #        and the measured bias would be the bench's and not the
    #        pipeline's),
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
    if psf_fwhm is None:
        # the session's own seeing, measured from the first frame: a source
        # injected sharper than the night's PSF is a source whose wings no
        # aperture can miss, and the photometric bias measured on it would
        # be the BENCH's bias (measured once: +0.15 mag with a 3.5 px source
        # on 4.6 px frames, which was the mismatch and not the pipeline)
        psf_fwhm = _session_psf(frames)
    psf_fwhm = float(psf_fwhm or 4.0)
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
    step = (float(rate_px_min) * math.cos(ang),
            float(rate_px_min) * math.sin(ang))
    # The position is a function of TIME and not of the frame index, and
    # that is measured, not pedantry: the real cadence is irregular (on the
    # 2025 UR visit it runs from 4 to 6 seconds between frames), so a fixed
    # step per frame is NOT a straight line in the sky, and the velocity
    # sweep, which fits a line, would then be judged against a motion nobody
    # made. Measured before the fix: the sweep found 35.5"/min at PA 5.9 deg
    # where the injected endpoint derivative said 34.0 at 0.2, and the
    # difference was the cadence and nothing else.
    jd0 = None
    for frame in frames:
        if frame.t_mid_jd is not None:
            jd0 = float(frame.t_mid_jd)
            break
    truth = []
    out_paths = []
    total = len(frames)
    for index, frame in enumerate(frames):
        if cancel is not None and cancel():
            break
        data, header = calibration.read_image(frame.path)
        dt_min = 0.0
        if jd0 is not None and frame.t_mid_jd is not None:
            dt_min = (float(frame.t_mid_jd) - jd0) * 1440.0
        x = float(start[0]) + step[0] * dt_min
        y = float(start[1]) + step[1] * dt_min
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
            "truth_at": truth_at, "out_dir": out_dir,
            "flux_adu": float(flux_adu), "psf_fwhm": float(psf_fwhm)}


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


def _session_psf(frames, default=4.0):
    # @args: frames - the frames to measure the seeing from, default - what
    #        to fall back to
    # @return: the session's median FWHM in pixels
    from . import calibration, register, track_stack
    for frame in frames:
        try:
            data = calibration.read_image(frame.path)[0]
            stars = register.detect_stars(register.source_image(data))
            value = track_stack.session_fwhm(data, stars)
            if value:
                return float(value)
        except Exception as err:
            logger.warning("the session's PSF could not be measured: %s", err)
            break
    return float(default)


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


def sky_motion(motion, t_mid_jd):
    # @args: motion - callable(jd) -> (ra_deg, dec_deg), t_mid_jd - the
    #        instant to measure the motion at
    # @return: (rate arcsec/min, PA degrees north through east), or
    #          (None, None) when the motion cannot be sampled
    # The SAME convention the sweep's seed uses (0 deg towards +dec, 90 deg
    # towards +RA), measured over a two-minute baseline so the divisor is
    # the arcsec PER MINUTE. It is written here instead of imported because
    # the sweep's version lives in the GUI's worker and this module is core:
    # the instrument cannot depend on the interface. If the two ever
    # disagree, the injected truth and the found velocity stop being
    # comparable, which is what this function exists to check.
    if motion is None or t_mid_jd is None:
        return None, None
    p0 = motion(float(t_mid_jd) - 1.0 / 1440.0)
    p1 = motion(float(t_mid_jd) + 1.0 / 1440.0)
    if not p0 or not p1:
        return None, None
    cosd = math.cos(math.radians(p0[1]))
    dra = (p1[0] - p0[0]) * cosd * 3600.0
    ddec = (p1[1] - p0[1]) * 3600.0
    rate = math.hypot(dra, ddec) / 2.0
    pa = math.degrees(math.atan2(dra, ddec)) % 360.0
    return float(rate), float(pa)


def pa_difference(a, b):
    # @args: a, b - two position angles in degrees
    # @return: the smallest absolute difference, in degrees (0..180)
    # A position angle is a direction and not a number: 359 and 1 are two
    # degrees apart, and subtracting them would report 358.
    if a is None or b is None:
        return None
    return float(abs((float(a) - float(b) + 180.0) % 360.0 - 180.0))


def _scaled_motion(motion, jd0, jd1, factor):
    # @args: motion - the true motion, jd0/jd1 - the sequence's ends,
    #        factor - how wrong the seed is (1.0 = exact)
    # @return: a linear motion through the first point whose velocity is
    #          `factor` times the true one
    # The ephemeris is never perfect, so the interesting question is not
    # "does the sweep keep the velocity it was given" (that is
    # self-consistency) but "does it find the truth when the seed is off".
    # The grid is +/- pct %, so beyond it the sweep CANNOT find it, and that
    # boundary is worth measuring.
    p0 = motion(jd0) if motion is not None else None
    p1 = motion(jd1) if motion is not None else None
    if not p0 or not p1 or jd1 <= jd0:
        return motion
    span = float(jd1) - float(jd0)

    def out(jd):
        t = (float(jd) - float(jd0)) / span
        return (float(p0[0]) + (float(p1[0]) - float(p0[0])) * factor * t,
                float(p0[1]) + (float(p1[1]) - float(p0[1])) * factor * t)
    return out


def motion_recovery(paths, flux_adu, rate_px_min, pa_deg, ref_wcs, cfg=None,
                    out_dir=None, seed=0, n_obs=1, method="sigma",
                    steps=5, pct=5.0, seed_factor=1.0, cancel=None,
                    progress=None):
    # @args: paths - the real frames, flux_adu - the injected source's flux,
    #        rate_px_min/pa_deg - the injected motion (px per minute),
    #        ref_wcs - the reference
    #        WCS, cfg - Config, out_dir - where the copies go, seed - the
    #        sub-pixel phase, n_obs/method - the chain's knobs, steps/pct -
    #        the sweep's grid, seed_factor - how wrong the ephemeris the
    #        chain is given is (1.0 = exact; 1.1 = ten per cent too fast),
    #        cancel/progress - as usual
    # @return: {"injected": {"rate", "pa"}, "found": {"rate", "pa"},
    #          "err_rate", "err_pa", "detected", "snr", "snr_ap", "note"}
    #
    # THE QUESTION THIS ANSWERS: is the velocity sweep centred where it
    # should be? The pipeline looks for the object on a grid around the
    # ephemeris' own velocity, and the grid is what decides whether a real
    # object is found at all. Injecting a source moving at a KNOWN rate and
    # heading and reading back what the sweep chose turns "the sweep looks
    # fine" into two numbers: the error in rate (arcsec/min) and the error
    # in position angle (degrees).
    from . import track_stack
    got = inject_sequence(paths, flux_adu, rate_px_min=rate_px_min,
                          pa_deg=pa_deg,
                          out_dir=out_dir, seed=seed, ref_wcs=ref_wcs,
                          cancel=cancel, progress=progress)
    if not got["paths"]:
        return {"injected": None, "found": None, "err_rate": None,
                "err_pa": None, "detected": False, "snr": None,
                "snr_ap": None, "note": "the source left the frame"}
    seed_motion = got["motion"]
    if seed_factor != 1.0 and got["motion"] is not None and got["truth"]:
        frames_jd = [f.t_mid_jd for f in track_stack.load_sequence(
            got["paths"]) if f.t_mid_jd is not None]
        if len(frames_jd) >= 2:
            seed_motion = _scaled_motion(got["motion"], frames_jd[0],
                                         frames_jd[-1], float(seed_factor))
    res = recover(got["paths"], seed_motion, ref_wcs, cfg=cfg, n_obs=n_obs,
                  method=method, cancel=cancel, sweep=True, steps=steps,
                  pct=pct, psf_fwhm=got.get("psf_fwhm"))
    injected = None
    if got.get("truth_at") is not None and res.get("t_mid_jd") is not None:
        rate, pa = sky_motion(got["motion"], res["t_mid_jd"])
        if rate is not None:
            injected = {"rate": rate, "pa": pa}
    found = res.get("sweep")
    return {"injected": injected, "found": found,
            "seed_factor": float(seed_factor),
            "err_rate": (None if not injected or not found
                         else float(found["rate"] - injected["rate"])),
            "err_pa": (None if not injected or not found
                       else pa_difference(found["pa"], injected["pa"])),
            "detected": bool(res.get("detected")), "snr": res.get("snr"),
            "err_mag": mag_error(res.get("flux"), got.get("flux_adu")),
            "err_mag_mf": mag_error(res.get("flux_mf"),
                                    got.get("flux_adu")),
            "snr_ap": None, "note": res.get("note"),
            "truth_at": got.get("truth_at")}


def _median_of(rows, key):
    # @args: rows - the trials that came back, key - which number to take
    # @return: its median over the trials that have it, or None
    values = [float(r[key]) for r in rows if r.get(key) is not None]
    return float(np.median(values)) if values else None


def mag_error(measured, injected):
    # @args: measured - the flux the pipeline read, injected - the flux that
    #        was put there, both in ADU above the sky
    # @return: the error in magnitudes, or None
    # -2.5 log10(measured / injected), and NO catalogue is needed: the zero
    # point cancels in the ratio, which is what makes this measurable
    # offline. A positive number means the pipeline read the source FAINTER
    # than it is (an aperture too small loses flux, a sky over-subtracted
    # gains it), and that is a systematic error of the magnitude, not a
    # scatter.
    if not measured or not injected or measured <= 0 or injected <= 0:
        return None
    return float(-2.5 * math.log10(float(measured) / float(injected)))


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
            cancel=None, progress=None, loader=None, sweep=False, steps=5,
            pct=5.0, psf_fwhm=None):
    # @args: paths - the frames to measure (the injected copies), motion -
    #        callable(jd) -> (ra, dec) (the truth's own motion), ref_wcs -
    #        the reference frame's astropy WCS (the solve is NOT part of what
    #        is being measured, see the module docstring), cfg - Config,
    #        n_obs - how many observations to split into, method - the
    #        combination, cancel/progress - as usual, loader - a
    #        calibrating loader (calibration.FrameCalibrator) when the run
    #        being measured is calibrated: the SAME chain then sees the same
    #        pixels the observer's run would, sweep - also run the VELOCITY
    #        SWEEP and return what it chose (see motion_recovery), steps/pct
    #        - the sweep's grid, psf_fwhm - the point spread to measure the
    #        flux with (the injected one, when the caller knows it): the
    #        aperture follows it and the matched filter is built from it
    # @return: {"detected", "snr", "x", "y", "n_frames", "note"}
    # The real chain, minus the plate solve: register, place the object with
    # the ephemeris, stack along the motion, and ask the detection gate.
    from . import track_stack
    frames = track_stack.load_sequence(paths, cfg)
    frames[0].wcs = ref_wcs
    track_stack.register_sequence(frames, cancel=cancel, loader=loader)
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
                                      cancel=cancel, loader=loader)
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
    found = None
    if sweep:
        # The velocity sweep, over the WHOLE sequence and on the cutout that
        # holds the trail, exactly as the observer's run does it: what comes
        # back is the velocity the pipeline chose, which is what the
        # instrument compares with the injected one.
        base_rate, base_pa = sky_motion(motion, t_all)
        if base_rate is not None:
            box_all = track_stack.cutout_box(frames, (0, len(frames)), q_all,
                                             margin_px=64, shape=shape)
            res_sweep = track_stack.sweep(
                frames, q_all, base_rate, base_pa, box_all, shape, pct=pct,
                steps=steps, method="median", cfg=cfg, loader=loader,
                cancel=cancel)
            best = getattr(res_sweep, "best", None)
            if best:
                found = {"rate": float(best.get("rate")),
                         "pa": float(best.get("pa"))}
    # the detection speaks in the STACK's own pixels (a box), and the truth
    # lives in the reference frame's: the box's origin is what joins them.
    # Comparing the two without it is comparing two different rulers, which
    # is what the first version of this test did (it read 11 px of error
    # where there was a fraction of a pixel).
    box = used_box or (0, 0, 0, 0)
    # The FLUX at the detected position, measured on the stack it was found
    # in. It is what a treatment changes: the detection and the position are
    # relative and survive almost anything, while the flux is the number the
    # flat moves. Without it, "calibrating" could not be measured at all.
    # The FLUX at the detected position, measured on the stack it was found
    # in, and measured TWICE: with the aperture rule the app itself uses for
    # that seeing, and with the matched filter. The injection is the only
    # place where the true flux is known, so this is where "does the pipeline
    # bias the brightness, and by how much" stops being an opinion. Without a
    # catalogue and without a zero point: the ratio of the measured flux to
    # the injected one IS the magnitude error, because the zero point cancels.
    flux = flux_mf = fwhm = None
    try:
        from . import photometry
        if stacks:
            st = stacks[-1][0]
            if st is not None:
                if psf_fwhm:
                    # the app's own rule: the aperture follows the seeing
                    radii = photometry.aperture_for_fwhm(float(psf_fwhm))
                else:
                    radii = (6.0, 10.0, 15.0)
                res = photometry.measure_point(
                    st, det.x, det.y, r_ap=radii[0], r_ann_in=radii[1],
                    r_ann_out=radii[2], fwhm=psf_fwhm)
                if res.get("ok"):
                    flux = float(res["flux"])
                if psf_fwhm:
                    mf = photometry.measure_matched(
                        st, det.x, det.y,
                        photometry.gaussian_psf(float(psf_fwhm)),
                        r_ap=radii[0], r_ann_in=radii[1], r_ann_out=radii[2],
                        fwhm=psf_fwhm)
                    if mf.get("ok"):
                        flux_mf = float(mf["flux"])
                fwhm = psf_fwhm
    except Exception as err:
        logger.warning("the injected source's flux could not be measured: %s",
                       err)
    return {"detected": bool(det.detected), "snr": float(det.snr or 0.0),
            "x": float(det.x) + float(box[0]),
            "y": float(det.y) + float(box[1]), "flux": flux,
            "flux_mf": flux_mf, "fwhm": fwhm,
            "t_mid_jd": used_jd, "sweep": found,
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
                          cfg=cfg, cancel=cancel,
                          psf_fwhm=got.get("psf_fwhm"))
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
                         "flux": res.get("flux"),
                         "err_mag": mag_error(res.get("flux"),
                                              got.get("flux_adu")),
                         "err_mag_mf": mag_error(res.get("flux_mf"),
                                                 got.get("flux_adu")),
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
            "flux_median": (float(np.median([r["flux"] for r in hits
                                             if r.get("flux") is not None]))
                            if any(r.get("flux") is not None
                                   for r in hits) else None),
            "err_mag_median": _median_of(hits, "err_mag"),
            "err_mag_mf_median": _median_of(hits, "err_mag_mf"),
            "err_px_median": (float(np.median(errs)) if errs else None),
            "err_px_max": (float(max(errs)) if errs else None)})
    return out
