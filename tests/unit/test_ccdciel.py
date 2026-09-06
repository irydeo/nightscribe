############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: CCDciel JSON-RPC client (ADR-030)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The client talks JSON-RPC 2.0 to a local CCDciel (http://host:3277/jsonrpc)
per the official script reference (2026-05-25). No network here: requests.post
is replaced by a faker that records the framed payloads and serves canned
responses. Reads must go through the db.http_get cache and never straight to
the server twice within the TTL.
"""

import requests
import pytest

from nightscribe.core.sources import ccdciel


class _Resp:
    # Minimal stand-in for requests.Response
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def _ok(value):
    return {"jsonrpc": "2.0", "result": value, "id": 1}


def _cmd_ok():
    return _ok({"status": "OK!"})


class _FakePost:
    # Records JSON-RPC requests; serves bodies in order, one per call.
    def __init__(self, bodies=None):
        self.calls = []
        self.bodies = list(bodies or [])
        self.raises = None

    def __call__(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.raises is not None:
            raise self.raises
        if self.bodies:
            return _Resp(self.bodies.pop(0))
        return _Resp(_cmd_ok())

    @property
    def methods(self):
        return [c["json"]["method"] for c in self.calls]


@pytest.fixture
def ccd_db(tmp_db, monkeypatch):
    # Point the module-level db singleton at a throwaway file (the real one
    # must never see a cache write).
    monkeypatch.setattr(ccdciel, "db", tmp_db)
    return tmp_db


@pytest.fixture
def fake_post(monkeypatch):
    fake = _FakePost()
    monkeypatch.setattr(ccdciel.requests, "post", fake)
    return fake


@pytest.fixture
def client():
    return ccdciel.Client("127.0.0.1", 3277)


# ---------------- transport / framing ----------------

def test_framing_no_params(client, fake_post):
    client.call("Telescope_track")
    req = fake_post.calls[0]
    assert req["url"] == "http://127.0.0.1:3277/jsonrpc"
    assert req["json"]["jsonrpc"] == "2.0"
    assert req["json"]["method"] == "Telescope_track"
    assert req["json"]["id"] == 1
    assert "params" not in req["json"]
    assert req["timeout"] > 0


def test_framing_with_params(client, fake_post):
    client.set_filter(2)
    assert fake_post.calls[0]["json"]["params"] == [2]


def test_command_ok_envelope_friendly(client, fake_post):
    assert client.call("Capture_start") == {"status": "OK!"}


def test_command_failed_raises(client, fake_post):
    fake_post.bodies = [_ok({"status": "Failed!", "error": "camera busy"})]
    with pytest.raises(ccdciel.CCDcielError, match="camera busy"):
        client.call("Capture_start")


def test_jsonrpc_error_member_raises(client, fake_post):
    fake_post.bodies = [{"error": {"code": -32601,
                                   "message": "Method not found"}}]
    with pytest.raises(ccdciel.CCDcielError, match="Method not found"):
        client.call("Capture_start")


def test_transport_error_wrapped(client, fake_post):
    fake_post.raises = requests.ConnectionError("refused")
    with pytest.raises(ccdciel.CCDcielError):
        client.call("Capture_start")


def test_reject_result_with_error_member(client, fake_post):
    fake_post.bodies = [_ok({"error": "nope"})]
    with pytest.raises(ccdciel.CCDcielError):
        client.slew_target(10.0, 20.0)


# ---------------- reads are cached ----------------

def test_ping_uses_cache(ccd_db, client, fake_post):
    fake_post.bodies = [_ok([2, 20, 1])]
    assert client.ping() == "2.20.1"
    assert client.ping() == "2.20.1"
    # second read comes from the cache: only one HTTP round trip
    assert len(fake_post.calls) == 1


def test_ping_unreachable_returns_none(ccd_db, client, fake_post):
    fake_post.raises = requests.ConnectionError("refused")
    assert client.ping() is None


def test_dashboard_filters_params_and_caches(ccd_db, client, fake_post):
    dash = {"camera": {"temperature": -12.3},
            "mount": {"slewing": False, "tracking": True}}
    fake_post.bodies = [_ok(dash)]
    assert client.dashboard() == dash
    assert client.dashboard() == dash
    assert len(fake_post.calls) == 1  # cached on repeat
    assert fake_post.calls[0]["json"]["params"] == [
        "devices", "mount", "camera", "wheel", "focuser", "capture",
        "sequence"]


def test_dashboard_transport_error_returns_empty(ccd_db, client, fake_post):
    fake_post.raises = requests.ConnectionError("down")
    assert client.dashboard() == {}


def test_filters_read_cached(ccd_db, client, fake_post):
    fake_post.bodies = [_ok(["L", "R"])]
    assert client.filters() == ["L", "R"]
    assert client.filters() == ["L", "R"]
    assert len(fake_post.calls) == 1


# ---------------- coordinates and motion ----------------

def test_apparent_converts_ra_degrees_to_hours(client, fake_post):
    fake_post.bodies = [_ok([10.5, -20.0])]
    ra_h, dec = client.apparent(157.5, -20.0)
    assert ra_h == 10.5
    assert dec == -20.0
    # [PAIR]-style parameter, one positional list (JSON-RPC [[RA, DEC]])
    assert fake_post.calls[0]["json"]["params"] == [[10.5, -20.0]]


def test_slew_j2000_to_apparent_then_async(client, fake_post):
    fake_post.bodies = [_ok([10.5, -20.0]), _cmd_ok()]
    client.slew_target(157.5, -20.0)
    assert fake_post.methods == ["J2000_to_Apparent", "Telescope_slewasync"]
    assert fake_post.calls[1]["json"]["params"] == [[10.5, -20.0]]


def test_sync_j2000_to_apparent_then_sync(client, fake_post):
    fake_post.bodies = [_ok([10.5, -20.0]), _cmd_ok()]
    client.sync_target(157.5, -20.0)
    assert fake_post.methods == ["J2000_to_Apparent", "Telescope_sync"]
    assert fake_post.calls[1]["json"]["params"] == [[10.5, -20.0]]


def test_slewing_live_state_not_cached(client, fake_post):
    fake_post.bodies = [_ok(True), _ok(False)]
    assert client.slewing() is True
    assert client.slewing() is False
    assert len(fake_post.calls) == 2  # live status never lands in the cache


# ---------------- capture settings ----------------

def test_push_plan_sets_settings_in_order(client, fake_post):
    fake_post.bodies = [_cmd_ok(), _cmd_ok(), _cmd_ok(), _cmd_ok()]
    assert client.push_plan(30, 60.0, "SN 2026ziz")
    assert fake_post.methods == ["Capture_setobjectname", "Capture_setexposure",
                                 "Capture_setcount", "Capture_setframetype"]
    assert [c["json"]["params"] for c in fake_post.calls] == [
        ["SN 2026ziz"], [60.0], [30], ["Light"]]


def test_start_capture(client, fake_post):
    client.start_capture()
    assert fake_post.methods == ["Capture_start"]


def test_wheel_getcurrent_filter(client, fake_post):
    fake_post.bodies = [_ok(3)]
    assert client.current_filter() == 3


# ---------------- CcdcielWorker (offscreen) ----------------

@pytest.fixture(scope="module")
def qapp():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication
    return QCoreApplication.instance() or QCoreApplication([])


def _pump(qapp, iters=300):
    # Let queued signals from the worker thread reach the slots.
    for _ in range(iters):
        qapp.processEvents()


def test_ccdciel_worker_runs_action_after_slew_settles(qapp):
    # The action runs, then the worker polls slewing() until idle (no net).
    class FakeClient:
        def __init__(self):
            self.polls = 0

        def slewing(self):
            self.polls += 1
            return self.polls < 3    # twice busy, then the mount rests

    client = FakeClient()
    seen = {}
    from nightscribe.gui.workers import CcdcielWorker
    w = CcdcielWorker(client, lambda c: "staged", poll_slew=True)
    w.finished.connect(lambda res, err: seen.update(res=res, err=err))
    w.start()
    assert w.wait(8000)
    _pump(qapp)
    assert seen.get("res") == "staged"
    assert seen.get("err") == ""
    assert client.polls >= 3


def test_ccdciel_worker_reports_ccdciel_error(qapp):
    from nightscribe.core.sources import ccdciel
    seen = {}
    from nightscribe.gui.workers import CcdcielWorker

    def boom(c):
        raise ccdciel.CCDcielError("mount e-stop")

    w = CcdcielWorker(ccdciel.Client(), boom)
    w.finished.connect(lambda res, err: seen.update(res=res, err=err))
    w.start()
    assert w.wait(5000)
    _pump(qapp)
    assert seen.get("res") is None
    assert "mount e-stop" in (seen.get("err") or "")