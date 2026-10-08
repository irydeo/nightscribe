############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Website generator: the landing and the user guide
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The NightScribe website, generated from the sources that already exist.

ONE SOURCE, TWO RENDERINGS (ADR-070). The prose is not written twice: the
landing is `README.md` / `README.es.md` and the manual is `docs/user/*.md`,
the very same files the application renders in Help > Documentation. This
script turns them into static HTML for the web, so the page a visitor reads
and the page the observer opens in the app cannot tell different stories.

What it does, in order:

  * reads the palette from `nightscribe/gui/theme.py`, so the site speaks the
    application's colours: the CSS gets them as custom properties and the
    visual identity keeps ONE source;
  * reads the target kinds from `nightscribe/core/kinds.py` (labels, blurbs,
    sources) and their Spanish from the `.ts` catalogue, so the landing's
    cards are the application's own Welcome cards;
  * renders the markdown subset the project writes: headings, paragraphs,
    lists (including the continuation lines and the code blocks inside an
    item), tables, fenced code, quotes, and the `> **Why ...?**` boxes as
    callouts;
  * writes `website/*.html` (the landing, one page per language), the guide
    under `website/docs/` (one page per chapter per language, with a sidebar,
    previous/next and heading anchors) and the assets;
  * is IDEMPOTENT: no timestamps, no counters, the same sources give the same
    bytes, which is what lets a test regenerate the site and compare it with
    what is committed.

It never touches the network and needs no third-party library.

