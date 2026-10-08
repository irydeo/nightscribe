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
delete them: to `procesados/` inside the project, where they can be
brought back with one call.

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


@dataclass
class MoveReport:
    moved: int = 0
    bytes: int = 0
    skipped: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    destination: str | None = None


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
    # The frames go to `procesados/<fecha de la visita>/` inside the
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
    dest_dir = Path(storage_dir) / "procesados" / date
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
        dest = Path(original)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            _move(src, dest)
        except OSError as err:
            report.errors.append(f"{src.name}: {err}")
            continue
        _follow_path(db, str(src), str(dest))
        db.execute("UPDATE astrometry_frames SET archived=0, moved_to=NULL"
                   " WHERE id=?", (frame_id,))
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
    # out of the visit AND out of the way, into `descartados/` inside the
    # project. Nothing is deleted (the same rule free_space follows: the
    # frames are the observer's data and the app only knows their path) and
    # the registry follows the move, so the visit's list keeps pointing at a
    # file that exists and the row can be brought back.
    from pathlib import Path as _Path
    report = MoveReport()
    files = [str(p) for p in (paths or []) if p]
    if not files:
        return report
    dest_dir = _Path(storage_dir) / "descartados"
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


def delete_calibrated(paths, progress=None, cancel=None):
    # @args: paths - the calibrated copies to remove, progress, cancel
    # @return: MoveReport (moved = how many were removed)
    # The calibrated frames are DERIVED: they can be rebuilt from the
    # originals, so they are deleted outright and are not kept in
    # `procesados`. This is the second, independent checkbox.
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
