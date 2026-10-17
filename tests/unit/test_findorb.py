############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: Find_Orb handoff (ADR-062, phase 5.2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase 5.2 acceptance: the interactive binary is refused, the input file
mixes our lines with the others', the residual parser survives an unknown
JSON shape, the robust scatter ignores a single bad observer, and the
verdict compares with the cloud (never with zero) and does not block when
there is nobody to compare with. Offline: no binary, no network."""

import json
import math

import pytest

from nightscribe.core import findorb


def _home_at(tmp):
    # @args: tmp - the folder that stands in for the observer's home
    # @return: a Path subclass whose home() is that folder. The search is
    #          hermetic: a test must not find the `~/findorb` of whoever runs
    #          the suite (this machine has one).
    from pathlib import Path

    class _Home(Path):
        @classmethod
        def home(cls):
            return tmp

    return _Home


@pytest.fixture
def no_auto(monkeypatch, tmp_path):
    # @return: None. Nothing is found on its own: no bundled copy, no
    #          ~/findorb, no environment in the data dir and no `fo` on PATH.
    from nightscribe import paths
    from nightscribe.core import findorb_install
    monkeypatch.setattr(paths, "findorb_bundle_dir", lambda: None)
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(findorb, "Path", _home_at(tmp_path / "home"))
    monkeypatch.setattr(findorb_install.shutil, "which", lambda name: None)


# ------------------------------------------------------------------ probe

def test_probe_refuses_the_interactive_binary(tmp_path):
    fake = tmp_path / "find_orb"
    fake.write_text("#!/bin/sh\n")
    path, message = findorb.probe(str(fake))
    assert path is None and "interactive" in message


def test_probe_reports_a_missing_path(no_auto):
    path, message = findorb.probe("/no/such/fo")
    assert path is None and "not found" in message


def test_probe_finds_fo_on_the_path(no_auto, monkeypatch):
    from nightscribe.core import findorb_install
    monkeypatch.setattr(findorb_install.shutil, "which",
                        lambda name: "/usr/bin/fo" if name == "fo" else None)
    path, _message = findorb.probe()
    assert path == "/usr/bin/fo"


def test_probe_says_when_nothing_is_configured(no_auto):
    path, message = findorb.probe()
    assert path is None and "not configured" in message


def test_the_app_finds_what_its_own_instructions_install(no_auto, tmp_path,
                                                         monkeypatch):
    # The install dialog tells the observer to create ~/findorb; following it
    # has to work. Until 2026-10-17 it did not: the app only looked at the
    # bundled copy and PATH, so it said "not configured" with Find_Orb right
    # there (reported).
    from nightscribe import paths
    from nightscribe.core import findorb_install
    home = tmp_path / "home"
    (home / "findorb" / "bin").mkdir(parents=True)
    (home / "findorb" / "bin" / "fo").write_bytes(b"x")
    monkeypatch.setattr(paths, "findorb_bundle_dir", lambda: None)
    monkeypatch.setattr(findorb, "Path", _home_at(home))
    monkeypatch.setattr(findorb_install.shutil, "which", lambda name: None)
    found, why = findorb.auto_find()
    assert found == str(home / "findorb" / "bin" / "fo")
    assert "home" in why
    path, message = findorb.probe("")
    assert path == found and "home" in message


def test_the_guided_installs_folder_is_searched_too(no_auto, tmp_path,
                                                    monkeypatch):
    # The guided install puts its private environment in <data dir>/findorb
    # by default; clearing the path must not lose it.
    from nightscribe import paths
    from nightscribe.core import findorb_install
    env = tmp_path / "data" / "findorb"
    (env / "bin").mkdir(parents=True)
    (env / "bin" / "fo").write_bytes(b"x")
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(findorb_install.shutil, "which", lambda name: None)
    found, why = findorb.auto_find()
    assert found == str(env / "bin" / "fo")
    assert "NightScribe" in why


def test_the_bundled_copy_wins_over_the_home_folder(no_auto, tmp_path,
                                                    monkeypatch):
    # The copy that travels with the app is the one to use: it is the same
    # version the app was built and tested with.
    from nightscribe import paths
    bundle = tmp_path / "bundle"
    (bundle / "bin").mkdir(parents=True)
    (bundle / "bin" / "fo").write_bytes(b"x")
    home = tmp_path / "home"
    (home / "findorb" / "bin").mkdir(parents=True)
    (home / "findorb" / "bin" / "fo").write_bytes(b"x")
    monkeypatch.setattr(paths, "findorb_bundle_dir", lambda: bundle)
    monkeypatch.setattr(findorb, "Path", _home_at(home))
    found, why = findorb.auto_find()
    assert found == str(bundle / "bin" / "fo")
    assert "bundled" in why


def test_a_configured_path_that_is_gone_falls_back(no_auto, tmp_path,
                                                   monkeypatch):
    # Filling the field (which the app now does) must not leave a stale path
    # behind for ever: a package update can move it, and then the app finds
    # the copy it has and says what happened.
    from nightscribe import paths
    home = tmp_path / "home"
    (home / "findorb" / "bin").mkdir(parents=True)
    (home / "findorb" / "bin" / "fo").write_bytes(b"x")
    monkeypatch.setattr(paths, "findorb_bundle_dir", lambda: None)
    monkeypatch.setattr(findorb, "Path", _home_at(home))
    path, message = findorb.probe("/gone/away/fo")
    assert path == str(home / "findorb" / "bin" / "fo")
    assert "gone" in message and "/gone/away/fo" in message


# ------------------------------------------------------------------ input

def test_write_input_mixes_ours_and_theirs(tmp_path):
    out = tmp_path / "obs.txt"
    findorb.write_input("OUR1\nOUR2\n", "OTHER1\n\nOTHER2", out)
    lines = out.read_text().splitlines()
    assert lines == ["OUR1", "OUR2", "OTHER1", "OTHER2"]


def test_write_input_accepts_a_list_of_lines(tmp_path):
    # the track & stack once handed a LIST to a function that split a string,
    # and the AttributeError took the whole run down. Either shape must work.
    out = tmp_path / "obs.txt"
    findorb.write_input(["OUR1", "OUR2"], ["OTHER1"], out)
    assert out.read_text().splitlines() == ["OUR1", "OUR2", "OTHER1"]


def test_write_environment_is_private(tmp_path):
    env = findorb.write_environment(tmp_path / "environ.dat")
    text = open(env).read()
    assert "PERTURBERS" in text


# ----------------------------------------------------------------- parser

def test_parse_output_reads_a_residual_list(tmp_path):
    data = {"objects": [{"elements": {}, "observations": [
        {"stn": "Z41", "dra": 0.2, "ddec": -0.1},
        {"stn": "I41", "dra": 0.4, "ddec": 0.3}]}]}
    (tmp_path / "total.json").write_text(json.dumps(data))
    parsed = findorb.parse_output(str(tmp_path))
    assert parsed["ok"] and len(parsed["residuals"]) == 2
    assert parsed["residuals"][0]["stn"] == "Z41"


def test_parse_output_without_the_file_is_not_fatal(tmp_path):
    parsed = findorb.parse_output(str(tmp_path))
    assert parsed["ok"] is False and parsed["residuals"] == []


# ------------------------------------------------------------- the verdict

def _other(dra, ddec, stn="X"):
    return {"dra": dra, "ddec": ddec, "stn": stn}


def test_robust_scatter_ignores_a_single_bad_observer():
    good = [_other(0.1 * i, 0.1 * i, f"S{i}") for i in range(1, 6)]
    with_bad = good + [_other(30.0, 30.0, "BAD")]
    _m1, s1 = findorb.robust_scatter([o["dra"] for o in good])
    _m2, s2 = findorb.robust_scatter([o["dra"] for o in with_bad])
    assert s2 < s1 * 3      # the MAD barely moves


def test_decide_does_not_block_inside_the_cloud():
    others = [_other(0.1 * i, 0.05 * i, f"S{i}") for i in range(-3, 4)]
    report = findorb.decide(0.05, 0.02, others, our_rms_arcsec=0.1)
    assert not report.blocked and not report.outlier
    assert report.n_others == 7 and report.n_stations == 7


def test_decide_blocks_a_far_outlier():
    others = [_other(0.05 * i, 0.05 * i, f"S{i}") for i in range(-3, 4)]
    report = findorb.decide(5.0, 5.0, others, our_rms_arcsec=0.1)
    assert report.blocked and report.outlier
    assert "check the measurement" in report.note


def test_decide_without_a_reference_does_not_block():
    report = findorb.decide(1.0, 1.0, [], our_rms_arcsec=0.1)
    assert report.no_reference and not report.blocked


def test_check_says_it_is_unavailable_without_findorb(no_auto):
    report = findorb.check("OUR LINE", "2025 UR", cfg=None)
    assert report.available is False and not report.blocked
    assert "not configured" in report.note
    # the pointer names the page the field actually lives on now
    assert "Settings > Measurement" in report.note


# ------------------------------------------------- the JSON output path

def test_run_points_the_json_output_at_the_workdir(tmp_path, monkeypatch):
    # On Linux fo drops total.json in ~/.find_orb, not the CWD, and only when
    # the JSON_*_NAME settings name it. Without this the parser looked for a
    # file that was never written ("Find_Orb produced no residuals").
    inp = tmp_path / "obs.txt"
    inp.write_text("LINE\n")
    seen = {}

    class _FakeProc:
        returncode = 0

        def __init__(self, args, **kwargs):
            seen["args"] = args
            env_path = args[args.index("-D") + 1]
            seen["env"] = open(env_path).read()

        def communicate(self, timeout=None):
            return "ok", ""

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    # run() polls a Popen so the observer's Cancel can stop it (QA-07), so the
    # test fakes Popen, not subprocess.run.
    monkeypatch.setattr(findorb.subprocess, "Popen", _FakeProc)
    ok, workdir, _log = findorb.run(str(inp), "/usr/bin/fo", timeout=5)
    assert ok
    assert "JSON_COMBINED_NAME=" in seen["env"]
    assert "total.json" in seen["env"]
    assert f"OUTPUT_DIR={workdir}" in seen["env"]


def test_run_honours_the_observers_cancel(tmp_path, monkeypatch):
    # The button used to do nothing: subprocess.run(timeout=...) cannot be
    # interrupted, so a run lasted up to the CPU limit or the wall timeout.
    inp = tmp_path / "obs.txt"
    inp.write_text("LINE\n")
    seen = {}

    class _FakeProc:
        returncode = None

        def __init__(self, args, **kwargs):
            pass

        def communicate(self, timeout=None):
            raise findorb.subprocess.TimeoutExpired("fo", timeout)

        def terminate(self):
            seen["terminated"] = True

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(findorb.subprocess, "Popen", _FakeProc)
    ok, _workdir, log = findorb.run(str(inp), "/usr/bin/fo",
                                    cancel=lambda: True, timeout=5)
    assert ok is False
    assert "cancel" in log.lower()
    assert seen.get("terminated")
def test_check_removes_both_of_its_temp_folders(tmp_path, monkeypatch):
    # Reported 2026-10-15: `check` removed the input folder but not the one
    # `run` made for itself, so every check left a `nightscribe-fo-*`
    # behind. Both go now.
    import os
    made = []
    real = findorb.tempfile.mkdtemp

    def spy(*a, **k):
        d = real(*a, **k)
        made.append(d)
        return d

    monkeypatch.setattr(findorb.tempfile, "mkdtemp", spy)
    monkeypatch.setattr(findorb, "probe",
                        lambda *a, **k: ("/usr/bin/fo", "ok"))

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(findorb.subprocess, "run", lambda *a, **k: _Proc())
    findorb.check(["OUR LINE"], "2025 UR", cfg=None,
                  others_lines=["OTHER LINE"])
    assert made, "the flow created its temp folders"
    for d in made:
        assert not os.path.exists(d), f"left behind: {d}"


def test_as_residual_reads_findorbs_obscode_key():
    # total.json calls the station "obscode"; the parser must read it, or
    # every residual would look like it came from an unknown station
    r = findorb._as_residual({"obscode": "Z41", "dRA": 0.5, "dDec": -0.2,
                              "JD": 2460000.5})
    assert r["stn"] == "Z41"
    assert r["dra"] == 0.5 and r["ddec"] == -0.2
    assert r["time"] == 2460000.5


def test_as_residual_keeps_the_fields_the_listing_needs():
    # The observer's table shows the instant, the direction and the
    # magnitude: the parser must carry them, not just the residual.
    r = findorb._as_residual({
        "obscode": "I41", "iso date": "2025-10-18T04:51:03.513Z",
        "RA": 17.66, "Dec": 21.96, "dRA": 0.0, "dDec": -0.1,
        "MagObs": 18.4, "MagBand": "R", "note1": "K"})
    assert r["iso"] == "2025-10-18T04:51:03.513Z"
    assert r["ra"] == 17.66 and r["dec"] == 21.96
    assert r["mag"] == 18.4 and r["band"] == "R"
    # a residual of exactly 0.0 is a PERFECT fit, never "missing"
    assert r["dra"] == 0.0
    assert r["note"] == "K"


def test_match_ours_prefers_the_same_instant_and_station():
    rows = [{"stn": "I41", "time": 100.0}, {"stn": "Z41", "time": 100.0},
            {"stn": "Z41", "time": 50.0}]
    ours, others = findorb._match_ours(rows, [100.0], "Z41")
    assert ours == [rows[1]] and len(others) == 2


def test_match_ours_handles_a_merged_near_duplicate():
    # Find_Orb merges our line into an already published point from our own
    # station (same night, seconds apart): our instant is not in the list,
    # so the nearest of OUR station's rows is the one that stands for us.
    rows = [{"stn": "Z41", "time": 100.0}, {"stn": "Z41", "time": 300.0}]
    ours, _others = findorb._match_ours(rows, [299.999], "Z41")
    assert ours == [rows[1]]


def test_match_ours_falls_back_to_the_first_line():
    rows = [{"stn": "X", "time": 1.0}, {"stn": "Y", "time": 2.0}]
    ours, others = findorb._match_ours(rows, [], "")
    assert ours == [rows[0]] and len(others) == 1


def test_decide_from_residuals_flags_ours_and_carries_the_listing():
    rows = [{"stn": "Z41", "time": 10.0, "dra": 0.1, "ddec": 0.1},
            {"stn": "I41", "time": 11.0, "dra": 0.2, "ddec": 0.2},
            {"stn": "F51", "time": 12.0, "dra": 0.3, "ddec": 0.3}]
    report = findorb._decide_from_residuals(rows, None, "Z41")
    assert report.residuals == rows and report.n_obs == 3
    assert [r["ours"] for r in rows] == [True, False, False]
    assert report.n_others == 2


def test_check_with_no_reference_is_not_a_failure(monkeypatch):
    # The old wording was "Find_Orb produced no residuals", which hid that
    # the real cause was an EMPTY reference (an object known only by its
    # NEOCP name). No reference is its own honest answer, not unavailable.
    monkeypatch.setattr(findorb, "probe",
                        lambda path=None: ("/usr/bin/fo", "fo"))
    report = findorb.check("OUR LINE", "A11HPKO", cfg=None,
                           others_lines="", obs_code="Z41")
    assert report.available is True and report.no_reference is True
    assert not report.blocked
    assert "no published observations" in report.note


def test_check_reports_no_fit_when_findorb_fits_nothing(tmp_path,
                                                        monkeypatch):
    # `fo` writes a TRUNCATED total.json when it fits zero objects; that is
    # "it ran but could not fit", not "it failed". It must not be dressed up
    # as "produced no residuals".
    work = tmp_path / "run"
    work.mkdir()
    (work / "total.json").write_text('{\n  "num": 0,\n  "ids": [],\n'
                                     '  "objects":\n  {\n')
    monkeypatch.setattr(findorb, "probe",
                        lambda path=None: ("/usr/bin/fo", "fo"))
    monkeypatch.setattr(findorb, "run",
                        lambda *a, **k: (True, str(work), "Processing 0 objects"))
    report = findorb.check("OUR LINE", "X", cfg=None,
                           others_lines="OTHER LINE", obs_code="Z41")
    assert report.available is True and report.no_fit is True
    assert not report.blocked
    assert "could not fit" in report.note


def test_all_our_observations_are_flagged_and_the_worst_sets_the_verdict():
    # ADR-086 rev: a combined run submits several observations; the check must
    # flag ALL of ours and its verdict must be about the WORST one, not the
    # first (a spurious point used to hide behind a good one).
    from nightscribe.core import mpc_astrometry
    pts = [
        {"mjd": 61322.8, "ra": 33.0, "dec": 35.0, "mag": 19.0, "band": "G"},
        {"mjd": 61322.9, "ra": 33.4, "dec": 35.4, "mag": 19.0, "band": "G"},
    ]
    ours = mpc_astrometry.to_mpc80(pts, "Z41", "2026 TQ8", None)
    jds = findorb._our_jds(ours)
    assert len(jds) == 2
    residuals = [
        {"stn": "Z41", "time": jds[0], "dra": 0.1, "ddec": 0.1},
        {"stn": "Z41", "time": jds[1], "dra": 200.0, "ddec": 0.0},
    ]
    # the others' cloud has a real spread, so the scatter is not zero
    residuals += [{"stn": f"X{i:02d}", "time": jds[0] + i * 0.001,
                   "dra": 0.1 * ((-1) ** i), "ddec": 0.05 * ((-1) ** i)}
                  for i in range(1, 9)]
    rep = findorb._decide_from_residuals(residuals, None, "Z41",
                                         ours_lines=ours)
    assert len([r for r in residuals if r["ours"]]) == 2
    assert rep.our_residual[0] == 200.0      # the worst, not ours[0]


# ------------------------------------------- the copy NightScribe ships

def test_probe_uses_the_bundled_copy(tmp_path, monkeypatch):
    # Installing the app brings Find_Orb with it: probe must find the shipped
    # `fo` before looking at PATH, so the check works out of the box.
    from nightscribe import paths
    bundle = tmp_path / "findorb"
    (bundle / "bin").mkdir(parents=True)
    fo = bundle / "bin" / "fo"
    fo.write_bytes(b"x")
    monkeypatch.setattr(paths, "findorb_bundle_dir", lambda: bundle)
    monkeypatch.setattr(findorb.shutil, "which", lambda name: None)
    path, message = findorb.probe()
    assert path == str(fo) and "bundled" in message


def test_probe_falls_back_to_path_without_a_bundle(no_auto, monkeypatch):
    from nightscribe.core import findorb_install
    monkeypatch.setattr(findorb_install.shutil, "which",
                        lambda name: "/usr/bin/fo" if name == "fo" else None)
    path, _message = findorb.probe()
    assert path == "/usr/bin/fo"


def test_seed_findorb_home_copies_the_shipped_data(tmp_path, monkeypatch):
    # The shipped `fo` was built with a prefix that no longer exists and
    # copies its data to $HOME/.find_orb on the first run. Seeding the folder
    # first is what makes a relocated copy start at all.
    from nightscribe import paths
    bundle = tmp_path / "bundle"
    data = bundle / "share" / "findorb" / "data"
    data.mkdir(parents=True)
    (data / "ObsCodes.htm").write_text("codes")
    (data / "calendar.txt").write_text("cal")
    monkeypatch.setattr(paths, "findorb_bundle_dir", lambda: bundle)
    home = tmp_path / "home"
    home.mkdir()
    findorb._seed_findorb_home(home)
    cfg = home / ".find_orb"
    assert (cfg / "ObsCodes.htm").read_text() == "codes"
    assert (cfg / "calendar.txt").read_text() == "cal"
    # a second seed is a no-op: it must never overwrite the observer's config
    (cfg / "calendar.txt").write_text("mine")
    findorb._seed_findorb_home(home)
    assert (cfg / "calendar.txt").read_text() == "mine"


def test_private_env_points_home_at_the_findorb_folder(tmp_path,
                                                       monkeypatch):
    from nightscribe import paths
    monkeypatch.setattr(paths, "findorb_home_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "findorb_bundle_dir", lambda: None)
    env = findorb._private_env()
    assert env["HOME"] == str(tmp_path)
    assert env["USERPROFILE"] == str(tmp_path)