Usage:  python3 website/tools/build_site.py [--out DIR] [--check]
"""

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent           # website/
ROOT = SITE.parent                                      # the repository
GUIDE_SRC = ROOT / "docs" / "user"                      # the manual's sources
I18N = ROOT / "nightscribe" / "gui" / "i18n"
TOOLS = Path(__file__).resolve().parent
ASSETS_SRC = ROOT / "nightscribe" / "assets"

REPO_URL = "https://github.com/irydeo/nightscribe"
SITE_URL = "https://irydeo.github.io/nightscribe"
LICENSE_URL = f"{REPO_URL}/blob/main/LICENSE"
LANGS = ("en", "es")
LANG_LABEL = {"en": "EN", "es": "ES"}


def _suffix(lang):
    # @args: lang - "en" | "es"
    # @return: ".es" for Spanish, "" for English: the repository's own
    #          convention for a language twin (README.es.md, X.es.html)
    return ".es" if lang == "es" else ""


def _other(lang):
    # @args: lang - "en" | "es"
    # @return: the other language
    return "es" if lang == "en" else "en"


def _page_name(stem, lang):
    # @args: stem - a guide page's stem ("README" is the guide's index),
    #        lang - "en" | "es"
    # @return: the file the site gives that page: the index gets a friendly
    #          name, the chapters keep their number
    return f'{"index" if stem == "README" else stem}{_suffix(lang)}.html'


# The short names the landing's navigation shows for the README's sections.
NAV_SHORT = {
    "en": {"What is NightScribe?": "What it is",
           "Your first five minutes": "First five minutes",
           "A whole night (and the weeks after)": "A whole night",
           "What you can do: in detail": "In detail",
           "Where the data comes from": "Data sources",
           "Optional integrations": "Integrations",
           "Your data stays with you": "Your data",
           "Quickstart and CLI": "Quickstart & CLI"},
    "es": {"¿Qué es NightScribe?": "Qué es",
           "Tus primeros cinco minutos": "Primeros cinco minutos",
           "Una noche completa (y las semanas siguientes)": "Una noche completa",
           "Qué puedes hacer: en detalle": "En detalle",
           "De dónde salen los datos": "Fuentes de datos",
           "Integraciones opcionales": "Integraciones",
           "Tus datos se quedan contigo": "Tus datos",
           "Arranque rápido y CLI": "Arranque y CLI"},
}

# The order the README's "what you can follow" bullets come in, matched to the
# catalogue's kind ids. Written down (and checked by the site's test) so a
# reordering or a rewording in the README cannot silently lose a card.
README_KIND_ORDER = ("neo", "comet", "pccp", "sn", "transit", "alert",
                     "hads", "variable")

# The README's sections that are dressed differently: the kinds become cards,
# the "in detail" chapter becomes an accordion.
KINDS_SECTION = ("What you can follow", "Qué puedes seguir")
DETAIL_SECTION = ("What you can do: in detail", "Qué puedes hacer: en detalle")

# The sections the top bar shows. It is a CURATED list, not every heading: a
# bar that lists everything (or that needs a scroll) guides nobody and looks
# crowded, which is what the first attempt got wrong twice. These four plus
# the guide fit on one line in both languages, with room to spare; each title
# has to exist in the README, and the site's test says so.
NAV_MAIN = {
    "en": ("What is NightScribe?", "What you can follow", "What you need",
           "Your first five minutes"),
    "es": ("¿Qué es NightScribe?", "Qué puedes seguir", "Qué necesitas",
           "Tus primeros cinco minutos"),
}

# The screenshots the site shows. They are REAL captures of the application,
# taken with the observer's own data and prepared by tools/prepare_screens.py
# into website/assets/screens/*.webp. A figure is drawn only when its file is
# there, so a capture that is still missing leaves the page whole (and the run
# says which ones are pending).
SHOTS = {
    # name: (English caption, Spanish caption)
    "welcome": ("The Welcome screen: your observatory, your equipment, your "
                "targets, your data",
                "La pantalla de bienvenida: tu observatorio, tu equipo, tus "
                "objetivos, tus datos"),
    "tonight": ("Tonight: the targets ranked for your site and your gear",
                "Esta noche: los objetivos ordenados para tu sitio y tu "
                "equipo"),
    "projects": ("A project, from the object card to publishing",
                 "Un proyecto, de la ficha del objeto a la publicación"),
    "project": ("The object card: what it is, how it moves, when to catch it",
                "La ficha del objeto: qué es, cómo se mueve, cuándo cazarlo"),
    "campaigns": ("Campaigns and vigils: what is due, what is happening",
                  "Campañas y vigilias: lo que toca y lo que está pasando"),
    "capture": ("Capture: the plan, the exposures and CCDciel",
                "Captura: el plan, las exposiciones y CCDciel"),
    "photometry": ("Photometry: the comparison sequence and its recipe",
                   "Fotometría: la secuencia de comparación y su receta"),
    "measure": ("Measuring on the plate, with the manual centre when the "
                "object is faint",
                "Midiendo en la placa, con el centro manual cuando el objeto "
                "es débil"),
    "curve": ("The light curve of the series, point by point",
              "La curva de luz de la serie, punto a punto"),
    "transit": ("An exoplanet transit, reduced and fitted",
                "Un tránsito de exoplaneta, reducido y ajustado"),
    "astrometry": ("The track & stack: the asteroid stands still while the "
                   "stars crawl",
                   "El track & stack: el asteroide se queda quieto mientras "
                   "las estrellas se mueven"),
    "posts": ("Publishing: the bilingual draft and the charts",
              "Publicación: el borrador bilingüe y los gráficos"),
    "settings": ("Settings: every section, with a sensible default",
                 "Ajustes: cada sección, con un valor por defecto sensato"),
}

# The three the landing's strip shows, in order.
LANDING_SHOTS = ("project", "astrometry", "photometry")

# The captures of each guide chapter, by the chapter's stem.
CHAPTER_SHOTS = {
    "01-getting-started": ("welcome",),
    "02-tonight": ("tonight",),
    "03-projects": ("projects",),
    "04-campaigns": ("campaigns",),
    "05-capture": ("capture",),
    "06-photometry": ("photometry", "measure", "curve", "transit"),
    "07-astrometry": ("astrometry",),
    "08-posts": ("posts",),
    "10-settings": ("settings",),
}

# The hero's "at a glance" facts: the same promises the README makes a screen
# below, in four words each.
GLANCE = {
    "en": ["GPL v3, free", "Linux and Windows", "Spanish and English",
           "No account, no telemetry"],
    "es": ["GPL v3, gratis", "Linux y Windows", "Español e inglés",
           "Sin cuenta ni telemetría"],
}

# The page chrome: buttons, navigation and the footer. UI labels, not prose.
CHROME = {
    "en": {"guide": "User guide", "contents": "Contents", "next": "Next",
           "prev": "Previous", "home": "Back to the start",
           "download": "Download", "github": "See it on GitHub",
           "read": "Read the guide", "chapters": "The guide, chapter by "
                                                 "chapter",
           "what": "What it is", "more": "See it in the guide",
           "app": "The app", "app_lead": "Screenshots of the running program, "
                                          "with real observations: not "
                                          "mockups.",
           "on_github": "GitHub",
           "licence": f'<a href="{LICENSE_URL}">GPL v3</a> · '
                      "Francisco José Calvo Fernández, "
                      "Observatorio Irydeo (MPC Z41)"},
    "es": {"guide": "Guía de usuario", "contents": "Índice",
           "next": "Siguiente", "prev": "Anterior",
           "home": "Volver al principio", "download": "Descargar",
           "github": "Verlo en GitHub", "read": "Leer la guía",
           "chapters": "La guía, capítulo a capítulo",
           "what": "Qué es", "more": "Verlo en la guía",
           "app": "La aplicación",
           "app_lead": "Capturas del programa en marcha, con observaciones "
                       "reales: no son maquetas.",
           "on_github": "GitHub",
           "licence": f'<a href="{LICENSE_URL}">GPL v3</a> · '
                      "Francisco José Calvo Fernández, "
                      "Observatorio Irydeo (MPC Z41)"},
}


# ------------------------------------------------------------------ palette

def palette():
    # @return: {name: colour} straight from the application's theme, so the
    #          website cannot drift from the app's own visual identity. The
    #          theme module imports Qt only inside its functions, so this
    #          stays a light import (no QApplication, no display).
    _path()
    from nightscribe.gui import theme
    return {
        "bg": theme.C_BG, "base": theme.C_BASE, "panel": theme.C_PANEL,
        "line": theme.C_LINE, "edge": theme.C_EDGE, "hover": theme.C_HOVER,
        "dim_fill": theme.C_DIM_FILL, "sel": theme.C_SEL,
        "text": theme.C_TEXT, "dim": theme.C_TEXT_DIM,
        "accent": theme.C_ACCENT, "warn": theme.C_WARN, "good": theme.C_GOOD,
        "ok": theme.C_OK,
    }


def kind_colors():
    # @return: {kind id: colour} from the theme: the same hues the Tonight
    #          rows and the Welcome cards wear.
    _path()
    from nightscribe.gui import theme
    return dict(theme.KIND_COLORS)


def _path():
    # Puts the repository on sys.path once, so the generator can read the
    # app's own palette and catalogue instead of copying them.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


# -------------------------------------------------------------------- kinds

def _ts_map(lang, context="NSKinds"):
    # @args: lang - "es" | "en", context - the translation context to read
    # @return: {source: translation} for that context, skipping the entries
    #          the catalogue marks vanished, obsolete or unfinished. Parsed
    #          with the standard library: the site must not need a Qt runtime
    #          just to know how the app names a kind in Spanish.
    import xml.etree.ElementTree as ET
    out = {}
    path = I18N / f"nightscribe_{lang}.ts"
    if not path.is_file():
        return out
    for ctx in ET.parse(path).getroot().findall("context"):
        if ctx.findtext("name") != context:
            continue
        for msg in ctx.findall("message"):
            tr, src = msg.find("translation"), msg.find("source")
            if src is None or tr is None or not (src.text or "").strip():
                continue
            if tr.get("type") in ("vanished", "obsolete", "unfinished"):
                continue
            if (tr.text or "").strip():
                out[src.text] = tr.text
    return out


def kinds_catalogue(lang):
    # @args: lang - "es" | "en"
    # @return: [{"id", "label", "blurb", "source", "color"}], in the
    #          catalogue's own order: the landing's cards, which are the
    #          application's own target kinds.
    _path()
    from nightscribe.core import kinds as catalogue
    from nightscribe.gui import theme
    tr = _ts_map(lang) if lang == "es" else {}
    return [{"id": k["id"],
             "label": tr.get(k["label"], k["label"]),
             "blurb": tr.get(k["blurb"], k["blurb"]),
             "source": tr.get(k["source"], k["source"]),
             "color": theme.KIND_COLORS.get(k["id"], theme.C_ACCENT)}
            for k in catalogue.KINDS]


def _card_blurb(text, limit=200):
    # @args: text - a kind's full blurb, limit - the cut
    # @return: a one-glance version, cut at a sentence or a word boundary.
    #          The same bargain the Welcome cards make: the card is the
    #          glance, the guide is the dossier.
    cut = text.find(". ")
    short = text[:cut + 1] if 0 < cut + 1 <= limit else text
    if len(short) <= limit:
        return short
    head = short[:limit]
    space = head.rfind(" ")
    return (head[:space] if space > 60 else head).rstrip(" ,;:") + "…"


# ------------------------------------------------------------------ markdown

def _esc(text):
    return html.escape(text, quote=False)


_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_EM_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(.*)$")
_FENCE_RE = re.compile(r"^(\s*)```")
_HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_RULE_RE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")


def slug(text):
    # @args: text - a heading's text (it may carry markdown)
    # @return: an id safe for href="#..." and unique enough for the page
    bare = _BOLD_RE.sub(r"\1", _EM_RE.sub(r"\1", _CODE_RE.sub(r"\1", text)))
    bare = _LINK_RE.sub(r"\1", bare)
    bare = re.sub(r"[^\w\s-]", "", bare, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_]+", "-", bare) or "section"


def inline(text, link=None):
    # @args: text - one line of inline markdown, link - a callable(href) that
    #        rewrites a link's target (the .html twin, the language switch),
    #        or None to leave it alone
    # @return: HTML for that line. Order matters: links first (so their
    #          brackets are gone), then inline code (which protects its
    #          content from the bold and italic passes).
    text = _esc(text)

    def _a(match):
        href = link(match.group(2)) if link else match.group(2)
        return f'<a href="{_esc(href)}">{match.group(1)}</a>'

    text = _LINK_RE.sub(_a, text)
    codes = []

    def _protect(match):
        codes.append(f"<code>{match.group(1)}</code>")
        return f"\x00C{len(codes) - 1}\x00"

    text = _CODE_RE.sub(_protect, text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _EM_RE.sub(r"<em>\1</em>", text)
    return re.sub("\x00C(\\d+)\x00", lambda m: codes[int(m.group(1))], text)


def _is_table_sep(line):
    # @args: line - a table's delimiter row (|---|:---:|)
    # @return: True when every cell is only dashes, colons and spaces
    bare = line.strip().strip("|").strip()
    return bool(bare) and all(
        cell.strip() == "" or set(cell.strip()) <= set("-: ")
        for cell in bare.split("|"))


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _alignments(sep):
    # @args: sep - the delimiter row
    # @return: the per-column alignment the markdown asked for
    out = []
    for cell in _cells(sep):
        left, right = cell.startswith(":"), cell.endswith(":")
        out.append("center" if left and right else
                   "right" if right else "left")
    return out


def _code_block(code):
    return f'<pre class="code"><code>{_esc(code)}</code></pre>'


def _quote_html(lines, link):
    # @args: lines - the quote's lines (markers already stripped)
    # @return: the quote as HTML. A quote that opens with a bold question is
    #          one of the project's "Why ...?" boxes: it gets its own class
    #          so the site dresses it as a callout, the way the app does.
    body = " ".join(inline(line, link) for line in lines if line.strip())
    why = bool(re.match(r"^<strong>[^<]*\?</strong>", body))
    return f'<blockquote class="{"why" if why else "quote"}">{body}</blockquote>'


def _item_html(lines, link):
    # @args: lines - one list item's lines (the first is the marker's text,
    #        the rest are continuation lines already dedented)
    # @return: the item's inner HTML: paragraphs, code blocks and quotes. An
    #          item can hold a fenced block (the README's install commands do)
    out, para = [], []

    def flush():
        if para:
            out.append(f'<p>{inline(" ".join(para), link)}</p>')
            para.clear()

    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            flush()
            i += 1
            continue
        m = _FENCE_RE.match(line)
        if m:
            flush()
            i += 1
            code = []
            while i < n and not _FENCE_RE.match(lines[i]):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(_code_block("\n".join(code)))
            continue
        if line.strip().startswith(">"):
            flush()
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(_quote_html(quote, link))
            continue
        para.append(line.strip())
        i += 1
    flush()
    return "".join(out)


def md_to_html(md, link=None):
    # @args: md - a full markdown document, link - the link rewriter
    # @return: (html, [{"level", "id", "text"}]) - the body and the headings
    #          found, which the guide uses for its anchors
    lines = md.replace("\r\n", "\n").split("\n")
    out, heads = [], []
    i, n = 0, len(lines)
    para = []

    def flush():
        if para:
            out.append(f'<p>{inline(" ".join(para), link)}</p>')
            para.clear()

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush()
            i += 1
            continue

        m = _FENCE_RE.match(line)
        if m:
            flush()
            base = len(m.group(1))
            i += 1
            code = []
            while i < n and not _FENCE_RE.match(lines[i]):
                code.append(lines[i][base:] if lines[i][:base].isspace()
                            else lines[i])
                i += 1
            i += 1
            out.append(_code_block("\n".join(code)))
            continue

        m = _HEAD_RE.match(line)
        if m:
            flush()
            level, text = len(m.group(1)), m.group(2).strip()
            anchor = slug(text)
            while any(h["id"] == anchor for h in heads):
                anchor += "-x"
            heads.append({"level": level, "id": anchor, "text": text})
            out.append(f'<h{level} id="{anchor}">{inline(text, link)}'
                       f"</h{level}>")
            i += 1
            continue

        if _RULE_RE.match(line):
            flush()
            out.append("<hr>")
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < n \
                and _is_table_sep(lines[i + 1]):
            flush()
            header, aligns = _cells(line), _alignments(lines[i + 1])
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1

            def _align(k):
                return aligns[k] if k < len(aligns) else "left"

            head = "".join(
                f'<th style="text-align:{_align(k)}">{inline(c, link)}</th>'
                for k, c in enumerate(header))
            body = "".join(
                "<tr>" + "".join(
                    f'<td style="text-align:{_align(k)}">'
                    f"{inline(c, link)}</td>" for k, c in enumerate(row))
                + "</tr>" for row in rows)
            out.append(f'<div class="table-wrap"><table><thead><tr>{head}'
                       f"</tr></thead><tbody>{body}</tbody></table></div>")
            continue

        if stripped.startswith(">"):
            flush()
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(_quote_html(quote, link))
            continue

        m = _ITEM_RE.match(line)
        if m:
            flush()
            ordered = m.group(2)[0].isdigit()
            marker = m.group(1)
            base = len(marker) + len(m.group(2)) + 1
            items = []
            while i < n:
                item = _ITEM_RE.match(lines[i])
                if not item or len(item.group(1)) > len(marker):
                    break
                content = [item.group(3)]
                i += 1
                while i < n:
                    nxt = lines[i]
                    if not nxt.strip():
                        j = i
                        while j < n and not lines[j].strip():
                            j += 1
                        if j < n and lines[j][:base].isspace() \
                                and not _ITEM_RE.match(lines[j]):
                            content.append("")
                            i = j
                            continue
                        break
                    if _ITEM_RE.match(nxt) and len(
                            _ITEM_RE.match(nxt).group(1)) <= len(marker):
                        break
                    if nxt[:base].isspace():
                        content.append(nxt[base:])
                        i += 1
                        continue
                    break
                items.append(content)
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(
                f"<li>{_item_html(it, link)}</li>" for it in items)
                + f"</{tag}>")
            continue

        para.append(line.strip())
        i += 1

    flush()
    return "".join(out), heads


# ------------------------------------------------------------------- shell

def _shell(*, lang, title, description, root, body, page_class, switcher,
           nav=None):
    # @args: lang - "en" | "es", title/description - the page's own,
    #        root - "" or "../" (how far the page is from website/),
    #        body - the page's HTML, page_class - a body class,
    #        switcher - the language twin's href, nav - the section links the
    #        sticky bar shows (the landing only)
    # @return: the whole HTML document, in the application's style
    chrome = CHROME[lang]
    bar_nav = ""
    if nav:
        bar_nav = "".join(f'<a href="{href}">{label}</a>'
                          for href, label in nav)
    # The guide appears twice only where it is not already in the menu: on the
    # landing the menu's last entry IS the guide, so a pill beside it was the
    # duplicate that made the bar crowded. On the guide's own pages there is
    # no menu, and the pill is the way back to its index.
    guide_pill = "" if nav else (
        f'<a class="ghost" href="{root}docs/index{_suffix(lang)}.html">'
        f'{chrome["guide"]}</a>')
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="icon" href="{root}assets/appicon.svg">
<link rel="stylesheet" href="{root}assets/style.css">
</head>
<body class="{page_class}">
<header class="bar">
  <div class="bar-in">
    <a class="brand" href="{root}index{_suffix(lang)}.html">
      <img src="{root}assets/appicon.svg" alt="" width="26" height="26">
      <span class="wordmark">NIGHT<b>SCRIBE</b></span>
    </a>
    <nav class="bar-nav">{bar_nav}</nav>
    <div class="bar-end">
      {guide_pill}
      <a class="lang" href="{switcher}">{LANG_LABEL[_other(lang)]}</a>
    </div>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="foot">
  <p>{chrome["licence"]}</p>
  <p><a href="{REPO_URL}" rel="noopener">{REPO_URL}</a></p>
</footer>
<script src="{root}assets/main.js"></script>
</body>
</html>
"""


