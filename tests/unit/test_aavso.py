############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: AAVSO editorial channel (ADR-037, SC4b)
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
from nightscribe.core.db import Database
from nightscribe.core.sources import aavso

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

LAT, LON = 28.3, -16.5          # Irydeo-ish site
DATE = datetime.date(2026, 9, 16)

# Real titles captured by the SC4b validation spike (2026-09-16)
SPIKE_TITLES = [
    ("Nova Sgr 2026 No. 3 - Observations needed", "Nova Sgr 2026 No. 3"),
    ("SU Tau is dimming", "SU Tau"),
    ("RCB variable NSV 11664 in Aquila is dimming", "NSV 11664"),
    ("T CRB Johnson V scores below 8.5! Please post observations here",
     "T CRB"),
    ("Photometry (and spectroscopy) requested for GK Per", "GK Per"),
    ("Request for frequent monitoring of RU Peg", "RU Peg"),
    ("About the Alerts category", None),
]

FORUM_JSON = json.dumps({"topic_list": {"topics": [
    {"id": 1887, "title": "About the Alerts category", "pinned": True,
     "created_at": "2025-02-08T00:00:00Z", "last_posted_at":
     "2025-02-08T00:00:00Z"},
    {"id": 4914, "title": "SU Tau is dimming",
     "created_at": "2026-08-12T10:00:00Z",
     "last_posted_at": "2026-08-12T10:00:00Z"},
    {"id": 4953, "title": "Nova Sgr 2026 No. 3 - Observations needed",
     "created_at": "2026-08-20T10:00:00Z",
     "last_posted_at": "2026-08-20T10:00:00Z"},
    {"id": 3000, "title": "An ancient alert",
     "created_at": "2020-01-01T00:00:00Z",
     "last_posted_at": "2020-01-01T00:00:00Z"},
]}}).encode()

CAMPAIGNS_HTML = b"""
<html><body><table class="text-left rounded-t-md">
<tr><th>id</th></tr>
<tr><td><a href="/v2/campaigns/940/">940</a></td>
 <td>Photometry (and spectroscopy) requested for GK Per</td>
 <td>Kimura, M.</td><td>2026-08-06 (UTC)</td><td>2026-09-16 (UTC)</td>
 <td>Spectroscopy, Photometry</td></tr>
<tr><td><a href="/v2/campaigns/938/">938</a></td>
 <td>Finding Phase-Step delta Scuti Variables</td>
 <td>Hintz, E.</td><td>2026-07-14 (UTC)</td><td>2027-04-30 (UTC)</td>
 <td>Photometry</td></tr>
<tr><td><a href="/v2/campaigns/900/">900</a></td>
 <td>Expired campaign for SU Tau</td>
 <td>Doe, J.</td><td>2026-01-01 (UTC)</td><td>2026-02-01 (UTC)</td>
 <td>Photometry</td></tr>
</table></body></html>
"""


class _Cfg:
    # Minimal Config stand-in (pattern: tests/unit/test_planner_campaigns.py)
    def __init__(self, **extra):
        self._d = dict(extra)

    def get(self, k, default=None):
        return self._d.get(k, default)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


@pytest.fixture
def fake_get(monkeypatch):
    # aavso._get routed to a payload table: {cache_key: bytes | Exception}
    calls = {}

    def _set(key, payload):
        calls[key] = payload

    def _fake(url, cache_key, force=False):
        payload = calls.get(cache_key)
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(aavso, "_get", _fake)
    return _set


# ---------------- source: parsing (fixtures from the spike) ----------------

def test_extract_star_name_on_spike_titles():
    for title, want in SPIKE_TITLES:
        assert aavso.extract_star_name(title) == want, title


def test_extract_star_name_normalizes_spacing():
    assert aavso.extract_star_name("V838 Her  still") == "V838 Her"


def test_alerts_parse_filter_and_sort(fake_get):
    fake_get("aavso:alerts", FORUM_JSON)
    out = aavso.alerts(days=60)
    # pinned and stale topics dropped, newest first
    assert [(a["id"], a["title"]) for a in out] == [
        (4953, "Nova Sgr 2026 No. 3 - Observations needed"),
        (4914, "SU Tau is dimming")]
    assert out[0]["url"].endswith("/t/4953")


