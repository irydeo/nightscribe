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

"""Phase-A acceptance, plus the two things that went wrong in the field:
finding a Python EXOTIC can live in (3.10 to 3.12), probing an EXOTIC import,
and building the venv (without pip, then bootstrapped) with the pip sequence
verified. The second half is the 2026-10-20 report: a prepare that wiped the
environment it was about to rebuild, and an app that said "no Python found"
when the configured interpreter was simply gone.

subprocess is monkeypatched; no network, no real venv.
"""

import subprocess
from pathlib import Path

import pytest

from nightscribe.core import exotic_env


def _completed(cmd, rc=0, out="", err=""):
    return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)


def test_detect_python_prefers_the_configured_path(tmp_path, monkeypatch):
    exe = tmp_path / "python3.10"
    exe.write_text("#!/bin/sh\n")
    monkeypatch.setattr(exotic_env, "version_ok", lambda p: True)
    assert exotic_env.detect_python(str(exe)) == str(exe)


def test_detect_python_rejects_a_wrong_version(tmp_path, monkeypatch):
    # A configured interpreter of the wrong version is not used... and the
    # search that follows finds nothing here either, so the answer is None
    # instead of a wrong interpreter.
    exe = tmp_path / "python3.13"
    exe.write_text("#!/bin/sh\n")
    monkeypatch.setattr(exotic_env, "version_ok", lambda p: False)
    monkeypatch.setattr(exotic_env.shutil, "which", lambda n: None)
    assert exotic_env.detect_python(str(exe)) is None


def test_detect_python_falls_back_to_which(monkeypatch):
    monkeypatch.setattr(exotic_env.shutil, "which",
                        lambda n: "/usr/bin/python3.10" if n == "python3.10"
                        else None)
    monkeypatch.setattr(exotic_env, "version_ok", lambda p: True)
    assert exotic_env.detect_python("") == "/usr/bin/python3.10"


def test_detect_python_none(monkeypatch):
    monkeypatch.setattr(exotic_env.shutil, "which", lambda n: None)
    assert exotic_env.detect_python("") is None


