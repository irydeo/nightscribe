############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - ExoClock (ESA Ariel) exoplanet catalogue source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import json
import logging

import requests

from .. import coords
from ..db import db

logger = logging.getLogger(__name__)

URL = "https://www.exoclock.space/database/planets_json"


def planets():
    # The ExoClock target catalogue, as a list of handy dicts.
    # @return: list of dicts with transit ephemeris and priorities
    def fetch():
        r = requests.get(URL, timeout=60)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get("exoclock:planets", "exoclock", fetch)
        raw = json.loads(body.decode("utf-8", "replace"))
    except (requests.RequestException, ValueError) as err:
        logger.warning("ExoClock fetch failed: %s", err)
        return []
    result = []
    for key, p in raw.items():
        try:
            result.append({
                "name": p.get("name") or key,
                "star": p.get("star"),
                "ra": coords.ra_hms_to_deg(p["ra_j2000"]),
                "dec": coords.dec_dms_to_deg(p["dec_j2000"]),
                "t0": float(p["ephem_mid_time"]),
                "period": float(p["ephem_period"]),
                "depth_mmag": p.get("depth_r_mmag"),
                "duration_h": p.get("duration_hours"),
                "v_mag": p.get("v_mag"),
                "priority": p.get("priority"),
                "min_telescope_in": p.get("min_telescope_inches"),
                "oc_min": p.get("current_oc_min"),
            })
        except (TypeError, ValueError, KeyError, AttributeError):
            continue
    return result