# ------------------------------------------------------------------ landing

def _hero_text(md):
    # @args: md - the README
    # @return: (tagline, definition) taken from the README's own opening, so
    #          the hero is the README and not a second copy of it
    lines = [ln.strip() for ln in md.split("\n")]
    tagline = next((ln for ln in lines if ln.startswith("**")
                    and ln.endswith("**")), "")
    start = lines.index(tagline) + 1 if tagline in lines else 0
    definition = []
    for line in lines[start:]:
        if not line:
            if definition:
                break
            continue
        if line.startswith(("#", "*[", ">")):
            break
        definition.append(line)
    return tagline.strip("*"), " ".join(definition)


def _sections(body):
    # @args: body - the rendered README
    # @return: [{"id", "text", "html"}] one entry per <h2>, with the HTML
    #          between it and the next heading
    marks = [(m.start(), m.group(1), m.group(2))
             for m in re.finditer(r'<h2 id="([^"]+)">(.*?)</h2>', body, re.S)]
    out = []
    for k, (start, anchor, title) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        out.append({"id": anchor,
                    "text": re.sub(r"<[^>]+>", "", title),
                    "title": title.strip(),
                    "html": body[body.index("</h2>", start) + 5:end]})
    return out


def _figure(name, lang, root=""):
    # @args: name - a shot's name (see SHOTS), lang - the page's language,
    #        root - "" or "../" (how far the page is from website/)
    # @return: the figure's HTML, or "" when the capture is not there yet.
    #          The page is never broken by a missing shot: the run says which
    #          ones are pending instead.
    image = SITE / "assets" / "screens" / f"{name}.webp"
    if not image.is_file():
        return ""
    caption = SHOTS.get(name, ("", ""))[0 if lang == "en" else 1]
    return (f'<figure class="shot">'
            f'<img src="{root}assets/screens/{name}.webp" '
            f'alt="{html.escape(caption)}" loading="lazy">'
            f'<figcaption>{html.escape(caption)}</figcaption></figure>')