def test_detect_python_uses_the_py_launcher_on_windows(tmp_path,
                                                       monkeypatch):
    # on Windows the launcher `py -3.10` resolves to a real interpreter.
    # A fake os module: mutating the real os.name would make pathlib build
    # WindowsPath on POSIX (and is_file would lie).
    import types
    exe = tmp_path / "python3.10"
    exe.write_text("#!/bin/sh\n")
    monkeypatch.setattr(exotic_env, "os", types.SimpleNamespace(name="nt"))
    monkeypatch.setattr(exotic_env.shutil, "which",
                        lambda n: "/usr/bin/py" if n == "py" else None)

    def fake_run(cmd, **k):
        joined = " ".join(str(c) for c in cmd)
        if "print(sys.executable)" in joined:
            return subprocess.CompletedProcess(cmd, 0, stdout=str(exe) + "\n")
        if "version_info" in joined:
            return subprocess.CompletedProcess(cmd, 0, stdout="3.10\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="")

    monkeypatch.setattr(exotic_env.subprocess, "run", fake_run)
    assert exotic_env.detect_python("") == str(exe)


def test_probe_ok_and_fail(monkeypatch):
    monkeypatch.setattr(exotic_env.subprocess, "run",
                        lambda *a, **k: _completed(a, 0, "4.3.1\n"))
    rep = exotic_env.probe("/usr/bin/python3.10")
    assert rep["ok"] and rep["version"] == "4.3.1"
    monkeypatch.setattr(exotic_env.subprocess, "run",
                        lambda *a, **k: _completed(a, 1, "", "ImportError"))
    assert not exotic_env.probe("/usr/bin/python3.10")["ok"]
    assert not exotic_env.probe(None)["ok"]


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


def test_version_ok_reads_the_interpreter(monkeypatch):
    # EXOTIC 4.x asks for >= 3.10 and its whole pinned stack has wheels for
    # 3.10, 3.11 and 3.12; 3.11 was verified with a full install on
    # 2026-10-20, and 3.13 is out (numpy 1.26 has no wheels for it).
    for version in ("3.10\n", "3.11\n", "3.12\n"):
        monkeypatch.setattr(exotic_env.subprocess, "run",
                            lambda *a, **k: _completed(a, 0, version))
        assert exotic_env.version_ok("/x/python"), version
    for version in ("3.9\n", "3.13\n"):
        monkeypatch.setattr(exotic_env.subprocess, "run",
                            lambda *a, **k: _completed(a, 0, version))
        assert not exotic_env.version_ok("/x/python"), version
    monkeypatch.setattr(exotic_env.subprocess, "run",
                        lambda *a, **k: _completed(a, 1, "", "boom"))
    assert not exotic_env.version_ok("/x/python")


def test_the_candidates_are_the_versions_exotic_accepts():
    # 3.9 and 3.8 are gone (EXOTIC 4.x does not support them: pip would
    # install an old EXOTIC there) and 3.13 is not offered either
    assert "python3.9" not in exotic_env._CANDIDATES
    assert "python3.8" not in exotic_env._CANDIDATES
    assert "python3.13" not in exotic_env._CANDIDATES
    assert set(exotic_env._CANDIDATES) == {"python3.10", "python3.11",
                                           "python3.12"}


def test_detect_python_looks_for_another_when_the_configured_one_is_gone(
        tmp_path, monkeypatch):
    # THE REPORTED CASE: the configured venv was deleted, and the app said
    # "no Python 3.10 interpreter found" while a working 3.11 sat on the PATH
    missing = tmp_path / "exotic-venv" / "bin" / "python"
    monkeypatch.setattr(exotic_env.shutil, "which",
                        lambda n: "/usr/bin/python3.11" if n == "python3.11"
                        else None)
    monkeypatch.setattr(exotic_env, "version_ok", lambda p: True)
    assert exotic_env.detect_python(str(missing)) == "/usr/bin/python3.11"


def test_configured_problem_says_which_one(tmp_path, monkeypatch):
    monkeypatch.setattr(exotic_env, "version_ok", lambda p: True)
    assert exotic_env.configured_problem("") is None
    assert exotic_env.configured_problem(
        str(tmp_path / "gone" / "python")) == "missing"
    exe = tmp_path / "python3.13"
    exe.write_text("#!/bin/sh\n")
    monkeypatch.setattr(exotic_env, "version_ok", lambda p: False)
    assert exotic_env.configured_problem(str(exe)) == "version"


def _fake_venv_builder(calls, fail_at=None):
    # @args: calls - the commands to record, fail_at - a substring of the
    #        command that must fail (the EXOTIC install, normally)
    # @return: a fake subprocess.run that creates what a real `venv` creates
    #          IN THE FOLDER THE COMMAND ASKS FOR (not in a fixed one: prepare
    #          builds in a sibling), and leaves no pip behind on the first
    #          attempt so the ensurepip quirk is exercised
    def fake_run(cmd, **k):
        args = [str(c) for c in cmd]
        calls.append(args)
        joined = " ".join(args)
        if fail_at and fail_at in joined:
            return _completed(cmd, 2, "", "boom")
        if "-m venv" in joined:
            target = Path(args[-1])
            py = exotic_env.venv_python(target)
            py.parent.mkdir(parents=True, exist_ok=True)
            py.write_text("#!/bin/sh\n")
        if "install --upgrade pip" in joined:
            target = Path(args[args.index("--python") + 1]).parent.parent
            (exotic_env.bin_dir(target) / "pip").write_text("")
        return _completed(cmd, 0, "ok")
    return fake_run


def test_prepare_runs_the_expected_pip_sequence(tmp_path, monkeypatch):
    # the ensurepip quirk: the first `venv` leaves no pip, so prepare redoes
    # the environment WITHOUT pip and bootstraps it through the base
    # interpreter, then installs EXOTIC in it
    install = tmp_path / "exotic-venv"
    calls = []
    monkeypatch.setattr(exotic_env.subprocess, "run",
                        _fake_venv_builder(calls))
    stages = []
    ok, log = exotic_env.prepare(install, "/usr/bin/python3.10",
                                 progress=stages.append)
    assert ok, log
    assert stages[-1] == "done"
    joined = " ".join(" ".join(c) for c in calls)
    assert "venv --without-pip" in joined
    assert "pip --python" in joined
    assert "install exotic" in joined


def test_prepare_builds_aside_and_swaps_at_the_end(tmp_path, monkeypatch):
    # The environment is built in a SIBLING folder and only moved into place
    # once it works: the swap is what makes a failed rebuild harmless.
    install = tmp_path / "exotic-venv"
    monkeypatch.setattr(exotic_env.subprocess, "run",
                        _fake_venv_builder([]))
    ok, log = exotic_env.prepare(install, "/usr/bin/python3.11")
    assert ok, log
    assert exotic_env.venv_python(install).is_file()
    assert not install.with_name(install.name + ".new").exists()
    assert not install.with_name(install.name + ".old").exists()


def test_a_failed_prepare_keeps_the_previous_environment(tmp_path,
                                                         monkeypatch):
    # THE BUG THAT ATE A REAL ENVIRONMENT (2026-10-20): the old code wiped the
    # target first, so a build that failed left nothing behind.
    install = tmp_path / "exotic-venv"
    old = install / "bin" / "python"
    old.parent.mkdir(parents=True)
    old.write_text("the environment that worked\n")
    monkeypatch.setattr(exotic_env.subprocess, "run",
                        _fake_venv_builder([], fail_at="install exotic"))
    ok, log = exotic_env.prepare(install, "/usr/bin/python3.11")
    assert not ok and "boom" in log
    assert old.is_file(), "the previous environment was destroyed"
    assert old.read_text() == "the environment that worked\n"
    assert not install.with_name(install.name + ".new").exists(), \
        "a half-built folder was left behind"


def test_a_cancelled_prepare_keeps_the_previous_environment(tmp_path,
                                                            monkeypatch):
    install = tmp_path / "exotic-venv"
    old = install / "bin" / "python"
    old.parent.mkdir(parents=True)
    old.write_text("still here\n")
    state = {"n": 0}

    def cancel():
        state["n"] += 1
        return state["n"] > 1

    monkeypatch.setattr(exotic_env.subprocess, "run",
                        _fake_venv_builder([]))
    ok, log = exotic_env.prepare(install, "/usr/bin/python3.11",
                                 cancel=cancel)
    assert not ok and "cancelled" in log
    assert old.is_file() and old.read_text() == "still here\n"
    assert not install.with_name(install.name + ".new").exists()


def test_prepare_refuses_a_base_interpreter_inside_the_target(tmp_path):
    # The app offers the venv it already built as the base interpreter, and
    # that is the case that destroyed a working environment: the wipe took the
    # interpreter away halfway through the build. It is refused with the why.
    install = tmp_path / "exotic-venv"
    base = install / "bin" / "python"
    base.parent.mkdir(parents=True)
    base.write_text("#!/bin/sh\n")
    ok, log = exotic_env.prepare(install, str(base))
    assert not ok
    assert "lives inside the folder being built" in log
    assert base.is_file(), "the interpreter was taken away"
