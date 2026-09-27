############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: EXOTIC environment (orchestration phase A)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase-A acceptance: finding a Python <=3.10, probing an EXOTIC import
and building the venv (without pip, then bootstrapped) with the pip
sequence verified. subprocess is monkeypatched; no network, no real venv.
"""

import subprocess
from pathlib import Path

import pytest

from nightscribe.core import exotic_env


def _completed(cmd, rc=0, out="", err=""):
    return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)


def test_detect_python_prefers_the_configured_path(tmp_path):
    exe = tmp_path / "python3.10"
    exe.write_text("#!/bin/sh\n")
    assert exotic_env.detect_python(str(exe)) == str(exe)


def test_detect_python_falls_back_to_which(monkeypatch):
    monkeypatch.setattr(exotic_env.shutil, "which",
                        lambda n: "/usr/bin/python3.10" if n == "python3.10"
                        else None)
    assert exotic_env.detect_python("") == "/usr/bin/python3.10"


def test_detect_python_none(monkeypatch):
    monkeypatch.setattr(exotic_env.shutil, "which", lambda n: None)
    assert exotic_env.detect_python("") is None


def test_probe_ok_and_fail(monkeypatch):
    monkeypatch.setattr(exotic_env.subprocess, "run",
                        lambda *a, **k: _completed(a, 0, "4.3.1\n"))
    rep = exotic_env.probe("/usr/bin/python3.10")
    assert rep["ok"] and rep["version"] == "4.3.1"
    monkeypatch.setattr(exotic_env.subprocess, "run",
                        lambda *a, **k: _completed(a, 1, "", "ImportError"))
    assert not exotic_env.probe("/usr/bin/python3.10")["ok"]
    assert not exotic_env.probe(None)["ok"]


def test_prepare_runs_the_expected_pip_sequence(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **k):
        calls.append([str(c) for c in cmd])
        return _completed(cmd, 0, "ok")

    monkeypatch.setattr(exotic_env.subprocess, "run", fake_run)
    install = tmp_path / "exotic-venv"
    stages = []
    ok, log = exotic_env.prepare(install, "/usr/bin/python3.10",
                                 progress=stages.append)
    assert ok
    assert stages[-1] == "done"
    joined = " ".join(" ".join(c) for c in calls)
    assert "venv --without-pip" in joined
    assert "pip --python" in joined
    assert "install exotic" in joined


def test_prepare_reports_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(exotic_env.subprocess, "run",
                        lambda cmd, **k: _completed(cmd, 2, "", "boom"))
    ok, log = exotic_env.prepare(tmp_path / "v", "/usr/bin/python3.10")
    assert not ok and "boom" in log


def test_prepare_cancels_cleanly(tmp_path, monkeypatch):
    state = {"n": 0}

    def cancel():
        state["n"] += 1
        return state["n"] > 1

    monkeypatch.setattr(exotic_env.subprocess, "run",
                        lambda cmd, **k: _completed(cmd, 0, "ok"))
    ok, log = exotic_env.prepare(tmp_path / "v", "/usr/bin/python3.10",
                                 cancel=cancel)
    assert not ok and "cancelled" in log


def test_venv_python_layout(tmp_path):
    p = exotic_env.venv_python(tmp_path / "v")
    assert p.name in ("python", "python.exe")
    assert p.parent.name in ("bin", "Scripts")
