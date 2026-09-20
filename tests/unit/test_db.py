############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SQLite cache and observations
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import time

from nightscribe.core.db import SOURCE_TTL


def test_cache_roundtrip(tmp_db):
    tmp_db.cache_put("k1", "noaa", b"hello", "text/plain")
    got = tmp_db.cache_get("k1")
    assert got is not None
    assert got[0] == b"hello"


def test_cache_expires(tmp_db):
    tmp_db.cache_put("k2", "noaa", b"x", "")
    # force the entry to look ancient
    tmp_db._conn.execute("UPDATE http_cache SET fetched=? WHERE key=?",
                         (time.time() - SOURCE_TTL["noaa"] - 10, "k2"))
    tmp_db._conn.commit()
    assert tmp_db.cache_get("k2") is None


def test_http_get_fetches_once(tmp_db):
    calls = []

    def fetch():
        calls.append(1)
        return b"data", "text/plain"
    tmp_db.http_get("k3", "sbdb", fetch)
    tmp_db.http_get("k3", "sbdb", fetch)
    assert len(calls) == 1  # second call served from cache


def test_http_get_survives_thread_pool(tmp_db):
    # The planner's pools (comets, NEO discovery dates — object-card plan
    # 5c) hammer the shared connection from several threads at once. One
    # sqlite3 connection must never run two statements simultaneously;
    # without the lock this raises "bad parameter or other API misuse".
    import threading
    errors = []

    def hammer(tag):
        def fetch():
            time.sleep(0.001)      # widen the race window
            return f"body-{tag}".encode(), "text/plain"
        try:
            for i in range(40):
                tmp_db.http_get(f"key-{tag}-{i % 5}", "sbdb", fetch)
                tmp_db.mark_observed(f"obj-{tag}")
                tmp_db.is_observed(f"obj-{tag}")
        except Exception as err:  # noqa: BLE001 - we assert on the list
            errors.append(err)

    threads = [threading.Thread(target=hammer, args=(t,)) for t in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"threaded access raised: {errors!r}"


def test_cache_get_drops_poisoned_row(tmp_path):
    # A row with NULL fetched/ttl (legacy DB, or an interrupted write from
    # the pre-lock era) must not crash cache_get — it is dropped on sight
    # and the caller refetches. The current schema forbids NULLs, so the
    # legacy table is rebuilt by hand here.
    import sqlite3
    from nightscribe.core.db import Database
    f = tmp_path / "legacy.db"
    conn = sqlite3.connect(f)
    conn.execute("CREATE TABLE http_cache (key TEXT PRIMARY KEY, source TEXT,"
                 " fetched REAL, ttl REAL, body BLOB, content_type TEXT)")
    conn.execute("INSERT INTO http_cache VALUES (?, ?, NULL, NULL, ?, ?)",
                 ("old-key", "sbdb", b"x", ""))
    conn.commit()
    conn.close()
    legacy = Database(f)
    try:
        assert legacy.cache_get("old-key") is None
        # and the row is really gone (no second poisoning)
        row = legacy._conn.execute(
            "SELECT COUNT(*) FROM http_cache WHERE key='old-key'").fetchone()
        assert row[0] == 0
    finally:
        legacy.close()


def test_observations_flow(tmp_db):
    assert not tmp_db.is_observed("29P")
    tmp_db.mark_observed("29P", "comet", "2026-08-21")
    assert tmp_db.is_observed("29P")
    assert not tmp_db.observed_recently("29P")
    tmp_db.mark_posted("29P")
    assert tmp_db.observed_recently("29P")
    hist = tmp_db.history()
    assert hist[0]["object"] == "29P"
    assert hist[0]["posted"] is True
    tmp_db.unmark_observed("29P")
    assert not tmp_db.is_observed("29P")
