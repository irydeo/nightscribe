############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: solving a whole visit (ADR-051)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The visit's batch solve, frame by frame, without ASTAP and without
network: what it skips, what it learns from the first frame that works,
what it counts and how it stops.

The numbers that justify it are in the real case: 35 frames of the V0526
Per visit, none of them carrying a position or a scale of its own, cost
35 x 66 s solved one by one by hand (the app's own path: a sky sweep) and
35 x 0.13 s with the project's field.
"""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                   # noqa: E402
from PySide6.QtTest import QSignalSpy            # noqa: E402
from PySide6.QtWidgets import QApplication      # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


CARDS = {"CRVAL1": 49.9937, "CRVAL2": 49.7802, "CRPIX1": 832.0,
         "CRPIX2": 626.5, "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
         "CD1_1": -0.000427, "CD1_2": 4.9e-05, "CD2_1": -4.9e-05,
         "CD2_2": -0.000427}


def _paths(tmp_path, n):
    return [str(tmp_path / f"f{i:02d}.fits") for i in range(n)]


def _patch(monkeypatch, results=None, solved=None, persist=None, calls=None):
    # The batch talks to the core through these three doors; none of them
    # needs a solver or a file to be tested.
    from nightscribe.core import solve as solve_mod
    from nightscribe.core import wcs_store
    results = results or {}
    solved = solved or {}
    calls = calls if calls is not None else []

    def fake_solve(path, pointing=None, cancel=None):
        calls.append((Path(path).name, pointing))
        out = results.get(Path(path).name)
        return dict(out) if out else None

    monkeypatch.setattr(solve_mod, "solve", fake_solve)
    monkeypatch.setattr(solve_mod, "solved_cards",
                        lambda path: solved.get(Path(path).name))
    monkeypatch.setattr(wcs_store, "persist_solution",
                        persist or (lambda path, cards: (True, "")))
    return calls


def test_the_batch_skips_the_frames_that_are_already_solved(qapp, tmp_path,
                                                            monkeypatch):
    # A visit is solved once: the frames that carry a WCS (solved by us, by
    # another program or by an earlier batch) are counted, not solved again.
    from nightscribe.gui.workers import VisitSolveWorker
    paths = _paths(tmp_path, 3)
    calls = _patch(monkeypatch,
                   results={"f01.fits": CARDS},
                   solved={"f00.fits": CARDS, "f02.fits": CARDS})
    w = VisitSolveWorker(paths, pointing=(49.99, 49.86))
    spy = QSignalSpy(w.finished)
    w.run()
    out = spy.at(0)[0]
    assert out["skipped"] == 2 and out["solved"] == 1
    assert [c[0] for c in calls] == ["f01.fits"]     # only the unsolved one


def test_the_pilot_learns_the_field_from_the_first_frame_that_works(
        qapp, tmp_path, monkeypatch):
    # No coordinates anywhere: the first frame is solved blind and the rest
    # follow ITS field, so the sky is swept once instead of 35 times.
    from nightscribe.gui.workers import VisitSolveWorker
    paths = _paths(tmp_path, 3)
    calls = _patch(monkeypatch, results={f"f{i:02d}.fits": CARDS
                                         for i in range(3)})
    w = VisitSolveWorker(paths, pointing=None)
    spy = QSignalSpy(w.finished)
    w.run()
    assert spy.at(0)[0]["solved"] == 3
    assert [c[1] for c in calls] == [None, (49.9937, 49.7802),
                                     (49.9937, 49.7802)]


def test_a_frame_that_fails_does_not_stop_the_batch(qapp, tmp_path,
                                                    monkeypatch):
    # One bad frame is not the visit: the batch counts it, says which one,
    # and carries on with the rest.
    from nightscribe.gui.workers import VisitSolveWorker
    paths = _paths(tmp_path, 3)
    _patch(monkeypatch, results={"f00.fits": CARDS, "f02.fits": CARDS})
    w = VisitSolveWorker(paths, pointing=(49.99, 49.86))
    spy = QSignalSpy(w.finished)
    w.run()
    out = spy.at(0)[0]
    assert out["solved"] == 2 and out["failed"] == 1
    assert out["failures"] == ["f01.fits"]
    assert out["cancelled"] is False


def test_cancel_stops_between_frames(qapp, tmp_path, monkeypatch):
    from nightscribe.gui.workers import VisitSolveWorker
    from nightscribe.core import solve as solve_mod
    paths = _paths(tmp_path, 4)
    calls = _patch(monkeypatch, results={f"f{i:02d}.fits": CARDS
                                         for i in range(4)})
    w = VisitSolveWorker(paths, pointing=(49.99, 49.86))
    spy = QSignalSpy(w.finished)
    real = solve_mod.solve

    def solve_then_cancel(path, pointing=None, cancel=None):
        out = real(path, pointing=pointing, cancel=cancel)
        w.cancel()                    # the observer pressed Cancel
        return out

    monkeypatch.setattr(solve_mod, "solve", solve_then_cancel)
    w.run()
    out = spy.at(0)[0]
    assert out["cancelled"] is True
    assert out["solved"] == 1 and len(calls) == 1


def test_the_open_frames_cards_come_back_for_the_editor(qapp, tmp_path,
                                                        monkeypatch):
    # The batch writes the solutions into the files; the frame open in the
    # editor needs its cards in memory too, or the tab would keep working
    # blind until the plate is reloaded.
    from nightscribe.gui.workers import VisitSolveWorker
    paths = _paths(tmp_path, 3)
    _patch(monkeypatch, results={f"f{i:02d}.fits": CARDS
                                 for i in range(3)})
    w = VisitSolveWorker(paths, pointing=(49.99, 49.86),
                         open_path=paths[1])
    spy = QSignalSpy(w.finished)
    w.run()
    assert spy.at(0)[0]["cards"] == CARDS


def test_a_solution_that_cannot_be_written_is_said(qapp, tmp_path,
                                                   monkeypatch):
    # A read-only frame solves and cannot be saved: the observer must hear
    # it, or the visit would look solved and be forgotten tomorrow.
    from nightscribe.gui.workers import VisitSolveWorker
    paths = _paths(tmp_path, 2)
    _patch(monkeypatch, results={f"f{i:02d}.fits": CARDS for i in range(2)},
           persist=lambda path, cards: (False, "read-only"))
    w = VisitSolveWorker(paths, pointing=(49.99, 49.86))
    spy = QSignalSpy(w.finished)
    w.run()
    out = spy.at(0)[0]
    assert out["solved"] == 2 and out["not_written"] == 2
