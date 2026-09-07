############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Exoplanet enrich context-merge tests
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Unit tests for the exoplanet branch of enrich.enrich (object-card
plan, subplan 3a).

The Exoplanet Archive knows the planet's story; only the planner target
knows TONIGHT's event (ingress/egress/depth/min telescope). The merge
follows the ADR-027 pattern: planner facts fill gaps, never overwrite.
No network: exoplanet_archive.planet is monkeypatched.
"""

import datetime

from nightscribe.core import enrich

# The Archive row for HD 209458 b (pscomppars shape, already JSON-parsed).
FAKE_ARCHIVE = {
    "pl_name": "HD 209458 b", "hostname": "HD 209458",
    "pl_orbper": 3.5247, "pl_radj": 1.38, "pl_bmassj": 0.73,
    "pl_eqt": 1449.0, "sy_dist": 48.3, "st_teff": 6091.0,
    "st_rad": 1.2, "disc_year": 1999, "discoverymethod": "Transit",
    "ra": 330.795, "dec": 18.884,
}

# The planner target for tonight's event (planner._transit_targets shape).
FAKE_TARGET = {
    "id": "HD 209458 b", "kind": "transit", "name": "HD 209458 b",
    "mag": 7.65, "ra_deg": 330.795, "dec_deg": 18.884,
    "max_alt": 61.2, "hours_up": None,
    "max_time": "2026-09-08T00:15:00+00:00",
    "window_start": "2026-09-07T22:40:00+00:00",
    "window_end": "2026-09-08T01:50:00+00:00",
    "transit": {
        "name": "HD 209458 b", "star": "HD 209458",
        "ra": 330.795, "dec": 18.884,
        "ingress": datetime.datetime(2026, 9, 7, 22, 40,
                                     tzinfo=datetime.timezone.utc),
        "mid": datetime.datetime(2026, 9, 8, 0, 15,
                                 tzinfo=datetime.timezone.utc),
        "egress": datetime.datetime(2026, 9, 8, 1, 50,
                                    tzinfo=datetime.timezone.utc),
        "coverage": 1.0, "full": True, "depth_mmag": 16.4,
        "duration_h": 3.1, "v_mag": 7.65, "priority": "high",
        "min_telescope_in": 6.0, "oc_min": -12.0, "max_alt": 61.2,
    },
}


def test_exoplanet_keeps_tonights_transit_event(monkeypatch):
    # The bug: the Archive branch dropped the planner's transit dict, so
    # the card (and the light curve) had nothing to show for tonight.
    from nightscribe.core.sources import exoplanet_archive
    monkeypatch.setattr(exoplanet_archive, "planet",
                        lambda _name: dict(FAKE_ARCHIVE))
    out = enrich.enrich("HD 209458 b", fallback_target=FAKE_TARGET)
    assert out["type"] == "exoplanet"
    d = out["data"]
    assert d.get("transit") == FAKE_TARGET["transit"], \
        "tonight's transit event lost in the merge"
    assert d.get("pl_orbper") == 3.5247, "Archive fact lost in the merge"
    assert d.get("mag") == 7.65


def test_exoplanet_merge_never_overwrites_archive(monkeypatch):
    # ADR-027 rule: the Archive's ra/dec (floats) win over the planner's.
    from nightscribe.core.sources import exoplanet_archive
    monkeypatch.setattr(exoplanet_archive, "planet",
                        lambda _name: dict(FAKE_ARCHIVE))
    out = enrich.enrich("HD 209458 b", fallback_target=FAKE_TARGET)
    assert out["data"]["ra"] == 330.795
    assert out["data"]["dec"] == 18.884


def test_exoplanet_without_archive_still_tells_tonight(monkeypatch):
    # Archive silent (unknown name, network down): the card must still
    # show tonight's event from the planner context alone.
    from nightscribe.core.sources import exoplanet_archive
    monkeypatch.setattr(exoplanet_archive, "planet", lambda _name: None)
    out = enrich.enrich("HD 209458 b", fallback_target=FAKE_TARGET)
    d = out["data"]
    assert d.get("transit") == FAKE_TARGET["transit"]
    assert d.get("ra") == 330.795, "planner ra_deg should fill the gap"
    assert d.get("dec") == 18.884
    assert d.get("window_start") == FAKE_TARGET["window_start"]


def test_exoplanet_without_context_unchanged(monkeypatch):
    # typed straight into Explore with no planner row: Archive only,
    # and an unknown planet still lands as "not found".
    from nightscribe.core.sources import exoplanet_archive
    monkeypatch.setattr(exoplanet_archive, "planet",
                        lambda _name: dict(FAKE_ARCHIVE))
    out = enrich.enrich("HD 209458 b")
    assert out["data"].get("pl_name") == "HD 209458 b"
    assert "transit" not in out["data"]
    monkeypatch.setattr(exoplanet_archive, "planet", lambda _name: None)
    out = enrich.enrich("HD 209458 b")
    assert not out["data"], "empty data must stay falsy (missing state)"
