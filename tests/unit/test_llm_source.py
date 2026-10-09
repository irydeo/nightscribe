############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the LLM source (ADR-075)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""`core/sources/llm` — the OpenAI-compatible client. The network is faked
at `requests.post`, so these run offline (the unit conftest would fail any
real call anyway). What matters here: the URL is built right, the key rides
in the header and NOWHERE else (never in an error the user will see), and a
local server with no key is a first-class case."""

import pytest
import requests

from nightscribe.core.sources import llm


class _Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _Cfg:
    def __init__(self, **v):
        self._v = {"ai_base_url": "", "ai_api_key": "", "ai_model": "",
                   "ai_temperature": 0.7}
        self._v.update(v)

    def get(self, k, d=None):
        return self._v.get(k, d)


def _ok(content="hola"):
    return _Resp(200, {"choices": [{"message": {"content": content}}]})


def test_not_configured_without_base_or_model():
    assert not llm.is_configured(_Cfg())
    assert not llm.is_configured(_Cfg(ai_base_url="http://x/v1"))
    assert not llm.is_configured(_Cfg(ai_model="qwen"))
    # a local server needs no key: base + model is enough
    assert llm.is_configured(_Cfg(ai_base_url="http://localhost:11434/v1",
                                  ai_model="qwen2.5:7b"))


def test_is_enabled_needs_the_switch_and_an_endpoint():
    # ADR-075: the master switch is authoritative. An endpoint alone is not
    # enough (the observer may have turned the AI off), and the switch alone
    # is not either (there is nothing to talk to).
    full = dict(ai_base_url="http://localhost:11434/v1",
                ai_model="qwen2.5:7b")
    assert not llm.is_enabled(_Cfg(**full))               # off by default
    assert not llm.is_enabled(_Cfg(ai_enabled=True))      # no endpoint
    assert llm.is_enabled(_Cfg(ai_enabled=True, **full))  # on + endpoint


def test_chat_returns_the_reply(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, data=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers
        seen["body"] = data
        return _ok("la curva sube")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    cfg = _Cfg(ai_base_url="http://localhost:11434/v1/", ai_model="qwen",
               ai_api_key="secret")
    out = llm.chat(cfg, [{"role": "user", "content": "hi"}])
    assert out == "la curva sube"
    # the trailing slash is normalised and the endpoint appended
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert '"model": "qwen"' in seen["body"]


def test_local_server_sends_no_authorization(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, data=None, timeout=None):
        seen["headers"] = headers
        return _ok()

    monkeypatch.setattr(llm.requests, "post", fake_post)
    cfg = _Cfg(ai_base_url="http://localhost:11434/v1", ai_model="qwen")
    llm.chat(cfg, [{"role": "user", "content": "hi"}])
    assert "Authorization" not in seen["headers"]


def test_http_error_is_raised_without_leaking_the_key(monkeypatch):
    def fake_post(url, headers=None, data=None, timeout=None):
        return _Resp(401, text="invalid api key: secret")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    cfg = _Cfg(ai_base_url="http://x/v1", ai_model="m", ai_api_key="TOPSECRET")
    with pytest.raises(llm.LlmError) as ei:
        llm.chat(cfg, [{"role": "user", "content": "hi"}])
    assert "401" in str(ei.value)
    # our key never appears in the message (the body is the server's own)
    assert "TOPSECRET" not in str(ei.value)


def test_network_failure_is_an_llm_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(llm.requests, "post", boom)
    cfg = _Cfg(ai_base_url="http://x/v1", ai_model="m")
    with pytest.raises(llm.LlmError):
        llm.chat(cfg, [{"role": "user", "content": "hi"}])


def test_bad_shape_is_an_llm_error(monkeypatch):
    monkeypatch.setattr(llm.requests, "post",
                        lambda *a, **k: _Resp(200, {"nope": 1}))
    cfg = _Cfg(ai_base_url="http://x/v1", ai_model="m")
    with pytest.raises(llm.LlmError):
        llm.chat(cfg, [{"role": "user", "content": "hi"}])


def test_chat_refuses_when_unconfigured():
    with pytest.raises(llm.LlmError):
        llm.chat(_Cfg(), [{"role": "user", "content": "hi"}])


def test_test_connection_reports_ok_and_failure(monkeypatch):
    cfg = _Cfg(ai_base_url="http://x/v1", ai_model="m")
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _ok("ok"))
    ok, msg = llm.test_connection(cfg)
    assert ok and "ok" in msg

    # a reasoning model can answer with no visible text: the connection
    # still works and the message says so instead of "Connected: "
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _ok(""))
    ok, msg = llm.test_connection(cfg)
    assert ok and "no text" in msg

    monkeypatch.setattr(llm.requests, "post",
                        lambda *a, **k: _Resp(500, text="boom"))
    ok, msg = llm.test_connection(cfg)
    assert not ok and "500" in msg

    ok, msg = llm.test_connection(_Cfg())
    assert not ok


def test_list_models_reads_the_openai_shape(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers
        return _Resp(200, {"object": "list", "data": [
            {"id": "qwen2.5:7b"}, {"id": "llama3.2:latest"}]})

    monkeypatch.setattr(llm.requests, "get", fake_get)
    cfg = _Cfg(ai_base_url="http://localhost:11434/v1/")
    out = llm.list_models(cfg)
    assert out == ["llama3.2:latest", "qwen2.5:7b"]     # sorted
    assert seen["url"] == "http://localhost:11434/v1/models"
    assert "Authorization" not in seen["headers"]        # a local server


def test_list_models_reads_the_native_shape(monkeypatch):
    monkeypatch.setattr(
        llm.requests, "get",
        lambda *a, **k: _Resp(200, {"models": [{"name": "phi3"}]}))
    assert llm.list_models(_Cfg(ai_base_url="http://x/v1")) == ["phi3"]


def test_list_models_needs_a_base():
    with pytest.raises(llm.LlmError):
        llm.list_models(_Cfg())


def test_list_models_error_is_safe(monkeypatch):
    monkeypatch.setattr(llm.requests, "get",
                        lambda *a, **k: _Resp(500, text="boom"))
    cfg = _Cfg(ai_base_url="http://x/v1", ai_api_key="SECRET")
    with pytest.raises(llm.LlmError) as ei:
        llm.list_models(cfg)
    assert "500" in str(ei.value) and "SECRET" not in str(ei.value)


def test_list_models_empty_is_an_error(monkeypatch):
    monkeypatch.setattr(llm.requests, "get",
                        lambda *a, **k: _Resp(200, {"data": []}))
    with pytest.raises(llm.LlmError):
        llm.list_models(_Cfg(ai_base_url="http://x/v1"))
