############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: parallel work sizing (speed plan)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The worker count must be COMPUTED, not chosen, and it must run the same
on Windows and Linux. What is proven here: the core detection falls through
its candidates in order (process_cpu_count, sched_getaffinity, cpu_count)
without a platform branch; the memory cap lowers the number when one task
does not fit; the settings override wins; and the map keeps the order of its
results and stops submitting when cancelled.
"""

import os

from nightscribe.core import parallel


# ------------------------------------------------------------ the cores

def test_cores_prefers_process_cpu_count(monkeypatch):
    # 3.13+ and affinity-aware: it is the most honest number when it exists
    monkeypatch.setattr(os, "process_cpu_count", lambda: 6, raising=False)
    monkeypatch.setattr(os, "sched_getaffinity", lambda _p: set(range(99)),
                        raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 64, raising=False)
    assert parallel.cpu_cores() == 6


def test_cores_falls_to_sched_getaffinity_on_linux(monkeypatch):
    # Python 3.12 has no process_cpu_count; the Linux truth is the affinity
    monkeypatch.delattr(os, "process_cpu_count", raising=False)
    monkeypatch.setattr(os, "sched_getaffinity", lambda _p: set(range(8)),
                        raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 64, raising=False)
    assert parallel.cpu_cores() == 8


def test_cores_falls_to_cpu_count_on_windows(monkeypatch):
    # Windows has neither process_cpu_count (3.12) nor sched_getaffinity:
    # the chain must survive with no platform branch
    monkeypatch.delattr(os, "process_cpu_count", raising=False)
    monkeypatch.delattr(os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 12, raising=False)
    assert parallel.cpu_cores() == 12


def test_cores_never_returns_zero(monkeypatch):
    monkeypatch.delattr(os, "process_cpu_count", raising=False)
    monkeypatch.delattr(os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: None, raising=False)
    assert parallel.cpu_cores() == 1


def test_cores_survives_a_failing_candidate(monkeypatch):
    def boom():
        raise OSError("no affinity here")
    monkeypatch.setattr(os, "process_cpu_count", boom, raising=False)
    monkeypatch.delattr(os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 5, raising=False)
    assert parallel.cpu_cores() == 5


# ------------------------------------------------------- the worker count

class _Cfg:
    def __init__(self, threads=0):
        self._d = {"astrometry_threads": threads}

    def get(self, key, default=None):
        return self._d.get(key, default)


def _fix_cores(monkeypatch, cores):
    monkeypatch.setattr(parallel, "cpu_cores", lambda: cores)


def test_worker_count_leaves_one_core_to_the_rest(monkeypatch):
    _fix_cores(monkeypatch, 4)
    assert parallel.worker_count() == 3


def test_worker_count_of_a_single_core_is_one(monkeypatch):
    _fix_cores(monkeypatch, 1)
    assert parallel.worker_count() == 1


def test_worker_count_is_capped(monkeypatch):
    _fix_cores(monkeypatch, 128)
    assert parallel.worker_count(cap=8) == 8


def test_worker_count_is_capped_by_memory(monkeypatch):
    # 32 cores but a task that does not fit more than twice: memory wins
    _fix_cores(monkeypatch, 32)
    assert parallel.worker_count(per_task_bytes=100, budget_bytes=250) == 2


def test_the_settings_override_wins(monkeypatch):
    _fix_cores(monkeypatch, 16)
    assert parallel.worker_count(cfg=_Cfg(3)) == 3
    # ... but never more than the machine has
    assert parallel.worker_count(cfg=_Cfg(99)) == 16


def test_available_memory_is_a_number_or_none():
    # Linux answers with an int; Windows with an int; and if neither can,
    # the answer is None and the caller keeps its own budget
    value = parallel.available_memory_bytes()
    assert value is None or (isinstance(value, int) and value > 0)


# ------------------------------------------------------------- the map

def test_map_parallel_keeps_the_order():
    out = parallel.map_parallel(lambda x: x * x, range(20), workers=4)
    assert out == [x * x for x in range(20)]


def test_map_parallel_serial_path():
    assert parallel.map_parallel(lambda x: x + 1, [1, 2], workers=1) == [2, 3]
    assert parallel.map_parallel(lambda x: x + 1, [1], workers=8) == [2]


def test_map_parallel_stops_submitting_when_cancelled():
    seen = []

    def fn(x):
        seen.append(x)
        return x

    # the first call says "cancel": nothing should be submitted at all
    out = parallel.map_parallel(fn, range(50), workers=4, cancel=lambda: True)
    assert seen == []
    assert out == [None] * 50
