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
