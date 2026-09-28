############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: live series driver (series plan, phase 10)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase-10 acceptance: the folder watch never reads a half-written FITS,
accumulates frames, commits a batch (N frames or T seconds) through the
shared engine grouped into the batch, and a cancelled run leaves nothing
hanging. Offline: a synthetic folder and an injected measure/clock."""

from nightscribe.core import live
from nightscribe.core import series_measure as sm


class _FakeResult:
    def __init__(self, group_n):
        self.group_n = group_n
        self.points = []


def _cfg():
    return sm.SeriesConfig(target_xy=(10.0, 10.0))


class _Measure:
    def __init__(self):
        self.calls = []

    def __call__(self, paths, cfg):
        self.calls.append((list(paths), cfg.group_n))
        return _FakeResult(cfg.group_n)


def test_half_written_file_is_not_read_until_stable(tmp_path):
    measure = _Measure()
    d = live.LiveDriver(tmp_path, _cfg(), measure=measure, batch_n=1)
    p = tmp_path / "a.fits"
    p.write_text("x")
    d.tick()                       # size recorded, not stable yet
    assert measure.calls == []
    p.write_text("xy")             # it grew: still not stable
    d.tick()
    assert measure.calls == []
    d.tick()                       # size unchanged since last scan: stable
    assert len(measure.calls) == 1
    assert measure.calls[0][0] == [str(p)]


def test_batch_commits_when_full(tmp_path):
    measure = _Measure()
    committed = []
    d = live.LiveDriver(tmp_path, _cfg(), measure=measure, batch_n=5,
                        on_points=committed.append)
    for i in range(5):
        (tmp_path / f"f{i}.fits").write_text("data")
    d.tick()                       # record sizes
    d.tick()                       # all stable -> batch of 5 -> commit
    assert len(measure.calls) == 1
    assert measure.calls[0][1] == 5        # one group of 5 (D19)
    assert len(committed) == 1


def test_batch_commits_on_time(tmp_path):
    t = [0.0]
    measure = _Measure()
    d = live.LiveDriver(tmp_path, _cfg(), measure=measure, batch_n=100,
                        batch_s=10.0, clock=lambda: t[0])
    (tmp_path / "a.fits").write_text("data")
    d.tick()                       # record
    d.tick()                       # stable, pending 1, timer starts
    assert measure.calls == []
    t[0] = 11.0
    d.tick()                       # T seconds elapsed -> commit
    assert len(measure.calls) == 1
    assert measure.calls[0][1] == 1


class _Boom:
    # A measure callable that always raises: the batch is lost (P2 #19).
    def __init__(self, message="engine down"):
        self.message = message
        self.calls = []

    def __call__(self, paths, cfg):
        self.calls.append(list(paths))
        raise RuntimeError(self.message)


def test_failed_batch_is_reported_not_swallowed(tmp_path):
    # P2 #19: a batch whose measure raised used to vanish in silence (the
    # frames were already marked processed and nothing was said). It must
    # be recorded on the driver, handed to on_error, and the watch goes on.
    lost = []
    measure = _Boom()
    d = live.LiveDriver(tmp_path, _cfg(), measure=measure, batch_n=2,
                        on_error=lambda msg, n: lost.append((msg, n)))
    for i in range(2):
        (tmp_path / f"b{i}.fits").write_text("data")
    d.tick()                       # record sizes
    d.tick()                       # stable -> commit -> the engine raises
    assert len(measure.calls) == 1
    assert lost == [("engine down", 2)]      # the UI can say it now
    assert d.last_error == "engine down"
    assert d.failed_frames == 2
    # the watch is not broken by it: the next frames are still tried
    for i in (2, 3):
        (tmp_path / f"b{i}.fits").write_text("data")
    d.tick()
    d.tick()
    assert len(measure.calls) == 2
    assert d.failed_frames == 4
    assert lost[-1] == ("engine down", 2)


def test_progress_reports_stage_keys_not_sentences(tmp_path):
    # P2 #19: core has no tr(), so the driver reports stage keys and the
    # GUI owns the wording of what the observer reads.
    seen = []
    measure = _Measure()
    d = live.LiveDriver(tmp_path, _cfg(), measure=measure, batch_n=1,
                        progress=lambda key, n: seen.append((key, n)))
    (tmp_path / "a.fits").write_text("data")
    d.tick()                       # record
    d.tick()                       # stable -> one frame added, one commit
    assert seen == [("added", 1)]


def test_cancelled_run_leaves_nothing_hanging(tmp_path):
    measure = _Measure()
    state = {"n": 0}

    def cancel():
        state["n"] += 1
        return state["n"] > 1      # run one tick, then stop

    d = live.LiveDriver(tmp_path, _cfg(), measure=measure, poll_s=0.0,
                        cancel=cancel)
    assert d.run() == "cancelled"
    assert d.status == "cancelled"
