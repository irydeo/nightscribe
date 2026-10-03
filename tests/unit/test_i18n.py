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

import xml.etree.ElementTree as ET
from pathlib import Path

I18N = Path(__file__).parents[2] / "nightscribe" / "gui" / "i18n"


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
