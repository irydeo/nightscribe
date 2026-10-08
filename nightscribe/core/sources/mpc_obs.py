############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Minor Planet Center observations source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Published astrometry from the Minor Planet Center (MPC).

Two endpoints, both verified 2026-10-04:

- get-obs       : confirmed objects, by designation.
- get-obs-neocp : unconfirmed NEOCP/PCCP tracklets, by submission id.

Both are GET requests **with a JSON body** (a POST answers 405) and answer
with the envelope ``[payload, http_status]``: a list whose first element
holds the data and whose trailing integer is the HTTP status. The payload
can carry ADES_DF (parsed here into Obs) and OBS80 (the 80-column lines,
handed over verbatim).

Everything goes through ``core/db.db`` so a designation is fetched once and
kept in the shared cache (TTL ``mpc_obs_ttl_h``, 6 h by default). Network
failures and unknown objects never raise: they answer empty, and the caller
degrades (the object card simply shows no fresh history).
"""

import datetime
import json
import logging
from dataclasses import dataclass

import requests

from ...config import config
from ..coords import datetime_from_jd, jd_from_datetime
from ..db import SOURCE_TTL, db

logger = logging.getLogger(__name__)

URL_OBS = "https://data.minorplanetcenter.net/api/get-obs"
URL_NEOCP = "https://data.minorplanetcenter.net/api/get-obs-neocp"

# db keeps a per-source TTL table; this source is not in the built-in
# defaults, so we register it from the config knob (mpc_obs_ttl_h, 6 h).
# setdefault keeps it idempotent if the module is imported twice.
SOURCE_TTL.setdefault(
    "mpc_obs", int(config.get("mpc_obs_ttl_h") or 6) * 3600)


@dataclass
class Obs:
    # One astrometric observation, normalised. RA/Dec are degrees (ICRS,
    # as published), MJD is UTC. rms_ra/rms_dec are arcseconds and may be
    # None: the MPC only reports them for modern, ADES-aware submissions
    # (Apophis: 2013 of 9527 rows), and inventing a zero would make
    # Find_Orb weight the observation as perfect.
    #
    # ra/dec may also be None: stellar occultations (mode "OCC", sys
    # "ICRF_KM") are timed positions given as a relative offset
    # (pos1/pos2/pos3 + dist), not as an equatorial direction. Dropping
    # them would silently shrink the history: for Apophis those 7 rows are
    # the difference between 9520 obs / 240 stations / last 2021-05-20 and
    # the real 9527 / 241 / 2022-04-09 (station 275 saw it only that way).
    stn: str
    mjd: float
    ra: float | None = None
    dec: float | None = None
    rms_ra: float | None = None
    rms_dec: float | None = None
    mag: float | None = None
    band: str = ""
    astcat: str = ""
    ref: str = ""
    mode: str = ""


def iso_to_mjd(text):
    # MPC times are ISO 8601 UTC with a trailing "Z"
    # ("2020-12-04T10:41:43.230Z"). datetime.fromisoformat only learned
    # the bare "Z" in Python 3.11, so we normalise it to "+00:00" first.
    # MJD is just JD - 2400000.5, and the JD conversion lives in coords so
    # the whole app reads one clock (no duplicated calendar math).
    # @args: text - ISO timestamp, possibly None
    # @return: MJD float, or None when the text is missing/unparseable
    if not text:
        return None
    raw = str(text).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    return jd_from_datetime(dt) - 2400000.5


def _to_float(value):
    # ADES numbers travel as strings ("53.53118"); a blank or null means
    # "not reported" and must stay None, never become 0.0.
    # @return: float, or None when absent/unparseable
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_str(value):
    # @return: trimmed string, "" for None
    return "" if value is None else str(value).strip()


def parse_ades_df(data):
    # Turns the decoded JSON envelope of either endpoint into Obs rows.
    # The envelope is a list whose elements are payload dicts and, at the
    # end, the HTTP status integer; NEOCP answers a null ADES_DF for an
    # unknown tracklet. We walk every dict, skip everything else, and drop
    # rows without a usable time: a row with no obstime cannot be placed
    # in the timeline, while a row with no RA/Dec (an occultation) is still
    # a real observation and must count.
    # @args: data - decoded JSON (list or dict)
    # @return: list[Obs]
    blocks = data if isinstance(data, list) else [data]
    rows_out = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for row in block.get("ADES_DF") or []:
            if not isinstance(row, dict):
                continue
            mjd = iso_to_mjd(row.get("obstime"))
            if mjd is None:
                continue
            rows_out.append(Obs(
                stn=_to_str(row.get("stn")),
                mjd=mjd,
                ra=_to_float(row.get("ra")),
                dec=_to_float(row.get("dec")),
                rms_ra=_to_float(row.get("rmsra")),
                rms_dec=_to_float(row.get("rmsdec")),
                mag=_to_float(row.get("mag")),
                band=_to_str(row.get("band")),
                astcat=_to_str(row.get("astcat")),
                ref=_to_str(row.get("ref")),
                mode=_to_str(row.get("mode")),
            ))
    return rows_out


def _get_json(url, payload, key, force):
    # Cached GET-with-body. The body must be JSON and the method GET: the
    # MPC rejects POST with 405 (verified 2026-10-04). A generous timeout
    # because a busy object is megabytes (Apophis: 18 MB, 9527 rows).
    # @args: payload - dict sent as the JSON body, key - cache key,
    #        force - True bypasses the cache read
    # @return: decoded JSON, or None on network/parse failure
    def fetch():
        r = requests.get(url, json=payload, timeout=120)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(key, "mpc_obs", fetch, force=force)
    except requests.RequestException as err:
        logger.warning("MPC request failed for %s: %s", key, err)
        return None
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except ValueError as err:
        logger.warning("MPC payload not parseable for %s: %s", key, err)
        return None


def observations(desig, force=False):
    # Every published observation of a designated (confirmed) object.
    # A single object can carry thousands of rows and hundreds of
    # stations (Apophis: 9527 rows, 241 stations), so callers that only
    # need a window should filter by MJD instead of trusting a small list.
    # Rows from stellar occultations have ra/dec None: a caller doing
    # positional work must skip them, a caller counting history must not.
    # @args: desig - MPC designation ("99942", "2020 CD3"),
    #        force - True bypasses the cache read
    # @return: list[Obs]; empty when the object is unknown or offline
    data = _get_json(URL_OBS,
                     {"desigs": [desig], "output_format": ["ADES_DF"]},
                     f"mpcobs:{desig}", force)
    return parse_ades_df(data) if data is not None else []


def neocp_observations(trksub, force=False):
    # Observations of an unconfirmed NEOCP/PCCP tracklet. The API keys on
    # the tracklet submission id (trksub), not on the provisional name.
    # @args: trksub - NEOCP submission id, force - bypass the cache read
    # @return: list[Obs]; empty when the tracklet is unknown or offline
    data = _get_json(URL_NEOCP,
                     {"trksubs": [trksub], "output_format": ["ADES_DF"]},
                     f"mpcobs:neocp:{trksub}", force)
    return parse_ades_df(data) if data is not None else []


def observations_80(desig, force=False):
    # The same observations as plain 80-column MPC lines, exactly as the
    # MPC formats them. These are what gets concatenated with our own
    # astrometry in the Find_Orb input file: re-formatting them by hand
    # would only add rounding risk, so we pass them through untouched.
    # @args: desig - MPC designation, force - bypass the cache read
    # @return: the block of lines as text ("" when unknown or offline)
    data = _get_json(URL_OBS,
                     {"desigs": [desig], "output_format": ["OBS80"]},
                     f"mpcobs:80:{desig}", force)
    blocks = data if isinstance(data, list) else [data]
    for block in blocks:
        if isinstance(block, dict) and block.get("OBS80"):
            return block["OBS80"]
    return ""


def history(desig, force=False):
    # The three figures the object card needs (D28): how many
    # observations exist, how many distinct observatories have seen it and
    # when it was last seen. A different stn is a different site, so the
    # set of stations is the honest "who has seen it"; many stations plus
    # a recent date means a live, well-determined object, one station and
    # months of silence means a candidate to be lost.
    # @args: desig - MPC designation, force - bypass the cache read
    # @return: dict {n_obs, n_stations, last_obs}; zeros and None when
    #          the object is unknown or the network is down
    obs = observations(desig, force=force)
    if not obs:
        return {"n_obs": 0, "n_stations": 0, "last_obs": None}
    last_dt = datetime_from_jd(max(o.mjd for o in obs) + 2400000.5)
    return {
        "n_obs": len(obs),
        "n_stations": len({o.stn for o in obs if o.stn}),
        "last_obs": last_dt.strftime("%Y-%m-%d"),
    }
