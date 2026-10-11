############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: MPC submission source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The submission POST, offline: the URL, the form fields and the honest
answer. No real submission ever leaves a test."""

from nightscribe.core.sources import mpc_submit


class _Resp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text


def test_mpc80_posts_the_batch_to_submit_obs(monkeypatch):
    calls = {}

    def fake_post(url, files=None, data=None, timeout=None):
        calls.update(url=url, files=files, data=data)
        return _Resp(200, "CurlID: abc123 - batch received")

    monkeypatch.setattr(mpc_submit.requests, "post", fake_post)
    out = mpc_submit.submit("mpc80", "COD Z41\n...")
    assert out["ok"] is True
    assert calls["url"].endswith("/submit_obs")
    # MPC 1992 carries AC2 in its own header: no form fields
    assert calls["data"] == {}
    assert calls["files"]["source"][1].startswith(b"COD Z41")


def test_ades_psv_sends_ack_ac2_and_obj_type(monkeypatch):
    calls = {}

    def fake_post(url, files=None, data=None, timeout=None):
        calls.update(url=url, data=data)
        return _Resp(200, "Batch transmitted")

    monkeypatch.setattr(mpc_submit.requests, "post", fake_post)
    out = mpc_submit.submit("ades", "provID|...", ack="x", email="a@b.c",
                            obj_type="NEOCP")
    assert out["ok"] is True
    assert calls["url"].endswith("/submit_psv")
    assert calls["data"] == {"ack": "x", "ac2": "a@b.c",
                             "obj_type": "NEOCP"}


def test_test_mode_hits_the_test_endpoint(monkeypatch):
    calls = {}

    def fake_post(url, files=None, data=None, timeout=None):
        calls["url"] = url
        return _Resp(200, "ok")

    monkeypatch.setattr(mpc_submit.requests, "post", fake_post)
    mpc_submit.submit("xml", "<ades/>", test=True)
    assert calls["url"].endswith("/submit_xml_test")


def test_a_network_error_is_reported_not_raised(monkeypatch):
    def fake_post(*a, **k):
        raise mpc_submit.requests.RequestException("boom")

    monkeypatch.setattr(mpc_submit.requests, "post", fake_post)
    out = mpc_submit.submit("ades", "x")
    assert out["ok"] is False
    assert "Could not reach" in out["text"]


def test_an_error_body_is_not_ok(monkeypatch):
    monkeypatch.setattr(mpc_submit.requests, "post",
                        lambda *a, **k: _Resp(200, "ERROR: bad header"))
    out = mpc_submit.submit("mpc80", "x")
    assert out["ok"] is False


def test_unknown_format_is_refused_before_any_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no network for an unknown format")

    monkeypatch.setattr(mpc_submit.requests, "post", boom)
    out = mpc_submit.submit("nope", "x")
    assert out["ok"] is False and "Unknown" in out["text"]
