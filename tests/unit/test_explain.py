############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the classification/figure explainer (ADR-058)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Guard tests for core/explain.py (ADR-058: no code or figure is shown
without an explanation). Every taxonomy must answer for its known codes
AND for an unknown one, in both languages, and the long density must be a
real mini-dossier, not an echo of the short one.
"""

from nightscribe.core import explain


def _both(entry):
    # @return: (short, long) pairs, each {"es","en"}, non-empty
    for key in ("short", "long"):
        pair = entry[key]
        assert pair["es"].strip(), f"{key}.es empty"
        assert pair["en"].strip(), f"{key}.en empty"
    return entry["short"], entry["long"]


def test_sn_type_ia_is_a_mini_dossier():
    entry = explain.sn_type("SN Ia")
    short, long = _both(entry)
    assert "vela estándar" in short["es"]
    assert "standard candle" in short["en"]
    assert "enana blanca" in long["es"] and "white dwarf" in long["en"]
    # the long is a real dossier, not the short repeated
    assert len(long["es"]) > len(short["es"]) + 80


def test_sn_type_subtypes_are_distinguished():
    for code, needle_es, needle_en in (
            ("SN Iax", "fallida", "failed"),
            ("SN IIn", "hidrógeno", "hydrogen"),
            ("SN Ib", "hidrógeno", "hydrogen"),
            ("SN II-P", "meseta", "plateau"),
            ("SN II-L", "lineal", "linearly"),
            ("SN II", "hidrógeno", "hydrogen"),
            ("SLSN", "luminosa", "luminous"),
            ("kilonova", "neutrones", "neutron"),
            ("Nova", "enana blanca", "white dwarf")):
        long = explain.long(explain.sn_type(code))
        assert needle_es in long["es"], f"{code}: {needle_es!r} missing"
        assert needle_en in long["en"], f"{code}: {needle_en!r} missing"


def test_sn_type_unknown_is_honest_not_empty():
    long = explain.long(explain.sn_type("QQ"))
    assert "clasificando" in long["es"]
    assert "classif" in long["en"]


def test_variable_type_decodes_composites():
    # NR+ELL is two phenomena: both must be named and explained
    entry = explain.variable_type("NR+ELL")
    long = explain.long(entry)
    assert "Nova recurrente" in long["es"]
    assert "Elipsoidal" in long["es"]
    assert "Recurrent nova" in long["en"]
    assert "Ellipsoidal" in long["en"]
    # and the epoch is still a minimum for the eclipsing component (the
    # caller's rule); here we only check the text side


def test_variable_type_known_families():
    for code, needle_es in (("M", "Mira"), ("E", "eclipsante"),
                            ("RCB", "hollín"), ("UGSS", "enana blanca"),
                            ("DSCT", "franja de inestabilidad"),
                            ("HADS", "gran amplitud")):
        long = explain.long(explain.variable_type(code))
        assert needle_es in long["es"], f"{code}: {needle_es!r} missing"


def test_variable_type_unknown_is_honest():
    long = explain.long(explain.variable_type("ZZZ"))
    assert "brillo cambia" in long["es"] or "variable" in long["es"].lower()


def test_spectral_class_known_and_unknown():
    assert "carbonáceo" in explain.long(explain.spectral_class("C"))["es"]
    assert "rocoso" in explain.long(explain.spectral_class("S-type"))["es"]
    assert "metálico" in explain.long(explain.spectral_class("M"))["es"]
    assert "incierta" in explain.long(explain.spectral_class("X"))["es"]
    unknown = explain.long(explain.spectral_class("Q"))
    assert "poco común" in unknown["es"]


def test_discovery_method_known_and_unknown():
    for method, needle in (("Transit", "parpadear"),
                           ("Radial Velocity", "bamboleo"),
                           ("Imaging", "imagen"),
                           ("Microlensing", "alineada"),
                           ("Timing", "pulsos"),
                           ("Astrometry", "desplazamiento")):
        assert needle in explain.long(explain.discovery_method(method))["es"]
    unknown = explain.long(explain.discovery_method("Telepathy"))
    assert "Telepathy" in unknown["es"]


def test_neofixer_priority_known_and_unknown():
    assert "puede perderse" in explain.long(
        explain.neofixer_priority("A"))["es"]
    assert "segunda opción" in explain.long(
        explain.neofixer_priority("medium"))["es"]
    assert "no corre peligro" in explain.long(
        explain.neofixer_priority("low"))["es"]
    generic = explain.long(explain.neofixer_priority("Z"))
    assert "prioridad" in generic["es"].lower()


def test_flare_class_known_and_unknown():
    assert "potente" in explain.long(explain.flare_class("X"))["es"]
    assert "auroras" in explain.long(explain.flare_class("M"))["es"]
    generic = explain.long(explain.flare_class("Q"))
    assert "fulguraciones" in generic["es"].lower()


def test_figure_short_lines_are_bilingual_and_real():
    figures = (
        explain.MAGNITUDE, explain.RATE, explain.ALTITUDE, explain.DEPTH,
        explain.PERIOD, explain.EXPOSURE, explain.MOON, explain.DISTANCE,
        explain.REDSHIFT, explain.EPOCH, explain.SIGMA, explain.COMET_LAW,
        explain.SIZE, explain.ALBEDO, explain.KP_INDEX,
    )
    for fig in figures:
        pair = explain.short(fig)
        assert pair["es"].strip() and pair["en"].strip()
        assert len(pair["es"]) > 30, pair["es"]


def test_short_and_long_accessors():
    entry = explain.sn_type("SN Ia")
    assert explain.short(entry) is entry["short"]
    assert explain.long(entry) is entry["long"]
    # an entry with no long falls back to its short
    bare = {"short": {"es": "x", "en": "y"}}
    assert explain.long(bare) == bare["short"]
