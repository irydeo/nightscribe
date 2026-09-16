############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: variable-star vigils (ADR-037, SC4a)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime
import json
import os

import pytest

from nightscribe.core import campaign, horizon, planner, project, suggest
from nightscribe.core import vigils
from nightscribe.core.db import Database

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

LAT, LON = 28.3, -16.5          # Irydeo-ish site
DATE = datetime.date(2026, 9, 16)

# T CrB coordinates (curated default), reused across the cache fixtures
TCRB = {"name": "T CrB", "ra_deg": 239.87567, "dec_deg": 25.92017,
        "direction": "rise", "baseline_mag": 10.2, "threshold": 0.75}


class _Cfg:
    # Minimal Config stand-in (pattern: tests/unit/test_planner_campaigns.py)
    def __init__(self, **extra):
        self._d = dict(extra)

    def get(self, k, default=None):
        return self._d.get(k, default)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _fetcher(mag, band="g"):
    # @return: a fake fetch (the network never runs in unit tests); the
    #          callable receives the vigil dict, per vigils.check_vigils
    def _f(v):
        return {"mjd": 61050.0, "filter": band, "mag": mag}
    return _f


# ---------------- list handling: config & settings text ----------------

def test_defaults_when_unset():
    out = vigils.vigils_from_config(_Cfg())
    assert [v["name"] for v in out] == ["T CrB", "R CrB"]
    assert out[0]["direction"] == "rise" and out[1]["direction"] == "drop"


def test_config_accepts_json_text():
    raw = json.dumps([{"name": "SS Cyg", "direction": "rise",
                       "baseline_mag": 12.0, "threshold": 1.0}])
    out = vigils.vigils_from_config(_Cfg(vigil_list=raw))
    assert len(out) == 1 and out[0]["name"] == "SS Cyg"
    assert "ra_deg" not in out[0]      # unresolved coords: via VSX later


def test_config_broken_json_falls_back_to_defaults():
    out = vigils.vigils_from_config(_Cfg(vigil_list="{not json"))
    assert [v["name"] for v in out] == ["T CrB", "R CrB"]


def test_config_broken_rows_are_skipped():
    raw = [{"name": "R CrB", "direction": "drop", "baseline_mag": 5.8},
           {"name": ""}, {"name": "X", "baseline_mag": "not-a-number"},
           "junk"]
    out = vigils.vigils_from_config(_Cfg(vigil_list=raw))
    assert [v["name"] for v in out] == ["R CrB"]
    assert out[0]["threshold"] == 0.75      # default threshold filled in


def test_settings_text_roundtrip():
    text = vigils.vigils_to_text(vigils.default_vigils())
    out = vigils.vigils_from_text(text)
    assert [v["name"] for v in out] == ["T CrB", "R CrB"]
    assert out[0]["ra_deg"] == pytest.approx(239.87567)
    assert out[1]["direction"] == "drop"


def test_settings_text_is_tolerant():
    text = ("# comment line\n\nT CrB | rise | 10.2 | 0.75\n"
            "broken line without fields\n| | | |\n")
    out = vigils.vigils_from_text(text)
    assert [v["name"] for v in out] == ["T CrB"]


# ---------------- the vigil rule (network injected) ----------------

def test_rise_alert_fires():
    out = vigils.check_vigils(_Cfg(vigil_list=[TCRB]), fetch=_fetcher(9.0))
    assert len(out) == 1
    a = out[0]
    assert a["direction"] == "rise" and a["delta"] == -1.2
    assert a["mag"] == 9.0 and a["filter"] == "g"


def test_drop_alert_fires():
    rcrb = {"name": "R CrB", "ra_deg": 237.1, "dec_deg": 28.1,
            "direction": "drop", "baseline_mag": 5.8, "threshold": 0.75}
    out = vigils.check_vigils(_Cfg(vigil_list=[rcrb]), fetch=_fetcher(6.9))
    assert len(out) == 1 and out[0]["direction"] == "drop"
    assert out[0]["delta"] == 1.1


