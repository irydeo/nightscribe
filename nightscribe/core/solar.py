############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Solar state module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging

from .sources import noaa, silso

logger = logging.getLogger(__name__)

# Aggregates the Sun's current state from NOAA + SILSO (see DATA_SOURCES).


def solar_now():
    # @return: dict with ssn, f107, kp, flare, regions, trend, aurora hint
    indices = noaa.solar_indices() or {}
    kp = noaa.kp_index() or {}
    flare = noaa.max_flare_7d()
    regions = noaa.active_regions()
    series = silso.daily_series(14)

    trend = None
    if len(series) >= 7:
        first = sum(d["ssn"] for d in series[:7]) / 7
        last = sum(d["ssn"] for d in series[-7:]) / 7
        if last > first * 1.1:
            trend = "up"
        elif last < first * 0.9:
            trend = "down"
        else:
            trend = "flat"

    aurora = None
    if kp.get("kp") is not None:
        if kp["kp"] >= 5:
            aurora = "possible"
        else:
            aurora = "unlikely"

    return {
        "ssn": indices.get("ssn"),
        "ssn_date": indices.get("time_tag"),
        "f107": indices.get("f107"),
        "kp": kp.get("kp"),
        "flare_7d": flare,
        "n_regions": len({r.get("region") for r in regions if r.get("region")}),
        "regions": regions,
        "trend": trend,
        "series": series,
        "aurora": aurora,
    }
