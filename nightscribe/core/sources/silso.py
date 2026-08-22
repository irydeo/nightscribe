############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - SILSO sunspot number source (SIDC, Belgium)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging

import requests

from ..db import db

logger = logging.getLogger(__name__)

URL = "https://www.sidc.be/SILSO/DATA/SN_d_tot_V2.0.txt"


def daily_series(days=30):
    # Recent daily sunspot numbers.
    # @args: days - how many days back
    # @return: list of dicts (date, ssn), oldest first; empty on failure
    def fetch():
        r = requests.get(URL, timeout=40)
        r.raise_for_status()
        return r.content, "text/plain"
    try:
        body, _ = db.http_get("silso:daily", "silso", fetch)
        lines = body.decode("utf-8", "replace").splitlines()
    except requests.RequestException as err:
        logger.warning("SILSO fetch failed: %s", err)
        return []
    series = []
    # Columns: year month day fraction ssn std n_obs definitive
    for line in lines[-days:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            ssn = float(parts[4])
        except ValueError:
            continue
        if ssn < 0:  # -1 means missing
            continue
        series.append({"date": f"{parts[0]}-{parts[1]}-{parts[2]}", "ssn": ssn})
    return series
