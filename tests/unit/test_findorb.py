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


# ------------------------------------------------------------------ probe

def test_probe_refuses_the_interactive_binary(tmp_path):
    fake = tmp_path / "find_orb"
    fake.write_text("#!/bin/sh\n")
    path, message = findorb.probe(str(fake))
    assert path is None and "interactive" in message


def test_probe_reports_a_missing_path():
    path, message = findorb.probe("/no/such/fo")
    assert path is None and "not found" in message


def test_probe_finds_fo_on_the_path(monkeypatch):
    monkeypatch.setattr(findorb.shutil, "which",
                        lambda name: "/usr/bin/fo" if name == "fo" else None)
    path, _message = findorb.probe()
    assert path == "/usr/bin/fo"


def test_probe_says_when_nothing_is_configured(monkeypatch):
    monkeypatch.setattr(findorb.shutil, "which", lambda name: None)
    path, message = findorb.probe()
    assert path is None and "not configured" in message


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


def test_check_says_it_is_unavailable_without_findorb(monkeypatch):
    monkeypatch.setattr(findorb.shutil, "which", lambda name: None)
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

    class _Proc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(args, **kwargs):
        seen["args"] = args
        env_path = args[args.index("-D") + 1]
        seen["env"] = open(env_path).read()
        return _Proc()

    monkeypatch.setattr(findorb.subprocess, "run", fake_run)
    ok, workdir, _log = findorb.run(str(inp), "/usr/bin/fo", timeout=5)
    assert ok
    assert "JSON_COMBINED_NAME=" in seen["env"]
    assert "total.json" in seen["env"]
    assert f"OUTPUT_DIR={workdir}" in seen["env"]


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


def test_probe_falls_back_to_path_without_a_bundle(monkeypatch):
    from nightscribe import paths
    monkeypatch.setattr(paths, "findorb_bundle_dir", lambda: None)
    monkeypatch.setattr(findorb.shutil, "which",
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
