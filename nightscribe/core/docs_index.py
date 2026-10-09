############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Local document index for the assistant (ADR-075)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""A tiny, offline index over the user guide and the ADRs.

The assistant's "about the app" scope answers from the app's own documents,
never from the model's memory: what is not written here is not said. No
embeddings and no network for the first version: the corpus is small (a
dozen guide chapters and the ADRs), so a keyword score is enough and can be
read, tested and trusted. If it ever falls short, embeddings are a later
step, not a hidden dependency now.

The documents are bilingual. A query in Spanish reads the Spanish guide and
the Spanish half of each ADR; a query in English reads the English ones.
"""

import logging
import re
from pathlib import Path

from .. import paths

logger = logging.getLogger(__name__)

# Words too common to tell one section from another. Kept small on purpose:
# the score only needs to rank, and an over-long list would hide real terms.
_STOP = {
    "the", "and", "for", "with", "you", "your", "that", "this", "from",
    "are", "was", "were", "can", "not", "but", "its", "how", "what", "why",
    "when", "where", "which", "into", "out", "all", "any", "one", "two",
    "los", "las", "una", "uno", "unos", "unas", "que", "con", "por", "para",
    "como", "del", "los", "este", "esta", "esto", "esa", "ese", "eso", "sus",
    "sin", "mas", "más", "muy", "hay", "tiene", "tienen", "hacer", "hago",
    "puedo", "puede", "quiero", "sobre", "entre", "donde", "cuando", "porque",
}

_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)


def _tokens(text):
    # @args: text - any string
    # @return: the set of meaningful lowercase words (len >= 3, no stopwords)
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def _split_sections(text):
    # @args: text - a markdown document
    # @return: list of (heading, body) split on level 1-3 headings
    out = []
    heading = ""
    body = []
    for line in text.splitlines():
        if re.match(r"^#{1,3} ", line):
            if heading or body:
                out.append((heading, "\n".join(body).strip()))
            heading = line.lstrip("# ").strip()
            body = []
        else:
            body.append(line)
    if heading or body:
        out.append((heading, "\n".join(body).strip()))
    return out


def _lang_slice(text, lang):
    # The ADRs carry both languages in one file, split by "## Español" and
    # "## English". Keep only the wanted half (the guide files are already
    # one language each).
    # @args: text - the ADR file, lang - "es"|"en"
    # @return: the wanted half, or the whole text when there is no split
    marker = "## Español" if lang == "es" else "## English"
    other = "## English" if lang == "es" else "## Español"
    i = text.find(marker)
    if i == -1:
        return text
    j = text.find(other, i + len(marker))
    return text[i + len(marker):j if j != -1 else len(text)]


def _files(lang):
    # @args: lang - "es"|"en"
    # @return: list of (label, Path) to index
    docs = paths.docs_dir()
    out = []
    user = docs / "user"
    if user.is_dir():
        for p in sorted(user.glob("*.md")):
            es = p.name.endswith(".es.md")
            if (lang == "es") == es:
                out.append((f"user/{p.name}", p))
    adr = docs / "adr"
    if adr.is_dir():
        for p in sorted(adr.glob("ADR-*.md")):
            out.append((f"adr/{p.name}", p))
    return out


_CACHE = {}


def _chunks(lang):
    # @args: lang - "es"|"en"
    # @return: the cached list of chunks: {label, heading, text, tokens}
    if lang in _CACHE:
        return _CACHE[lang]
    chunks = []
    for label, p in _files(lang):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as err:
            logger.warning("docs index: cannot read %s: %s", p, err)
            continue
        if label.startswith("adr/"):
            text = _lang_slice(text, lang)
        for heading, body in _split_sections(text):
            if not body:
                continue
            chunks.append({"label": label, "heading": heading, "text": body,
                           "tokens": _tokens(heading + "\n" + body)})
    _CACHE[lang] = chunks
    return chunks


def clear_cache():
    # @return: None; forget the index so the next search re-reads the files
    #          (used when the docs could have changed under our feet)
    _CACHE.clear()


def search(query, lang="es", k=4):
    # @args: query - the question, lang - "es"|"en", k - how many chunks
    # @return: the best chunks: [{label, heading, text, score}], best first,
    #          only those that match at least one query word
    words = _tokens(query)
    if not words:
        return []
    scored = []
    for ch in _chunks(lang):
        head = _tokens(ch["heading"])
        score = 0
        for w in words:
            if w in head:
                score += 3              # a hit in the title is worth more
            elif w in ch["tokens"]:
                score += 1
        if score:
            scored.append({"label": ch["label"], "heading": ch["heading"],
                           "text": ch["text"], "score": score})
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:k]