def test_within_baseline_stays_silent():
    assert vigils.check_vigils(_Cfg(vigil_list=[TCRB]),
                               fetch=_fetcher(10.4)) == []


def test_wrong_direction_stays_silent():
    # a rise-watch does not fire on a fade, however deep
    assert vigils.check_vigils(_Cfg(vigil_list=[TCRB]),
                               fetch=_fetcher(12.0)) == []


def test_no_detection_is_silent():
    assert vigils.check_vigils(_Cfg(vigil_list=[TCRB]),
                               fetch=lambda ra, dec: None) == []


def test_a_failing_star_never_breaks_the_run():
    def _boom(v):
        raise RuntimeError("network down")
    assert vigils.check_vigils(_Cfg(vigil_list=[TCRB]), fetch=_boom) == []


def test_no_coords_without_resolve_is_skipped():
    v = {"name": "SS Cyg", "direction": "rise", "baseline_mag": 12.0,
         "threshold": 1.0}
    out = vigils.check_vigils(_Cfg(vigil_list=[v]), fetch=_fetcher(8.0),
                              resolve=False)
    assert out == []


# ---------------- cache-only path (the signals console) ----------------

def _seed_vigil_cache(db, ra, dec, mag):
    # Writes the two vigil cache entries latest_mag_cached reads.
    cone = {"items": [{"oid": "ZTF1", "meanra": ra, "meandec": dec}]}
    lc = {"detections": [{"mjd": 61050.0, "fid": 1, "magpsf_corr": mag,
                          "sigmapsf_corr_ext": 0.02}]}
    db.cache_put(f"vigils:cone:{ra:.4f}:{dec:.4f}", "vigils",
                 json.dumps(cone).encode(), "application/json")
    db.cache_put("vigils:lc:ZTF1", "vigils",
                 json.dumps(lc).encode(), "application/json")


def test_cached_alerts_empty_without_cache(db):
    assert vigils.cached_alerts(_Cfg(vigil_list=[TCRB]), db) == []


def test_cached_alerts_fire_from_cache(db):
    # the ZTF cache path belongs to FAINT vigils (bright ones read the
    # AAVSO cache — ADR-037 SC4a rev.), so the fixture star is faint
    faint = {"name": "V455 And", "ra_deg": 352.6, "dec_deg": 39.4,
             "direction": "rise", "baseline_mag": 16.4, "threshold": 1.0}
    _seed_vigil_cache(db, faint["ra_deg"], faint["dec_deg"], 14.0)
    out = vigils.cached_alerts(_Cfg(vigil_list=[faint]), db)
    assert len(out) == 1 and out[0]["name"] == "V455 And"


# ---------------- planner: standalone rows and the fusion rule ----------------

def _alert(name="T CrB", ra=10.0, dec=80.0, direction="rise", mag=9.0):
    return {"name": name, "ra_deg": ra, "dec_deg": dec,
            "direction": direction, "baseline_mag": 10.2,
            "threshold": 0.75, "mag": mag, "filter": "g",
            "mjd": 61050.0, "delta": -1.2}


def test_vigil_targets_standalone_row():
    out = planner._vigil_targets([_alert()], LAT, LON, DATE,
                                 horizon.FlatHorizon(10.0), 0.0)
    assert len(out) == 1
    t = out[0]
    assert t["kind"] == "variable" and t["id"] == "T CrB"
    assert t["vigil"]["delta"] == -1.2
    assert t["window_start"] is not None


def test_vigil_targets_skip_consumed_and_invisible():
    alerts = [_alert(), _alert(name="R CrB"), _alert(name="Low",
                                                    dec=-80.0)]
    out = planner._vigil_targets(alerts, LAT, LON, DATE,
                                 horizon.FlatHorizon(10.0), 0.0,
                                 consumed={"tcrb"})
    assert [t["name"] for t in out] == ["R CrB"]     # fused and
                                                     # never-up ones out


