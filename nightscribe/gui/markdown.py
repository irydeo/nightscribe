############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Minimal Markdown → Qt HTML converter
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# Renders the subset of Markdown used by the project docs into the
# limited HTML that QTextBrowser understands: headings, paragraphs,
# bold/italic/inline code/links, lists, tables, code blocks and rules.
# No external dependency: keep the deps minimal.

import re
from html import escape

# ---- inline -------------------------------------------------------------


def _escape(text):
    # @args: text - raw markdown fragment
    # @return: the fragment, HTML-escaped
    return escape(text, quote=False)


def _md_link(match):
    # The line is already html-escaped before this runs, so the groups
    # are safe to reuse verbatim; just wrap them.
    return f'<a href="{match.group(2)}">{match.group(1)}</a>'


def _md_bold(match):
    return f"<b>{match.group(1)}</b>"


def _md_italic(match):
    return f"<i>{match.group(1)}</i>"


_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_EM_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


def inline(text):
    # @args: text - one line of inline markdown
    # @return: Qt-HTML for that line
    # Order matters: links lose their brackets first, then inline code
    # protects its content from the bold/italic passes.
    text = _escape(text)
    text = _LINK_RE.sub(_md_link, text)

    codes = []

    def _protect(match):
        codes.append(f'<tt>{match.group(1)}</tt>')
        return f"\x00C{len(codes) - 1}\x00"

    text = _CODE_RE.sub(_protect, text)
    text = _BOLD_RE.sub(_md_bold, text)
    text = _EM_RE.sub(_md_italic, text)

    def _restore(match):
        return codes[int(match.group(1))]

    return re.sub("\x00C(\\d+)\x00", _restore, text)


# ---- line helpers ---------------------------------------------------------

def _is_table_sep(line):
    # A table delimiter row: |---|:---:|---|
    bare = line.strip().strip("|").strip()
    return bool(bare) and all(
        cell.strip() == "" or set(cell.strip()) <= set("-: ")
        for cell in bare.split("|"))


def _split_row(line):
    # @args: line - "|a|b|c|" style table row
    # @return: list of stripped cell strings
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _hr(line):
    bare = line.strip()
    if len(bare) < 3:
        return False
    ch = bare[0]
    return ch in "-*_" and set(bare) <= {ch, " "}


# ---- document -------------------------------------------------------------

def to_html(md):
    # @args: md - full markdown document as text
    # @return: Qt-HTML ready for QTextBrowser.setHtml()
    lines = md.replace("\r\n", "\n").split("\n")
    out, i, n = [], 0, len(lines)
    para = []

    def flush_para():
        if para:
            out.append("<br>".join(inline(l.strip()) for l in para))
            para.clear()

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_para()
            i += 1
            continue

        if _hr(line):
            flush_para()
            out.append("<hr>")
            i += 1
            continue

        # fenced code block
        if stripped.startswith("```"):
            flush_para()
            i += 1
            code = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # skip closing fence (or run off the end)
            body = "<br>".join(escape(c, quote=False) for c in code)
            out.append(f'<pre style="background:#12141f; color:#dfe4f0; '
                       f'padding:8px; border-radius:4px;">{body}</pre>')
            continue

        m = re.match(r"(#{1,6})\s+(.*)", line)
        if m:
            flush_para()
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue

        # table: header row + separator row
        if stripped.startswith("|") and i + 1 < n and _is_table_sep(lines[i + 1]):
            flush_para()
            header = _split_row(line)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            thead = "".join(f"<th>{inline(h)}</th>" for h in header)
            tbody = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>"
                for row in rows)
            out.append(f'<table border="1" cellspacing="4" '
                       f'cellpadding="4"><tr>{thead}</tr>{tbody}</table>')
            continue

        # list items (ul or ol)
        m = re.match(r"(\s*)([-*+]|\d+\.)\s+(.*)", line)
        if m:
            flush_para()
            ordered = m.group(2)[0].isdigit()
            tag = "ol" if ordered else "ul"
            items = []
            while i < n:
                lm = re.match(r"(\s*)([-*+]|\d+\.)\s+(.*)", lines[i])
                if not lm:
                    break
                items.append(f"<li>{inline(lm.group(3).strip())}</li>")
                i += 1
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue

        # blockquote (rendered as a styled paragraph)
        if stripped.startswith(">"):
            flush_para()
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            body = "<br>".join(inline(q) for q in quote if q)
            out.append(f'<span style="color:#8899bb; '
                       f'font-style:italic;">{body}</span>')
            continue

        para.append(line)
        i += 1

    flush_para()
    blocks = []
    for chunk in out:
        # bare chunks are loose paragraphs; wrap them so they get spacing
        if chunk and not (chunk.startswith("<h") or chunk.startswith(
                ("<table", "<ul", "<ol", "<hr", "<pre", "<span"))):
            blocks.append(f"<p>{chunk}</p>")
        else:
            blocks.append(chunk)
    return "".join(blocks)
