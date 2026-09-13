############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Functional tests: live AAVSO VSX lookup (network, subplan VE.2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

pytestmark = pytest.mark.network

from nightscribe.core.sources import vsx


def test_vsx_t_crb_live():
    # A real recurring nova, known to the VSX; fresh download bypassing cache
    d = vsx.lookup("T CrB", force=True)
    assert d is not None, "VSX unreachable or star not found"
    # basic shape: celestial position inside the sky
    assert 0.0 <= d["ra_deg"] < 360.0
    assert -90.0 <= d["dec_deg"] <= 90.0
    # Crateris: RA ~ 240 deg, Dec ~ +26
    assert abs(d["ra_deg"] - 240.0) < 3.0
    assert abs(d["dec_deg"] - 26.0) < 2.0
    assert d["var_type"], "var_type missing"
    assert "NR" in d["var_type"].upper()     # recurring nova
    assert d["period_d"] is None or d["period_d"] > 0
    # epoch in MJD: a recurring nova has published epochs since the 1800s
    if d["epoch_mjd"] is not None:
        assert 30000.0 < d["epoch_mjd"] < 80000.0


def test_vsx_unknown_star_degrades():
    # a made-up name must not raise: lookup() returns None (V-c degradation)
    assert vsx.lookup("NQZ Fictitious 9", force=True) is None