def test_alerts_degrade_gracefully(fake_get):
    fake_get("aavso:alerts", b"not json")
    assert aavso.alerts() == []
    fake_get("aavso:alerts", None)
    assert aavso.alerts() == []


def test_campaigns_parse_and_filter_active(fake_get):
    fake_get("aavso:campaigns", CAMPAIGNS_HTML)
    out = aavso.campaigns(today="2026-09-16")
    assert [(c["id"], c["title"]) for c in out] == [
        (940, "Photometry (and spectroscopy) requested for GK Per"),
        (938, "Finding Phase-Step delta Scuti Variables")]
    assert out[0]["requester"] == "Kimura, M."
    assert out[0]["url"].endswith("/v2/campaigns/940/")
    assert out[0]["end"] == "2026-09-16"
    # 900 ended in February: filtered out; the header row is not a campaign


def test_campaigns_degrade_gracefully(fake_get):
    fake_get("aavso:campaigns", None)
    assert aavso.campaigns() == []


# ---------------- planner phase ----------------

def _vsx_ok(name):
    return {"name": name.title() if name.isupper() else name,
            "ra_deg": 10.0, "dec_deg": 80.0, "max": 11.0}


def test_aavso_fetch_respects_the_toggle(monkeypatch):
    monkeypatch.setattr(aavso, "alerts", lambda **k: pytest.fail(
        "the feed must not run when disabled"))
    assert planner._aavso_fetch(_Cfg(aavso_feed=False)) == []


def test_aavso_fetch_extracts_names(monkeypatch):
    monkeypatch.setattr(aavso, "alerts", lambda **k: [
        {"id": 1, "title": "SU Tau is dimming", "date": "2026-08-12",
         "url": "u1"}, {"id": 2, "title": "No star here",
                       "date": "2026-08-12", "url": "u2"}])
    monkeypatch.setattr(aavso, "campaigns", lambda **k: [
        {"id": 9, "title": "Request for frequent monitoring of RU Peg",
         "requester": "A", "start": "2026-01-01", "end": "2027-01-01",
         "kinds": "Photometry", "url": "u9"}])
    out = planner._aavso_fetch(_Cfg())
    assert [(i["name"], i["kind"]) for i in out] == [
        ("SU Tau", "alert"), ("RU Peg", "campaign")]


def test_aavso_targets_resolve_and_gate(monkeypatch):
    from nightscribe.core.sources import vsx
    monkeypatch.setattr(vsx, "lookup", lambda name, **k: _vsx_ok(name))
    items = [{"name": "SU Tau", "kind": "alert", "title": "t",
              "date": "2026-08-12", "url": "u"},
             {"name": "V9999 Foo", "kind": "alert", "title": "t",
              "date": "2026-08-12", "url": "u"},
             {"name": "SU Tau", "kind": "campaign", "title": "dup",
              "date": "2026-08-13", "url": "u2"}]

    def _lookup(name, **k):
        return None if name.startswith("V9999") else _vsx_ok(name)
    monkeypatch.setattr(vsx, "lookup", _lookup)
    out = planner._aavso_targets(items, _Cfg(), LAT, LON, DATE,
                                 horizon.FlatHorizon(10.0), 0.0)
    assert len(out) == 1                       # unresolved + duplicate out
    t = out[0]
    assert t["kind"] == "variable" and t["aavso"]["kind"] == "alert"
    assert t["window_start"] is not None


def test_aavso_targets_retry_mixed_case(monkeypatch):
    from nightscribe.core.sources import vsx
    seen = []

    def _lookup(name, **k):
        seen.append(name)
        return _vsx_ok(name) if name == "T CrB" else None
    monkeypatch.setattr(vsx, "lookup", _lookup)
    items = [{"name": "T CRB", "kind": "alert", "title": "t",
              "date": "2026-08-12", "url": "u"}]
    out = planner._aavso_targets(items, _Cfg(), LAT, LON, DATE,
                                 horizon.FlatHorizon(10.0), 0.0)
    assert seen == ["T CRB", "T CrB"] and len(out) == 1