def _shots(names, lang, root=""):
    # @args: names - the shots to draw, lang, root - the path prefix
    # @return: the figures that exist, wrapped in their grid (or "" when none)
    figures = "".join(_figure(n, lang, root) for n in names)
    return f'<div class="shots">{figures}</div>' if figures else ""


def _kinds_cards(lang):
    # @args: lang - "es" | "en"
    # @return: the target kinds as cards: the chip and the colour the app
    #          gives each kind, its one-glance blurb, its data source and a
    #          link to the guide. It is the "what can it do" answer, in the
    #          app's own language.
    chrome = CHROME[lang]
    guide = f'docs/index{_suffix(lang)}.html'
    cards = []
    for kind in kinds_catalogue(lang):
        cards.append(
            f'<article class="kind" style="--kind:{kind["color"]}">'
            f'<header><span class="chip">{html.escape(kind["label"])}</span>'
            f"</header>"
            f"<p>{html.escape(_card_blurb(kind['blurb']))}</p>"
            f'<p class="kind-src">{html.escape(kind["source"])}</p>'
            f'<a class="more" href="{guide}">{chrome["more"]} →</a>'
            f"</article>")
    return f'<div class="kinds">{"".join(cards)}</div>'


def _accordion(section_html):
    # @args: section_html - a section whose subsections are h3s
    # @return: the same, with each h3 and its content folded into <details>,
    #          so the landing stays scannable
    parts = re.split(r'(<h3 id="[^"]+">)', section_html)
    if len(parts) < 3:
        return section_html
    out = [parts[0]]
    for k in range(1, len(parts), 2):
        chunk = parts[k + 1]
        title = chunk[:chunk.index("</h3>")]
        rest = chunk[chunk.index("</h3>") + 5:]
        out.append(f'<details class="detail"><summary>{title}</summary>'
                   f'<div class="detail-body">{rest}</div></details>')
    return "".join(out)


