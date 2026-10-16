############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the user-facing text names no ADRs
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Los ADR son el registro interno del proyecto y no se nombran al usuario.

The ADRs are how the project remembers WHY it is built the way it is, and
they live in `docs/adr/` for whoever changes the code. The observer never
needs the acronym: an "ADR-061" in the guide, in the landing page or in a
tooltip is a door that leads nowhere for the person reading it. Where the
idea has to be said (the assistant really does read them), it is said in
plain words ("the app's design notes"), not with the code.

Why a test: the guide was cleaned by hand on 2026-10-15 and the acronym came
back the same day, because a rule that is not checked is a rule that will be
lost. This one walks the user guide, both READMEs and every string the app
shows: the `.ui` texts (labels, tooltips, whatsThis) and the `tr()` literals
of the GUI. The ADRs' own files and the code's comments are NOT walked: there
the acronym is content, not a reference.
"""

import glob
import os
import re
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
GUI = os.path.join(ROOT, "nightscribe", "gui")
UI = os.path.join(GUI, "ui")

# "ADR" and "ADRs", and the numbered form "ADR-061" with them. Anchored on
# word boundaries so a word that merely CONTAINS the letters is left alone.
ADR = re.compile(r"\bADRs?\b")


def _docs():
    # @return: [(file, text)] over the user guide and the landing page: what
    #          the observer reads on the web or in the app's own viewer
    paths = sorted(glob.glob(os.path.join(ROOT, "docs", "user", "**", "*.md"),
                             recursive=True))
    paths += [os.path.join(ROOT, "README.md"),
              os.path.join(ROOT, "README.es.md")]
    out = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            out.append((os.path.relpath(path, ROOT), fh.read()))
    return out


def _ui_strings():
    # @return: [(file, widget, where, text)] over every .ui's labels,
    #          tooltips and whatsThis: what the observer can read without
    #          opening anything else
    out = []
    for path in sorted(glob.glob(os.path.join(UI, "*.ui"))):
        name = os.path.basename(path)
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as err:                      # never silent
            raise AssertionError(f"{name} does not parse: {err}") from err
        for widget in root.iter("widget"):
            for prop in widget.findall("property"):
                if prop.get("name") not in ("toolTip", "whatsThis", "text"):
                    continue
                node = prop.find("string")
                if node is None or not (node.text or "").strip():
                    continue
                out.append((name, widget.get("name"), prop.get("name"),
                            node.text))
    return out


def _tr_strings():
    # @return: [(file, line, text)] over the tr("…") literals of the GUI,
    #          which is where the dialogs' own texts live (not in a .ui)
    out = []
    pattern = re.compile(r'tr\(\s*((?:"[^"]*"\s*)+)\)')
    files = (sorted(glob.glob(os.path.join(GUI, "*.py")))
             + sorted(glob.glob(os.path.join(GUI, "widgets", "*.py"))))
    for path in files:
        src = open(path, encoding="utf-8").read()
        for match in pattern.finditer(src):
            text = " ".join(re.findall(r'"([^"]*)"', match.group(1)))
            if text.strip():
                out.append((os.path.basename(path),
                            src[:match.start()].count("\n") + 1, text))
    return out


def test_the_user_guide_and_the_readmes_name_no_adrs():
    # @return: None. The documents, in both languages.
    bad = []
    for name, text in _docs():
        for hit in ADR.finditer(text):
            line = text[:hit.start()].count("\n") + 1
            snippet = text[max(0, hit.start() - 50):hit.end() + 50].strip()
            bad.append(f"{name}:{line}: …{snippet}…")
    assert not bad, ("la documentación de usuario nombra un ADR: eso es el "
                     "registro interno del proyecto, y al observador se le "
                     "dice la idea en palabras llanas (\"las notas de diseño "
                     "de la app\"):\n  " + "\n  ".join(bad))


def test_the_app_names_no_adrs_in_what_it_shows():
    # @return: None. The strings the app paints: the .ui texts and the tr()
    #          literals.
    bad = []
    for name, widget, where, text in _ui_strings():
        for hit in ADR.finditer(text):
            snippet = text[max(0, hit.start() - 50):hit.end() + 50]
            bad.append(f"{name} :: {widget} ({where}): …{snippet}…")
    for name, line, text in _tr_strings():
        for hit in ADR.finditer(text):
            snippet = text[max(0, hit.start() - 50):hit.end() + 50]
            bad.append(f"{name}:{line}: …{snippet}…")
    assert not bad, ("la app nombra un ADR en un texto que el observador lee: "
                     "dile la idea, no el código:\n  " + "\n  ".join(bad))


def test_the_guard_would_catch_the_text_that_was_removed():
    # A guard nobody has seen fail is a guard nobody can trust: these are the
    # exact fragments that lived in the guide, the README and the app before
    # 2026-10-16, and every one of them has to trip.
    removed = (
        "A **visit** is one observing night on that project (ADR-045).",
        "An **astrometry run** is one execution of track & stack over a "
        "visit's frames (ADR-062).",
        "the user guide and the ADRs. Questions like \"how do I calibrate\"",
        "answers from the app's own guide and ADRs, offline",
        "The user guide and the ADRs",
        "Design decisions (ADR)",
    )
    for text in removed:
        assert ADR.search(text), text


def test_a_word_that_merely_contains_the_letters_is_left_alone():
    # The guard is anchored on word boundaries: it is the ACRONYM that must
    # not appear, not a word that happens to carry its three letters.
    assert not ADR.search("the ADRess of the observer")
    assert not ADR.search("a cuadrADRa")
