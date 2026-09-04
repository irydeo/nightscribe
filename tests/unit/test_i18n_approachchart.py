############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - approach chart i18n tests (offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""i18n smoke tests for the ApproachChart and its panel slot title (ADR-029).

The compiled .qm must carry every string the ApproachChart shows
(scene labels, Play/Pause, CA, no-return) and the ObjectPanel
"Approach" title.  Install the translator, read the strings via
w.tr(...), then remove the translator.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def _qm(lang):
    from pathlib import Path
    return Path(__file__).parents[2] / "nightscribe" / "gui" / "i18n" \
        / f"nightscribe_{lang}.qm"


@pytest.fixture()
def translator(qapp):
    from PySide6.QtCore import QTranslator
    qm = _qm("es")
    tr = QTranslator(qapp)
    assert tr.load(str(qm)), f"failed to load {qm}"
    qapp.installTranslator(tr)
    yield tr
    qapp.removeTranslator(tr)


def test_approachchart_strings_translate_es(qapp, translator):
    # ApproachChart context — every scene label, Play/Pause, CA and no-return.
    from nightscribe.gui.widgets.approach_widget import ApproachChart
    w = ApproachChart()
    try:
        assert w.tr("Moon")  == "Luna"
        assert w.tr("Earth") == "Tierra"
        assert w.tr("Play")  == "Reproducir"
        assert w.tr("Pause") == "Pausa"
        assert w.tr("1 LD")  == "1 LD"
        assert w.tr("no return (open orbit)") == "sin retorno (órbita abierta)"
        ca = w.tr("CA %1 LD")
        assert ca == "CA %1 LD" or "CA" in ca
        ca_status = w.tr("CA %1 LD (%2)")
        assert "CA" in ca_status and "%1" in ca_status
    finally:
        w.deleteLater()


def test_objectpanel_approach_title_es(qapp, translator):
    # ObjectPanel context — the "Approach" slot title.
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(chart_dir="/tmp/charts")
    try:
        assert p.tr("Approach") == "Aproximación"
    finally:
        p.deleteLater()


def test_approachchart_strings_passthrough_en(qapp):
    # English .qm is a passthrough: tr("X") == "X".
    from pathlib import Path
    from PySide6.QtCore import QTranslator
    qm = _qm("en")
    tr = QTranslator(qapp)
    assert tr.load(str(qm)), f"failed to load {qm}"
    qapp.installTranslator(tr)
    from nightscribe.gui.widgets.approach_widget import ApproachChart
    w = ApproachChart()
    try:
        assert w.tr("Moon")  == "Moon"
        assert w.tr("Earth") == "Earth"
        assert w.tr("Play")  == "Play"
        assert w.tr("Pause") == "Pause"
        assert w.tr("no return (open orbit)") == "no return (open orbit)"
    finally:
        w.deleteLater()
        qapp.removeTranslator(tr)
