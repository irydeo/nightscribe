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
import signal
import time
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
    # the GUI says "ran past its time limit", not "did not finish": the two
    # send the observer to different places
    assert res["timed_out"] and not res["cancelled"]


def test_run_removes_exotics_own_log_but_keeps_ours(tmp_path):
    # EXOTIC writes exotic.log (26 MB of DEBUG for one run) plus the files
    # of its daily rotator; the app streams exotic_run.log, so EXOTIC's is
    # dropped at the end and our merged log stays
    script = _fake(tmp_path, "exotic_noisy.py", """
import pathlib, sys
print("EXOTIC fake: starting", flush=True)
pathlib.Path("exotic.log").write_text("numba chatter\\n")
pathlib.Path("exotic.log.2026-10-01").write_text("rotated\\n")
print("EXOTIC fake: done", flush=True)
sys.exit(0)
""")
    work = tmp_path / "w"
    work.mkdir()
    (work / "exotic.log").write_text("leftover from a killed run\n")
    res = exotic_run.run(script, work, tmp_path / "inits.json")
    assert res["ok"]
    assert not list(work.glob("exotic.log*"))       # nothing left behind
    assert (work / exotic_run.LOG_NAME).exists()    # ours is still there
    assert "done" in (work / exotic_run.LOG_NAME).read_text()


def _pid_alive(pid):
    # @args: pid - process id to probe
    # @return: True only if the pid still exists and is not a zombie
    #          (an unreaped zombie is already dead for our purposes)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = Path("/proc") / str(pid) / "stat"
    if stat.exists():                       # Linux: zombies count as dead
        try:
            return not stat.read_text().rsplit(") ", 1)[1].startswith("Z")
        except OSError:
            pass
    return True


def test_run_does_not_hang_on_a_child_holding_the_pipe(tmp_path):
    # Regression (2026-09-30): a child that inherits stdout keeps the pipe
    # open after its parent is gone, so the reader never sees EOF. Without
    # the drain grace the app sat on "Running EXOTIC" until the two-hour
    # timeout although EXOTIC had finished. The fake prints its child's pid
    # and exits; the child sleeps, holding the write end.
    script = _fake(tmp_path, "exotic_orphan.py", """
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c",
                          "import time; time.sleep(15)"],
                         stdin=subprocess.DEVNULL)
print(child.pid, flush=True)
print("done", flush=True)
sys.exit(0)
""")
    state = {"child": None}

    def progress(line):
        if line.strip().isdigit():
            state["child"] = int(line.strip())

    start = time.monotonic()
    res = exotic_run.run(script, tmp_path / "w", tmp_path / "inits.json",
                         progress=progress, timeout_s=20)
    elapsed = time.monotonic() - start
    try:
        assert res["ok"] and res["returncode"] == 0
        assert elapsed < 6, f"waited {elapsed:.1f}s for a dead parent"
    finally:
        if state["child"] is not None and _pid_alive(state["child"]):
            try:
                os.kill(state["child"],
                        getattr(signal, "SIGKILL", signal.SIGTERM))
            except OSError:
                pass


@pytest.mark.skipif(os.name != "posix",
                    reason="group kill is verified on POSIX; Windows goes "
                           "through taskkill /T /F")
def test_cancel_kills_the_whole_process_tree(tmp_path):
    # EXOTIC uses multiprocessing: cancelling the parent alone left its
    # children running (P1 #8). The fake parent spawns a real child and
    # prints its pid; after the cancel both must be gone.
    script = _fake(tmp_path, "exotic_tree.py", """
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c",
                          "import time; time.sleep(60)"],
                         stdin=subprocess.DEVNULL)
print(child.pid, flush=True)
time.sleep(60)
""")
    state = {"n": 0, "child": None}

    def progress(line):
        if line.strip().isdigit():
            state["child"] = int(line.strip())

    def cancel():
        state["n"] += 1
        return state["n"] > 1

    res = exotic_run.run(script, tmp_path / "w", tmp_path / "inits.json",
                         progress=progress, cancel=cancel)
    try:
        assert res["cancelled"] and not res["ok"]
        assert state["child"] is not None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _pid_alive(state["child"]):
            time.sleep(0.05)
        assert not _pid_alive(state["child"])
    finally:
        if state["child"] is not None and _pid_alive(state["child"]):
            os.kill(state["child"], signal.SIGKILL)   # never leak the child
