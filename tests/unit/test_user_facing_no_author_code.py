############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the user-facing text names no real station
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""El código de observatorio del autor no es un ejemplo que copiar.

The wizard, the guide and the README used to say "your MPC code (e.g. Z41)":
a real, working station code, and the author's own. An observer who copies an
example into their settings does not get a placeholder, they get a WORKING
code that is not theirs, and every report they send is filed under someone
else's observatory (reported 2026-10-17). The shape is what the text has to
teach ("three characters, the ones assigned to your station"), never a code.

Why a test: the example was in six places at once (the wizard's validation
message, the field's placeholder, the guide, both READMEs and an ADR) and it
would come back one at a time. This walks what the observer reads and copies:
the user guide, the READMEs, the `.ui` texts, the GUI's `tr()` literals and the
wizard's own `QT_TRANSLATE_NOOP` table (the setup assistant's strings, which
are not `tr()` calls).

The authorship line of the About box ("Irydeo Observatory (MPC Z41)") is NOT
walked on purpose: it says who wrote the app, not what to type in a field, and
it is an f-string rather than a translatable string. The ADRs are not walked
either: they are the design record, and ADR-077 tells a real case with its own
code in it.
"""

import glob
import os
import re

from test_user_facing_no_adr import _docs, _tr_strings, _ui_strings

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
GUI = os.path.join(ROOT, "nightscribe", "gui")

# The author's station. Anchored on word boundaries so a word that merely
# contains it (or a longer code) is left alone.
CODE = re.compile(r"\bZ41\b")

# The wizard's own string table: literals handed to QT_TRANSLATE_NOOP, which
# the tr() walker cannot see.
_NOOP = re.compile(r'QT_TRANSLATE_NOOP\(\s*"[^"]*"\s*,\s*((?:"[^"]*"\s*)+)\)')


def _wizard_strings():
    # @return: [(file, line, text)] over the setup assistant's literals
    out = []
    for name in ("wizard.py",):
        path = os.path.join(GUI, name)
        src = open(path, encoding="utf-8").read()
        for match in _NOOP.finditer(src):
            text = " ".join(re.findall(r'"([^"]*)"', match.group(1)))
            if text.strip():
                out.append((name, src[:match.start()].count("\n") + 1, text))
    return out


def _hits(text):
    # @args: text - a user-facing string
    # @return: the matched code, or None
    hit = CODE.search(text or "")
    return hit.group(0) if hit else None


def test_the_guide_and_the_readmes_name_no_real_station():
    bad = []
    for name, text in _docs():
        hit = _hits(text)
        if hit:
            bad.append(f"{name}: …{text[max(0, text.find(hit) - 50):][:110]}…")
    assert not bad, ("la guía o el README usan el código de una estación real "
                     "como ejemplo (el del autor): enseña la FORMA, nunca un "
                     "código que se pueda copiar:\n  " + "\n  ".join(bad))


def test_the_app_offers_no_real_station_as_an_example():
    bad = []
    for name, widget, where, text in _ui_strings():
        if _hits(text):
            bad.append(f"{name} :: {widget} ({where}): {text[:90]}")
    for name, line, text in _tr_strings():
        if _hits(text):
            bad.append(f"{name}:{line}: {text[:90]}")
    for name, line, text in _wizard_strings():
        if _hits(text):
            bad.append(f"{name}:{line}: {text[:90]}")
    assert not bad, ("la app pone un código de estación real como ejemplo: "
                     "que enseñe la forma («tres caracteres, los de tu "
                     "estación») y no un código que el observador pueda "
                     "copiar:\n  " + "\n  ".join(bad))


def test_the_guard_would_catch_the_example_that_was_removed():
    # A guard nobody has seen fail is a guard nobody can trust: these are the
    # exact fragments that lived in the app and the guide before 2026-10-17.
    removed = (
        "**Your MPC code** (e.g. `Z41`): the coordinates resolve automatically",
        "**Tu código MPC** (por ejemplo `Z41`): las coordenadas se resuelven",
        "MPC codes are three characters, for example Z41.",
        "e.g. Z41",
        "observatory code matching the configured one (e.g. Z41)",
    )
    for text in removed:
        assert _hits(text), text


def test_a_longer_code_is_not_a_hit():
    # The guard is anchored: it is that station that must not be an example,
    # not a word or a longer code that happens to contain it.
    assert not _hits("station Z410 or the Z41X file")
    assert not _hits("Z-41")
