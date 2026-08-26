############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - markdown converter tests
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Unit tests for the inline and block markdown -> Qt HTML converter."""

from pathlib import Path

from nightscribe.gui import markdown


def test_inline_features():
    out = markdown.inline("Read **bold**, *italics*, `code` and "
                          "[a link](https://x.io/a?b=1&c=2).")
    assert "<b>bold</b>" in out
    assert "<i>italics</i>" in out
    assert "<tt>code</tt>" in out
    # the & in the URL must survive the html escape quoted for the href
    assert 'href="https://x.io/a?b=1&amp;c=2"' in out
    assert ">a link</a>" in out


def test_inline_escaping():
    assert "&lt;tag&gt;" in markdown.inline("<tag>")


def test_headings():
    out = markdown.to_html("# Title\n\n## Sub\n\n### Deep")
    assert "<h1>" in out and "<h2>" in out and "<h3>" in out


def test_paragraphs():
    out = markdown.to_html("hello\n\nworld")
    assert "<p>hello</p>" in out and "<p>world</p>" in out


def test_lists():
    out = markdown.to_html("- uno\n- dos\n\n1. uno\n2. dos")
    assert "<ul><li>uno</li><li>dos</li></ul>" in out
    assert "<ol><li>uno</li><li>dos</li></ol>" in out


def test_table():
    md = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    out = markdown.to_html(md)
    assert "<table" in out
    assert "<th>A</th>" in out and "<td>4</td>" in out


def test_code_block():
    out = markdown.to_html("text\n\n```\nx = 1  # <kept>\n```\n")
    assert "x = 1" in out
    assert "&lt;kept&gt;" in out
    assert "<tt>" not in out  # the fenced content must stay verbatim


def test_rule():
    assert "<hr>" in markdown.to_html("---")


def test_real_docs_render():
    # Every bundled doc must convert without raising and produce headings.
    docs = Path(__file__).parents[2] / "docs"
    for path in sorted(docs.rglob("*.md")):
        html = markdown.to_html(path.read_text(encoding="utf-8"))
        assert len(html) > 200, path
        assert "<h" in html, path
