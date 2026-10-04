############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: freeing space (ADR-062, phase 9)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase 9 acceptance: only a successful run's frames are offered, the
move goes to procesados/ and the registry follows it, restoring brings
them back, a missing frame is skipped, and the calibrated copies are
deleted outright (they are derived). Never a hard delete of an original."""

import json

from nightscribe.core import free_space, project as proj_mod
from nightscribe.core import followup as fu
from nightscribe.core import astrometry_store as store


def _setup(tmp_db, tmp_path, n=3):
    p = proj_mod.create(tmp_db, "neo", "2025 UR")
    session_id = fu.create_session(tmp_db, p["id"], obs_date="2025-10-18")
    run = store.create_run(tmp_db, p["id"], session_id, cfg={},
                           object_name="2025 UR", status="complete")
    frames = []
    for i in range(n):
        f = tmp_path / f"frame{i:03d}.fits"
        f.write_bytes(b"x" * (1024 * (i + 1)))
        proj_mod.add_file(tmp_db, p["id"], str(f), "fits",
                          session_id=session_id, meta={"filter": "Clear"})
        frames.append({"path": str(f), "size": f.stat().st_size,
                       "filter": "Clear", "exptime_s": 3.0,
                       "date_obs": "2025-10-18T21:40:07"})
    store.add_frames(tmp_db, run, frames)
    return p, session_id, run, [f["path"] for f in frames]


def test_freeable_counts_only_the_run_frames(tmp_db, tmp_path):
    _p, _s, run, paths = _setup(tmp_db, tmp_path)
    info = free_space.freeable(tmp_db, run)
    assert info["n"] == 3
    assert info["bytes"] == sum(1024 * (i + 1) for i in range(3))
    assert set(info["files"]) == set(paths)


def test_move_to_processed_moves_and_follows(tmp_db, tmp_path):
    p, _s, run, paths = _setup(tmp_db, tmp_path)
    dest = tmp_path / "project"
    report = free_space.move_to_processed(tmp_db, run, dest)
    assert report.moved == 3 and not report.errors
    for path in paths:
        assert not (tmp_path / path.split("/")[-1]).exists()
        moved = dest / "procesados" / "2025-10-18" / path.split("/")[-1]
        assert moved.exists()
        row = tmp_db.execute("SELECT path, meta FROM project_files"
                             " WHERE path=?", (str(moved),)).fetchone()
        assert row is not None
        assert json.loads(row[1])["archived"] is True
    # the manifest remembers where each frame went
    rows = tmp_db.execute("SELECT archived, moved_to FROM astrometry_frames"
                          " WHERE run_id=?", (run,)).fetchall()
    assert all(r[0] == 1 and r[1] for r in rows)
    # and nothing is left to free
    assert free_space.freeable(tmp_db, run)["n"] == 0


def test_restore_brings_the_frames_back(tmp_db, tmp_path):
    _p, _s, run, paths = _setup(tmp_db, tmp_path)
    dest = tmp_path / "project"
    free_space.move_to_processed(tmp_db, run, dest)
    report = free_space.restore(tmp_db, run)
    assert report.moved == 3 and not report.errors
    for path in paths:
        assert (tmp_path / path.split("/")[-1]).exists()
    assert free_space.freeable(tmp_db, run)["n"] == 3


def test_a_missing_frame_is_skipped_not_fatal(tmp_db, tmp_path):
    _p, _s, run, paths = _setup(tmp_db, tmp_path)
    import os
    os.remove(paths[1])
    report = free_space.move_to_processed(tmp_db, run, tmp_path / "project")
    assert report.moved == 2 and paths[1] in report.skipped


def test_only_the_run_frames_are_touched(tmp_db, tmp_path):
    _p, _s, run, _paths = _setup(tmp_db, tmp_path)
    other = tmp_path / "other.fits"
    other.write_bytes(b"y" * 50)
    free_space.move_to_processed(tmp_db, run, tmp_path / "project")
    assert other.exists()


def test_delete_calibrated_removes_derived_files(tmp_path):
    a = tmp_path / "cal_a.fits"
    b = tmp_path / "cal_b.fits"
    a.write_bytes(b"z" * 100)
    b.write_bytes(b"z" * 200)
    report = free_space.delete_calibrated([str(a), str(b)])
    assert report.moved == 2 and report.bytes == 300
    assert not a.exists() and not b.exists()


def test_delete_calibrated_reports_a_missing_file(tmp_path):
    report = free_space.delete_calibrated([str(tmp_path / "nope.fits")])
    assert report.moved == 0 and report.errors