def _landing_link(href, lang):
    # @args: href - a link found in the README, lang - the page's language
    # @return: where that link goes on the site: the guide's pages stay in
    #          the site (in this language), the language twin goes to the
    #          other landing, and anything else (a repo file, a folder) goes
    #          to the repository, where it is readable as it is
    if href.startswith(("http://", "https://", "#", "mailto:")):
        return href
    if href.endswith(".md"):
        twin = href.endswith(".es.md")
        base = href[:-len(".es.md")] if twin else href[:-len(".md")]
        if base == "README":
            return f"index{_suffix('es' if twin else 'en')}.html"
        if base.startswith("docs/user/"):
            stem = base[len("docs/user/"):]
            if stem == "README":
                return f"docs/index{_suffix('es' if twin else 'en')}.html"
            return f"docs/{stem}{_suffix(lang)}.html"
        return f"{REPO_URL}/blob/main/{base}.md"
    if href.startswith("docs/user"):
        return f"docs/index{_suffix(lang)}.html"
    if href.startswith("docs/"):
        return f"{REPO_URL}/tree/main/{href.rstrip('/')}"
    return href


def build_landing(lang):
    # @args: lang - "en" | "es"
    # @return: the landing's HTML: one long page, navigation by sections
    md = (ROOT / f"README{_suffix(lang)}.md").read_text(encoding="utf-8")
    chrome = CHROME[lang]
    tagline, definition = _hero_text(md)
    first_section = next((k for k, ln in enumerate(md.split("\n"))
                          if ln.startswith("## ")), 0)
    body, _heads = md_to_html(
        "\n".join(md.split("\n")[first_section:]),
        lambda href: _landing_link(href, lang))

    sections = []
    for sec in _sections(body):
        if sec["text"] in KINDS_SECTION:
            # the section's own introduction stays (the cards replace the
            # bullets, not the paragraph that says what the list is)
            cut = sec["html"].find("<ul>")
            lead = sec["html"][:cut] if cut >= 0 else ""
            sec["html"] = lead + _kinds_cards(lang)
        if sec["text"] in DETAIL_SECTION:
            sec["html"] = _accordion(sec["html"])
        sections.append(sec)
    # the bar shows the curated sections and the guide block the page adds
    wanted = NAV_MAIN[lang]
    nav = [(f'#{s["id"]}', _nav_label(s, lang)) for s in sections
           if s["text"] in wanted]
    nav.append(("#guide", chrome["guide"]))

    glance = "".join(f'<span class="glance">{html.escape(g)}</span>'
                     for g in GLANCE[lang])
    # The README's sections, in order, with the captures' strip right after
    # the target kinds: by then the visitor knows what the app does and can
    # see it.
    parts = []
    for sec in sections:
        parts.append(f'<section class="block" id="{sec["id"]}">'
                     f'<h2>{sec["title"]}</h2>{sec["html"]}</section>')
        if sec["text"] in KINDS_SECTION:
            shots = _shots(LANDING_SHOTS, lang)
            if shots:
                parts.append(f'<section class="block" id="shots">'
                             f'<h2>{chrome["app"]}</h2>'
                             f'<p class="lead">{chrome["app_lead"]}</p>'
                             f"{shots}</section>")
    sections_html = "".join(parts)
    chapters = "".join(
        f'<a class="chapter" href="docs/{c["stem"]}{_suffix(lang)}.html">'
        f'<span class="chapter-n">{html.escape(c["num"])}</span>'
        f'<span class="chapter-t">{html.escape(c["title"][lang])}</span></a>'
        for c in _chapters())

    body_html = f"""<div class="hero">
  <img class="hero-sky" src="assets/welcome_sky.svg" alt="" aria-hidden="true">
  <div class="hero-in">
    <p class="hero-kicker">NightScribe · GPL v3</p>
    <h1 class="hero-title">NIGHT<b>SCRIBE</b></h1>
    <p class="hero-tag">{html.escape(tagline)}</p>
    <p class="hero-what">{html.escape(definition)}</p>
    <p class="hero-cta">
      <a class="btn primary" href="{REPO_URL}/releases">{chrome["download"]}</a>
      <a class="btn" href="{REPO_URL}" rel="noopener">{chrome["github"]}</a>
      <a class="btn ghost" href="docs/index{_suffix(lang)}.html">{chrome["read"]}</a>
    </p>
    <p class="hero-glance">{glance}</p>
  </div>
</div>

""" + sections_html + f"""
<section class="block" id="guide">
  <h2>{chrome["guide"]}</h2>
  <p class="lead">{chrome["chapters"]}</p>
  <div class="chapters">{chapters}</div>
</section>
"""
    return _shell(lang=lang, title="NightScribe · "
                  + (tagline or chrome["guide"]),
                  description=definition, root="", body=body_html,
                  page_class="landing-page", nav=nav,
                  switcher=f"index{_suffix(_other(lang))}.html")


