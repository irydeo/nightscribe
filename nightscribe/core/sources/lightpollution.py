############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Light pollution (sky brightness) source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The site's sky brightness, from the light-pollution atlas.

NightScribe knows the observer's coordinates, so it can look up how bright
their zenith sky is instead of asking them to guess. The data is the
**New World Atlas of Artificial Night Sky Brightness** (Falchi et al. 2016)
and its **Sky brightness** successor (NASA Black Marble 2.0), served per
point by lightpollutionmap.info. The site documents the exact conversion
(FAQ #31): the query returns the ARTIFICIAL brightness in mcd/m2, and with
the natural reference (22.0 mag/arcsec2 = 0.171168465 mcd/m2) the total is
that plus the natural part, and

    MPSAS = log10(total_mcd_m2 / 108000000) / -0.4

The query needs a **key** from the site (the same pattern as the other
optional keys): without it, the observer types the value by hand, read off
the map. The atlas is static, so the answer is cached for a long time.

What the number IS and IS NOT (the site says so, and the guide repeats it):
it is the modelled ZENITH brightness, a "best case"; VIIRS is nearly blind
to blue, so a sky lit by white LEDs can be brighter than predicted. Good for
comparing sites; a starting point, not a promise.
"""

import json
import logging
import math

import requests

from ..db import db

logger = logging.getLogger(__name__)

# The atlas, per point. wa_2015 is the Falchi 2016 World Atlas layer the site
# documents the conversion for.
_ENDPOINT = "https://www.lightpollutionmap.info/QueryRaster/"
_LAYER = "wa_2015"
_TIMEOUT = 12.0

# The natural night sky: 22.0 mag/arcsec2 equals this radiance (mcd/m2). The
# total zenith brightness is the artificial part plus this floor.
NATURAL_MCD_M2 = 0.171168465
# The constant in the site's documented conversion.
_MCD_REFERENCE = 108000000.0


class LightPollutionError(Exception):
    # The atlas did not answer, or the key was rejected.
    pass


def mpsas_from_artificial(artificial_mcd_m2):
    # The site's own conversion (FAQ #31): artificial radiance (mcd/m2) to
    # mag/arcsec2. Raises LightPollutionError on a value that cannot be a
    # radiance (negative or not a number), so a broken answer is never shown
    # as a sky brightness.
    # @args: artificial_mcd_m2 - the atlas value in mcd/m2
    # @return: sky brightness in mag/arcsec2 (float)
    try:
        value = float(artificial_mcd_m2)
    except (TypeError, ValueError) as err:
        raise LightPollutionError(f"not a number: {artificial_mcd_m2!r}") from err
    if value < 0:
        raise LightPollutionError(f"negative radiance: {value}")
    total = value + NATURAL_MCD_M2
    return math.log10(total / _MCD_REFERENCE) / -0.4


def _parse_value(body):
    # The endpoint's response shape is not documented; this reads the common
    # ones (a bare number, a {"value"/"data"/"result": ...} envelope, or a
    # plain text number) and raises when none fits, so the failure is named
    # instead of turning into a silent zero. Pinning it against the real
    # endpoint is pending (same philosophy as ADR-021/030).
    # @args: body - the decoded JSON (dict/number) or the raw text
    # @return: the artificial brightness (float)
    if isinstance(body, dict):
        for key in ("value", "data", "result", "brightness", "radiance"):
            if key in body:
                return _parse_value(body[key])
        raise LightPollutionError(f"unexpected atlas reply: {body!r}")
    if isinstance(body, (int, float)):
        return float(body)
    try:
        return float(str(body).strip())
    except (TypeError, ValueError) as err:
        raise LightPollutionError(f"unexpected atlas reply: {body!r}") from err


def sky_brightness_mpsas(lat, lon, key):
    # The modelled zenith sky brightness at a point.
    # @args: lat/lon - degrees, key - the lightpollutionmap.info API key
    # @return: mag/arcsec2 (float)
    # @raise: LightPollutionError when there is no key or the atlas fails
    if not key:
        raise LightPollutionError("no API key")
    qd = f"{float(lon):.6f},{float(lat):.6f}"

    def fetch():
        try:
            r = requests.get(_ENDPOINT,
                             params={"ql": _LAYER, "qt": "point",
                                     "qd": qd, "key": key},
                             timeout=_TIMEOUT)
            text = r.text
        except requests.RequestException as err:
            raise LightPollutionError(f"no answer from the atlas: {err}") from err
        try:
            body = json.loads(text)
        except ValueError:
            body = text
        value = _parse_value(body)
        return str(value).encode("utf-8"), "text/plain"

    # cached (source "lightpollution", TTL 30 days: the atlas is static)
    raw, _ = db.http_get(f"lightpollution:{_LAYER}:{qd}", "lightpollution", fetch)
    return mpsas_from_artificial(float(raw.decode("utf-8")))