def test_vsx_retry_name():
    assert planner._vsx_retry_name("T CRB") == "T CrB"
    assert planner._vsx_retry_name("NSV 11664") == "NSV 11664"


def test_aavso_fusion_into_campaign_project(db, monkeypatch):
    # SC-g: the AAVSO item about a campaign star joins its reasons and
    # never reappears as a standalone row
    cid = campaign.create(db, "Campaña SU Tau",
                          protocol={"cadence_nights": 3})
    project.create(db, "variable", "SU Tau",
                   {"ra_deg": 10.0, "dec_deg": 80.0, "mag": 11.0},
                   campaign_id=cid)
    item = {"name": "SU Tau", "kind": "campaign", "title": "monitorea",
            "end": "2027-01-01", "url": "u"}
    consumed = set()
    out = planner._campaign_targets(_Cfg(), LAT, LON, DATE,
                                    horizon.FlatHorizon(10.0), 0.0,
                                    db_obj=db, vigil_alerts=[],
                                    vigil_consumed=consumed,
                                    aavso_items=[item])
    assert len(out) == 1                       # up-to-date, listed by AAVSO
    assert out[0]["campaign"]["aavso"]["title"] == "monitorea"
    assert "sutau" in consumed
    from nightscribe.core.sources import vsx
    monkeypatch.setattr(vsx, "lookup", lambda name, **k: _vsx_ok(name))
    assert planner._aavso_targets([item], _Cfg(), LAT, LON, DATE,
                                  horizon.FlatHorizon(10.0), 0.0,
                                  consumed=consumed) == []


def test_phases_order_aavso_between_vigils_and_approach():
    p = planner.PHASES
    assert p.index("vigils") < p.index("aavso") < p.index("approach")


# ---------------- scoring & phrases ----------------

def _aavso_item(kind="alert"):
    base = {"name": "SU Tau", "title": "SU Tau is dimming",
            "date": "2026-08-12", "url": "u", "kind": kind}
    if kind == "campaign":
        base["end"] = "2027-01-01"
    return base


def test_standalone_aavso_boosts_urgency_and_phrases():
    base = {"id": "SU Tau", "kind": "variable", "name": "SU Tau",
            "mag": 11.0}
    plain, p_parts = suggest.score_target(dict(base), _Cfg())[0:2]
    boosted, b_parts = suggest.score_target(
        dict(base, aavso=_aavso_item()), _Cfg())[0:2]
    assert b_parts["urgency"] - p_parts["urgency"] == pytest.approx(6)
    assert boosted > plain
    phrase = suggest.why_phrase(dict(base, aavso=_aavso_item()), _Cfg())
    assert "AAVSO" in phrase["es"] and "AAVSO" in phrase["en"]


def test_fused_aavso_fragment_via_campaign():
    t = {"id": "SU Tau", "kind": "variable", "name": "SU Tau",
         "mag": 11.0,
         "campaign": {"id": 1, "name": "C", "overdue_days": 0,
                      "cadence_nights": 3, "never_visited": False,
                      "event": None, "aavso": _aavso_item("campaign")}}
    phrase = suggest.why_phrase(t, _Cfg())
    assert "Campaña AAVSO activa" in phrase["es"]
    assert "Active AAVSO campaign" in phrase["en"]


# ---------------- settings widget ----------------

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def test_settings_dialog_has_the_aavso_checkbox(qapp):
    from nightscribe.gui.main_window import _load_ui
    dlg = _load_ui("settings_dialog")
    assert hasattr(dlg, "chk_aavso") and hasattr(dlg, "edt_vigils")


def test_on_open_settings_maps_aavso_and_vigils(qapp):
    # the dialog is modal; assert the wiring exists in the source (the
    # pattern of test_settings_storage.py)
    import inspect
    from nightscribe.gui import main_window as mw
    src = inspect.getsource(mw.MainWindow.on_open_settings)
    assert 'config.get("aavso_feed"' in src
    assert 'config.set("aavso_feed", dlg.chk_aavso.isChecked())' in src
    assert 'config.set("vigil_list"' in src
