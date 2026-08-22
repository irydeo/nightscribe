############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - JPL Close-Approach Data source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime
import json
import logging

import requests

from ..db import db

logger = logging.getLogger(__name__)

URL = "https://ssd-api.jpl.nasa.gov/cad.api"


def next_approach(des, years=10, dist_max=0.1):
    # Next close approaches of an object to Earth.
    # @args: des - designation, years - forward window, dist_max - AU limit
    # @return: dict with date, dist_au, dist_km, v_rel (km/s) or None
    today = datetime.datetime.now(datetime.timezone.utc)
    params = {
        "des": des,
        "date-min": today.strftime("%Y-%m-%d"),
        "date-max": (today + datetime.timedelta(days=365 * years)).strftime("%Y-%m-%d"),
        "dist-max": str(dist_max),
        "sort": "date",
    }

    def fetch():
        r = requests.get(URL, params=params, timeout=30)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(f"cad:{des}:{years}", "cad", fetch)
        data = json.loads(body.decode("utf-8", "replace"))
        rows = data.get("data") or []
        if not rows:
            return None
        fields = data["fields"]
        first = dict(zip(fields, rows[0]))
        dist_au = float(first["dist"])
        return {
            "date": first.get("cd"),
            "dist_au": dist_au,
            "dist_km": dist_au * 149597870.7,
            "dist_ld": dist_au * 149597870.7 / 384400.0,
            "v_rel": float(first["v_rel"]) if first.get("v_rel") else None,
        }
    except (requests.RequestException, ValueError, KeyError) as err:
        logger.warning("CAD failed for %s: %s", des, err)
        return None