def _make_campaign_project(db, name, cadence=3, visited_days_ago=0):
    # @return: (campaign_id, project_id); visited today -> NOT due
    cid = campaign.create(db, "Campaña " + name,
                          protocol={"cadence_nights": cadence})
    p = project.create(db, "variable", name,
                       {"ra_deg": 10.0, "dec_deg": 80.0, "mag": 10.0},
                       campaign_id=cid)
    if visited_days_ago is not None:
        import time
        from nightscribe.core import followup
        followup.create_session(db, p["id"])
        sid = followup.list_sessions(db, p["id"])[0]["id"]
        db.execute("UPDATE project_sessions SET created=? WHERE id=?",
                   (time.time() - visited_days_ago * 86400, sid))
        db.commit()
    return cid, p["id"]


def test_vigil_fusion_pulls_up_to_date_project(db):
    # SC-g: the vigil alert lists the existing project (never a second
    # row) even when no cadence/event/extremum reason fired
    _make_campaign_project(db, "T CrB")
    consumed = set()
    out = planner._campaign_targets(_Cfg(), LAT, LON, DATE,
                                    horizon.FlatHorizon(10.0), 0.0,
                                    db_obj=db, vigil_alerts=[_alert()],
                                    vigil_consumed=consumed)
    assert len(out) == 1
    assert out[0]["campaign"]["vigil"]["mag"] == 9.0
    assert "tcrb" in consumed
    # ...and the vigils phase must not emit the standalone row
    assert planner._vigil_targets([_alert()], LAT, LON, DATE,
                                  horizon.FlatHorizon(10.0), 0.0,
                                  consumed=consumed) == []


def test_vigil_fusion_attaches_to_already_listed_project(db):
    _make_campaign_project(db, "T CrB", visited_days_ago=None)  # due
    out = planner._campaign_targets(_Cfg(), LAT, LON, DATE,
                                    horizon.FlatHorizon(10.0), 0.0,
                                    db_obj=db, vigil_alerts=[_alert()],
                                    vigil_consumed=set())
    assert len(out) == 1
    assert out[0]["campaign"]["never_visited"] is True
    assert out[0]["campaign"]["vigil"]["direction"] == "rise"


def test_no_vigils_means_no_fusion_and_no_rows(db):
    _make_campaign_project(db, "T CrB")
    assert planner._campaign_targets(
        _Cfg(), LAT, LON, DATE, horizon.FlatHorizon(10.0), 0.0,
        db_obj=db, vigil_alerts=[], vigil_consumed=set()) == []


def test_phases_order_vigils_between_campaigns_and_approach():
    p = planner.PHASES
    assert p.index("campaigns") < p.index("vigils") < p.index("approach")


# ---------------- scoring & phrases ----------------

def test_standalone_vigil_boosts_urgency_and_phrases():
    base = {"id": "T CrB", "kind": "variable", "name": "T CrB",
            "mag": 9.0}
    plain, p_parts = suggest.score_target(dict(base), _Cfg())[0:2]
    boosted, b_parts = suggest.score_target(
        dict(base, vigil=_alert()), _Cfg())[0:2]
    assert b_parts["urgency"] - p_parts["urgency"] == pytest.approx(8)
    assert boosted > plain
    phrase = suggest.why_phrase(dict(base, vigil=_alert()), _Cfg())
    assert "Vigilia ZTF" in phrase["es"] and "ZTF vigil" in phrase["en"]


def test_fused_vigil_boosts_and_phrases_via_campaign():
    t = {"id": "T CrB", "kind": "variable", "name": "T CrB", "mag": 9.0,
         "campaign": {"id": 1, "name": "T CrB 2026", "overdue_days": 0,
                      "cadence_nights": 3, "never_visited": False,
                      "event": None, "vigil": _alert()}}
    _score, parts = suggest.score_target(t, _Cfg())
    assert parts["urgency"] >= 8
    phrase = suggest.why_phrase(t, _Cfg())
    assert "posible erupción en curso" in phrase["es"]


def test_drop_vigil_fragment_wording():
    frag = suggest._vigil_fragment(_alert(direction="drop", mag=6.9))
    assert "descenso" in frag[0] and "decline" in frag[1]


# ---------------- brightness router (ADR-037 SC4a rev.) ----------------

