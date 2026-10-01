############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Functional test: the ASTAP pointing (ADR-051)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The real frame, the real ASTAP, the real difference (ADR-051).

The bug this pins: the app never told ASTAP where the plate looks, so on a
foreign frame with no position and no scale of its own (the V0526 Per
visit: FOCALLEN=0, no RA/DEC, INSTRUME SXV-H18) ASTAP swept the sky: 55.8 s
to find it, and 66 s through the app's own two attempts. With the project's
field and a search radius the same frame answers in 0.13 s.

It needs ASTAP installed and the real frames: set NIGHTSCRIBE_V0526_PER to
the folder holding v526per-*Rcal.fit; it skips otherwise. Nothing is
written into the observer's frames: `astap.solve` only leaves its own .wcs
sidecar in the app folder, and the solution is never persisted here.
"""

import os
import shutil
import time
from pathlib import Path

import pytest

from nightscribe.core.sources import astap

SERIES_DIR = os.environ.get("NIGHTSCRIBE_V0526_PER")
# the project's own coordinates (the app's context for V0526 Per)
FIELD = (49.99038, 49.86875)
# the solve is 0.13 s measured; 5 s is a generous ceiling that still fails
# loudly if the pointing stops reaching ASTAP (the blind path is ~60 s)
BUDGET_S = 5.0


class _NoCache:
    # The app caches by content hash, and this test measures ASTAP, not the
    # cache: a previous run would otherwise answer in microseconds.

    def cache_get(self, key):
        return None

    def cache_put(self, key, source, body, content_type=None):
        pass


@pytest.fixture()
def frame(tmp_path):
    if not SERIES_DIR:
        pytest.skip("set NIGHTSCRIBE_V0526_PER to the series folder")
    src = sorted(Path(SERIES_DIR).glob("v526per-*Rcal.fit"))
    if not src:
        pytest.skip(f"no frames in {SERIES_DIR}")
    if astap.resolve_binary() is None:
        pytest.skip("ASTAP is not installed")
    # a copy: ASTAP's own outputs never land next to the observer's images
    # (they go to the app folder through -o) and nothing writes to the
    # original either way
    out = tmp_path / src[0].name
    shutil.copyfile(src[0], out)
    return out


def test_the_pointing_takes_the_real_frame_from_a_minute_to_a_moment(
        frame, monkeypatch):
    monkeypatch.setattr(astap, "db", _NoCache())
    t0 = time.monotonic()
    cards = astap.solve(frame, pointing=FIELD)
    took = time.monotonic() - t0
    assert cards, "the pointed solve must answer"
    assert took < BUDGET_S, f"the pointed solve took {took:.1f} s"
    # and it is the right field: the solution sits where the project says
    # (the plate centre is a few arcminutes off the target, never degrees)
    assert abs(cards["CRVAL1"] - FIELD[0]) < 0.5
    assert abs(cards["CRVAL2"] - FIELD[1]) < 0.5
    # a real plate scale came back (the frame declares none of its own)
    scale = ((cards["CD1_1"] ** 2 + cards["CD2_1"] ** 2) ** 0.5) * 3600.0
    assert 1.0 < scale < 2.5, scale


def test_a_wrong_pointing_gives_up_at_once_and_the_blind_path_solves(
        frame, monkeypatch):
    # The safety property the whole design rests on: a bad hint is CHEAP
    # (ASTAP searches a 5-degree box and stops in ~0.3 s) and the blind
    # attempts behind it still deliver.
    monkeypatch.setattr(astap, "db", _NoCache())
    wrong = (150.0, -20.0)
    t0 = time.monotonic()
    cards = astap.solve(frame, pointing=wrong)
    took = time.monotonic() - t0
    assert cards, "the blind path must still solve it"
    assert took < 180.0                      # the dispatcher's own ceiling
    assert abs(cards["CRVAL1"] - FIELD[0]) < 0.5   # and it is the real field


def test_the_batch_solves_a_visit_of_real_frames_in_seconds(tmp_path,
                                                            monkeypatch):
    # The visit's batch (ADR-051) on the real frames: one field, five
    # plates, no WCS of their own. Blind this is minutes; pointed it is
    # seconds. The copies get the solution written into them (the real
    # frames are never touched) and the summary counts what happened.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if not SERIES_DIR:
        pytest.skip("set NIGHTSCRIBE_V0526_PER to the series folder")
    if astap.resolve_binary() is None:
        pytest.skip("ASTAP is not installed")
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui.workers import VisitSolveWorker
    app = QApplication.instance() or QApplication([])
    frames = sorted(Path(SERIES_DIR).glob("v526per-*Rcal.fit"))[:5]
    if len(frames) < 5:
        pytest.skip(f"not enough frames in {SERIES_DIR}")
    copies = []
    for src in frames:
        dst = tmp_path / src.name
        shutil.copyfile(src, dst)
        copies.append(str(dst))
    monkeypatch.setattr(astap, "db", _NoCache())
    out = {}
    worker = VisitSolveWorker(copies, pointing=FIELD)
    worker.finished.connect(lambda summary: out.update(summary))
    t0 = time.monotonic()
    worker.run()
    took = time.monotonic() - t0
    assert app is not None
    # the visit arrives with some frames already solved (the observer's own
    # first frame, in this case): those are SKIPPED, the rest are solved,
    # and every one of them ends up solved
    assert out.get("solved", 0) + out.get("skipped", 0) == 5, out
    assert out.get("solved", 0) >= 4, out
    assert not out.get("failed"), out.get("failures")
    assert took < 20.0, f"five pointed frames took {took:.1f} s"
    from nightscribe.core import solve as solve_mod
    assert all(solve_mod.solved_cards(c) is not None for c in copies)
    # and the originals were never touched (the copies are the ones solved)
    before = sum(1 for f in frames if solve_mod.solved_cards(f) is not None)
    assert before == 1, before