def _nav_label(section, lang):
    return NAV_SHORT.get(lang, {}).get(section["text"], section["text"])


# -------------------------------------------------------------------- guide

def _chapters():
    # @return: [{"num", "stem", "title": {"en", "es"}}] read from the guide's
    #          own index table, which is also what the app lists
    rows = re.findall(r"\[([^\]]+)\]\((\d\d-[a-z-]+)\.md\)",
                      (GUIDE_SRC / "README.md").read_text(encoding="utf-8"))
    rows_es = re.findall(
        r"\[([^\]]+)\]\((\d\d-[a-z-]+)\.es\.md\)",
        (GUIDE_SRC / "README.es.md").read_text(encoding="utf-8"))
    es = {stem: title for title, stem in rows_es}
    out = []
    for title, stem in rows:
        num, _, rest = title.partition(". ")
        en = rest.strip() or title
        out.append({"num": num.strip(), "stem": stem,
                    "title": {"en": en, "es": es.get(stem, en)}})
    return out


def _guide_link(href, lang):
    # @args: href - a link found in a chapter, lang - the page's language
    # @return: the site's target: a chapter's .md becomes its .html twin in
    #          this language (the guide's own index included); anything else
    #          (http, anchors) is left alone
    if href.endswith(".md"):
        stem = href[:-len(".md")]
        if stem.endswith(".es"):
            stem = stem[:-len(".es")]
        return _page_name(stem, lang)
    return href


