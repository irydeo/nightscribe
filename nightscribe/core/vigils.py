############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Vigils: standing watch on high-value variables (ADR-037)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Vigils (ADR-037, SC4a): a short standing watch list of high-value
variable stars whose interesting event is UNPREDICTABLE — a recurrent-nova
eruption (T CrB), an R CrB dust fade — so it cannot be scheduled, only
watched. The check compares the latest public survey magnitude (ZTF via
ALeRCE, core/sources/surveys.py) with each star's baseline; the observer's
own points are detect_event's job (ADR-035, V-h), never mixed here.

Two honest caveats: ZTF's cadence is ~2-3 days and ALeRCE ingestion adds
latency (a vigil is a zero-cost safety net, not an alert network); and the
ZTF g/r bands are not V — the thresholds are indicative, wide enough to
ignore quiescent wobble and catch real onsets.
"""

import json
import logging

logger = logging.getLogger(__name__)

# The curated defaults (the user edits the list in Settings; J2000
# coordinates from VSX). direction: "rise" watches for BRIGHTENING (mag
# falling below baseline - threshold), "drop" watches for FADING (mag
# above baseline + threshold) — mind the inverted magnitude axis.
DEFAULT_VIGILS = [
    {"name": "T CrB", "ra_deg": 239.87567, "dec_deg": 25.92017,
     "direction": "rise", "baseline_mag": 10.2, "threshold": 0.75},
    {"name": "R CrB", "ra_deg": 237.1433, "dec_deg": 28.1567,
     "direction": "drop", "baseline_mag": 5.8, "threshold": 0.75},
]


def default_vigils():
    # @return: a fresh copy of the curated watch list
    return [dict(v) for v in DEFAULT_VIGILS]


def norm_name(name):
    # Object names compare without case or inner spacing ("T CrB" ==
    # "t  crb") — the vigil list, the projects and VSX spellings differ.
    # @return: normalized name string
    return "".join(str(name or "").lower().split())


def vigils_from_config(cfg):
    # The configured watch list, or the curated defaults when unset/broken.
    # @args: cfg - Config ("vigil_list" holds a list of dicts, or its JSON
    #        text form straight from the settings editor)
    # @return: list of vigil dicts (name, direction, baseline_mag,
    #          threshold; ra_deg/dec_deg when known)
    raw = cfg.get("vigil_list")
    if not raw:
        return default_vigils()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            logger.warning("vigil_list is not valid JSON; using defaults")
            return default_vigils()
    out = []
    for v in raw if isinstance(raw, list) else []:
        if not isinstance(v, dict) or not v.get("name"):
            continue
        try:
            entry = {"name": str(v["name"]).strip(),
                     "direction": "drop" if v.get("direction") == "drop"
                     else "rise",
                     "baseline_mag": float(v["baseline_mag"]),
                     "threshold": float(v.get("threshold", 0.75))}
        except (TypeError, ValueError):
            continue
        if v.get("ra_deg") is not None and v.get("dec_deg") is not None:
            try:
                entry["ra_deg"] = float(v["ra_deg"])
                entry["dec_deg"] = float(v["dec_deg"])
            except (TypeError, ValueError):
                pass
        out.append(entry)
    return out or default_vigils()


def vigils_to_text(vigils):
    # The settings-editor form: one vigil per line,
    # name | rise|drop | baseline | threshold [| ra_deg | dec_deg].
    # @return: the multi-line text
    lines = []
    for v in vigils or []:
        parts = [v.get("name", ""), v.get("direction", "rise"),
                 f"{float(v.get('baseline_mag', 0)):.2f}",
                 f"{float(v.get('threshold', 0.75)):.2f}"]
        if v.get("ra_deg") is not None and v.get("dec_deg") is not None:
            parts += [f"{float(v['ra_deg']):.5f}", f"{float(v['dec_deg']):.5f}"]
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def vigils_from_text(text):
    # Tolerant parse of the settings-editor text (the inverse of
    # vigils_to_text). Blank/comment (#) lines and broken rows are
    # skipped — a bad line never breaks the rest of the list.
    # @return: list of vigil dicts (empty when nothing parses)
    out = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        try:
            entry = {"name": parts[0],
                     "direction": "drop" if parts[1].lower() == "drop"
                     else "rise",
                     "baseline_mag": float(parts[2]),
                     "threshold": float(parts[3])}
            if len(parts) >= 6:
                entry["ra_deg"] = float(parts[4])
                entry["dec_deg"] = float(parts[5])
        except ValueError:
            continue
        out.append(entry)
    return out


def _anomaly(vigil, latest):
    # The vigil rule (ADR-037): the latest survey magnitude is off the
    # baseline by at least the threshold, in the watched direction.
    # @args: vigil - vigil dict, latest - {"mag", "filter", "mjd"} | None
    # @return: alert dict or None
    if not latest or latest.get("mag") is None:
        return None
    base = float(vigil["baseline_mag"])
    thr = float(vigil.get("threshold", 0.75))
    delta = round(latest["mag"] - base, 2)   # inverted axis: + = fainter
    rise = vigil.get("direction") == "rise" and delta <= -thr
    drop = vigil.get("direction") == "drop" and delta >= thr
    if not (rise or drop):
        return None
    return {"name": vigil["name"], "direction": vigil["direction"],
            "baseline_mag": base, "threshold": thr,
            "mag": round(latest["mag"], 2),
            "filter": latest.get("filter") or "?",
            "mjd": latest.get("mjd"), "delta": delta,
            "ra_deg": vigil.get("ra_deg"), "dec_deg": vigil.get("dec_deg")}


def _resolve(name):
    # name -> (ra_deg, dec_deg) via VSX (7-day cached source), or
    # (None, None) when unknown — a vigil without coordinates is skipped.
    from .sources import vsx
    obj = vsx.lookup(name)
    if not obj:
        return None, None
    return obj.get("ra_deg"), obj.get("dec_deg")


BRIGHT_LIMIT = 11.5     # ZTF saturates brighter than ~this: those vigils
                        # read the AAVSO community photometry instead
                        # (verified live 2026-09-16: T CrB/R CrB have no
                        # ALeRCE object at all)


def _default_fetch(cfg):
    # The fetch router (ADR-037 SC4a, rev.): a vigil whose baseline is
    # brighter than BRIGHT_LIMIT reads the latest AAVSO community point
    # (needs the user's API token from Settings; without one the bright
    # vigil stays silent), fainter ones read the latest ZTF point.
    # @return: callable vigil -> {"mjd", "filter", "mag"} | None
    from .sources import aavso, surveys
    token = cfg.get("aavso_api_token", "")

    def _fetch(v):
        if float(v.get("baseline_mag", 99)) < BRIGHT_LIMIT:
            return aavso.latest_community_mag(v["name"], token)
        if v.get("ra_deg") is None:
            return None
        return surveys.latest_mag(v["ra_deg"], v["dec_deg"])
    return _fetch


def _cached_fetch(cfg, db_obj):
    # Cache-only twin of _default_fetch (the signals console never
    # touches the network): miss/uncached -> None.
    from .sources import aavso, surveys

    def _fetch(v):
        if float(v.get("baseline_mag", 99)) < BRIGHT_LIMIT:
            return aavso.latest_community_mag_cached(v["name"],
                                                     db_obj=db_obj)
        if v.get("ra_deg") is None:
            return None
        return surveys.latest_mag_cached(v["ra_deg"], v["dec_deg"],
                                         db_obj=db_obj)
    return _fetch


def check_vigils(cfg, fetch=None, resolve=True):
    # Runs the watch list against the latest survey/community magnitude.
    # One misbehaving star (network, VSX, bad row) never breaks the run.
    # @args: cfg - Config, fetch - injectable vigil-dict ->
    #        {"mjd", "filter", "mag"} | None (default: the brightness
    #        router, _default_fetch), resolve - allow VSX name resolution
    #        (needs network on a cache miss; the cache-only callers pass
    #        False)
    # @return: [alert dicts] (see _anomaly)
    if fetch is None:
        fetch = _default_fetch(cfg)
    alerts = []
    for v in vigils_from_config(cfg):
        v = dict(v)
        if (v.get("ra_deg") is None or v.get("dec_deg") is None):
            if not resolve:
                continue
            ra, dec = _resolve(v["name"])
            if ra is None or dec is None:
                continue
            v["ra_deg"], v["dec_deg"] = ra, dec
        try:
            latest = fetch(v)
        except Exception as err:  # a source failure never breaks Tonight
            logger.warning("vigil %s failed: %s", v["name"], err)
            continue
        hit = _anomaly(v, latest)
        if hit:
            alerts.append(hit)
    return alerts


def cached_alerts(cfg, db_obj=None):
    # Cache-only re-read of the last vigil check, for the signals console
    # (which must never touch the network). Empty when Tonight has not run
    # yet, the short caches expired, or (bright vigils) no AAVSO token is
    # configured — the console just shows none.
    # @args: cfg - Config, db_obj - Database (default: shared singleton)
    # @return: [alert dicts], possibly empty
    return check_vigils(cfg, fetch=_cached_fetch(cfg, db_obj),
                        resolve=False)
