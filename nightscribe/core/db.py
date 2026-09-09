############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - SQLite database module (cache + state)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import json
import logging
import sqlite3
import time

from .. import paths

logger = logging.getLogger(__name__)

# One hour/day in seconds, just to read the TTL table below at a glance
HOUR = 3600
DAY = 24 * HOUR

# Cache TTL per source, in seconds. Sources are expensive and some are
# one-person projects: be a good citizen and never hit them twice.
SOURCE_TTL = {
    "noaa": 1 * HOUR,
    "sdo": 1 * HOUR,
    "neofixer": 12 * HOUR,
    "neofixer-orbit": 1.5 * HOUR,
    "horizons": 12 * HOUR,
    "rochester": 6 * HOUR,
    "cobs": 6 * HOUR,
    "esa_neo": 6 * HOUR,
    "pccp": 6 * HOUR,
    "exoclock": 24 * HOUR,
    "silso": 24 * HOUR,
    "sbdb": 7 * DAY,
    "simbad": 7 * DAY,
    "cad": 7 * DAY,
    "exoplanet_archive": 7 * DAY,
    "obscodes": 30 * DAY,
    "cutouts": 30 * DAY,
    "tns": 6 * HOUR,
    "astrometry": 30 * DAY,
    "ccdciel": 60,  # local JSON-RPC: covers quick reads (temp, filters,
                    # slewing) without hammering the observatory software
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (
    key          TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    fetched      REAL NOT NULL,
    ttl          REAL NOT NULL,
    body         BLOB NOT NULL,
    content_type TEXT
);
CREATE TABLE IF NOT EXISTS observations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    object     TEXT NOT NULL,
    type       TEXT,
    obs_date   TEXT NOT NULL,
    notes      TEXT DEFAULT '',
    posted     INTEGER DEFAULT 0,
    created    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observations_object ON observations(object);
"""

# Phase 3 (ADR-019): project tables + observations.project_id link.
_V1 = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    object_name TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',
    created     REAL NOT NULL,
    updated     REAL NOT NULL,
    context     TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS project_steps (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    step       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    data       TEXT DEFAULT '{}',
    updated    REAL NOT NULL,
    UNIQUE(project_id, step)
);
CREATE TABLE IF NOT EXISTS project_files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    created    REAL NOT NULL
);
"""


def _migrate(conn):
    # Idempotent base schema, then versioned migrations (ADR-002).
    conn.executescript(_SCHEMA)
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    if v < 1:
        conn.executescript(_V1)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(observations)")}
        if "project_id" not in cols:
            conn.execute("ALTER TABLE observations ADD COLUMN project_id INTEGER")
        conn.execute("PRAGMA user_version = 1")
    if v < 2:
        # ADR-019 review (2026-08-28): the "analyse" step was removed from the
        # step machine. Drop those rows; if a project was stopped on them,
        # hand "current" to the next step (publish) so the flow keeps moving.
        rows = conn.execute(
            "SELECT project_id, id, status FROM project_steps WHERE step=?",
            ("analyse",)).fetchall()
        for pid, sid, status in rows:
            if status == "current":
                # the flow was stopped on the analyse step: hand "current" to
                # the next step (publish)
                conn.execute(
                    "UPDATE project_steps SET status=?, updated=? WHERE"
                    " project_id=? AND step=?",
                    ("current", time.time(), pid, "publish"))
            conn.execute("DELETE FROM project_steps WHERE id=?", (sid,))
        conn.execute("PRAGMA user_version = 2")
    if v < 3:
        # ADR-030 review (2026-09-06): "capture" was merged into "plan"
        # (Plan & Captura). Move its data over, hand "current" to "process"
        # if a project was stopped on capture, then drop the step row.
        rows = conn.execute(
            "SELECT id, project_id, status, data FROM project_steps"
            " WHERE step=?",
            ("capture",)).fetchall()
        for sid, pid, status, data in rows:
            if status == "current":
                conn.execute(
                    "UPDATE project_steps SET status=?, updated=?"
                    " WHERE project_id=? AND step=?",
                    ("current", time.time(), pid, "process"))
            if data and data != "{}":
                plan = conn.execute(
                    "SELECT data FROM project_steps WHERE project_id=?"
                    " AND step=?",
                    (pid, "plan")).fetchone()
                if plan:
                    merged = json.loads(plan[0] or "{}")
                    merged.update(json.loads(data))
                    conn.execute(
                        "UPDATE project_steps SET data=?, updated=?"
                        " WHERE project_id=? AND step=?",
                        (json.dumps(merged, ensure_ascii=False), time.time(),
                         pid, "plan"))
            conn.execute("DELETE FROM project_steps WHERE id=?", (sid,))
        conn.execute("PRAGMA user_version = 3")
    if v < 4:
        # Track A (project-concept v2): lifecycle & classification — close
        # date, final outcome, free-form tags and favourites on a project.
        # Guarded column checks keep it idempotent (a fresh DB already has the
        # columns when _V1 is extended in a future revision; re-opening a v4
        # DB is a no-op).
        cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
        if "closed_at" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN closed_at REAL")
        if "outcome" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN outcome TEXT")
        if "tags" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN tags TEXT DEFAULT ''")
        if "favorite" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN favorite INTEGER"
                         " DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_created"
                     " ON projects(created)")
        conn.execute("PRAGMA user_version = 4")
    conn.commit()


