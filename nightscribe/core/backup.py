############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Pre-migration database backup module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# ADR-042: the app snapshots the database before the update wizard ever
# runs. This module deliberately does not import core/db.py: importing
# that module creates the shared connection and migrates the schema on
# the fly, and the snapshot must capture the state the user had before
# this version touched anything.

import logging
import sqlite3
import time
from pathlib import Path

from .. import paths

logger = logging.getLogger(__name__)


def backup(src=None, keep=3):
    # SQLite online-backup snapshot of the database, taken before the
    # update wizard migrates anything. The copy is a consistent image
    # even while app code still holds its own connection open.
    # The newest `keep` copies are retained, older ones are dropped,
    # and the copy's integrity is verified before it is reported as ok.
    # @args: src - Path of the database to copy (default: the app's own)
    #        keep - how many old backups to retain (default 3)
    # @return: dict with file (Path), schema_version (int, the original
    #          one, so the wizard can say where the data came from),
    #          size (bytes) and integrity ("ok" | "problem"), or None
    #          when there is nothing to back up or the copy failed
    src = Path(src) if src is not None else paths.db_path()
    if not src.exists():
        return None
    dst = None
    ver = 0
    try:
        src_conn = sqlite3.connect(str(src))
        ver = src_conn.execute("PRAGMA user_version").fetchone()[0]
        bakdir = paths.backups_dir()
        base = f"nightscribe_{time.strftime('%Y-%m-%d_%H%M')}_v{ver}"
        dst = bakdir / (base + ".db")
        n = 1
        while dst.exists():  # same-minute reruns: numbered, never overwrite
            dst = bakdir / f"{base}_{n}.db"
            n += 1
        dst_conn = sqlite3.connect(str(dst))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
        src_conn.close()
    except (sqlite3.Error, OSError) as err:
        logger.warning("db backup failed: %s", err)
        if dst is not None:
            dst.unlink(missing_ok=True)
        return None
    # a backup nobody trusts is worse than none: verify the copy
    integrity = "ok"
    try:
        chk = sqlite3.connect(str(dst))
        result = chk.execute("PRAGMA integrity_check").fetchone()[0]
        chk.close()
        if result != "ok":
            integrity = "problem"
    except sqlite3.Error:
        integrity = "problem"
    # keep the newest `keep`, drop the rest
    try:
        old = sorted(paths.backups_dir().glob("nightscribe_*_v*.db"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
        for extra in old[keep:]:
            extra.unlink(missing_ok=True)
    except OSError:
        pass
    return {
        "file": dst,
        "schema_version": ver,
        "size": dst.stat().st_size,
        "integrity": integrity,
    }
