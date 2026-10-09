############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the grounded assistant (ADR-075)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""`core/assistant` — the conversation's ground and rules. No network: the
LLM call is monkeypatched. What must hold: the context is the only source,
the sources we show are the ones we injected, and the editor's next step
comes from the app, never from the model."""

import pytest

from nightscribe.core import assistant
from nightscribe.core.sources import llm


def _brief():
    return {
        "language": "es",
        "object": {"name": "SN 2026abc", "kind": "sn",
                   "kind_label": "Supernovae"},
        "object_facts": [{"label": "Tipo de evento", "value": "SN Ia",
                          "why": "Una enana blanca", "level": "basic"}],
        "night": {}, "observations": {}, "assets": [],
        "observatory": {"name": "Irydeo", "mpc": "Z41"},
    }


class _Cfg:
    def ui_language(self):
        return "es"

    def get(self, k, d=None):
        return {"ai_temperature": 0.7}.get(k, d)


def test_the_system_prompt_is_the_honesty_contract():
    msgs, _ = assistant.build_messages(assistant.SCOPE_APP, "hola", lang="es")
    sys = msgs[0]["content"]
    assert "ONLY the CONTEXT" in sys
    assert "do not know" in sys
    assert "never invent" in sys


def test_object_scope_carries_the_brief():
    msgs, sources = assistant.build_messages(
        assistant.SCOPE_OBJECT, "¿qué es?", brief=_brief(), lang="es")
    body = msgs[-1]["content"]
    assert "SN 2026abc" in body
    assert "Tipo de evento" in body
    assert sources and "SN 2026abc" in sources[0]


def test_app_scope_pulls_the_documents():
    msgs, sources = assistant.build_messages(
        assistant.SCOPE_APP, "cómo calibro las tomas", lang="es")
    assert "### " in msgs[-1]["content"]
    assert sources


def test_editor_scope_includes_the_state_and_its_next_step():
    state = {"project": "SN 2026abc", "tab": "Fotometría",
             "loaded": ["12 tomas"], "missing": ["comparadas"],
             "next_step": "Elegir las comparadas en la carta de comparación"}
    msgs, sources = assistant.build_messages(
        assistant.SCOPE_EDITOR, "¿puedo hacer la curva?", editor_state=state,
        lang="es")
    body = msgs[-1]["content"]
    assert "Siguiente paso" in body
    assert "comparadas" in body
    assert "Estado del editor" in sources


def test_format_editor_state_skips_empty_keys():
    txt = assistant.format_editor_state(
        {"project": "X", "missing": [], "next_step": ""}, lang="en")
    assert "Project: X" in txt
    assert "Missing" not in txt


def test_ask_returns_the_answer_and_the_injected_sources(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "  la respuesta  ")
    out = assistant.ask(_Cfg(), assistant.SCOPE_OBJECT, "¿qué es?",
                        brief=_brief())
    assert out["answer"] == "la respuesta"
    assert out["sources"]


def test_history_is_capped(monkeypatch):
    seen = {}

    def fake(cfg, messages, **k):
        seen["n"] = len(messages)
        return "ok"

    monkeypatch.setattr(llm, "chat", fake)
    history = [{"role": "user", "content": f"q{i}"} for i in range(20)]
    assistant.ask(_Cfg(), assistant.SCOPE_APP, "now", history=history)
    # system + at most HISTORY_TURNS turns + the current question
    assert seen["n"] <= assistant.HISTORY_TURNS + 2
