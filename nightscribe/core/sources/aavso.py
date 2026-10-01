############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - AAVSO editorial channel source (alerts + campaigns)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The AAVSO editorial channel (ADR-037, SC4b): what the world's variable-
star authority currently flags as worth observing — forum *alerts* (the
Alerts category of forums.aavso.org; Discourse serves native per-category
JSON, validated in the SC4b spike 2026-09-16) and the *observing campaigns*
list (apps.aavso.org/v2/campaigns/, server-rendered HTML parsed
tolerantly). Both cached via db.py (source "aavso", TTL 12 h). Every
failure degrades to [] — Tonight must never break over a news feed.

Titles are free text, so the star name is extracted with tolerant patterns
("SU Tau", "T CRB", "V838 Her", "NSV 11664", "Nova Sgr 2026 No. 3") and
validated through VSX by the caller — a title that resolves to nothing is
simply not shown.
"""

import json
import logging
import re
import time

import requests

from ..db import db

logger = logging.getLogger(__name__)

ALERTS_URL = "https://forums.aavso.org/c/observing/alerts/50.json"
CAMPAIGNS_URL = "https://apps.aavso.org/v2/campaigns/"
TOPIC_URL = "https://forums.aavso.org/t/{}"

# star-name patterns in free-text titles (order matters: the first match
# wins). Validated downstream through VSX, so false positives cost one
# cached lookup and simply drop out.
_RE_NOVA = re.compile(
    r"\b(Nova\s+[A-Z][a-z]{2}\s+\d{4}(?:\s+No\.?\s*\d+)?)")
_RE_NSV = re.compile(r"\b(NSV\s*\d{1,5})\b")
_RE_DESIG = re.compile(
    r"\b((?:V\d{3,4}|[A-Z]{1,2})\s+(?:[A-Z][a-z]{2}|[A-Z]{2,3}))\b")


def _get(url, cache_key, force=False):
    # One cached GET; returns the decoded body or None on failure.
    def fetch():
        r = requests.get(url, headers={"User-Agent": "NightScribe"},
                         timeout=30)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(cache_key, "aavso", fetch, force=force)
        return body
    except requests.RequestException as err:
        logger.warning("AAVSO fetch failed (%s): %s", cache_key, err)
        return None


def alerts(days=60, force=False):
    # Recent topics of the forum's Alerts category (Discourse JSON).
    # @args: days - a topic counts as current when its last post is at
    #        most this many days old, force - bypass the cache reads
    # @return: [{"id", "title", "date", "url"}] newest first
    body = _get(ALERTS_URL, "aavso:alerts", force=force)
    try:
        topics = (json.loads(body.decode("utf-8", "replace"))
                  .get("topic_list", {}).get("topics", [])) if body else []
    except ValueError:
        logger.warning("AAVSO alerts JSON not parseable")
        return []
    out = []
    for t in topics:
        if t.get("pinned"):      # the "About the Alerts category" post
            continue
        last = (t.get("last_posted_at") or t.get("created_at") or "")[:10]
        try:
            age = time.time() - time.mktime(
                time.strptime(last, "%Y-%m-%d"))
        except ValueError:
            continue
        if age > days * 86400:
            continue
        out.append({"id": t.get("id"), "title": (t.get("title") or "")
                    .strip(), "date": last, "url": TOPIC_URL.format(
                        t.get("id"))})
    out.sort(key=lambda a: a["date"], reverse=True)
    return out


def campaigns(today=None, force=False):
    # The ACTIVE observing campaigns, parsed from the list page (rows:
    # id+link | title | requester | start | end | kinds).
    # @args: today - datetime.date (default: today, UTC), force - bypass
    #        the cache reads
    # @return: [{"id", "title", "requester", "start", "end", "kinds",
    #          "url"}]
    body = _get(CAMPAIGNS_URL, "aavso:campaigns", force=force)
    if not body:
        return []
    html = body.decode("utf-8", "replace")
    today = today or time.strftime("%Y-%m-%d")
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"\s+", " ",
                        re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 6 or not cells[0].isdigit():
            continue
        href = re.search(r'href="([^"]*campaigns/\d+[^"]*)"', row)
        start, end = cells[3].split(" ")[0], cells[4].split(" ")[0]
        if not (start <= today <= end):
            continue
        out.append({"id": int(cells[0]), "title": cells[1],
                    "requester": cells[2], "start": start, "end": end,
                    "kinds": cells[5],
                    "url": ("https://apps.aavso.org" + href.group(1))
                    if href else CAMPAIGNS_URL})
    return out


PHOTOMETRY_URL = "https://apps.aavso.org/v2/api/observations/photometry/"


def _get_auth(url, params, cache_key, token, force=False):
    # One cached GET against the token-protected AAVSO API (the photometry
    # endpoint answers 401 without it). The token never enters the cache
    # key — the same star reads the same cache whoever asks.
    def fetch():
        r = requests.get(url, params=params,
                         headers={"User-Agent": "NightScribe",
                                  "Authorization": f"Token {token}"},
                         timeout=30)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(cache_key, "aavso", fetch, force=force)
        return body
    except requests.RequestException as err:
        logger.warning("AAVSO auth fetch failed (%s): %s", cache_key, err)
        return None


def _parse_latest_obs(body):
    # Tolerant parse of the photometry answer (DRF-paginated {"results":
    # [...]} or a bare list); the newest point wins by jd_dbl.
    # @return: {"mjd", "filter", "mag"} or None
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except (ValueError, AttributeError):
        return None
    rows = data.get("results") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return None
    best = None
    for r in rows:
        try:
            jd = float(r.get("jd_dbl") or r.get("jd"))
            mag = float(r.get("magnitude"))
        except (TypeError, ValueError):
            continue
        if best is None or jd > best[0]:
            best = (jd, mag, str(r.get("band") or "?"))
    if best is None:
        return None
    return {"mjd": best[0] - 2400000.5, "filter": best[2],
            "mag": best[1]}


def latest_community_mag(name, token, days=30, force=False):
    # The freshest AAVSO community magnitude of a star (ADR-037 SC4a
    # bright-vigil backend): the right source for stars brighter than
    # ZTF's saturation limit (~11-12 mag) — and fresher, since observers
    # report within hours. Needs the user's API token (AAVSO account);
    # without one the caller never reaches here.
    # @args: name - star name as AAVSO knows it ("T CrB"), token - API
    #        token, days - look-back window, force - bypass cache reads
    # @return: {"mjd", "filter", "mag"} or None
    if not token:
        return None
    end = time.strftime("%Y-%m-%d", time.gmtime())
    start = time.strftime("%Y-%m-%d", time.gmtime(time.time()
                                                  - days * 86400))
    body = _get_auth(PHOTOMETRY_URL,
                     {"target": name, "start_date": start,
                      "end_date": end},
                     f"aavso:phot:{name}:{days}", token, force=force)
    if body is None:
        return None
    return _parse_latest_obs(body)


def latest_community_mag_cached(name, days=30, db_obj=None):
    # Cache-only twin (the signals console never touches the network):
    # returns None on a miss — also when no token was ever configured, so
    # the entry simply never got cached.
    cache = db_obj if db_obj is not None else db
    body = cache.cache_get(f"aavso:phot:{name}:{days}")
    if not body:
        return None
    return _parse_latest_obs(body[0])


def _parse_curve(body, bands=None, min_points=1):
    # The whole photometry answer as a light curve (quality plan, D1):
    # every observation with a usable magnitude, its error when the
    # observer gave one, the band and whether it is a visual estimate
    # (which is a different animal from a CCD measurement).
    # @args: body - the raw HTTP body, bands - band labels to keep
    #        (None: all), min_points - give up below this many
    # @return: [{"mjd", "mag", "err", "filter", "kind", "observer"}]
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except (ValueError, AttributeError):
        return []
    rows = data.get("results") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    keep = {b.upper() for b in bands} if bands else None
    out = []
    for r in rows:
        try:
            jd = float(r.get("jd_dbl") or r.get("jd"))
            mag = float(r.get("magnitude"))
        except (TypeError, ValueError):
            continue
        band = str(r.get("band") or "?").strip()
        if keep is not None and band.upper() not in keep:
            continue
        err = None
        for key in ("uncertainty", "error", "mag_err"):
            try:
                if r.get(key) is not None:
                    err = abs(float(r.get(key)))
                    break
            except (TypeError, ValueError):
                continue
        kind = str(r.get("obs_type") or "").lower()
        visual = "visual" in kind or "estimate" in kind or \
            r.get("visual") is True
        out.append({"mjd": jd - 2400000.5, "mag": mag, "err": err,
                    "filter": band, "kind": "visual" if visual else "ccd",
                    "observer": (r.get("observer") or "").strip()})
    out.sort(key=lambda p: p["mjd"])
    return out if len(out) >= min_points else out


def fetch_lightcurve(name, token, days=3650, bands=None, force=False):
    # The AAVSO community light curve of a star (quality plan, D1): the
    # way a single observing night stops being the whole story — the
    # reference report of the V0526 Per case was made exactly like this,
    # with the community's past observations fixing the period.
    #
    # It needs the observer's API token (the same one the bright-vigil
    # channel uses) because the AAVSO API refuses anonymous reads, and it
    # is cached like everything else (source "aavso", 12 h).
    #
    # @args: name - the star as AAVSO knows it ("V0526 Per", "T CrB"),
    #        token - API token, days - look-back window (default 10 years),
    #        bands - band labels to keep (None: all of them), force -
    #        bypass the cache reads
    # @return: {"points": [...], "n": int, "bands": {band: n}} - or None
    #          when there is no token, no connection or no answer
    if not token or not name:
        return None
    end = time.strftime("%Y-%m-%d", time.gmtime())
    start = time.strftime("%Y-%m-%d", time.gmtime(time.time()
                                                  - float(days) * 86400))
    body = _get_auth(PHOTOMETRY_URL,
                     {"target": name, "start_date": start,
                      "end_date": end},
                     f"aavso:curve:{name}:{int(days)}", token, force=force)
    if body is None:
        return None
    points = _parse_curve(body, bands=bands)
    counts = {}
    for p in points:
        counts[p["filter"]] = counts.get(p["filter"], 0) + 1
    return {"points": points, "n": len(points), "bands": counts,
            "start": start, "end": end}


def extract_star_name(title):
    # The star a free-text alert/campaign title is about, or None.
    # "Photometry requested for GK Per" -> "GK Per"; "T CRB Johnson V
    # scores below 8.5" -> "T CRB"; "RCB variable NSV 11664 in Aquila is
    # dimming" -> "NSV 11664" (the NSV name, not the class word).
    # @return: candidate name string for a VSX lookup, or None
    title = title or ""
    for pat in (_RE_NOVA, _RE_NSV, _RE_DESIG):
        m = pat.search(title)
        if m:
            return " ".join(m.group(1).split())
    return None
