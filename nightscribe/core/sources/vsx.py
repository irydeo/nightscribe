############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - AAVSO VSX source module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""AAVSO VSX (Variable Star Index) object lookup.

One HTTP call per star through the db cache (TTL 7 days, V-c). NOTE: the
API lives on the `vsx.aavso.org` subdomain — `www.aavso.org` sits behind a
Cloudflare challenge that blocks plain clients (verified 2026-09-11).
Failure never breaks anything: lookup() returns None and the caller falls
back to SIMBAD/manual.
"""

import json
import logging

import requests

from ..db import db

logger = logging.getLogger(__name__)

URL = "https://vsx.aavso.org/index.php"


def lookup(name, force=False):
    # One variable star from the VSX API (name or AUID).
    # @args: name - e.g. "T CrB", force - bypass the cache read
    # @return: dict {name, auid, ra_deg, dec_deg, var_type, period_d,
    #          epoch_mjd, max, min, max_band, min_band, spectral,
    #          constellation} or None when unknown / on failure
    def fetch():
        r = requests.get(URL, params={"view": "api.object", "ident": name,
                                      "format": "json"}, timeout=30)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(f"vsx:object:{name}", "vsx", fetch,
                              force=force)
    except requests.RequestException as err:
        logger.warning("VSX lookup failed for %s: %s", name, err)
        return None
    return parse_object(body)


def _float(text):
    # @return: float of the first token of a VSX numeric string, or None
    try:
        return float(str(text).split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def _mag(text):
    # VSX magnitudes carry the band: "2.0 V" -> (2.0, "V")
    # @return: (value or None, band string)
    parts = str(text or "").split()
    return _float(text), (parts[1] if len(parts) > 1 else "")


def parse_object(body):
    # @args: body - raw JSON bytes of the api.object answer
    # @return: curated dict, or None when VSX does not know the name
    #          ({"VSXObject":[]}) or the payload is broken
    try:
        obj = json.loads(body.decode("utf-8", "replace")).get("VSXObject")
    except (ValueError, AttributeError) as err:
        logger.warning("VSX payload not parseable: %s", err)
        return None
    if not obj:
        return None
    epoch_mjd = None
    if _float(obj.get("Epoch")) is not None:
        epoch_mjd = _float(obj.get("Epoch")) - 2400000.5  # JD -> MJD
    max_mag, max_band = _mag(obj.get("MaxMag"))
    min_mag, min_band = _mag(obj.get("MinMag"))
    return {"name": obj.get("Name") or "",
            "auid": obj.get("AUID") or "",
            "ra_deg": _float(obj.get("RA2000")),
            "dec_deg": _float(obj.get("Declination2000")),
            "var_type": obj.get("VariabilityType") or "",
            "period_d": _float(obj.get("Period")),
            "epoch_mjd": epoch_mjd,
            "max": max_mag, "min": min_mag,
            "max_band": max_band, "min_band": min_band,
            "spectral": obj.get("SpectralType") or "",
            "constellation": obj.get("Constellation") or ""}
