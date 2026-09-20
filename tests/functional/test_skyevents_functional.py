############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Functional test: the sky-events engine end to end
# (Track SC2; pure local maths — no network needed even here)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""End to end, with the REAL user config (site, horizon): the 7-day sky
calendar comes out with its families, the Galilean satellite windows carry
their site observability, and every row honours the documented contract.
"""

import pytest

from nightscribe.config import config
from nightscribe.core import skyevents


def test_week_calendar_end_to_end_with_real_site():
    lat = float(config.get("lat"))
    lon = float(config.get("lon"))
    evs = skyevents.events(lat, lon, days=7)
    assert evs, "a week of sky events must never come back empty"
    # the contract on every row, whatever the mix tonight happens to be
    for ev in evs:
        for key in ("jd", "date", "kind", "icon", "objects", "tonight"):
            assert key in ev
        assert isinstance(ev["tonight"], bool)
    # Io's ~1.77 d orbit guarantees Galilean windows in any 7-day span
    # (both phenomena: the moon itself and its shadow)
    kinds = {e["kind"] for e in evs}
    assert "sat_transit" in kinds and "shadow_transit" in kinds
    # site observability is computed for every satellite event
    for ev in evs:
        if ev["kind"] in ("sat_transit", "shadow_transit"):
            assert ev["observable"] in (True, False)
            assert ev["uncertainty_min"] > 0
            assert ev["t0"] is not None and ev["t1"] is not None
