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
import os
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

# The grouping fallback (ADR-084 rev): when neither the subfolders nor the
# manifest can place the frames, a gap this many times the typical one (and at
# least this many seconds) is taken for the re-point between observations.
GAP_FACTOR = 2.5
GAP_MIN_S = 30.0



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
    # center on it, ensure the guider is running, push the plan for that many
    # frames and capture, wait for the capture to end (reporting the frames as
    # they come), then do it again (the object is near the edge by then).
    # Every effect is a callable so the loop can be tested without a mount, a
    # network or a clock.
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
    #        guide - callable() -> bool or None: blocks until the guider is
    #           guiding (True) or gives up (False); called before each capture
    #           so a slew does not leave the observation unguided,
    #        capture_progress - callable() -> dict or None: the live capture
    #           numbers (frames done, remaining exposure...) the loop forwards
    #           in the "progress" events,
    #        group_observation - callable(i, t0, t1) -> int|None or None: files
    #           the observation's frames (the subfolder copy) and answers how
    #           many it filed; None keeps the manifest on the planned count,
    #        calibrate - True asks the guider to calibrate before guiding,
    #        sleep - injectable sleep, clock - injectable monotonic clock,
    #        wall - injectable wall clock (for the manifest's timestamps),
    #        poll_s - seconds between capture polls

    def __init__(self, plan, *, resolve_position, center, push_plan,
                 start_capture, capturing, stop_capture=None, cancel=None,
                 progress=None, sleep=time.sleep, clock=time.monotonic,
                 wall=time.time, poll_s=DEFAULT_POLL_S, guide=None,
                 capture_progress=None, group_observation=None,
                 calibrate=False):
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
        self._wall = wall
        self._poll_s = max(0.01, float(poll_s))
        self._guide = guide
        self._capture_progress = capture_progress
        self._group = group_observation
        self._calibrate = bool(calibrate)
        self.status = "idle"
        # What the reduction needs to group the frames: one entry per
        # observation, with the frame count and its wall-clock window. It is
        # the backbone of the grouping (ADR-084 rev): the subfolders may not
        # be reachable in remote operation, but the manifest is always written.
        self.manifest = {"observations": [], "t0": None, "t1": None}

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
        self.manifest["t0"] = self._wall()
        self._say("start", n=n, frames=frames)
        for i in range(1, n + 1):
            if self._cancelled():
                return self._end("cancelled")
            t0 = self._wall()
            self._say("centering", i=i, n=n)
            pos = self._resolve()
            if not pos:
                return self._end("failed", reason="no_position")
            self._center(pos["ra_deg"], pos["dec_deg"])
            if self._cancelled():
                return self._end("cancelled")
            # the slew stopped the guider: put it back before capturing
            if self._guide is not None:
                self._say("guiding", i=i, n=n)
                if not self._guide():
                    # a guide failure does NOT kill the run: the frames are
                    # still taken, and the observer decides (short NEO
                    # exposures are often usable unguided)
                    self._say("guide_failed", i=i, n=n)
                if self._cancelled():
                    return self._end("cancelled")
            self._say("capturing", i=i, n=n, frames=frames)
            self._push(frames, exp_s)
            self._start()
            outcome = self._wait_capture(expected_s, i=i, n=n)
            if outcome == "cancelled":
                return self._end("cancelled")
            if outcome == "timeout":
                # the software never said it was capturing: it may simply not
                # report it, so we say it and go on rather than hang
                self._say("capture_timeout", i=i, n=n)
            t1 = self._wall()
            filed = None
            if self._group is not None:
                try:
                    filed = self._group(i, t0, t1)
                except Exception as err:      # a copy that fails is not a stop
                    logger.warning("filing the observation failed: %s", err)
            self.manifest["observations"].append({
                "i": i, "frames": int(filed) if filed else frames,
                "t0": t0, "t1": t1})
            # the object has been drifting for the whole observation: the next
            # iteration re-points at its fresh position
        return self._end("done")

    def _wait_capture(self, expected_s, i=None, n=None):
        # Wait until the software stops reporting a capture, with the planned
        # duration as the honest fallback when it never reports one. Every poll
        # also forwards the live capture numbers (frames done, remaining
        # exposure) so the window shows real progress, not a spinner.
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
            if self._capture_progress is not None:
                try:
                    prog = self._capture_progress() or {}
                except Exception as err:
                    logger.warning("capture progress failed: %s", err)
                    prog = {}
                self._say("progress", i=i, n=n, **prog)
            self._sleep(self._poll_s)
        return "done" if started else "timeout"

    def _end(self, status, reason=None):
        self.status = status
        self.manifest["t1"] = self._wall()
        self._say("finished", status=status, reason=reason)
        return status


