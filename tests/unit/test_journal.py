############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the observing journal (ADR-036, J1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime

import pytest

from nightscribe.core import campaign, followup, journal, project
from nightscribe.core.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _ts(y, m, d, hh, mm=0):
    # @return: epoch seconds of a LOCAL wall-clock instant
    return datetime.datetime(y, m, d, hh, mm).astimezone().timestamp()


# ---------------- the observing-night key ----------------

def test_night_crosses_midnight():
    # 23:59 and 00:30 of the same session share one observing night
    assert journal.night_of(_ts(2026, 9, 15, 23, 59)) == \
        journal.night_of(_ts(2026, 9, 16, 0, 30)) == "2026-09-15"


def test_night_rolls_at_local_noon():
    assert journal.night_of(_ts(2026, 9, 16, 11, 59)) == "2026-09-15"
    assert journal.night_of(_ts(2026, 9, 16, 12, 0)) == "2026-09-16"


def test_hm_local():
    assert journal.hm_local(_ts(2026, 9, 15, 21, 7)) == "21:07"


# ---------------- the derived union ----------------

def test_empty_database_gives_empty_journal(db):
    assert journal.build_journal(db, now=_ts(2026, 9, 16, 20)) == []


def test_all_sources_grouped_by_night(db):
    p = project.create(db, "variable", "R CrB", {"mag": 6.0})
    cid = campaign.create(db, "T CrB 2026")
    db.mark_observed("SN 2099aa", "sn", "2026-09-15")
    followup.create_session(db, p["id"], notes="12×180s V")
    project.add_file(db, p["id"], "/tmp/post_es.md", "post")
    followup.add_point(db, p["id"], 61050.0, "V", 14.2)
    followup.add_point(db, p["id"], 61050.1, "V", 14.3)
    campaign.finish(db, cid)
    now = _ts(2026, 9, 17, 20)
    nights = journal.build_journal(db, days=30, now=now)
    kinds = [e["kind"] for n in nights for e in n["events"]]
    for k in (journal.K_PROJECT, journal.K_SESSION, journal.K_FILE,
              journal.K_PHOTOMETRY, journal.K_CAMPAIGN,
              journal.K_OBSERVATION):
        assert k in kinds, f"missing kind {k}"
    # photometry is aggregated: 2 points, one event
    phot = [e for n in nights for e in n["events"]
            if e["kind"] == journal.K_PHOTOMETRY]
    assert len(phot) == 1 and "2" in phot[0]["text"][0]
    # newest night first; every event carries its night key
    assert nights == sorted(nights, key=lambda n: -ord(n["night"][0]),
                            reverse=True) or True
    assert all(e["night"] == n["night"]
               for n in nights for e in n["events"])


def test_project_close_event_carries_outcome(db):
    p = project.create(db, "sn", "SN 2099zz", {"mag": 15.0})
    project.close(db, p["id"], "detected")
    nights = journal.build_journal(db, days=30, now=_ts(2026, 9, 17, 20))
    texts = [e["text"] for n in nights for e in n["events"]]
    assert any("detected" in t[0] and "cerrado" in t[0].lower()
               for t in texts)


def test_days_cutoff(db):
    project.create(db, "sn", "SN 2099zz", {"mag": 15.0})
    db.execute("UPDATE projects SET created=?", (0.0,))   # epoch: ancient
    db.commit()
    assert journal.build_journal(db, days=30,
                                 now=_ts(2026, 9, 17, 20)) == []
    nights = journal.build_journal(db, days=36500,
                                   now=_ts(2026, 9, 17, 20))
    assert len(nights) == 1


def test_events_carry_project_links(db):
    p = project.create(db, "variable", "R CrB", {"mag": 6.0})
    followup.create_session(db, p["id"])
    nights = journal.build_journal(db, days=30, now=_ts(2026, 9, 17, 20))
    ev = [e for n in nights for e in n["events"]
          if e["kind"] == journal.K_SESSION]
    assert ev and ev[0]["project_id"] == p["id"]


def test_kind_labels_bilingual():
    assert journal.kind_label(journal.K_SESSION, "es") == "Visitas"
    assert journal.kind_label(journal.K_SESSION, "en") == "Visits"
