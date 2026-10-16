############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: v23 migration (the folder rename)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""v23 acceptance (ADR-062 rev): the project's housekeeping folders lost
their Spanish names (procesados/ -> prcd/, descartados/ -> dscrd/). The
rename travels with the schema because the registry stores FULL paths: a
database written by the previous version opens with the folder renamed AND
every stored path rewritten, so an archived frame is still restorable.
Idempotent, and a project with nothing archived is left alone. No network.
"""

import json
import os

from nightscribe.core.db import Database
from nightscribe.core import astrometry_store as store
from nightscribe.core import followup as fu
from nightscribe.core import free_space, project as proj_mod


def _archived_project(tmp_path, name="legacy.db"):
    # @return: (db_path, storage, frame_path) with one frame already moved
    #          to the NEW folder, so a test can fake the old layout
    path = str(tmp_path / name)
    db = Database(path)
    p = proj_mod.create(db, "neo", "2025 UR")
    session = fu.create_session(db, p["id"], obs_date="2025-10-18")
    run = store.create_run(db, p["id"], session, cfg={}, object_name="2025 UR",
                           status="complete")
    frame = tmp_path / "frame000.fits"
    frame.write_bytes(b"x" * 2048)
    proj_mod.add_file(db, p["id"], str(frame), "fits", session_id=session)
    store.add_frames(db, run, [{"path": str(frame), "size": 2048,
                                "filter": "Clear", "exptime_s": 3.0,
                                "date_obs": "2025-10-18T21:40:07"}])
    storage = tmp_path / "project"
    free_space.move_to_processed(db, run, storage)
    return path, db, storage, frame


def _fake_old_layout(db, storage):
    # Puts the folder and the stored paths back the way the old app left
    # them: procesados/ on disk, "procesados" in the registry.
    legacy = storage / "procesados"
    os.rename(str(storage / free_space.PROCESSED_DIR), str(legacy))
    rows = db.execute("SELECT id, path, meta FROM project_files").fetchall()
    for fid, old, meta in rows:
        moved = str(legacy / "2025-10-18" / os.path.basename(old))
        db.execute("UPDATE project_files SET path=?, meta=? WHERE id=?",
                   (moved, json.dumps({"archived": True, "moved_from": old}),
                    fid))
    db.execute("UPDATE astrometry_frames SET moved_to=replace(moved_to, ?, ?)",
               (os.sep + free_space.PROCESSED_DIR + os.sep,
                os.sep + "procesados" + os.sep))
    db.execute("PRAGMA user_version = 22")
    db.commit()


def test_v23_renames_the_folder_and_the_paths(tmp_path):
    path, db, storage, _frame = _archived_project(tmp_path)
    _fake_old_layout(db, storage)
    db.close()

    db = Database(path)              # reopening runs the migration
    assert db.execute("PRAGMA user_version").fetchone()[0] == 24
    # the folder is renamed on disk
    assert (storage / free_space.PROCESSED_DIR / "2025-10-18").is_dir()
    assert not (storage / "procesados").exists()
    # and every stored path follows it: the frame can be brought back
    row = db.execute("SELECT path, meta FROM project_files").fetchone()
    assert "procesados" not in row[0]
    assert free_space.PROCESSED_DIR in row[0]
    assert os.path.exists(row[0])
    moved_to = db.execute("SELECT moved_to FROM astrometry_frames").fetchone()
    assert "procesados" not in moved_to[0]
    db.close()


def test_v23_migration_is_idempotent(tmp_path):
    path, db, storage, _frame = _archived_project(tmp_path, "twice.db")
    db.close()
    db = Database(path)              # nothing legacy: no-op
    assert db.execute("PRAGMA user_version").fetchone()[0] == 24
    assert (storage / free_space.PROCESSED_DIR / "2025-10-18").is_dir()
    db.close()
    db = Database(path)              # and again
    assert db.execute("PRAGMA user_version").fetchone()[0] == 24
    db.close()


def test_v23_leaves_a_clean_project_alone(tmp_path):
    # A project with no archived frames has no folder to rename and no path
    # to rewrite: the migration must not invent one.
    path = str(tmp_path / "clean.db")
    db = Database(path)
    p = proj_mod.create(db, "sn", "SN 2026x")
    fu.create_session(db, p["id"], obs_date="2026-01-02")
    db.execute("PRAGMA user_version = 22")
    db.commit()
    db.close()
    db = Database(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 24
    assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
    db.close()
