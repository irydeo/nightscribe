############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Survey light-curve context source (ALeRCE/ZTF)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Survey photometry context for light curves (V-f): grey reference points
under the observer's own ones, never mixed with them (source="survey:ztf").

Provider: the ALeRCE ZTF API v1 (verified live 2026-09-11). Two cached
calls per object (conesearch -> oid, oid -> lightcurve), TTL 30 days.
Failure returns [] — nothing downstream may break.
"""

import json
import logging

import requests

from ..db import db

logger = logging.getLogger(__name__)

_BASE = "https://api.alerce.online/ztf/v1"
_FID = {1: "g", 2: "r", 3: "i"}      # ZTF band ids


def fetch_points(ra_deg, dec_deg, radius_arcsec=3.0, force=False):
    # ZTF detections near a position, as followup-point shaped dicts.
    # @args: ra_deg/dec_deg - target (degrees), radius_arcsec - match
    #        radius, force - bypass the cache reads
    # @return: [{"mjd", "filter", "mag", "err", "source": "survey:ztf"}]
    oid = _conesearch_oid(ra_deg, dec_deg, radius_arcsec, force=force)
    if not oid:
        return []
    return _to_points(_lightcurve(oid, force=force))


def _get(url, params, cache_key, force):
    # One cached GET; returns the decoded JSON or None on failure.
    def fetch():
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(cache_key, "surveys", fetch, force=force)
        return json.loads(body.decode("utf-8", "replace"))
    except (requests.RequestException, ValueError) as err:
        logger.warning("survey fetch failed (%s): %s", cache_key, err)
        return None


def _conesearch_oid(ra_deg, dec_deg, radius_arcsec, force=False):
    # @return: the oid of the nearest ALeRCE object inside the radius, None
    data = _get(f"{_BASE}/objects/",
                {"ra": ra_deg, "dec": dec_deg, "radius": radius_arcsec,
                 "page_size": 5},
                f"surveys:cone:{ra_deg:.4f}:{dec_deg:.4f}", force)
    items = (data or {}).get("items") or []
    best, best_d = None, None
    for it in items:
        d2 = ((it.get("meanra") or 1e9) - ra_deg) ** 2 \
            + ((it.get("meandec") or 1e9) - dec_deg) ** 2
        if best is None or d2 < best_d:
            best, best_d = it, d2
    return (best or {}).get("oid")


def _lightcurve(oid, force=False):
    # @return: {"detections": [...], "non_detections": [...]} or None
    return _get(f"{_BASE}/objects/{oid}/lightcurve", {},
                f"surveys:lc:{oid}", force)


def _to_points(data):
    # ALeRCE detections -> point dicts. Prefer the corrected PSF mag when
    # its error is valid; fid maps to the ZTF band letter.
    out = []
    for d in (data or {}).get("detections") or []:
        mag, err = d.get("magpsf_corr"), d.get("sigmapsf_corr_ext")
        if mag is None or err is None:
            mag, err = d.get("magpsf"), d.get("sigmapsf")
        if mag is None or d.get("mjd") is None:
            continue
        out.append({"mjd": d["mjd"],
                    "filter": _FID.get(d.get("fid"), str(d.get("fid"))),
                    "mag": mag, "err": err, "source": "survey:ztf"})
    return out
