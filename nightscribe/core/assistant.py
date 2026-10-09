############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Grounded conversational assistant (ADR-075)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The assistant: one conversation, three scopes (ADR-075).

The same window answers about the object you are working on, about the app
itself, or about the editor you have in front. What changes is the GROUND:
the object's brief, the user guide and the ADRs, or the editor's state plus
the documents. The model only phrases what the ground says.

The honesty rule is the whole point: the context is the ONLY source, the
model is told to say "I do not know" when the answer is not in it, and the
sources we show are the ones we actually injected (we do not trust the
model to cite them). For the editor, the app computes the state and the
next step; the model explains them, it never decides them.
"""

import logging

from . import docs_index
from .sources import llm

logger = logging.getLogger(__name__)

SCOPE_OBJECT = "object"
SCOPE_APP = "app"
SCOPE_EDITOR = "editor"

# How many past turns of the conversation travel with the question. Small on
# purpose: a long history crowds the ground out and a small model loses the
# thread anyway.
HISTORY_TURNS = 6

# The answer budget. It also has to cover a reasoning model's "thinking",
# which counts against the same cap: too small and the answer comes back
# empty (measured on a local reasoning model: 8000 was enough for a post).
MAX_TOKENS = 8000


def _system(lang):
    # @args: lang - "es"|"en"
    # @return: the system prompt (the contract: only the context, no invented
    #          facts, every classification or figure explained)
    where = "Spanish" if lang == "es" else "English"
    return (
        "You are NightScribe's assistant. NightScribe is a desktop app for "
        "amateur astronomy observatories: it plans the night, measures "
        "photometry and astrometry, and reports.\n"
        "Answer the observer's question using ONLY the CONTEXT provided. If "
        "the answer is not in the context, say you do not know: never guess, "
        "never invent a figure, a date or a classification.\n"
        "When you mention a classification or a figure, explain what it means "
        "and why it matters, in plain words.\n"
        "Be concise and practical. Answer in " + where + ".\n"
        "If the question asks what to do next, use the next step in the "
        "context when there is one; do not invent steps."
    )


_STATE_LABELS = {
    "project": {"es": "Proyecto", "en": "Project"},
    "kind": {"es": "Tipo", "en": "Kind"},
    "tab": {"es": "Pestaña activa", "en": "Active tab"},
    "loaded": {"es": "Cargado", "en": "Loaded"},
    "ready": {"es": "Listo", "en": "Ready"},
    "missing": {"es": "Falta", "en": "Missing"},
    "next_step": {"es": "Siguiente paso", "en": "Next step"},
}


def format_editor_state(state, lang="es"):
    # Turns the editor snapshot into a readable block for the prompt.
    # @args: state - a dict with the keys in _STATE_LABELS (missing keys are
    #        skipped), lang - "es"|"en"
    # @return: the block, or "" when there is nothing to say
    if not state:
        return ""
    lines = []
    for key, labels in _STATE_LABELS.items():
        val = state.get(key)
        if val in (None, "", [], ()):
            continue
        if isinstance(val, (list, tuple)):
            val = ", ".join(str(v) for v in val)
        lines.append(f"- {labels.get(lang, labels['en'])}: {val}")
    return "\n".join(lines)


def _context(scope, question, brief, editor_state, lang):
    # Gathers the ground for a question and the sources to show.
    # @args: scope - SCOPE_*, question - the text, brief - object brief dict
    #        or None, editor_state - dict or None, lang - "es"|"en"
    # @return: (context_text, sources list)
    from . import object_brief
    parts, sources = [], []
    if scope == SCOPE_OBJECT:
        if brief:
            parts.append(object_brief.to_text(brief, lang=lang))
            name = (brief.get("object") or {}).get("name") or ""
            sources.append(("Ficha del proyecto " if lang == "es"
                            else "Project fact sheet ") + name)
    if scope in (SCOPE_APP, SCOPE_EDITOR):
        hits = docs_index.search(question, lang)
        for h in hits:
            parts.append(f"### {h['label']} · {h['heading']}\n{h['text']}")
            sources.append(f"{h['label']} · {h['heading']}")
    if scope == SCOPE_EDITOR and editor_state:
        block = format_editor_state(editor_state, lang)
        if block:
            parts.insert(0, block)
            sources.insert(0, "Estado del editor" if lang == "es"
                           else "Editor state")
    return "\n\n".join(parts), sources


def build_messages(scope, question, history=(), brief=None,
                   editor_state=None, lang="es"):
    # @args: scope - SCOPE_*, question - the text, history - past
    #        {role, content} turns, brief/editor_state - the ground,
    #        lang - "es"|"en"
    # @return: (messages, sources)
    context, sources = _context(scope, question, brief, editor_state, lang)
    messages = [{"role": "system", "content": _system(lang)}]
    for turn in list(history)[-HISTORY_TURNS:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    body = (f"CONTEXT:\n{context}\n\nQUESTION: {question}"
            if context else f"QUESTION: {question}")
    messages.append({"role": "user", "content": body})
    return messages, sources


def ask(cfg, scope, question, history=(), brief=None, editor_state=None):
    # One turn of the conversation.
    # @args: cfg - Config, scope - SCOPE_*, question - the text, history -
    #        past turns, brief/editor_state - the ground
    # @return: {"answer": str, "sources": [str]}; raises llm.LlmError
    lang = cfg.ui_language()
    messages, sources = build_messages(scope, question, history=history,
                                       brief=brief, editor_state=editor_state,
                                       lang=lang)
    answer = llm.chat(cfg, messages, max_tokens=MAX_TOKENS)
    return {"answer": (answer or "").strip(), "sources": sources}