def test_router_bright_needs_the_aavso_token(monkeypatch):
    from nightscribe.core.sources import aavso, surveys
    calls = []
    monkeypatch.setattr(aavso, "latest_community_mag",
                        lambda name, token, **k: calls.append(name)
                        or _fetcher(9.0)({}))
    monkeypatch.setattr(surveys, "latest_mag",
                        lambda ra, dec, **k: pytest.fail(
                            "bright vigil must not hit ZTF"))
    out = vigils.check_vigils(
        _Cfg(vigil_list=[TCRB], aavso_api_token="tok"),
        fetch=vigils._default_fetch(_Cfg(vigil_list=[TCRB],
                                       aavso_api_token="tok")))
    assert len(out) == 1 and calls == ["T CrB"]


def test_router_bright_without_token_stays_silent():
    # no token configured: latest_community_mag returns None BEFORE any
    # network, so the bright vigil simply never fires
    out = vigils.check_vigils(_Cfg(vigil_list=[TCRB], aavso_api_token=""))
    assert out == []


def test_router_faint_uses_ztf(monkeypatch):
    from nightscribe.core.sources import aavso, surveys
    faint = {"name": "V455 And", "ra_deg": 352.6, "dec_deg": 39.4,
             "direction": "rise", "baseline_mag": 16.4, "threshold": 1.0}
    monkeypatch.setattr(surveys, "latest_mag",
                        lambda ra, dec, **k: _fetcher(14.0)({}))
    monkeypatch.setattr(aavso, "latest_community_mag",
                        lambda name, token, **k: pytest.fail(
                            "faint vigil must not hit AAVSO"))
    out = vigils.check_vigils(_Cfg(vigil_list=[faint]))
    assert len(out) == 1 and out[0]["name"] == "V455 And"


def test_cached_router_picks_the_aavso_cache_for_bright(db, monkeypatch):
    from nightscribe.core.sources import surveys
    monkeypatch.setattr(surveys, "latest_mag_cached",
                        lambda *a, **k: pytest.fail(
                            "bright vigil must read the AAVSO cache"))
    payload = {"count": 1, "results": [
        {"jd_dbl": 2461050.5, "magnitude": 9.0, "band": "V"}]}
    db.cache_put("aavso:phot:T CrB:30", "aavso",
                 json.dumps(payload).encode(), "application/json")
    out = vigils.cached_alerts(_Cfg(vigil_list=[TCRB]), db)
    assert len(out) == 1 and out[0]["direction"] == "rise"


# ---------------- the AAVSO photometry parsing ----------------

def test_latest_community_mag_needs_no_network_without_token():
    from nightscribe.core.sources import aavso
    assert aavso.latest_community_mag("T CrB", "") is None


def test_parse_latest_obs_drf_and_bare_and_junk():
    from nightscribe.core.sources import aavso
    drf = {"count": 2, "results": [
        {"jd_dbl": 2461049.5, "magnitude": 10.1, "band": "V"},
        {"jd_dbl": 2461050.5, "magnitude": 9.0, "band": "g"}]}
    out = aavso._parse_latest_obs(json.dumps(drf).encode())
    assert out["mag"] == 9.0 and out["filter"] == "g"       # newest wins
    bare = [{"jd": 2461051.5, "magnitude": 10.0, "band": "V"}]
    out = aavso._parse_latest_obs(json.dumps(bare).encode())
    assert out["mjd"] == pytest.approx(2461051.5 - 2400000.5)
    assert aavso._parse_latest_obs(b"not json") is None
    assert aavso._parse_latest_obs(b'{"results": "junk"}') is None


def test_settings_dialog_has_the_token_field(qapp_=None):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from nightscribe.gui.main_window import _load_ui
    dlg = _load_ui("settings_dialog")
    assert hasattr(dlg, "edt_aavso_token")


def test_on_open_settings_maps_the_token():
    import inspect
    from nightscribe.gui import main_window as mw
    src = inspect.getsource(mw.MainWindow.on_open_settings)
    assert 'config.get("aavso_api_token"' in src
    assert 'config.set("aavso_api_token"' in src
