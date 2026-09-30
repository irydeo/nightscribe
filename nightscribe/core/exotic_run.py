############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - EXOTIC headless runner (orchestration phase C)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Run EXOTIC headless and locate its outputs (plan phase C).

The verified invocation (2026-09-27) is the console script inside the
external venv: `exotic -red <inits.json> -ov`, from a work directory, with
stdin closed so any prompt fails fast instead of hanging the app. stdout
and stderr are merged into one log file; the process can be cancelled and
is killed on timeout. EXOTIC uses multiprocessing, so it is spawned as the
leader of its own process group and the kill reaches the whole group:
signalling only the parent leaves children eating CPU and holding files.
"""

import logging
import os
import queue
import signal
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 7200.0     # a full EXOTIC run can take a while
LOG_NAME = "exotic_run.log"
# After EXOTIC's process is gone, the pipe can still hold its last lines (and
# a child that inherited the write end can keep it open forever). This is how
# long the reader keeps draining an already-dead process before we stop: long
# enough for the tail to land in the log, short enough that a stuck pipe can
# never masquerade as a two-hour run.
_DRAIN_GRACE_S = 1.5

# Run EXOTIC through the USER's interpreter (their own install or the venv
# the app prepared), not the console script: that script's path depends on
# the install layout, while `-c` works for any interpreter that has EXOTIC.
_MAIN = ("import sys; sys.argv[0] = 'exotic'; "
         "from exotic.exotic import main; sys.exit(main())")


def _group_kwargs():
    # Popen extras so EXOTIC leads a brand-new process group (session on
    # POSIX) and its multiprocessing children join it: _kill_tree can then
    # take the whole tree down instead of orphaning the children.
    # @args: none
    # @return: dict of Popen keyword arguments for this platform
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _kill_tree(proc, hard=False):
    # Signal EXOTIC's whole process group, not just the parent.
    # @args: proc - Popen of the EXOTIC parent (leader of its own group,
    #        see _group_kwargs), hard - SIGKILL the group instead of
    #        SIGTERM (POSIX; taskkill /F is a hard kill already)
    # @return: nothing
    fallback = proc.kill if hard else proc.terminate
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
            return
        except (OSError, subprocess.SubprocessError):
            fallback()          # no taskkill: at least stop the parent
            return
    try:
        os.killpg(proc.pid, signal.SIGKILL if hard else signal.SIGTERM)
    except OSError:
        fallback()              # group already gone: parent-only signal


def run(python, work_dir, inits_path, mode="red", override=True,
        progress=None, cancel=None, timeout_s=DEFAULT_TIMEOUT_S):
    # @args: python - the Python <=3.10 interpreter that has EXOTIC installed,
    #        work_dir - cwd (its plots land here per the inits),
    #        inits_path - the inits.json, mode - red|phot|pre|rt,
    #        override - pass -ov (adopt our params, skips the interactive
    #        parameter prompt), progress - callable(line),
    #        cancel - callable() -> bool, timeout_s - hard cap
    # @return: {"ok", "returncode", "log_path", "out_dir", "cancelled",
    #          "timed_out"}
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    log_path = work_dir / LOG_NAME
    cmd = [str(python), "-c", _MAIN, f"-{mode}", str(inits_path)]
    if override:
        cmd.append("-ov")
    logger.info("running EXOTIC: %s (cwd=%s)", " ".join(cmd), work_dir)
    start = time.monotonic()
    cancelled = False
    timed_out = False
    proc = None
    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as lf:
            proc = subprocess.Popen(
                cmd, cwd=str(work_dir), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                **_group_kwargs())
            lines = queue.Queue()

            def _reader(pipe):
                # a thread so a silent EXOTIC cannot freeze cancel/timeout
                for line in pipe:
                    lines.put(line)
                lines.put(None)

            threading.Thread(target=_reader, args=(proc.stdout,),
                             daemon=True).start()
            gone_at = None
            while True:
                try:
                    line = lines.get(timeout=0.5)
                except queue.Empty:
                    line = ""
                if line is None:
                    break
                if line:
                    lf.write(line)
                    lf.flush()
                    if progress is not None:
                        progress(line.rstrip())
                if cancel is not None and cancel():
                    cancelled = True
                    _kill_tree(proc)
                    break
                if timeout_s and time.monotonic() - start > timeout_s:
                    timed_out = True
                    logger.warning("EXOTIC timed out after %ss", timeout_s)
                    _kill_tree(proc)
                    break
                if proc.poll() is not None:
                    # The process is gone: drain what is left in the pipe,
                    # then stop. Without this we would only leave the loop
                    # on EOF, and a pipe that never closes (a child holding
                    # the write end) would keep the app "running" until the
                    # two-hour timeout while EXOTIC had long finished.
                    if line:
                        gone_at = None          # still draining
                    elif gone_at is None:
                        gone_at = time.monotonic()
                    elif time.monotonic() - gone_at > _DRAIN_GRACE_S:
                        break
                else:
                    gone_at = None
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                _kill_tree(proc, hard=True)
    except (OSError, subprocess.SubprocessError) as err:
        logger.warning("EXOTIC run failed: %s", err)
        return {"ok": False, "returncode": None, "log_path": str(log_path),
                "out_dir": str(work_dir), "cancelled": False,
                "timed_out": False}
    rc = proc.returncode if proc is not None else None
    logger.info("EXOTIC finished: rc=%s in %.1fs (cancelled=%s, timed_out=%s)",
                rc, time.monotonic() - start, cancelled, timed_out)
    return {"ok": (rc == 0 and not cancelled and not timed_out),
            "returncode": rc, "log_path": str(log_path),
            "out_dir": str(work_dir), "cancelled": cancelled,
            "timed_out": timed_out}


def find_outputs(out_dir):
    # Locate EXOTIC's result files in its output folder (root plus temp/).
    # @args: out_dir - the "Directory to Save Plots"
    # @return: {"curve_csv", "params_json", "normalized_txt", "figure_png",
    #          "aavso_txt"} each a path string or None
    out = Path(out_dir)
    temp = out / "temp"

    def _first(folder, pattern):
        if not folder.is_dir():
            return None
        hits = sorted(folder.glob(pattern))
        return str(hits[0]) if hits else None

    return {
        "curve_csv": _first(temp, "FinalLightCurve_*.csv"),
        "params_json": _first(temp, "FinalParams_*.json"),
        "normalized_txt": _first(temp, "NormalizedFlux_*.txt"),
        "figure_png": _first(out, "FinalLightCurve_*.png"),
        "aavso_txt": _first(out, "AAVSO_*.txt"),
    }