class Database:
    # Single SQLite access point: HTTP cache plus the observatory's own
    # observation history. Everything persistent lives here (see ADR-002).
    #
    # The connection is shared with the planner's thread pools (comets,
    # NEO discovery dates — object-card plan 5c), and one sqlite3
    # connection must never run two statements at once: every public
    # method serialises through _lock. (Without it, concurrent calls
    # interleave and sqlite3 raises "bad parameter or other API misuse",
    # and an interrupted write can even land a half-bound row.)

    def __init__(self, db_file=None):
        import threading
        self._lock = threading.RLock()
        self._file = str(db_file or paths.db_path())
        self._conn = sqlite3.connect(self._file, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        _migrate(self._conn)

    def close(self):
        # Closes the database connection
        self._conn.close()

    def execute(self, sql, params=()):
        # Public SQL helper for domain modules (e.g. core/project.py).
        # Does NOT auto-commit: call commit() when your operation is done.
        # @args: sql - SQL string with placeholders, params - tuple/list
        # @return: sqlite3 cursor (caller may fetchone/fetchall)
        with self._lock:
            return self._conn.execute(sql, params)

    def commit(self):
        # Commits the current transaction
        with self._lock:
            self._conn.commit()

    # ---------------- HTTP cache ----------------

    def cache_get(self, key):
        # Returns a fresh cached response for the key, or None.
        # @args: key - cache key (usually url + sorted params)
        # @return: (body bytes, content_type) or None
        with self._lock:
            row = self._conn.execute(
                "SELECT body, content_type, fetched, ttl FROM http_cache"
                " WHERE key=?",
                (key,),
            ).fetchone()
            if not row:
                return None
            body, content_type, fetched, ttl = row
            if fetched is None or ttl is None:
                # poisoned row (a legacy DB or an interrupted racy write):
                # drop it and let the caller refetch
                self._conn.execute("DELETE FROM http_cache WHERE key=?",
                                   (key,))
                self._conn.commit()
                return None
            if time.time() - fetched > ttl:
                return None
            return body, content_type

    def cache_put(self, key, source, body, content_type=""):
        # Stores a response in the cache with the TTL of its source.
        # @args: key - cache key, source - source name (see SOURCE_TTL),
        #        body - raw bytes, content_type - optional MIME type
        ttl = SOURCE_TTL.get(source, 6 * HOUR)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO http_cache (key, source, fetched, ttl,"
                " body, content_type) VALUES (?, ?, ?, ?, ?, ?)",
                (key, source, time.time(), ttl, body, content_type),
            )
            self._conn.commit()

    def http_get(self, key, source, fetch_fn, force=False):
        # Cache-aside helper: returns cached bytes or calls fetch_fn(),
        # stores the result and returns it.
        # @args: key - cache key, source - source name,
        #        fetch_fn - callable returning (body bytes, content_type),
        #        force - True bypasses the cache read (still stores the
        #                fresh result for the next caller)
        # @return: (body bytes, content_type)
        cached = None if force else self.cache_get(key)
        if cached:
            logger.debug("cache hit: %s", key)
            return cached
        body, content_type = fetch_fn()
        self.cache_put(key, source, body, content_type)
        return body, content_type

    # ---------------- Observations ----------------

    def mark_observed(self, obj, obj_type="", obs_date=None, notes="",
                      project_id=None):
        # Marks an object as observed (tonight by default).
        # @args: obj - object name, obj_type - neo|comet|pccp|sn|transit|sun,
        #        obs_date - ISO date string, notes - free text,
        #        project_id - optional link to a project (ADR-019)
        obs_date = obs_date or time.strftime("%Y-%m-%d")
        with self._lock:
            self._conn.execute(
                "INSERT INTO observations"
                " (object, type, obs_date, notes, created, project_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (obj, obj_type, obs_date, notes, time.time(), project_id),
            )
            self._conn.commit()

    def unmark_observed(self, obj):
        # Removes all observed marks for an object.
        # @args: obj - object name
        with self._lock:
            self._conn.execute("DELETE FROM observations WHERE object=?",
                               (obj,))
            self._conn.commit()

    def is_observed(self, obj):
        # @args: obj - object name
        # @return: True if the object was ever marked as observed
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM observations WHERE object=? LIMIT 1", (obj,)
            ).fetchone()
            return bool(row)

    def mark_posted(self, obj):
        # Flags the latest observation of an object as already posted.
        # @args: obj - object name
        with self._lock:
            self._conn.execute(
                "UPDATE observations SET posted=1 WHERE object=?", (obj,)
            )
            self._conn.commit()

    def history(self, limit=100):
        # @args: limit - max rows
        # @return: list of dicts with the latest observations
        with self._lock:
            rows = self._conn.execute(
                "SELECT object, type, obs_date, notes, posted FROM observations"
                " ORDER BY created DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"object": r[0], "type": r[1], "obs_date": r[2], "notes": r[3],
             "posted": bool(r[4])}
            for r in rows
        ]

    def observed_recently(self, obj, days=30):
        # @args: obj - object name, days - look-back window
        # @return: True if the object was posted within the window
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM observations WHERE object=? AND posted=1"
                " AND created > ? LIMIT 1",
                (obj, time.time() - days * DAY),
            ).fetchone()
            return bool(row)


# Shared instance (tests build their own with a temp file)
db = Database()
