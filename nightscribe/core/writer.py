############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Post writer: turn a brief into a bilingual draft
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Asks a language model to write the post from the object brief (ADR-075).

The template in `core/post.py` stays: it is the offline answer and the
fallback. This module is the optional layer on top, and it is deliberately
thin. All the truth lives in the brief; the writer only phrases it, and the
prompt is built so a small model cannot wander:

* it may use ONLY the dossier's facts, so no figure is invented;
* every code or figure must arrive with its meaning, reusing the dossier's
  own explanations (ADR-058), never a bare "SN Ia" or a bare magnitude;
* the two languages must say the same thing;
* the answer is a strict JSON object, which is easy to parse and easy to
  reject: a malformed answer is a failure, not a half-post.

The actual HTTP call lives in `core/sources/llm.py`; here we build the
messages, call it, and parse the reply. No Qt, no network in the tests.
"""

import json
import logging
import re

from . import narrative, prompts
from .sources import llm

logger = logging.getLogger(__name__)

# Enough for a bilingual post plus the tweet. It also has to cover a
# reasoning model's "thinking": those tokens count against the same budget,
# so a tight cap leaves the answer empty (measured on a local reasoning
# model: 3000 and 4000 tokens came back with no text at all, 8000 produced
# the JSON). A runaway reply is still cut by the endpoint.
MAX_TOKENS = 8000

# The LONG report is a bilingual article and nothing else (the short post and
# the tweet are a second call), so the article gets the whole budget. It also
# has to cover a reasoning model's "thinking": those tokens count against the
# same budget. A local server pays nothing for the room; a paid endpoint
# charges for it, which is why the long form is a setting (ADR-075).
#
# Kept at the value the single-call report already proved on real endpoints:
# some OpenAI-compatible servers reject a `max_tokens` above their own cap or
# the model's context, and the call fails outright (seen when this was raised
# to 24000: the report stopped coming out). The article is per-language and
# the model is told to keep it to a substantial but bounded length, so 16000
# is room enough without asking a server for more than it will give.
MAX_TOKENS_REPORT = 16000

# A long bilingual article on a local model can take longer than the post.
# The default chat timeout is 120 s; the report gets more room, because a
# timeout is a failed report and the observer would rather wait than retry.
REPORT_TIMEOUT_S = 300.0


def hashtags_for(brief):
    # The same tags the template uses, so the two paths agree, plus the
    # observatory's MPC code when there is one.
    # @args: brief - build_brief's dict
    # @return: the hashtag string
    kind = (brief.get("object") or {}).get("kind") or ""
    mpc = (brief.get("observatory") or {}).get("mpc") or ""
    tags = narrative.hashtags(kind)
    if mpc:
        tags += f" #MPC{mpc}"
    return tags


def build_messages(brief, brief_text=None):
    # @args: brief - build_brief's dict, brief_text - the rendered dossier
    #        (recomputed here when not given)
    # @return: the OpenAI-style message list
    from . import object_brief
    dossier = (brief_text if brief_text is not None
               else object_brief.to_text(brief))
    tags = hashtags_for(brief)
    user = (f"HASHTAGS: {tags}\n\n"
            f"DOSSIER:\n{dossier}\n\n"
            f"{prompts.POST_USER_TAIL}")
    return [{"role": "system", "content": prompts.POST_SYSTEM},
            {"role": "user", "content": user}]


def build_messages_report(brief, brief_text=None):
    # The long-report prompt: the same dossier, rendered WITH the deep facts
    # and the image list, plus the article rules. It asks for the ARTICLE
    # only; the short post and the tweet are write_post's job.
    # @args: brief - build_brief's dict (built with long=True),
    #        brief_text - the rendered dossier (recomputed here when not given)
    # @return: the OpenAI-style message list
    from . import object_brief
    dossier = (brief_text if brief_text is not None
               else object_brief.to_text(brief, deep=True))
    tags = hashtags_for(brief)
    user = (f"HASHTAGS: {tags}\n\n"
            f"DOSSIER:\n{dossier}\n\n"
            f"{prompts.REPORT_USER_TAIL}")
    return [{"role": "system", "content": prompts.REPORT_SYSTEM},
            {"role": "user", "content": user}]


def _parse_json(text, keys):
    # Tolerant reader for the model's JSON: strips a code fence and finds
    # the outer object, because free models often wrap the JSON in prose.
    # Every key in `keys` must be present and non-empty, or the whole answer
    # is rejected (a half report is worse than a clean failure).
    # @args: text - the model's raw reply, keys - the required keys
    # @return: {key: text} or None when it cannot be read
    if not text:
        return None
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1 or j <= i:
        return None
    try:
        data = json.loads(s[i:j + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    out = {}
    for key in keys:
        val = data.get(key)
        if not isinstance(val, str) or not val.strip():
            return None
        out[key] = val.strip()
    return out


def parse_post(text):
    # @args: text - the model's raw reply
    # @return: {"es","en","tweet"} or None when it cannot be read
    return _parse_json(text, ("es", "en", "tweet"))


def parse_report(text):
    # @args: text - the model's raw reply
    # @return: {"report_es","report_en"} or None. The short post and the
    #          tweet are NOT part of the report any more: they are a second
    #          call, so the article is not shortened to make room for them.
    return _parse_json(text, ("report_es", "report_en"))


def write_post(brief, cfg=None, max_tokens=MAX_TOKENS):
    # The whole AI draft in one call.
    # @args: brief - build_brief's dict, cfg - Config, max_tokens - cap
    # @return: {"es","en","tweet"}; raises llm.LlmError on any failure (the
    #          caller then falls back to the template)
    cfg = cfg or _config()
    raw = llm.chat(cfg, build_messages(brief), max_tokens=max_tokens)
    parsed = parse_post(raw)
    if parsed is None:
        raise llm.LlmError("The model did not return a usable JSON post")
    return parsed


def write_report(brief, cfg=None, max_tokens=MAX_TOKENS_REPORT,
                 timeout=REPORT_TIMEOUT_S):
    # The long report (ADR-075): a bilingual article, and then the short post
    # and the tweet. TWO calls on purpose: asking a small model for a long
    # article AND three short pieces in one JSON made it shorten the article
    # (the defect the observer saw). The article gets its own call and its own
    # budget; the short pieces keep the original, focused call.
    # @args: brief - build_brief(long=True), cfg - Config, max_tokens - cap
    # @return: {"report_es","report_en"} plus {"es","en","tweet"} when the
    #          second call works; raises llm.LlmError only when the REPORT
    #          fails (the caller falls back to the template for the short
    #          pieces when they are missing)
    cfg = cfg or _config()
    raw = llm.chat(cfg, build_messages_report(brief), max_tokens=max_tokens,
                   timeout=timeout)
    parsed = parse_report(raw)
    if parsed is None:
        raise llm.LlmError("The model did not return a usable JSON report")
    out = dict(parsed)
    try:
        out.update(write_post(brief, cfg))
    except llm.LlmError:
        # the article survives; the worker fills the short pieces with the
        # template (the offline answer is always there)
        logger.info("the short post failed after the report; the template "
                    "will fill it")
    return out


def _config():
    # @return: the shared Config (imported lazily so tests can inject one)
    from ..config import config
    return config
