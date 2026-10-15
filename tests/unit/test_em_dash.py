############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the house rule against the em dash
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The text the observer READS carries no em dash.

AGENTS.md says we write with ":", "," and ";", and reserves the en dash for
numeric ranges. The code's comments still hold plenty of em dashes (that is
history, and the rule is about prose), but the two places where user-facing
text is authored must be clean: the published guide (docs/user) and the
interface strings (.ui, ADR-005). A <string> of four or more words is prose;
a bare "—" placeholder is a UI glyph, not a sentence, and is left alone.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "user"
UI = ROOT / "nightscribe" / "gui" / "ui"

DASH = "\u2014"


def test_the_guide_has_no_em_dash():
    offenders = []
    for p in sorted(GUIDE.glob("*.md")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(),
                                   1):
            if DASH in line:
                offenders.append(f"{p.name}:{i}")
    assert not offenders, offenders


def test_no_ui_string_uses_an_em_dash_as_prose():
    offenders = []
    for p in sorted(UI.glob("*.ui")):
        text = p.read_text(encoding="utf-8")
        # the content cannot contain "<", so a self-closing <string/> or a
        # neighbour element can never be swallowed by the match
        for m in re.finditer(r"<string[^>]*>([^<]*)</string>", text):
            val = m.group(1)
            if DASH in val and len(val.split()) >= 4:
                offenders.append(f"{p.name}: {val[:70]!r}")
    assert not offenders, offenders
