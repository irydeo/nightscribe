############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Parallel work sizing module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""How many workers a CPU-bound stage may use, and the tiny map that runs
them.

Why this module exists at all: the astrometry pipeline (register, warp,
combine) runs inside ONE worker thread and leaves every other core idle.
Measured on a 16-core machine, scipy's affine warp scales x9.7 over 16
threads and numpy's median x4.7 over 8, because both release the GIL. That
is the cheapest speed-up in the whole engine and it needs no dependency.

Two rules keep it honest:

* the number is COMPUTED, never hardcoded. It comes from the cores the
  process may actually use (respecting affinity, so a container or a
  cgroup is not overcounted) minus a margin for the GUI and the OS, and it
  is then capped by MEMORY: every worker holds its own frame-sized buffer,
  so a 2048^2 warp with sixteen workers would ask for gigabytes. The
  smaller of the two wins.
* it must run the same on Windows and Linux. There is no `platform` branch
  and no Linux-only import: the candidates are looked up with getattr and
  the first one that answers wins. `os.sched_getaffinity` simply does not
  exist on Windows and is skipped; `os.process_cpu_count` only exists on
  3.13+ and falls through to `os.cpu_count` on 3.12.

Threads and not processes, on purpose: Windows has no fork, so a process
pool would need spawn, an `if __name__ == "__main__"` guard and pickling
the frame arrays between processes. Threads avoid all of that and still
scale, because the heavy loops are in C and release the GIL.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# The ceiling for the AUTO number. Past a point the memory bandwidth is
# saturated and adding workers only adds contention (measured: 8 threads
# gave x7.1 and 16 gave x9.7 on the same 16-core machine, so the curve is
# already flattening). The observer can override it in the settings.
MAX_WORKERS = 16


def cpu_cores():
    # The logical cores THIS process may use, at least 1. The order matters:
    # process_cpu_count (3.13+) respects the affinity and the Windows
    # processor groups; sched_getaffinity is the Linux truth (it is what a
    # container leaves visible); cpu_count is the last resort on Windows.
    # @return: int >= 1
    for name in ("process_cpu_count",):
        fn = getattr(os, name, None)
        if callable(fn):
            try:
                n = int(fn())
                if n > 0:
                    return n
            except (OSError, ValueError, TypeError):
                pass
    sched = getattr(os, "sched_getaffinity", None)   # Linux only
    if callable(sched):
        try:
            n = len(sched(0))
            if n > 0:
                return n
        except (OSError, ValueError, TypeError):
            pass
    try:
        n = int(os.cpu_count() or 1)
    except (TypeError, ValueError):
        n = 1
    return max(1, n)


def available_memory_bytes():
    # Free physical memory, so the worker count can be capped by what the
    # machine can really hold. Two paths, one per family, and None when
    # neither answers (the caller then falls back to its own budget).
    # @return: int bytes, or None
    try:
        pages = os.sysconf("SC_AVPHYS_PAGES")        # Linux / macOS
        size = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and size > 0:
            return int(pages) * int(size)
    except (ValueError, OSError, AttributeError):
        pass
    try:
        import ctypes

        class _MemoryStatusEx(ctypes.Structure):     # Windows
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
    except Exception:                                 # no windll off Windows
        pass
    return None


def worker_count(per_task_bytes=0, budget_bytes=None, cfg=None,
                 cap=MAX_WORKERS):
    # How many workers a stage may run, from the CORES and from the MEMORY.
    # @args: per_task_bytes - the working set of one task (a warp's output
    #        box, a combine slice), or 0 when it is negligible,
    #        budget_bytes - the memory the stage may use (None: the free
    #        physical memory, or the caller's own budget when that cannot be
    #        read), cfg - Config with the optional "astrometry_threads"
    #        override (0 = automatic), cap - the ceiling for the automatic
    #        number
    # @return: int >= 1
    cores = cpu_cores()
    # one core is left to the GUI thread, the OS and whatever numpy/scipy
    # spin up on their own
    auto = max(1, cores - 1)
    if budget_bytes is None:
        budget_bytes = available_memory_bytes()
    by_memory = auto
    if per_task_bytes and per_task_bytes > 0 and budget_bytes:
        by_memory = max(1, int(budget_bytes // per_task_bytes))
    n = min(auto, by_memory, max(1, int(cap)))
    want = 0
    if cfg is not None:
        try:
            want = int(cfg.get("astrometry_threads", 0) or 0)
        except (TypeError, ValueError):
            want = 0
    if want > 0:
        # an explicit choice wins, but never more than the machine has
        n = min(want, cores)
    return max(1, n)


def map_parallel(fn, items, workers=1, cancel=None):
    # Runs fn over items, keeping the ORDER of the results (the caller's
    # index alignment is not negotiable: one stack per observation). With
    # workers <= 1 or a single item it stays serial, so the simple path is
    # also the tested one.
    # @args: fn - callable(item) -> result, items - iterable,
    #        workers - how many threads, cancel - optional callable()
    #        -> bool; no new task is submitted once it says True (the ones
    #        already running finish: a thread cannot be killed)
    # @return: list of results, one per item, in order
    items = list(items)
    if workers <= 1 or len(items) <= 1:
        return [fn(item) for item in items]
    out = [None] * len(items)
    with ThreadPoolExecutor(max_workers=int(workers)) as pool:
        pending = {}
        for index, item in enumerate(items):
            if cancel is not None and cancel():
                break
            pending[pool.submit(fn, item)] = index
        for future in as_completed(pending):
            out[pending[future]] = future.result()
    return out
