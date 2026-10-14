############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: start-and-follow run (ADR-084)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The driven run: plan_run turns "N observations" into numbers (frames per
observation from the field crossing, the wall clock, the re-point cost), and
FollowRun is the loop with every effect injected. No mount, no network, no
real clock.
"""

from nightscribe.core import capture_recipe, follow


def _cfg(**kw):
    base = {"pixel_um": 3.76, "focal_mm": 2000.0, "pixel_binning": "1x1",
            "ccd_gain": 1.0, "ccd_read_noise": 2.0,
            "cam_full_well_e": 50000.0, "cam_max_exposure_s": 3600.0,
            "sky_brightness_mag": 21.0, "cam_readout_s": 15.0,
            "cam_preset": "imx571", "follow_s": 60.0}
    base.update(kw)
    return base


_LONG_NIGHT = {"window_start": "2026-10-13T20:00:00+00:00",
               "window_end": "2026-10-14T02:00:00+00:00"}


# ---------------------------------------------------------------- plan_run

def test_plan_uses_the_field_crossing_for_each_observation():
    ctx = {"rate_arcsec_min": 60.0, **_LONG_NIGHT}
    plan = follow.plan_run("neo", ctx, _cfg(), 3)
    rec = capture_recipe.recommend("neo", ctx, _cfg())
    assert plan["n_obs"] == 3
    assert plan["frames"] == rec["n_frames"]      # the crossing bound
    assert plan["fits"] is True
    assert plan["total_s"] == 3 * plan["obs_span_s"] + 2 * plan["follow_s"]


def test_plan_says_when_the_run_does_not_fit_the_window():
    # a 30-minute window cannot hold ten long observations
    ctx = {"rate_arcsec_min": 60.0,
           "window_start": "2026-10-13T20:00:00+00:00",
           "window_end": "2026-10-13T20:30:00+00:00"}
    plan = follow.plan_run("neo", ctx, _cfg(), 10)
    assert plan["fits"] is False
    assert "does_not_fit" in plan["warnings"]


def test_plan_without_a_window_says_it_cannot_check_the_night():
    plan = follow.plan_run("neo", {"rate_arcsec_min": 60.0}, _cfg(), 3)
    assert "no_window" in plan["warnings"]


def test_plan_flags_a_fixed_object():
    # a fixed target does not cross the field: the loop makes no sense
    plan = follow.plan_run("sn", {"mag": 15.0, **_LONG_NIGHT}, _cfg(), 3)
    assert "not_moving" in plan["warnings"]


def test_plan_clamps_the_number_of_observations():
    assert follow.plan_run("neo", {"rate_arcsec_min": 60.0},
                             _cfg(), 0)["n_obs"] == 1
    assert follow.plan_run("neo", {"rate_arcsec_min": 60.0},
                             _cfg(), 99999)["n_obs"] == \
        follow.MAX_OBSERVATIONS


def test_plan_honours_the_observers_frames_and_exposure():
    # ADR-084: the run must do what the observer set in the Plan step, not the
    # recipe's suggestion
    ctx = {"rate_arcsec_min": 60.0, **_LONG_NIGHT}
    plan = follow.plan_run("neo", ctx, _cfg(), 2,
                             frames=10, exposure_s=8.0)
    assert plan["frames"] == 10
    assert plan["exposure_s"] == 8.0
    assert plan["obs_span_s"] == 10 * (8.0 + 15.0)
    # no overrides: the recipe's values
    rec = capture_recipe.recommend("neo", ctx, _cfg())
    assert follow.plan_run("neo", ctx, _cfg(), 2)["frames"] == rec["n_frames"]


def test_plan_warns_when_the_observers_frames_pass_the_crossing():
    # the observer's number is HONOURED (they may want a longer observation),
    # but if it goes past the field crossing the run says the object may leave
    ctx = {"rate_arcsec_min": 60.0, **_LONG_NIGHT}
    plan = follow.plan_run("neo", ctx, _cfg(), 2, frames=999)
    assert plan["frames"] == 999                      # not clipped
    assert "exceeds_crossing" in plan["warnings"]
    assert 0 < plan["crossing_frames"] < 999
    # a count that fits does not warn
    fits = follow.plan_run("neo", ctx, _cfg(), 2,
                             frames=plan["crossing_frames"])
    assert "exceeds_crossing" not in fits["warnings"]


# --------------------------------------------------------------- FollowRun

class _Clock:
    # A monotonic clock whose sleep ADVANCES it, so the run's wait loops
    # terminate instantly in a test.
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += float(s)


def _plan(n=3, frames=4, exp=5.0, span=40.0):
    return {"n_obs": n, "frames": frames, "exposure_s": exp, "obs_span_s": span}


def test_run_centers_and_captures_once_per_observation():
    clock = _Clock()
    centers, starts, events = [], [], []

    def capturing():
        # True then False: one capture that starts and ends per observation
        return len(starts) % 2 == 1

    run = follow.FollowRun(
        _plan(),
        resolve_position=lambda: {"ra_deg": 10.0, "dec_deg": 20.0},
        center=lambda ra, dec: centers.append((ra, dec)),
        push_plan=lambda n, e: starts.append(("push", n, e)),
        start_capture=lambda: starts.append(("start",)),
        capturing=capturing,
        progress=lambda ev, **k: events.append(ev),
        sleep=clock.sleep, clock=clock, poll_s=1.0)
    assert run.run() == "done"
    assert len(centers) == 3
    assert starts.count(("start",)) == 3
    assert starts[0] == ("push", 4, 5.0)
    assert "centering" in events and "capturing" in events


def test_run_stops_when_the_observer_cancels():
    clock = _Clock()
    state = {"cancel": False, "stops": 0, "starts": 0}

    def capturing():
        state["cancel"] = True       # ask to stop during the first wait
        return True

    run = follow.FollowRun(
        _plan(n=5),
        resolve_position=lambda: {"ra_deg": 1.0, "dec_deg": 2.0},
        center=lambda ra, dec: None,
        push_plan=lambda n, e: None,
        start_capture=lambda: state.__setitem__("starts", state["starts"] + 1),
        capturing=capturing,
        stop_capture=lambda: state.__setitem__("stops", state["stops"] + 1),
        cancel=lambda: state["cancel"],
        sleep=clock.sleep, clock=clock, poll_s=1.0)
    assert run.run() == "cancelled"
    assert state["starts"] == 1          # it never started the second one
    assert state["stops"] == 1           # and it stopped the camera


def test_run_fails_honestly_when_the_position_cannot_be_resolved():
    clock = _Clock()
    run = follow.FollowRun(
        _plan(),
        resolve_position=lambda: None,
        center=lambda ra, dec: None,
        push_plan=lambda n, e: None,
        start_capture=lambda: None,
        capturing=lambda: False,
        sleep=clock.sleep, clock=clock, poll_s=1.0)
    assert run.run() == "failed"


def test_run_says_a_capture_timeout_and_goes_on():
    # a software that never reports the capture must not hang the run: the
    # planned duration is the fallback, and the timeout is said
    clock = _Clock()
    events = []
    run = follow.FollowRun(
        _plan(n=2),
        resolve_position=lambda: {"ra_deg": 1.0, "dec_deg": 2.0},
        center=lambda ra, dec: None,
        push_plan=lambda n, e: None,
        start_capture=lambda: None,
        capturing=lambda: False,          # never reports capturing
        progress=lambda ev, **k: events.append(ev),
        sleep=clock.sleep, clock=clock, poll_s=1.0)
    assert run.run() == "done"
    assert events.count("capture_timeout") == 2


# ------------------------------------------- guiado, progreso y manifiesto

def test_run_records_a_manifest_per_observation():
    # ADR-084 rev: the run writes down how many frames each observation took
    # (what the reduction groups by), with the wall-clock window of each one.
    clock = _Clock()
    wall = [1000.0]
    filed = []

    def group(i, t0, t1):
        filed.append((i, t0, t1))
        wall[0] += 10.0
        return 3                       # the run filed 3 frames

    run = follow.FollowRun(
        _plan(n=2, frames=4),
        resolve_position=lambda: {"ra_deg": 1.0, "dec_deg": 2.0},
        center=lambda ra, dec: None,
        push_plan=lambda n, e: None,
        start_capture=lambda: None,
        capturing=lambda: False,
        group_observation=group,
        progress=lambda ev, **k: None,
        sleep=clock.sleep, clock=clock, wall=lambda: wall[0], poll_s=1.0)
    assert run.run() == "done"
    obs = run.manifest["observations"]
    assert [o["i"] for o in obs] == [1, 2]
    assert [o["frames"] for o in obs] == [3, 3]     # the filed count wins
    assert len(filed) == 2
    assert run.manifest["t0"] is not None and run.manifest["t1"] is not None


def test_run_guides_before_each_capture():
    clock = _Clock()
    order = []
    run = follow.FollowRun(
        _plan(n=2),
        resolve_position=lambda: {"ra_deg": 1.0, "dec_deg": 2.0},
        center=lambda ra, dec: order.append("center"),
        push_plan=lambda n, e: order.append("push"),
        start_capture=lambda: order.append("start"),
        capturing=lambda: False,
        guide=lambda: order.append("guide") or True,
        progress=lambda ev, **k: None,
        sleep=clock.sleep, clock=clock, poll_s=1.0)
    assert run.run() == "done"
    assert order[:4] == ["center", "guide", "push", "start"]


def test_a_guide_failure_is_said_and_the_run_goes_on():
    clock = _Clock()
    events = []
    run = follow.FollowRun(
        _plan(n=1),
        resolve_position=lambda: {"ra_deg": 1.0, "dec_deg": 2.0},
        center=lambda ra, dec: None,
        push_plan=lambda n, e: None,
        start_capture=lambda: None,
        capturing=lambda: False,
        guide=lambda: False,
        progress=lambda ev, **k: events.append(ev),
        sleep=clock.sleep, clock=clock, poll_s=1.0)
    assert run.run() == "done"
    assert "guide_failed" in events


def test_the_capture_numbers_ride_the_progress_events():
    clock = _Clock()
    seen = []
    run = follow.FollowRun(
        _plan(n=1),
        resolve_position=lambda: {"ra_deg": 1.0, "dec_deg": 2.0},
        center=lambda ra, dec: None,
        push_plan=lambda n, e: None,
        start_capture=lambda: None,
        capturing=lambda: True,          # stays capturing, so progress fires
        capture_progress=lambda: {"current": 2, "total": 5,
                                  "exposure_remaining": 3.0},
        progress=lambda ev, **k: seen.append((ev, k)),
        sleep=clock.sleep, clock=clock, poll_s=1.0)
    run.run()
    prog = [k for ev, k in seen if ev == "progress"]
    assert prog and prog[0]["current"] == 2 and prog[0]["total"] == 5


# ------------------------------------------------- agrupación de las tomas

class _Frame:
    def __init__(self, path, t):
        self.path = path
        self.t_mid_jd = t


def test_group_by_folder_separates_the_observations():
    frames = [_Frame("/cap/obj_20261014/obs01/a.fits", 1.0),
              _Frame("/cap/obj_20261014/obs01/b.fits", 1.001),
              _Frame("/cap/obj_20261014/obs02/c.fits", 2.0),
              _Frame("/cap/obj_20261014/obs02/d.fits", 2.001)]
    assert follow.group_by_folder(frames) == [(0, 2), (2, 4)]


def test_group_by_folder_needs_more_than_one_folder():
    frames = [_Frame("/cap/a.fits", 1.0), _Frame("/cap/b.fits", 1.001)]
    assert follow.group_by_folder(frames) == []


def test_group_by_manifest_places_the_frames_by_count():
    frames = [_Frame(f"/cap/{i}.fits", float(i)) for i in range(5)]
    manifest = {"observations": [{"frames": 2}, {"frames": 3}]}
    assert follow.group_by_manifest(frames, manifest) == [(0, 2), (2, 5)]
    # a total that does not match is refused (the observer added a frame)
    assert follow.group_by_manifest(frames + [_Frame("/cap/x.fits", 9.0)],
                                    manifest) == []


def test_group_by_gaps_splits_at_the_repoint():
    # intra-observation gap ~2 s, re-point ~60 s: one clean split
    times = [1.0, 1.0 + 2 / 86400, 1.0 + 4 / 86400,
             1.0 + 64 / 86400, 1.0 + 66 / 86400]
    frames = [_Frame(f"/c/{i}.fits", t) for i, t in enumerate(times)]
    assert follow.group_by_gaps(frames) == [(0, 3), (3, 5)]


def test_resolve_groups_prefers_the_folders_then_the_manifest():
    frames = [_Frame("/cap/obs01/a.fits", 1.0),
              _Frame("/cap/obs02/b.fits", 1.1)]
    groups, source = follow.resolve_groups(frames)
    assert source == "folders" and groups == [(0, 1), (1, 2)]
    # one folder, 0.86 s apart: no subfolders and no gap, so the manifest
    flat = [_Frame(f"/cap/{i}.fits", 1.0 + i * 1e-5) for i in range(4)]
    groups, source = follow.resolve_groups(
        flat, manifest={"observations": [{"frames": 2}, {"frames": 2}]})
    assert source == "manifest" and groups == [(0, 2), (2, 4)]
    # nothing to go on: the manual count decides
    groups, source = follow.resolve_groups(flat, n_obs=2)
    assert source == "manual" and len(groups) == 2
