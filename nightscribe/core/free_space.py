############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Freeing space after a run (ADR-062, phase 9)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Giving the observer their disk back, without losing the data.

A track & stack night is hundreds of FITS of 8 MB. Once the stack, the
sequence and the report are saved, the originals are no longer needed to
keep working, but deleting them is destructive: they are the observer's
data, and NightScribe only knows their PATH (project.add_file stores a
path, it never copies the frame). So this module MOVES them, it does not
delete them: to `prcd/` inside the project, where they can be brought back
with one call.

Three rules make it safe:

- **Only the frames of a successful run**, taken from the run's own
  manifest (astrometry_frames), never "everything in the folder".
- **Nothing moves without a confirmation**: the caller asks `freeable`
  first and shows the count and the bytes.
- **The registry stays truthful**: the project_files rows follow the move
  (path + meta["archived"]) so the visit's list shows them as archived
  instead of pointing at a file that is not there.

A memory-mapped frame cannot be renamed (on Windows, not even opened for
rename), so the caller must have closed the readers first; the manifest
move would fail with a clear OS error otherwise.
"""

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# The two housekeeping folders inside a project. Their names are short and
# language-neutral on purpose (ADR-062 rev, 2026-10-16): a folder name
# travels in a zip, sits next to a colleague's files and shows up in a
# path, so "procesados"/"descartados" became "prcd"/"dscrd".
PROCESSED_DIR = "prcd"      # frames of a successful run, brought back at will
DISCARDED_DIR = "dscrd"     # frames the observer took out of the night

# The old Spanish names, with what they are called now. The rename is a data
# migration (migrate_legacy_dirs): the registry stores the full path of every
# moved frame, so without it an archived frame could not be brought back.
_LEGACY_DIRS = (("procesados", PROCESSED_DIR),
                ("descartados", DISCARDED_DIR))


@dataclass
class MoveReport:
    moved: int = 0
    bytes: int = 0
    skipped: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    destination: str | None = None
    renamed: list = field(default_factory=list)   # (wanted, actual) on restore


def freeable(db, run_id):
    # @args: db - Database, run_id - the execution
    # @return: dict {n, bytes, files} for the frames not yet archived
    # The count and the size are what the confirmation dialog shows; the
    # bytes are read from the manifest, not recomputed from disk, so a
    # frame that already moved does not inflate the figure.
    rows = db.execute(
        "SELECT path, size FROM astrometry_frames"
        " WHERE run_id=? AND (archived IS NULL OR archived=0)",
        (run_id,)).fetchall()
    files = [r[0] for r in rows]
    total = sum(int(r[1] or 0) for r in rows)
    return {"n": len(files), "bytes": total, "files": files}


def _project_of(db, run_id):
    # @args: db, run_id
    # @return: the project dict of the run, or None
    from . import project as project_mod
    row = db.execute("SELECT project_id FROM astrometry_runs WHERE id=?",
                     (run_id,)).fetchone()
    if not row or row[0] is None:
        return None
    return project_mod.get(db, row[0])


def _follow_path(db, old_path, new_path, flag="archived"):
    # @args: db - Database, old_path/new_path - the frame, flag - the meta
    #        key that says WHY it moved ("archived" after a successful run,
    #        "discarded" when the observer took it out by hand)
    # @return: True when a project_files row followed the move
    # The visit's resource list must not end up pointing at a file that is
    # no longer there: the row follows the frame and is marked.
    import json
    rows = db.execute("SELECT id, meta FROM project_files WHERE path=?",
                      (old_path,)).fetchall()
    for row in rows:
        try:
            meta = json.loads(row[1]) if row[1] else {}
        except (TypeError, ValueError):
            meta = {}
        meta[flag] = True
        meta["moved_from"] = old_path
        db.execute("UPDATE project_files SET path=?, meta=? WHERE id=?",
                   (new_path, json.dumps(meta), row[0]))
    if rows:
        db.commit()
    return bool(rows)


def move_to_processed(db, run_id, storage_dir, progress=None, cancel=None):
    # @args: db - Database, run_id - the execution, storage_dir - the
    #        project's storage dir (project.storage_dir), progress -
    #        callable(done, total, label), cancel - callable() -> True
    # @return: MoveReport
    # The frames go to `prcd/<fecha de la visita>/` inside the
    # project. The move is a rename when it can be (same filesystem) and a
    # copy-then-remove otherwise; in both cases the destination is written
    # through a temporary name and renamed, so an interrupted move never
    # leaves a half file in place.
    project = _project_of(db, run_id)
    if project is None:
        return MoveReport(errors=["the run has no project"])
    rows = db.execute(
        "SELECT id, path, size, date_obs FROM astrometry_frames"
        " WHERE run_id=? AND (archived IS NULL OR archived=0)",
        (run_id,)).fetchall()
    if not rows:
        return MoveReport()
    date = _visit_date(db, run_id, rows)
    dest_dir = Path(storage_dir) / PROCESSED_DIR / date
    dest_dir.mkdir(parents=True, exist_ok=True)
    report = MoveReport(destination=str(dest_dir))
    total_bytes = sum(int(r[2] or 0) for r in rows)
    free = shutil.disk_usage(str(dest_dir)).free
    if free < total_bytes:
        report.errors.append(
            f"not enough space at the destination: {total_bytes} bytes "
            f"needed, {free} free")
        return report
    total = len(rows)
    for index, (frame_id, path, size, _date) in enumerate(rows, 1):
        if cancel is not None and cancel():
            break
        src = Path(path)
        if not src.exists():
            report.skipped.append(path)
            _mark_archived(db, frame_id, None)
            continue
        dest = _unique(dest_dir / src.name)
        try:
            _move(src, dest)
        except OSError as err:
            report.errors.append(f"{src.name}: {err}")
            continue
        _follow_path(db, path, str(dest))
        _mark_archived(db, frame_id, str(dest))
        report.moved += 1
        report.bytes += int(size or 0)
        if progress is not None:
            progress(index, total, src.name)
    db.commit()
    return report


def _move(src, dest):
    # @args: src, dest - Paths
    # @return: None
    # os.replace is atomic but only within one filesystem; across devices
    # (the observer's capture disk vs the project's) it raises EXDEV and
    # the copy+remove of shutil.move is used instead.
    tmp = dest.with_name(dest.name + ".part")
    try:
        os.replace(str(src), str(dest))
        return
    except OSError:
        pass
    shutil.copy2(str(src), str(tmp))
    os.replace(str(tmp), str(dest))
    os.remove(str(src))


def _unique(path):
    # @args: path - the desired destination
    # @return: path, or path with a numeric suffix when it already exists
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(1, 1000):
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{stem}_{os.getpid()}{suffix}")


def _mark_archived(db, frame_id, moved_to):
    # @args: db, frame_id, moved_to - the new path (None if it was gone)
    db.execute("UPDATE astrometry_frames SET archived=1, moved_to=?"
               " WHERE id=?", (moved_to, frame_id))


def _visit_date(db, run_id, rows):
    # @args: db, run_id, rows - the manifest rows
    # @return: a folder name for the visit (its date, or the run id)
    from . import followup as fu
    row = db.execute("SELECT session_id FROM astrometry_runs WHERE id=?",
                     (run_id,)).fetchone()
    if row and row[0] is not None:
        session = fu.get_session(db, row[0])
        if session and session.get("obs_date"):
            return str(session["obs_date"])
    for _fid, _path, _size, date in rows:
        if date:
            return str(date)[:10]
    return f"run{run_id}"


def restore(db, run_id, progress=None, cancel=None):
    # @args: db, run_id, progress, cancel
    # @return: MoveReport
    # The manifest knows where each frame came from, so bringing them back
    # is the same move in reverse. This is what makes "free space" safe:
    # it is not a delete, it is a move.
    rows = db.execute(
        "SELECT id, path, moved_to FROM astrometry_frames"
        " WHERE run_id=? AND archived=1 AND moved_to IS NOT NULL",
        (run_id,)).fetchall()
    report = MoveReport()
    total = len(rows)
    for index, (frame_id, original, moved_to) in enumerate(rows, 1):
        if cancel is not None and cancel():
            break
        src = Path(moved_to)
        if not src.exists():
            report.skipped.append(moved_to)
            continue
        wanted = Path(original)
        wanted.parent.mkdir(parents=True, exist_ok=True)
        # The original name may be taken again (the observer recaptured into
        # the same folder): os.replace would OVERWRITE the new frame and it
        # would be gone in silence. The restore lands on a free name instead,
        # and the registry follows so the visit stays truthful.
        dest = _unique(wanted)
        try:
            _move(src, dest)
        except OSError as err:
            report.errors.append(f"{src.name}: {err}")
            continue
        if dest != wanted:
            report.renamed.append((str(wanted), str(dest)))
        _follow_path(db, str(src), str(dest))
        # The manifest's `path` is the frame's CURRENT home: keep it honest
        # when the name changed, or the run would point at a file that is no
        # longer there.
        db.execute("UPDATE astrometry_frames SET archived=0, moved_to=NULL,"
                   " path=? WHERE id=?", (str(dest), frame_id))
        report.moved += 1
        if progress is not None:
            progress(index, total, src.name)
    db.commit()
    return report


def discard_files(db, paths, storage_dir, progress=None, cancel=None):
    # @args: db - Database, paths - the frames to move aside, storage_dir -
    #        the project's storage dir (project.storage_dir), progress -
    #        callable(done, total, name), cancel - callable() -> True
    # @return: MoveReport (moved, bytes, skipped, errors, destination)
    # THE FRAME AN OBSERVER DOES NOT WANT IN THE NIGHT. A trailed frame, one
    # under a cloud, the 0-byte one a cut capture left behind: they are taken
    # out of the visit AND out of the way, into `dscrd/` inside the
    # project. Nothing is deleted (the same rule free_space follows: the
    # frames are the observer's data and the app only knows their path) and
    # the registry follows the move, so the visit's list keeps pointing at a
    # file that exists and the row can be brought back.
    from pathlib import Path as _Path
    report = MoveReport()
    files = [str(p) for p in (paths or []) if p]
    if not files:
        return report
    dest_dir = _Path(storage_dir) / DISCARDED_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    report.destination = str(dest_dir)
    total = len(files)
    for index, path in enumerate(files, 1):
        if cancel is not None and cancel():
            break
        src = _Path(path)
        if not src.exists():
            report.skipped.append(path)
            continue
        dest = _unique(dest_dir / src.name)
        try:
            size = src.stat().st_size
            _move(src, dest)
        except OSError as err:
            report.errors.append(f"{src.name}: {err}")
            continue
        _follow_path(db, path, str(dest), flag="discarded")
        report.moved += 1
        report.bytes += int(size or 0)
        if progress is not None:
            progress(index, total, src.name)
    db.commit()
    return report


def migrate_legacy_dirs(conn):
    # ADR-062 rev (2026-10-16): rename the project's old Spanish folders
    # ("procesados", "descartados") to "prcd"/"dscrd" and rewrite every path
    # that pointed into them. The registry stores the FULL path of a moved
    # frame, so a rename without this would leave an archived frame
    # unrestorable and the visit's list pointing at a file that is not there.
    #
    # It runs once, from the database migration (core/db.py, schema v23),
    # and it is idempotent: with nothing to do it reads a couple of queries
    # and returns. The folders are taken from the ROWS themselves, never from
    # the Settings: a project's folder is wherever the observer put it.
    # @args: conn - the open sqlite3 connection (inside the migration)
    # @return: {"dirs": [renamed folders], "paths": n rows rewritten}
    report = {"dirs": [], "paths": 0}

    def _has_table(name):
        # A hand-built or half-migrated database may not carry both tables
        # yet (the old tests build partial schemas): never crash on that.
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,)).fetchone() is not None

    has_files = _has_table("project_files")
    has_frames = _has_table("astrometry_frames")
    if not has_files and not has_frames:
        return report

    # 1. every storage folder that still holds a legacy one, from the paths
    #    the registry and the run manifests kept
    folders = set()
    for old, _new in _LEGACY_DIRS:
        queries = []
        if has_files:
            queries.append("SELECT path AS p FROM project_files"
                           " WHERE path LIKE ?")
        if has_frames:
            queries.append("SELECT moved_to AS p FROM astrometry_frames"
                           " WHERE moved_to LIKE ?")
        for sql in queries:
            for (raw,) in conn.execute(sql, (f"%{old}%",)).fetchall():
                parts = Path(str(raw or "")).parts
                if old in parts:
                    folders.add((str(Path(*parts[:parts.index(old)])), old))
    # 2. rename on disk. A folder already under the new name is left alone
    #    (an interrupted migration); when BOTH exist the old one is merged
    #    in without overwriting anything.
    handled = set()
    for storage, old in sorted(folders):
        new = dict(_LEGACY_DIRS)[old]
        old_dir, new_dir = Path(storage) / old, Path(storage) / new
        if not old_dir.exists():
            handled.add((storage, old))     # already moved (or gone)
            continue
        try:
            if new_dir.exists():
                for child in sorted(old_dir.iterdir()):
                    _move(child, _unique(new_dir / child.name))
                old_dir.rmdir()
            else:
                os.rename(str(old_dir), str(new_dir))
        except OSError as err:
            # The rename failed: leave BOTH the folder and its paths as they
            # were, so the registry stays truthful about where the frames
            # are (a half-done migration is worse than an old name).
            logger.warning("could not rename %s: %s", old_dir, err)
            continue
        handled.add((storage, old))
        report["dirs"].append(str(new_dir))
    # 3. rewrite the stored paths, component by component (never a blind
    #    string replace: "procesados_2025.fits" is a file name, not a folder)
    for old, new in _LEGACY_DIRS:
        targets = []
        if has_files:
            targets.append(("project_files", "path"))
        if has_frames:
            targets.extend((("astrometry_frames", "moved_to"),
                            ("astrometry_frames", "path")))
        for table, column in targets:
            rows = conn.execute(
                f"SELECT rowid, {column} FROM {table}"
                f" WHERE {column} LIKE ?", (f"%{old}%",)).fetchall()
            for rowid, raw in rows:
                parts = list(Path(str(raw or "")).parts)
                if old not in parts:
                    continue
                storage = str(Path(*parts[:parts.index(old)]))
                if (storage, old) not in handled:
                    continue
                parts[parts.index(old)] = new
                conn.execute(f"UPDATE {table} SET {column}=? WHERE rowid=?",
                             (str(Path(*parts)), rowid))
                report["paths"] += 1
    if report["dirs"] or report["paths"]:
        logger.info("legacy project folders migrated: %s", report)
    return report


def delete_calibrated(paths, progress=None, cancel=None):
    # @args: paths - the calibrated copies to remove, progress, cancel
    # @return: MoveReport (moved = how many were removed)
    # The calibrated frames are DERIVED: they can be rebuilt from the
    # originals, so they are deleted outright and are not kept in
    # `prcd`. This is the second, independent checkbox.
    report = MoveReport()
    total = len(paths)
    for index, path in enumerate(paths, 1):
        if cancel is not None and cancel():
            break
        try:
            size = os.path.getsize(path)
            os.remove(path)
            report.moved += 1
            report.bytes += size
        except OSError as err:
            report.errors.append(f"{Path(path).name}: {err}")
        if progress is not None:
            progress(index, total, Path(path).name)
    return report