def _sidebar(lang, chapters, current):
    # @args: lang, chapters - the guide's chapters, current - the page's stem
    # @return: the contents list the guide's pages share
    chrome = CHROME[lang]
    out = [f'<a class="toc-link{" on" if current == "README" else ""}" '
           f'href="{_page_name("README", lang)}">{chrome["guide"]}</a>']
    for chapter in chapters:
        on = " on" if chapter["stem"] == current else ""
        out.append(f'<a class="toc-link{on}" '
                   f'href="{_page_name(chapter["stem"], lang)}">'
                   f'<span>{html.escape(chapter["num"])}</span>'
                   f'{html.escape(chapter["title"][lang])}</a>')
    return f'<nav class="toc">{"".join(out)}</nav>'


def _prev_next(lang, pages, pos):
    # @args: lang, pages - every guide page in order, pos - this page's index
    # @return: the previous/next pair, each pointing at its own title
    chrome = CHROME[lang]
    out = []
    for step, label, cls in ((-1, chrome["prev"], "pn-prev"),
                             (1, chrome["next"], "pn-next")):
        k = pos + step
        if not (0 <= k < len(pages)):
            continue
        page = pages[k]
        href = _page_name(page["stem"], lang)
        title = page["title"][lang] if page["title"] else chrome["guide"]
        out.append(f'<a class="{cls}" href="{href}"><span>{label}</span>'
                   f"{html.escape(title)}</a>")
    return "".join(out)


