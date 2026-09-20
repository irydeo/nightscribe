############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: campaigns planner phase (Track V, VA.1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime
import time

import pytest

from nightscribe.core import campaign, followup, horizon, planner, project
from nightscribe.core.db import Database

LAT, LON = 28.3, -16.5          # Irydeo-ish site
DATE = datetime.date(2026, 9, 11)


class _Cfg:
    def __init__(self, limit_mag=14.0, **extra):
        self._d = {"limit_mag": limit_mag}
        self._d.update(extra)

    def get(self, k, default=None):
        return self._d.get(k, default)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _make_due(db, name="T CrB", ra=10.0, dec=80.0, mag=10.0,
              kind="variable", cadence=1, visited_days_ago=None, ctx=None):
    # @return: (campaign_id, project_id) of a campaign + project pair
    cid = campaign.create(db, "Campaña " + name,
                          protocol={"cadence_nights": cadence})
    full_ctx = {"ra_deg": ra, "dec_deg": dec, "mag": mag}
    full_ctx.update(ctx or {})
    p = project.create(db, kind, name, full_ctx, campaign_id=cid)
    if visited_days_ago is not None:
        followup.create_session(db, p["id"])
        sid = followup.list_sessions(db, p["id"])[0]["id"]
        db.execute("UPDATE project_sessions SET created=? WHERE id=?",
                   (time.time() - visited_days_ago * 86400, sid))
        db.commit()
    return cid, p["id"]


def _targets(db, limit_mag=14.0, **extra):
    return planner._campaign_targets(_Cfg(limit_mag, **extra), LAT, LON, DATE,
                                     horizon.FlatHorizon(10.0), 0.0,
                                     db_obj=db)


def test_phases_include_campaigns_before_approach():
    assert "campaigns" in planner.PHASES
    assert planner.PHASES.index("campaigns") < \
        planner.PHASES.index("approach")


def test_due_campaign_project_is_listed(db):
    _make_due(db)                            # never visited -> due
    out = _targets(db)
    assert len(out) == 1
    t = out[0]
    assert t["kind"] == "variable" and t["id"] == "T CrB"
    assert t["project_id"] is not None
    assert t["campaign"]["name"] == "Campaña T CrB"
    assert t["campaign"]["never_visited"] is True
    assert t["campaign"]["event"] is None
    assert t["window_start"] is not None


def test_up_to_date_campaign_is_not_listed(db):
    _make_due(db, cadence=3, visited_days_ago=0)
    assert _targets(db) == []


def test_not_visible_tonight_is_excluded(db):
    _make_due(db, dec=-70.0)                 # never up from lat 28.3
    assert _targets(db) == []


def test_magnitude_gate(db):
    _make_due(db, mag=15.5)
    assert _targets(db, limit_mag=14.0) == []
    assert len(_targets(db, limit_mag=16.0)) == 1


def test_missing_coordinates_are_skipped(db):
    cid = campaign.create(db, "C")
    project.create(db, "variable", "NoCoords", {}, campaign_id=cid)
    assert _targets(db) == []


def test_no_campaigns_no_targets(db):
    assert _targets(db) == []


def test_variable_subdict_with_fresh_extremum(db):
    _make_due(db, ctx={"variable": {"var_type": "M", "period_d": 300.0,
                                    "epoch_mjd": 60000.0, "max": 9.0,
                                    "min": 13.5, "spectral": "M6e"}})
    t = _targets(db)[0]
    v = t["variable"]
    assert v["amp"] == 4.5                       # min - max (inverted axis)
    assert v["next_extremum"]["kind"] in ("max", "min")
    assert v["next_extremum"]["days"] >= 0


def test_event_flag_from_own_points(db):
    _cid, pid = _make_due(db)
    for i, m in enumerate((12.0, 12.1, 11.9, 12.0, 12.9)):
        followup.add_point(db, pid, 61000.0 + i, "V", m)
    t = _targets(db)[0]
    assert t["campaign"]["event"]["direction"] == "drop"


def test_no_variable_no_subdict(db):
    _make_due(db)
    assert "variable" not in _targets(db)[0]


# ---------------- ADR-037 SC1: event / extremum listing ----------------

def test_up_to_date_event_project_is_listed(db):
    # the bug due_campaigns had (ADR-037): a WeSb drop seen today must not
    # wait for the cadence — an event alone gets the project listed
    _cid, pid = _make_due(db, "R CrB", cadence=3, visited_days_ago=0)
    for i, m in enumerate((12.0, 12.1, 11.9, 12.0, 12.9)):
        followup.add_point(db, pid, 61000.0 + i, "V", m)
    out = _targets(db)
    assert len(out) == 1
    assert out[0]["campaign"]["event"]["direction"] == "drop"
    assert out[0]["campaign"]["imminent_extremum"] is False


def test_imminent_extremum_project_is_listed(db):
    from nightscribe.core import variables
    epoch = variables._now_mjd() + 2 - 300.0 * 100    # max ~2 days out
    _make_due(db, "WeSb 1", cadence=3, visited_days_ago=0,
              ctx={"variable": {"var_type": "M", "period_d": 300.0,
                                "epoch_mjd": epoch}})
    out = _targets(db)
    assert len(out) == 1                              # up-to-date otherwise
    assert out[0]["campaign"]["imminent_extremum"] is True
    assert out[0]["variable"]["next_extremum"]["kind"] == "max"
    assert out[0]["variable"]["next_extremum"]["days"] >= 1.0


def test_extremum_window_is_configurable(db):
    from nightscribe.core import variables
    epoch = variables._now_mjd() + 2 - 300.0 * 100    # max ~2 days out
    _make_due(db, "WeSb 1", cadence=3, visited_days_ago=0,
              ctx={"variable": {"var_type": "M", "period_d": 300.0,
                                "epoch_mjd": epoch}})
    assert len(_targets(db)) == 1                     # default window: 3 d
    assert _targets(db, campaign_extremum_days=1) == []   # 2 d > 1 d window
    assert _targets(db, campaign_extremum_days=0) == []   # 0 = today only


def test_event_threshold_is_configurable(db):
    # a 0.6 mag jump is an event at the default 0.5 threshold but not at 1
    _cid, pid = _make_due(db, "R CrB", cadence=3, visited_days_ago=0)
    for i, m in enumerate((12.0, 12.1, 11.9, 12.0, 12.6)):
        followup.add_point(db, pid, 61000.0 + i, "V", m)
    assert len(_targets(db)) == 1                     # 0.6 >= 0.5
    assert _targets(db, event_mag_threshold=1.0) == []
