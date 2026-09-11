############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Variable detection & enrich branch (Track V, VB.5/VB.6)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core import enrich


def test_detect_variable_gcvs_names():
    assert enrich.detect_type("T CrB") == "variable"
    assert enrich.detect_type("EE Cep") == "variable"
    assert enrich.detect_type("V1490 Cyg") == "variable"
    assert enrich.detect_type("NSV 01234") == "variable"


def test_detect_collisions_stay_put():
    assert enrich.detect_type("GP And") == "hads"         # HADS regression
    assert enrich.detect_type("GQ Lup b") == "exoplanet"  # 3 tokens: planet
    assert enrich.detect_type("SN 2026abc") == "transient"
    assert enrich.detect_type("2026 AB1") == "small_body"


def test_detect_local_variable_project_name(monkeypatch):
    class _FakeDb:
        def execute(self, sql, params=()):
            class _Cur:
                def fetchone(self):
                    return (1,)
            return _Cur()
    from nightscribe.core import db as dbmod
    monkeypatch.setattr(dbmod, "db", _FakeDb())
    assert enrich.detect_type("WeSb 1") == "variable"     # not GCVS-shaped