def build_guide(out, lang):
    # @args: out - the site's root, lang - "en" | "es"
    # @return: None. Writes one page per chapter plus the guide's index, all
    #          sharing the sidebar, the previous/next pair and the anchors
    chrome = CHROME[lang]
    chapters = _chapters()
    pages = [{"stem": "README", "num": "", "title": None}] + chapters
    for pos, page in enumerate(pages):
        src = GUIDE_SRC / (f"{page['stem']}{_suffix(lang)}.md")
        body, _heads = md_to_html(
            src.read_text(encoding="utf-8"),
            lambda href: _guide_link(href, lang))
        title = page["title"][lang] if page["title"] else chrome["guide"]
        if page["stem"] != "README":
            # the chapter's own h1 repeats the page title: the sidebar and the
            # tab already say it, so the article starts at the first h2
            body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1)
            # its captures go right under the title, where they explain what
            # the chapter is about before the first paragraph
            shots = _shots(CHAPTER_SHOTS.get(page["stem"], ()), lang, "../")
            body = f"<h1>{html.escape(title)}</h1>{shots}{body}"
        html_text = f"""<div class="doc">
  <aside class="side">
    <p class="side-title">{chrome["contents"]}</p>
    {_sidebar(lang, chapters, page["stem"])}
    <p class="side-back"><a href="../index{_suffix(lang)}.html">
      {chrome["home"]}</a></p>
  </aside>
  <div class="doc-main">
    <article class="paper">{body}</article>
    <nav class="pn">{_prev_next(lang, pages, pos)}</nav>
  </div>
</div>
"""
        target = out / "docs" / _page_name(page["stem"], lang)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            _shell(lang=lang, title=f"{title} · NightScribe",
                   description=title, root="../", body=html_text,
                   page_class="guide-page",
                   switcher=_page_name(page["stem"], _other(lang))),
            encoding="utf-8")


# ------------------------------------------------------------------- assets

def write_assets(out):
    # @args: out - the site's root
    # @return: None. The CSS is a template with the application's palette and
    #          the kind colours injected, so the visual identity has ONE
    #          source (theme.py) and the site follows it on its own.
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    css = (TOOLS / "site.css").read_text(encoding="utf-8")
    for key, value in palette().items():
        css = css.replace(f"/*{key}*/", value)
    css = css.replace("/*kinds*/", "\n".join(
        f"  --kind-{kid}: {color};" for kid, color in kind_colors().items()))
    (assets / "style.css").write_text(css, encoding="utf-8")
    shutil.copyfile(TOOLS / "site.js", assets / "main.js")
    for name in ("appicon.svg", "welcome_sky.svg"):
        shutil.copyfile(ASSETS_SRC / name, assets / name)
    # The captures live in assets/screens (prepared by tools/prepare_screens.py
    # and committed with the site). They are copied into the output because CI
    # builds into a folder of its own: without this the pages would reference
    # images that the deployed artifact does not carry (they 404). A local
    # build writes them over themselves, which is skipped.
    screens = SITE / "assets" / "screens"
    if screens.is_dir():
        target_dir = assets / "screens"
        target_dir.mkdir(parents=True, exist_ok=True)
        for shot in sorted(screens.glob("*.webp")):
            target = target_dir / shot.name
            if shot.resolve() != target.resolve():
                shutil.copyfile(shot, target)


# -------------------------------------------------------------------- build

def build(out=SITE):
    # @args: out - where the site is written (the repository's website/)
    # @return: None. Idempotent: the same sources give the same bytes
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if not GUIDE_SRC.is_dir():
        raise SystemExit(
            f"the user guide is missing at {GUIDE_SRC}: the site is built "
            f"from it (see docs/user)")
    for lang in LANGS:
        (out / f"index{_suffix(lang)}.html").write_text(
            build_landing(lang), encoding="utf-8")
        build_guide(out, lang)
    write_assets(out)


def _generated(root):
    # @args: root - a site folder
    # @return: the files the generator OWNS, relative to that folder. The
    #          tools folder is left out: site.css and site.js are its
    #          sources, not its output.
    root = Path(root)
    return sorted(
        p.relative_to(root) for p in root.rglob("*")
        if p.is_file() and p.suffix in (".html", ".css", ".js", ".svg")
        and "tools" not in p.relative_to(root).parts)


def main(argv=None):
    # @args: argv - the command line, or None for sys.argv
    # @return: 0 on success, 1 when --check finds the site out of date
    parser = argparse.ArgumentParser(description="Build the NightScribe site")
    parser.add_argument("--out", default=str(SITE),
                        help="where to write the site (default: website/)")
    parser.add_argument("--check", action="store_true",
                        help="build into a temp folder and compare with what "
                             "is committed")
    args = parser.parse_args(argv)
    if not args.check:
        build(Path(args.out))
        print(f"site written to {args.out}")
        return 0
    import filecmp
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp))
        fresh = _generated(tmp)
        committed = _generated(SITE)
        bad = [str(p) for p in fresh
               if not (SITE / p).is_file()
               or not filecmp.cmp(SITE / p, Path(tmp) / p, shallow=False)]
        extra = [str(p) for p in committed if p not in set(fresh)]
        if bad or extra:
            print("the committed site is out of date: run build_site.py")
            for path in bad:
                print(f"  differs or missing: {path}")
            for path in extra:
                print(f"  no longer generated: {path}")
            return 1
        print(f"the committed site matches the sources ({len(fresh)} files)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
