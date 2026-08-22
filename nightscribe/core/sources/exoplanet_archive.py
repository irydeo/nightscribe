############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - NASA Exoplanet Archive source (TAP)
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

from ..db import db

logger = logging.getLogger(__name__)

URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

_FIELDS = ("pl_name,hostname,pl_orbper,pl_radj,pl_bmassj,pl_eqt,sy_dist,"
           "st_teff,st_rad,disc_year,discoverymethod,ra,dec")


def planet(name):
    # Fetches the composite parameters of a confirmed exoplanet.
    # @args: name - e.g. "HD 209458 b"
    # @return: dict or None
    query = (f"select {_FIELDS} from pscomppars where pl_name='{name}'")

    def fetch():
        r = requests.get(URL, params={"query": query, "format": "json"},
                         timeout=40)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(f"exoplanet_archive:{name}", "exoplanet_archive",
                              fetch)
        rows = json.loads(body.decode("utf-8", "replace"))
        return rows[0] if rows else None
    except (requests.RequestException, ValueError, IndexError) as err:
        logger.warning("Exoplanet Archive failed for %s: %s", name, err)
        return None
