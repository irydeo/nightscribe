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
           "st_teff,st_rad,disc_year,discoverymethod,ra,dec,"
           # Track D (EXOTIC handoff): orbital geometry, the published
           # mid-transit time and the stellar context the inits.json wants.
           # NB: pscomppars metallicity is st_met (+st_metratio="[Fe/H]") —
           # st_metfe does NOT exist in this table (verified 2026-09-10).
           "pl_orbincl,pl_orbeccen,st_logg,st_met,st_metratio,pl_orbsmax,"
           "pl_tranmid,sy_pmra,sy_pmdec,"
           # The uncertainties travel with them (2026-09-30): EXOTIC fits the
           # transit time inside a window built from them, and with none it
           # falls back to a window so wide that its aperture/comparison
           # search cannot fit the time at all (measured: 3 distinct tmid
           # values in 3809 search fits against 1289 once they are filled,
           # and the final T_mid went from +-0.0019 to +-0.0011 d).
           "pl_tranmiderr1,pl_orbpererr1,pl_radjerr1,st_raderr1,"
           "pl_orbinclerr1,pl_orbsmaxerr1,pl_orbeccenerr1,pl_orblper,"
           "st_tefferr1,st_tefferr2,st_meterr1,st_meterr2,"
           "st_loggerr1,st_loggerr2")

# Cache namespace bump (Track D, uncertainties): rows cached before the
# _FIELDS extension lack the new columns, so they must not be served under
# the old key. v2 -> v3 (2026-09-30).
_CACHE = "exoplanet_archive:v3"


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
        body, _ = db.http_get(f"{_CACHE}:{name}", "exoplanet_archive",
                              fetch)
        rows = json.loads(body.decode("utf-8", "replace"))
        return rows[0] if rows else None
    except (requests.RequestException, ValueError, IndexError) as err:
        logger.warning("Exoplanet Archive failed for %s: %s", name, err)
        return None
