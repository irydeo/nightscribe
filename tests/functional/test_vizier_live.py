############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Functional tests: live VizieR cone search + sequence
# (network, ADR-042)
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

from nightscribe.core import compstars
from nightscribe.core.sources import vizier

# T CrB field (a real, well-populated variable-star field)
RA, DEC = 239.8757, 25.9202


def test_vizier_gaia_cone_search_live():
    res = vizier.cone_search("gaia", RA, DEC, 5.0, max_rows=200, force=True)
    assert res is not None, "VizieR unreachable"
    headers, rows = res
    assert "Gmag" in headers and "RAJ2000" in headers
    assert len(rows) > 10, "a 5' cone at T CrB must hold dozens of sources"


def test_vizier_vsx_cone_search_finds_t_crb():
    res = vizier.cone_search("vsx", RA, DEC, 5.0, max_rows=200, force=True)
    assert res is not None, "VizieR VSX table unreachable"
    _, rows = res
    names = [r.get("Name", "") for r in rows]
    assert any("T CrB" in n for n in names)


def test_load_field_and_proposal_live():
    field = compstars.load_field("gaia", RA, DEC, 10.0, force=True)
    assert field is not None, "field load failed (VizieR down?)"
    assert len(field["stars"]) > 5
    assert field["vsx_warning"] is False
    # T CrB itself must be flagged as a variable and never proposed
    seq = compstars.propose_comps(field["stars"], target_mag=10.0, n=5)
    assert seq["comps"], "no comparison proposal on a rich field"
    assert all(e["star"].get("vsx") is None for e in seq["comps"])
    assert seq["check"] is None or seq["check"]["star"].get("vsx") is None
