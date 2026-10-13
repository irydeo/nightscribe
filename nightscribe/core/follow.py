############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Start-and-follow run module (ADR-084)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Start and follow: a driven run of N observations of a MOVING object (ADR-084).

The observer asks for a number of observations and the app gets the most out
of each one: it points the telescope at the object, captures as many frames as
fit before the object reaches the edge of the camera's field, and then points
again at the object's fresh position to start the next observation. The app
"follows" the object across the sky, one observation at a time, instead of
re-pointing by hand. Each step IS a recenter onto the object's UPDATED
ephemeris (not back to a fixed coordinate), which is the commercial "recenter"
of CCDciel and NINA's "Center After Drift" applied to an object that really
moves.

Two pieces, both free of Qt and of the network:

* `plan_run` turns "N observations" into numbers: frames per observation (the
  field-crossing bound from `core/capture_recipe`), the wall clock of each one,
  the cost of the re-points and whether the whole thing fits the visibility
  window.
* `FollowRun` is the loop itself, with every side effect injected (resolve
  the position, center, push the plan, start the capture, read whether it is
  running). Tests drive it with doubles and a fake clock, exactly like
  `core/live.py`.

The detection of the edge is OPEN LOOP: we know the object's apparent rate and
the field it must not leave, so when an observation's frames are done the
object is by construction near the edge and it is time to point again. Solving
every frame to measure the real offset is a heavier, later refinement.
"""

import logging
import time

from . import capture_recipe, exposure

logger = logging.getLogger(__name__)

# The cost of ONE re-point, in seconds: the slew, the frame the solver eats,
# the correction and the settle. It is what turns N observations into
# N + (N-1) pointings, so it belongs in the budget. Measured on a real rig the
# round trip is under a minute; the config key lets the observer tune it.
DEFAULT_FOLLOW_S = 60.0

# A typo must not park the mount for a week: the run never plans more than this.
MAX_OBSERVATIONS = 500

# The capture poll: how often we ask the software whether it is still capturing.
DEFAULT_POLL_S = 1.0

# The wait is the planned duration times this margin: the frames take what they
# take, but a rig that never reports "done" must not hang the run forever.
CAPTURE_MARGIN = 1.4


def plan_run(kind, ctx, cfg, n_obs, frames=None, exposure_s=None):
    # Turns "N observations" into the numbers the observer and the loop need.
    # @args: kind - object kind id, ctx - project context (rate, window),
    #        cfg - the Config, n_obs - observations wanted,
    #        frames/exposure_s - the values the OBSERVER set in the Plan step;
    #        when given they are used as-is (the run must do what was asked,
    #        not the suggestion), else the recipe's values are used
    # @return: dict {n_obs, frames, exposure_s, per_frame_s, obs_span_s,
    #          follow_s, total_s, window_s, fits, warnings,
    #          crossing_frames, rate_arcsec_min}
    try:
        n = int(n_obs)
    except (TypeError, ValueError):
        n = 0
    n = max(1, min(MAX_OBSERVATIONS, n or 1))
    rec = capture_recipe.recommend(kind, ctx, cfg)
    if frames is None:
        frames = int(rec["n_frames"])
    else:
        frames = max(1, int(frames))
    if exposure_s is None:
        exp_s = float(rec["exposure_s"])
    else:
        exp_s = max(0.0, float(exposure_s))
    per_frame = exp_s + exposure.frame_overhead_s(cfg)
    obs_s = frames * per_frame
    follow_s = float(cfg.get("follow_s") or DEFAULT_FOLLOW_S)
    total_s = n * obs_s + max(0, n - 1) * follow_s
    window_s = capture_recipe._window_span_s(ctx) or None
    warnings = []
    fits = True
    if window_s is None:
        warnings.append("no_window")
    elif total_s > window_s:
        fits = False
        warnings.append("does_not_fit")
    if kind not in capture_recipe.MOVING_KINDS:
        # a fixed object does not cross the field: the loop makes no sense
        warnings.append("not_moving")
    if "field_unknown" in (rec.get("warnings") or []):
        # the per-observation size could not be bounded by the field
        warnings.append("no_crossing")
    # how many frames fit before the object reaches the edge: the observer's
    # number is HONOURED (they may want a longer observation), but if it goes
    # past the crossing the run says the object may leave the field (ADR-084)
    crossing_frames = None
    t_cross, _fov = capture_recipe._field_crossing_s(kind, ctx, cfg)
    if t_cross is not None and per_frame > 0:
        crossing_frames = max(1, int(t_cross / per_frame))
        if frames > crossing_frames:
            warnings.append("exceeds_crossing")
    return {
        "n_obs": n,
        "frames": frames,
        "exposure_s": exp_s,
        "per_frame_s": per_frame,
        "obs_span_s": obs_s,
        "follow_s": follow_s,
        "total_s": total_s,
        "window_s": window_s,
        "fits": fits,
        "warnings": warnings,
        "crossing_frames": crossing_frames,
        "rate_arcsec_min": ctx.get("rate_arcsec_min"),
    }


class FollowRun:
    # The loop: for each observation, resolve the object's CURRENT position,
    # center on it, push the plan for that many frames and capture, wait for
    # the capture to end, then do it again (the object is near the edge by
    # then). Every effect is a callable so the loop can be tested without a
    # mount, a network or a clock.
    #
    # @args: plan - the dict from plan_run,
    #        resolve_position - callable() -> {ra_deg, dec_deg} or None,
    #        center - callable(ra_deg, dec_deg) (blocks until pointed),
    #        push_plan - callable(frames, exposure_s),
    #        start_capture - callable(),
    #        capturing - callable() -> bool (is the camera still capturing?),
    #        stop_capture - callable() or None (used on cancel),
    #        cancel - callable() -> bool,
    #        progress - callable(event, **info) (core has no tr(): the GUI owns
    #           the wording),
    #        sleep - injectable sleep, clock - injectable monotonic clock,
    #        poll_s - seconds between capture polls

    def __init__(self, plan, *, resolve_position, center, push_plan,
                 start_capture, capturing, stop_capture=None, cancel=None,
                 progress=None, sleep=time.sleep, clock=time.monotonic,
                 poll_s=DEFAULT_POLL_S):
        self._plan = plan or {}
        self._resolve = resolve_position
        self._center = center
        self._push = push_plan
        self._start = start_capture
        self._capturing = capturing
        self._stop_capture = stop_capture
        self._cancel = cancel
        self._progress = progress
        self._sleep = sleep
        self._clock = clock
        self._poll_s = max(0.01, float(poll_s))
        self.status = "idle"

    def _cancelled(self):
        # @return: True when the observer asked to stop
        return bool(self._cancel and self._cancel())

    def _say(self, event, **info):
        if self._progress:
            self._progress(event, **info)

    def run(self):
        # @return: "done" | "cancelled" | "failed"
        plan = self._plan
        n = int(plan.get("n_obs") or 1)
        frames = int(plan.get("frames") or 1)
        exp_s = float(plan.get("exposure_s") or 0.0)
        # how long one observation should take, with the safety margin
        expected_s = max(1.0, float(plan.get("obs_span_s") or 0.0)
                         * CAPTURE_MARGIN)
        self.status = "running"
        self._say("start", n=n, frames=frames)
        for i in range(1, n + 1):
            if self._cancelled():
                return self._end("cancelled")
            self._say("centering", i=i, n=n)
            pos = self._resolve()
            if not pos:
                return self._end("failed", reason="no_position")
            self._center(pos["ra_deg"], pos["dec_deg"])
            if self._cancelled():
                return self._end("cancelled")
            self._say("capturing", i=i, n=n, frames=frames)
            self._push(frames, exp_s)
            self._start()
            outcome = self._wait_capture(expected_s)
            if outcome == "cancelled":
                return self._end("cancelled")
            if outcome == "timeout":
                # the software never said it was capturing: it may simply not
                # report it, so we say it and go on rather than hang
                self._say("capture_timeout", i=i, n=n)
            # the object has been drifting for the whole observation: the next
            # iteration re-points at its fresh position
        return self._end("done")

    def _wait_capture(self, expected_s):
        # Wait until the software stops reporting a capture, with the planned
        # duration as the honest fallback when it never reports one.
        # @args: expected_s - the planned wall clock (with margin)
        # @return: "done" | "cancelled" | "timeout"
        started = False
        deadline = self._clock() + expected_s
        while self._clock() < deadline:
            if self._cancelled():
                if self._stop_capture is not None:
                    self._stop_capture()
                return "cancelled"
            try:
                capturing = bool(self._capturing())
            except Exception as err:      # a read that fails is not a stop
                logger.warning("capture poll failed: %s", err)
                capturing = False
            if capturing:
                started = True
            elif started:
                return "done"
            self._sleep(self._poll_s)
        return "done" if started else "timeout"

    def _end(self, status, reason=None):
        self.status = status
        self._say("finished", status=status, reason=reason)
        return status
