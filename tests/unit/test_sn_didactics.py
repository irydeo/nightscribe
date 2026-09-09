############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SN type didactics + TNS enrich (Track B, B7)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core.orbits import _sn_type_text, explain_transient


# ---------------- _sn_type_text extended types ----------------

def test_sn_type_ia():
    r = _sn_type_text("SN Ia")
    assert "vela" in r["es"].lower() or "standard candle" in r["en"].lower()


def test_sn_type_iax():
    r = _sn_type_text("SN Iax")
    assert r is not None
    assert "prima hermana" in r["es"].lower() or "cousin" in r["en"].lower()


def test_sn_type_iin():
    r = _sn_type_text("SN IIn")
    assert r is not None
    assert "hidrógeno" in r["es"].lower()


def test_sn_type_ii_p():
    r = _sn_type_text("SN II-P")
    assert r is not None
    assert "meseta" in r["es"].lower() or "plateau" in r["en"].lower()


def test_sn_type_ii_l():
    r = _sn_type_text("SN II-L")
    assert r is not None
    assert "lineal" in r["es"].lower() or "linear" in r["en"].lower()


def test_sn_type_ib_c():
    r = _sn_type_text("SN Ib/c")
    assert r is not None
    assert "envoltura" in r["es"].lower() or "envelope" in r["en"].lower()


def test_sn_type_slsn():
    r = _sn_type_text("SN SLSN")
    assert r is not None
    assert "superluminosa" in r["es"].lower() or "superlumin" in r["en"].lower()


def test_sn_type_kilonova():
    r = _sn_type_text("kilonova")
    assert r is not None
    assert "neutron" in r["es"].lower() or "neutron" in r["en"].lower()


def test_sn_type_unclassified():
    r = _sn_type_text("")
    assert r is not None
    assert "genérico" in r["es"].lower() or "generic" in r["en"].lower()


def test_sn_type_unknown_falls_back():
    r = _sn_type_text("SN XYZ")
    assert r is not None   # falls back to generic


def test_sn_type_both_languages():
    for otype in ("SN Ia", "SN II-P", "SN IIn", "SN Iax", "SN SLSN",
                  "kilonova", ""):
        r = _sn_type_text(otype)
        assert "es" in r and "en" in r
        assert len(r["es"]) > 10 and len(r["en"]) > 10


# ---------------- explain_transient didactic note ----------------

def test_explain_transient_has_multi_filter_note():
    d = {"simbad": {"otype": "SN Ia"},
            "host": {"name": "NGC 123"},
            "dist_mly": 74, "mag": 16.0, "disc_date": "2026-09-01"}
    rows = explain_transient(d)
    # find the didactic multi-filter note
    didactic = [r for r in rows if r["level"] == "didactic"]
    assert len(didactic) == 1
    assert "filtro" in didactic[0]["es"].lower() or "filter" in didactic[0]["en"].lower()


def test_explain_transient_didactic_only_for_sn():
    # non-SN types should not get the didactic note
    d = {"simbad": {"otype": "Galaxy"}, "host": {"name": "NGC 123"}}
    rows = explain_transient(d)
    didactic = [r for r in rows if r["level"] == "didactic"]
    assert len(didactic) == 0


def test_explain_transient_no_type_no_didactic():
    d = {"simbad": {}, "host": {"name": "NGC 123"}}
    rows = explain_transient(d)
    didactic = [r for r in rows if r["level"] == "didactic"]
    assert len(didactic) == 0
