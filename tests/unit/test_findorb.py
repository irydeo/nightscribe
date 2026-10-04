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
