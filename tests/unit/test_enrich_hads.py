############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - HADS enrich detection tests (subplan B.3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""HADS detection in enrich.detect_type is catalog-membership based and
alias-aware, and it MUST run before the exoplanet regex: "GP And" ends in
"d", which the planet-letter rule would otherwise swallow. No network:
detect_type is local; the enrich branch only touches the bundled catalog
plus the (fabricated) planner fallback.
"""

from nightscribe.core import enrich


def test_detect_type_hads_by_primary_name():
    assert enrich.detect_type("GP And") == "hads"
    assert enrich.detect_type("CY Aqr") == "hads"


def test_detect_type_hads_by_alias():
    assert enrich.detect_type("GSC 01739-01964") == "hads"


def test_gp_and_is_not_an_exoplanet():
    # regression: the planet-letter regex would claim the trailing "d"
    assert enrich.detect_type("GP And") != "exoplanet"


def test_unknown_names_fall_through():
    assert enrich.detect_type("Ceres") == "small_body"
    assert enrich.detect_type("HD 209458 b") == "exoplanet"
    assert enrich.detect_type("SN 2026abc") == "transient"


def test_enrich_hads_uses_the_catalog_offline():
    e = enrich.enrich("CY Aqr")
    assert e["type"] == "hads"
    star = e["data"]["hads"]
    assert star["period_h"] == 1.46 and abs(star["max"] - 11.3) < 0.01


def test_enrich_hads_planner_values_win():
    fallback = {"kind": "hads", "name": "CY Aqr",
                "safe_window": "2026-09-12T00:00|2026-09-12T04:00",
                "best_time": "2026-09-12T01:00:00",
                "hads": {"period_h": 1.46, "amp": 0.5, "cycles": 4.2,
                         "session_fits": True}}
    e = enrich.enrich("CY Aqr", fallback_target=fallback)
    assert e["data"]["hads"]["cycles"] == 4.2      # tonight's, not catalog's
    assert e["data"]["safe_window"].startswith("2026-09-12T00:00")
    assert e["data"]["best_time"] == "2026-09-12T01:00:00"
