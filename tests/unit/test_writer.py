############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the post writer (ADR-075)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""`core/writer` — the prompt and the tolerant JSON reader. No network: the
LLM call is monkeypatched. The two things that must hold: the prompt carries
the brief AND the honesty rules, and a malformed answer is a clean failure
(so the caller falls back to the template) rather than a half-post."""

import pytest

from nightscribe.core import object_brief, writer
from nightscribe.core.sources import llm


def _cfg():
    class C:
        def get(self, k, d=None):
            return d
    return C()


def _brief():
    return {
        "language": "es",
        "object": {"name": "SN 2026abc", "kind": "sn",
                   "kind_label": "Supernovae", "status": "active"},
        "object_facts": [{"label": "Tipo de evento", "value": "SN Ia",
                          "why": "Una enana blanca que estalla",
                          "level": "basic"}],
        "night": {},
        "observations": {"n_points": 3, "n_nights": 3, "filters": ["Clear"],
                         "latest": {"date": "2026-10-02", "filter": "Clear",
                                    "mag": 15.6, "err": 0.03},
                         "campaign": {"points": 3, "slope_mag_per_day": 0.3,
                                      "verdict": "normal"}},
        "assets": [],
        "observatory": {"name": "Observatorio Irydeo", "mpc": "Z41"},
    }


def test_hashtags_include_the_mpc_code():
    tags = writer.hashtags_for(_brief())
    assert "#supernova" in tags
    assert "#MPCZ41" in tags


def test_prompt_carries_the_dossier_and_the_rules():
    brief = _brief()
    msgs = writer.build_messages(brief)
    assert msgs[0]["role"] == "system"
    # the honesty contract is in the system message
    assert "ONLY the facts" in msgs[0]["content"]
    assert "Never leave a bare code" in msgs[0]["content"]
    user = msgs[1]["content"]
    assert "SN 2026abc" in user
    assert "Tipo de evento" in user          # the explained fact travelled
    assert "#MPCZ41" in user
    # the dossier rendering is the same one the preview shows
    assert object_brief.to_text(brief) in user


def test_parse_plain_json():
    out = writer.parse_post('{"es":"hola","en":"hi","tweet":"hey #astro"}')
    assert out == {"es": "hola", "en": "hi", "tweet": "hey #astro"}


def test_parse_fenced_and_wrapped_json():
    raw = 'Sure!\n```json\n{"es":"a","en":"b","tweet":"c"}\n```\nDone.'
    assert writer.parse_post(raw) == {"es": "a", "en": "b", "tweet": "c"}


@pytest.mark.parametrize("raw", [
    None, "", "no json here", '{"es":"a","en":"b"}',
    '{"es":"a","en":"b","tweet":""}', '{"es":1,"en":"b","tweet":"c"}',
    "[1,2,3]",
])
def test_parse_rejects_anything_incomplete(raw):
    assert writer.parse_post(raw) is None


def test_write_post_returns_the_parsed_draft(monkeypatch):
    monkeypatch.setattr(llm, "chat",
                        lambda *a, **k: '{"es":"hola","en":"hi","tweet":"yo"}')
    out = writer.write_post(_brief(), cfg=_cfg())
    assert out == {"es": "hola", "en": "hi", "tweet": "yo"}


def test_write_post_raises_on_garbage(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "I cannot help with that")
    with pytest.raises(llm.LlmError):
        writer.write_post(_brief(), cfg=_cfg())


# ---------------- the long report (2026-10-09) ----------------

def test_report_prompt_asks_for_the_article_and_the_images():
    brief = _brief()
    brief["gallery"] = [{"key": "orbit", "name": "SN2026abc_orbit.png",
                         "caption": {"es": "Órbita", "en": "Orbit"}}]
    msgs = writer.build_messages_report(brief)
    system = msgs[0]["content"]
    # the article contract and the exact JSON keys live in the system message
    assert "LONG" in system or "full article" in system
    assert "report_es" in system and "report_en" in system
    # the image list (with the exact file name) reaches the model
    user = msgs[1]["content"]
    assert "SN2026abc_orbit.png" in user
    assert "IMAGES WE MADE" in user


def test_parse_report_requires_the_article_keys():
    # the report is only the article now (the short post is a second call):
    # a JSON without report_es/report_en is not a report
    ok = writer.parse_report('{"report_es":"a","report_en":"b"}')
    assert ok == {"report_es": "a", "report_en": "b"}
    assert writer.parse_report('{"es":"c","en":"d","tweet":"e"}') is None


def test_write_report_makes_two_calls(monkeypatch):
    # one call for the article, one for the short post + tweet: the article
    # is not shortened to make room for the short pieces
    calls = {"n": 0}

    def fake_chat(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return '{"report_es":"A","report_en":"B"}'
        return '{"es":"c","en":"d","tweet":"e"}'

    monkeypatch.setattr(llm, "chat", fake_chat)
    out = writer.write_report(_brief(), cfg=_cfg())
    assert calls["n"] == 2
    assert out == {"report_es": "A", "report_en": "B",
                   "es": "c", "en": "d", "tweet": "e"}


def test_write_report_survives_a_short_post_failure(monkeypatch):
    # the article is the point: if the second call fails, the report is kept
    # and the worker fills the short pieces with the template
    calls = {"n": 0}

    def fake_chat(*a, **k):
        calls["n"] += 1
        return '{"report_es":"A","report_en":"B"}' if calls["n"] == 1 \
            else "not json"

    monkeypatch.setattr(llm, "chat", fake_chat)
    out = writer.write_report(_brief(), cfg=_cfg())
    assert out["report_es"] == "A"
    assert "es" not in out


def test_write_report_raises_on_garbage(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "no json")
    with pytest.raises(llm.LlmError):
        writer.write_report(_brief(), cfg=_cfg())
