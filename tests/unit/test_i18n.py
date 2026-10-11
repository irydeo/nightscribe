############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: translations are complete
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

I18N = Path(__file__).parents[2] / "nightscribe" / "gui" / "i18n"
ROOT = Path(__file__).parents[2]


def test_ts_files_complete():
    # no source string may be left unfinished in either language (ADR-014)
    for lang in ("es", "en"):
        tree = ET.parse(I18N / f"nightscribe_{lang}.ts")
        missing = []
        for ctx in tree.getroot().findall("context"):
            for msg in ctx.findall("message"):
                tr = msg.find("translation")
                if tr.get("type") == "unfinished" or tr.text is None:
                    src = msg.find("source")
                    missing.append(src.text if src is not None else "?")
        assert not missing, f"{lang}: unfinished translations: {missing}"


def test_qm_compiled():
    # compiled .qm must exist next to the .ts sources
    for lang in ("es", "en"):
        assert (I18N / f"nightscribe_{lang}.qm").exists()


def test_no_double_escaped_entities():
    # A translation carrying "&amp;apos;" is read back by the XML parser as
    # the LITERAL text "&apos;" (the parser unescapes once, to the entity,
    # not to the apostrophe), so the user reads "Tonight&apos;s best
    # objects" on screen. It happened once, with three English strings, when
    # a helper escaped an already-escaped value (2026-10-02). After parsing,
    # no source or translation may contain an HTML entity: that is always a
    # double escape, never a legitimate string.
    entities = ("&apos;", "&quot;", "&lt;", "&gt;", "&amp;")
    for lang in ("es", "en"):
        tree = ET.parse(I18N / f"nightscribe_{lang}.ts")
        for ctx in tree.getroot().findall("context"):
            for msg in ctx.findall("message"):
                for node in ("source", "translation"):
                    el = msg.find(node)
                    if el is None or not el.text:
                        continue
                    for token in entities:
                        assert token not in el.text, (
                            f"{lang}: {ctx.findtext('name')} {node} "
                            f"{el.text[:60]!r} carries a re-escaped {token}")


def test_the_english_catalogue_repeats_the_source():
    # "en" is the PASS-THROUGH language: its catalogue repeats every source
    # verbatim, and that is what the app reads when the observer works in
    # English. Nothing else notices when it does not, and it did not:
    #
    #   * on 2026-10-07, four strings of the resampling combo (Bilinear,
    #     Cubic, Quintic and the "Resampling:" label) shipped with their
    #     SPANISH value in the English catalogue, because the script that
    #     filled the two files wrote the same table into both. The English
    #     interface showed "Remuestreo: [Bilineal (más limpio)]", and the
    #     whole suite stayed green;
    #   * and three more were already there, of a subtler kind: a string that
    #     is CONCATENATED to a line (" along PA %1°") had lost its leading
    #     space, so English read "mag 18.3along PA 46°".
    #
    # Vanished and obsolete entries are skipped: they are strings that no
    # longer exist in the code and nothing reads them.
    tree = ET.parse(I18N / "nightscribe_en.ts")
    wrong = []
    for ctx in tree.getroot().findall("context"):
        for msg in ctx.findall("message"):
            src = msg.find("source")
            tr = msg.find("translation")
            if src is None or src.text is None or tr is None:
                continue
            if tr.get("type") in ("vanished", "obsolete"):
                continue
            if (tr.text or "") != src.text:
                wrong.append((ctx.findtext("name"), src.text, tr.text))
    assert not wrong, ("the English catalogue must repeat the source "
                       "verbatim: %r" % (wrong,))


def test_the_app_loads_its_catalogue_from_memory_not_mapped():
    # QTranslator MEMORY-MAPS a .qm loaded BY FILENAME. Rebuilding the
    # catalogue while the app is open rewrites that file in place, the live
    # mapping is invalidated, and the next translation walks off it and
    # crashes: that is the GUI core dump of 2026-10-10, inside
    # QTranslator::translate, reached from a plain self.tr() in the
    # sky-event chips. app.load_translator reads the BYTES instead, so the
    # catalogue never appears in the process maps and a rebuild cannot touch
    # it. Run in a CHILD process: /proc/self/maps is global, and another test
    # in this session may already have mapped the file.
    if not sys.platform.startswith("linux"):
        pytest.skip("needs /proc/self/maps")
    code = textwrap.dedent("""
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QTranslator
        from PySide6.QtWidgets import QApplication
        from nightscribe.gui.app import load_translator
        app = QApplication([])
        tr = load_translator(app, "es")
        assert tr is not None, "no translator was installed"
        # for contrast: loading BY PATH maps the file, which is the hazard.
        # Keep a reference (a temporary is destroyed at once and its mapping
        # released) and translate once so the file is really faulted in.
        by_path = QTranslator()
        by_path.load("nightscribe/gui/i18n/nightscribe_en.qm")
        by_path.translate("MainWindow", "Date")
        maps = open("/proc/self/maps").read()
        print("ES:" + ("MAPPED" if "nightscribe_es.qm" in maps else "MEMORY"))
        print("EN:" + ("MAPPED" if "nightscribe_en.qm" in maps else "MEMORY"))
    """)
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True)
    assert "ES:MEMORY" in out.stdout, out.stdout + out.stderr
    assert "EN:MAPPED" in out.stdout, out.stdout + out.stderr
