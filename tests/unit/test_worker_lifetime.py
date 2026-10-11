############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: QThread lifetime guard (workers.hold)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""A QThread destroyed while its thread still runs is FATAL in Qt 6
("QThread: Destroyed while thread is still running"), and the app aborts with
a core dump. Every worker here shadows QThread.finished with its own signal,
emitted BEFORE the thread stops, so the guard keeps a strong reference until
the thread has REALLY finished (QThread.isFinished())."""

from nightscribe.gui import workers


class _Fake:
    # The only surface hold()/prune use.
    def __init__(self, finished):
        self._finished = finished

    def isFinished(self):
        return self._finished

    def isRunning(self):
        return not self._finished


def _clean():
    workers._LIVE_WORKERS.clear()


def test_hold_keeps_a_running_worker_alive():
    _clean()
    running = _Fake(finished=False)
    assert workers.hold(running) is running      # returns it for inline use
    assert running in workers._LIVE_WORKERS
    _clean()


def test_prune_drops_only_the_finished_workers():
    # A worker is let go only after its thread has stopped: dropping it while
    # it runs is exactly what aborts the app.
    _clean()
    running = _Fake(finished=False)
    done = _Fake(finished=True)
    workers.hold(running)
    workers.hold(done)          # appends, then prunes the finished one
    assert running in workers._LIVE_WORKERS
    assert done not in workers._LIVE_WORKERS
    _clean()


def test_running_workers_lists_only_those_still_running():
    _clean()
    running = _Fake(finished=False)
    done = _Fake(finished=True)
    workers.hold(running)
    workers.hold(done)
    assert workers.running_workers() == [running]
    _clean()
