############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the documentation's own links
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Every relative .md link in docs/ must point to a file that exists.

The in-app documentation browser (Help > Documentation, and the "?" of the
series block) follows relative markdown links, resolving them against the
open file: a broken one lands the observer on nothing at all, which is worse
than no link. Links to folders count as broken too, because the browser can
only render files. Code spans and code blocks are skipped: they are examples
of the syntax, not links.
"""

import re
from pathlib import Path

DOCS = Path(__file__).parents[2] / "docs"


def _without_code(text):
    # @args: text - a markdown file
    # @return: the text with fenced blocks and inline spans removed (their
    #          content is an EXAMPLE, not a link)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    return text


def test_every_relative_link_in_the_docs_resolves():
    missing = []
    for path in sorted(DOCS.rglob("*.md")):
        text = _without_code(path.read_text(encoding="utf-8"))
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean = target.split("#")[0].strip()
            if not clean:
                continue
            if not (path.parent / clean).resolve().is_file():
                missing.append((path.relative_to(DOCS).as_posix(), target))
    assert not missing, missing


def test_the_series_guide_and_the_editor_guide_point_at_each_other():
    # The "?" of the series block opens SEQUENCES and the band's colours are
    # explained in UFE: the two chapters have to reach each other, or the
    # observer who lands in one cannot find the answer that lives in the
    # other (which is exactly how the colour code stayed invisible).
    for series, ufe in (("SEQUENCES.md", "UFE.md"),
                        ("SEQUENCES.es.md", "UFE.es.md")):
        assert "(" + ufe + ")" in (DOCS / series).read_text(encoding="utf-8")
        assert "(" + series + ")" in (DOCS / ufe).read_text(encoding="utf-8")