# ---------------- grouping the frames per observation (ADR-084 rev) -----------

def _frame_path(frame):
    # @return: the frame's path ("" when the object has none)
    return getattr(frame, "path", None) or ""


def _frame_time(frame):
    # @return: the frame's mid-exposure instant (t_mid_jd preferred, mjd as a
    #          fallback), or None
    t = getattr(frame, "t_mid_jd", None)
    if t is None:
        t = getattr(frame, "mjd", None)
    return t


def group_by_folder(frames):
    # The follow run copies each observation into its own subfolder, so the
    # folder IS the observation. Only groups when EVERY frame has a folder and
    # there is more than one distinct folder; a single folder (or none) means
    # "no subfolders", and the caller falls back to the manifest or the gaps.
    # @args: frames - time-ordered frames (each with a .path)
    # @return: list of (start, end) index pairs, or [] when there is nothing
    #          to group by
    folders = [os.path.dirname(_frame_path(f)) for f in frames]
    if not folders or any(not d for d in folders):
        return []
    if len(set(folders)) < 2:
        return []
    groups, start = [], 0
    for i in range(1, len(folders)):
        if folders[i] != folders[i - 1]:
            groups.append((start, i))
            start = i
    groups.append((start, len(folders)))
    return groups


def group_by_manifest(frames, manifest):
    # The run wrote down how many frames each observation took. When the
    # attached frames are exactly those (the total matches), the counts place
    # them by ORDER, with no clock to reconcile between two machines.
    # @args: frames - time-ordered frames, manifest - the run's manifest dict
    # @return: list of (start, end) index pairs, or [] when it does not fit
    counts = [int(o.get("frames") or 0)
              for o in (manifest or {}).get("observations") or []]
    counts = [c for c in counts if c > 0]
    if not counts or sum(counts) != len(frames):
        return []
    groups, start = [], 0
    for c in counts:
        groups.append((start, start + c))
        start += c
    return groups


def group_by_gaps(frames, factor=GAP_FACTOR, min_s=GAP_MIN_S):
    # Last automatic resort: the re-point leaves a gap much larger than the
    # frames' own cadence, so a gap over `factor` times the typical one (and at
    # least `min_s`) starts a new observation. It is honest about its limit: an
    # exposure longer than the re-point itself can fool it, which is why the
    # manifest and the subfolders come first.
    # @args: frames - time-ordered frames, factor/min_s - the split rule
    # @return: list of (start, end) index pairs (always at least one)
    n = len(frames)
    if n == 0:
        return []
    stamps = [_frame_time(f) for f in frames]
    if any(s is None for s in stamps):
        return [(0, n)]
    deltas = [(float(stamps[i]) - float(stamps[i - 1])) * 86400.0
              for i in range(1, n)]
    positive = sorted(d for d in deltas if d > 0)
    median = positive[len(positive) // 2] if positive else 0.0
    threshold = max(min_s, factor * median)
    groups, start = [], 0
    for i, gap in enumerate(deltas, start=1):
        if gap > threshold:
            groups.append((start, i))
            start = i
    groups.append((start, n))
    return groups


def resolve_groups(frames, manifest=None, n_obs=None, follow_s=None):
    # The priority the editor uses: the subfolders the run created, then the
    # run's manifest, then the re-point gaps, and the manual count last. It
    # returns WHICH rule won, so the tab can say it instead of pretending.
    # @args: frames - time-ordered frames, manifest - the run's manifest or
    #        None, n_obs - the observer's manual count (or None),
    #        follow_s - the re-point cost, to scale the gap rule
    # @return: (groups, source): groups is a list of (start, end), source is
    #          "folders" | "manifest" | "gaps" | "manual" | "single"
    n = len(frames)
    if n == 0:
        return [], "single"
    groups = group_by_folder(frames)
    if len(groups) > 1:
        return groups, "folders"
    groups = group_by_manifest(frames, manifest)
    if len(groups) > 1:
        return groups, "manifest"
    if n > 1:
        groups = group_by_gaps(frames)
        if len(groups) > 1:
            return groups, "gaps"
    if n_obs is not None and n_obs >= 1:
        from .track_stack import split_groups
        return split_groups(frames, int(n_obs)), "manual"
    return [(0, n)], "single"

