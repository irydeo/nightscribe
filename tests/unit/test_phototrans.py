############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: photometric transformations (ADR-042)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core import phototrans


def test_poly_horner():
    # 2*x^2 + 3*x + 4 at x = 2 -> 18
    assert phototrans.poly((2.0, 3.0, 4.0), 2.0) == pytest.approx(18.0)
    assert phototrans.poly((5.0,), 99.0) == pytest.approx(5.0)


def test_gaia_to_johnson_at_bp_rp_1():
    # Hand-computed from the Riello et al. 2021 polynomials at BP-RP = 1:
    # G-B = -0.972201, G-V = -0.21414, G-R = 0.238865, G-I = 0.67843
    jc = phototrans.gaia_to_johnson(10.0, 1.0)
    assert jc["B"] == pytest.approx(10.972201, abs=1e-5)
    assert jc["V"] == pytest.approx(10.21414, abs=1e-5)
    assert jc["R"] == pytest.approx(9.761135, abs=1e-5)
    assert jc["I"] == pytest.approx(9.32157, abs=1e-5)
    assert jc["B"] - jc["V"] == pytest.approx(0.758061, abs=1e-5)


def test_gaia_to_johnson_ri_limit():
    # R/I are only documented for BP-RP <= 2.75
    jc = phototrans.gaia_to_johnson(12.0, 3.0)
    assert "B" in jc and "V" in jc
    assert "R" not in jc and "I" not in jc


def test_gaia_to_johnson_out_of_range_is_none():
    assert phototrans.gaia_to_johnson(12.0, 4.5) is None
    assert phototrans.gaia_to_johnson(12.0, -0.6) is None
    # the boundaries are valid
    assert phototrans.gaia_to_johnson(12.0, -0.5) is not None
    assert phototrans.gaia_to_johnson(12.0, 4.0) is not None


def test_combine_err():
    assert phototrans.combine_err(0.03, 0.04) == pytest.approx(0.05)
    assert phototrans.combine_err(None, 0.04) is None
    assert phototrans.combine_err(0.03, None) is None


def test_classify_bv_boundaries_and_languages():
    assert phototrans.classify_bv(-0.2) == "Azulada"
    assert phototrans.classify_bv(-0.2, "en") == "Bluish"
    assert phototrans.classify_bv(0.0) == "Blanco-azulada"
    assert phototrans.classify_bv(0.4) == "Blanquecina"
    assert phototrans.classify_bv(0.65) == "Amarillenta"
    assert phototrans.classify_bv(0.65, "en") == "Yellowish"
    assert phototrans.classify_bv(1.0) == "Anaranjada"
    assert phototrans.classify_bv(2.0) == "Rojiza"
    assert phototrans.classify_bv(2.0, "en") == "Reddish"
    assert phototrans.classify_bv(None) == "Sin dato"
    assert phototrans.classify_bv(float("nan"), "en") == "No data"
