############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: kind inference (Explore -> project)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import kinds


def test_project_kind_from_enriched_type():
    assert kinds.project_kind({"type": "exoplanet"}) == "transit"
    assert kinds.project_kind({"type": "transient"}) == "sn"
    assert kinds.project_kind({"type": "hads"}) == "hads"
    assert kinds.project_kind({"type": "variable"}) == "variable"
    assert kinds.project_kind({"type": "small_body"}) == "neo"
    assert kinds.project_kind({"type": "comet"}) == "comet"


def test_project_kind_accepts_kind_or_string():
    assert kinds.project_kind({"kind": "transit"}) == "transit"
    assert kinds.project_kind("neo") == "neo"
    assert kinds.project_kind("unknown") is None
    assert kinds.project_kind({"type": "sun"}) is None
    assert kinds.project_kind(None) is None
