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


def test_context_line_speaks_each_kind_language():
    # The one-glance numbers of a project row. Which ones matter depends on
    # what the project is.
    assert kinds.context_line("sn", {"mag": 15.24, "sn_type": "Ia",
                                     "host": "NGC 4414"}) == \
        "mag 15.2 · Ia · NGC 4414"
    assert kinds.context_line("neo", {"mag": 17.8, "rate_arcsec_min": 12.44,
                                      "moid": 0.0213}) == \
        "mag 17.8 · 12.4″/min · MOID 0.021 au"
    assert kinds.context_line("hads", {"period_d": 0.1348,
                                       "amplitude": 0.83}) == \
        "period 0.1348 d · amp 0.8 mag"
    assert kinds.context_line("comet", {"mag": 11.2,
                                        "perihelion_date": "2026-11-03"}) == \
        "mag 11.2 · perihelion 2026-11-03"


def test_context_line_keeps_the_row_short():
    line = kinds.context_line("neo", {"mag": 17.8, "rate_arcsec_min": 12.4,
                                      "moid": 0.02, "h": 22.1})
    assert line.count("·") == 2               # three fields, no more


def test_context_line_never_raises_on_a_half_written_context():
    assert kinds.context_line("sn", {}) == ""
    assert kinds.context_line("sn", None) == ""
    assert kinds.context_line("unknown", {"mag": 1}) == ""
    # a value the enricher left as text, or missing keys among good ones
    assert kinds.context_line("sn", {"mag": "n/a"}) == "mag n/a"
    assert kinds.context_line("sn", {"mag": 12.0, "host": ""}) == "mag 12"
