############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: EXOTIC headless runner (phase C)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase-C acceptance: run EXOTIC headless, merge its log, cancel it and
kill it on timeout, and locate its outputs. A fake `exotic` script stands
in for the real one. No network."""

import os
from pathlib import Path

import pytest

from nightscribe.core import exotic_run


def _fake(tmp_path, name, body):
    script = tmp_path / name
    script.write_text("#!/usr/bin/env python3\n" + body)
    os.chmod(script, 0o755)
    return script


def _ok_script(tmp_path):
    return _fake(tmp_path, "exotic_ok.py", """
import os, sys
from pathlib import Path
print("EXOTIC fake: starting", flush=True)
print("Running photometry", flush=True)
cwd = Path(os.getcwd())
(cwd / "temp").mkdir(exist_ok=True)
(cwd / "temp" / "FinalLightCurve_X.csv").write_text("BJD,Flux\\n")
(cwd / "temp" / "FinalParams_X.json").write_text("{}")
(cwd / "FinalLightCurve_X.png").write_bytes(b"png")
print("EXOTIC has successfully run!!!", flush=True)
sys.exit(0)
""")


def test_run_success_and_find_outputs(tmp_path):
    script = _ok_script(tmp_path)
    work = tmp_path / "work"
    lines = []
    res = exotic_run.run(script, work, tmp_path / "inits.json",
                         progress=lines.append)
    assert res["ok"] and res["returncode"] == 0 and not res["cancelled"]
    assert Path(res["log_path"]).exists()
    assert any("photometry" in ln for ln in lines)
    out = exotic_run.find_outputs(work)
    assert out["curve_csv"] and out["params_json"] and out["figure_png"]
    assert out["normalized_txt"] is None      # not produced by the fake


def test_run_failure(tmp_path):
    script = _fake(tmp_path, "exotic_fail.py",
                   "import sys\nprint('boom', flush=True)\nsys.exit(2)\n")
    res = exotic_run.run(script, tmp_path / "w", tmp_path / "inits.json")
    assert not res["ok"] and res["returncode"] == 2


def test_run_can_be_cancelled(tmp_path):
    script = _fake(tmp_path, "exotic_slow.py", """
import time
print("started", flush=True)
time.sleep(30)
""")
    state = {"n": 0}

    def cancel():
        state["n"] += 1
        return state["n"] > 1

    res = exotic_run.run(script, tmp_path / "w", tmp_path / "inits.json",
                         cancel=cancel)
    assert res["cancelled"] and not res["ok"]


def test_run_times_out(tmp_path):
    script = _fake(tmp_path, "exotic_hang.py", """
import time
print("started", flush=True)
time.sleep(30)
""")
    res = exotic_run.run(script, tmp_path / "w", tmp_path / "inits.json",
                         timeout_s=0.6)
    assert not res["ok"]
