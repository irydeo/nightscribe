############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the help texts name no case
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Las ayudas no nombran el caso concreto del que salió una medida, ni un
ejemplo con nombre propio.

The rule (AGENTS.md and CONTRIBUTING): the help says WHY and the ORDER OF
MAGNITUDE, and the case it was measured on and its exact figures live in the
ADR and in the code's comments. A tooltip that cites one visit ages badly and
reads as if that visit were the only case; and a figure without its case is
still a figure with its explanation, which is what ADR-058 asks for.

Why a test: a rule that is not checked is a rule that will be lost. This one
walks every tooltip and every label of `gui/ui/*.ui` and every `tr()` string of
the GUI, and fails on a NARROW list of case patterns. The legitimate
exceptions are written down beside them, so the guard does not fight with what
is right: the services the app talks to (AAVSO, VSX, MPC, ExoClock, Gaia), the
values of a control (the zoom factors), a real astronomical fact (the Galilean
transits' season) and the objects the app itself curates (the vigils).
"""

import glob
import os
import re
import xml.etree.ElementTree as ET

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
GUI = os.path.join(HERE, "..", "..", "nightscribe", "gui")
UI = os.path.join(GUI, "ui")

# WHAT CANNOT APPEAR IN A HELP. Each entry says what it catches, so a failure
# reads as an instruction and not as a mystery.
CASES = (
    (re.compile(r"\b(?:FG18|HL5|PY9|JR7|HatP32)\b"),
     "el nombre de una visita"),
    (re.compile(r"real visit \(20\d\d"),
     "la fórmula «measured on a real visit (20xx)»"),
    (re.compile(r"on real 20\d\d"),
     "«measured on real 20xx data»"),
    (re.compile(r"magnitude \d+\.\d+|\d+\.\d+\s*mag"),
     "una magnitud con sus decimales (la de un caso)"),
    (re.compile(r"ADU/px"),
     "la unidad de un ruido de píxel"),
    (re.compile(r"\bT CrB\b|\bR CrB\b"),
     "un objeto concreto como ejemplo"),
)

# EL ÚNICO SITIO donde estas cosas son contenido y no ejemplo: la ayuda de las
# vigilias, que ES su lista. Allí T CrB y R CrB no ilustran nada, son los
# objetivos que cura la app (core/vigils.py), y su base de brillo es un dato
# del propio mando. La excepción es semántica a propósito, para que no se pudra
# como una lista de nombres de widget.
VIGILS = re.compile(r"vigil|watch list", re.I)


def _ui_strings():
    # @return: [(file, widget, where, text)] over every .ui's tooltips,
    #          whatsThis and labels: the whole of what the observer can read
    #          without opening anything else
    out = []
    for path in sorted(glob.glob(os.path.join(UI, "*.ui"))):
        name = os.path.basename(path)
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as err:                      # never silent
            pytest.fail(f"{name} does not parse: {err}")
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
    #          which is where the dialogs' helps live (they are not in a .ui)
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


def _hits(text):
    # @args: text - a help string
    # @return: [(what, matched)] for every case pattern that trips, honouring
    #          the semantic exception (the vigils' own help)
    if VIGILS.search(text):
        return []
    out = []
    for pattern, what in CASES:
        hit = pattern.search(text)
        if hit:
            out.append((what, hit))
    return out


def test_no_help_names_a_concrete_case():
    # @return: None. The check itself, over both sources.
    bad = []
    for name, widget, where, text in _ui_strings():
        for what, hit in _hits(text):
            bad.append(f"{name} :: {widget} ({where}): {what}: "
                       f"…{text[max(0, hit.start() - 40):hit.end() + 40]}…")
    for name, line, text in _tr_strings():
        for what, hit in _hits(text):
            bad.append(f"{name}:{line}: {what}: "
                       f"…{text[max(0, hit.start() - 40):hit.end() + 40]}…")
    assert not bad, ("una ayuda nombra un caso concreto: el porqué y el orden "
                     "de magnitud sí, el caso y sus cifras exactas van al ADR "
                     "y a los comentarios del código:\n  " + "\n  ".join(bad))


def test_the_guard_would_catch_the_text_that_was_removed():
    # A guard nobody has seen fail is a guard nobody can trust. These are the
    # exact fragments that lived in the helps before 2026-10-07, and each one
    # has to trip at least one pattern.
    removed = (
        "measured on a real visit (2025 FG18, 207 frames, injecting sources)",
        "the bilinear and the cubic tie at magnitude 18.20 against 18.21",
        "the pixel noise differs by 29 % (6.58 against 8.49 ADU/px)",
        "the sigma-clipped mean (the default) reaches magnitude 18.23",
        "the smooth vignetting alone is worth 0.087 mag of systematic error",
        "measured on real 2025 UR data: 1.55 to 1.63 times the aperture's",
        "the zero point's error 2.6 times smaller (0.035 against 0.092 "
        "magnitudes)",
        "a slight defocus helps (T CrB lesson)",
        "Name it after the goal, e.g. “T CrB 2026 eruption”",
    )
    for text in removed:
        assert _hits(text), text


def test_the_vigils_help_may_name_its_own_objects():
    # The exception, tested in both directions: the vigils' own help names T
    # CrB and R CrB because they ARE the list, and the same names in a help
    # that is NOT about them are still a case.
    assert not _hits("Standing watch list checked against the latest ZTF "
                     "magnitude: rise = eruption watch (T CrB), drop = fade "
                     "watch (R CrB)")
    assert _hits("A campaign groups the projects of one shared effort, e.g. "
                 "“T CrB 2026 eruption”")
    assert _hits("a slight defocus helps (T CrB lesson)")
