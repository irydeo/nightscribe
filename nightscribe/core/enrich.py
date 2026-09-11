############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Object enrichment orchestrator
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime
import logging
import re

from . import coords, ephem_minor, hads, orbits
from .sources import cad, exoplanet_archive, horizons, neofixer, sbdb, simbad

logger = logging.getLogger(__name__)

# Detects the object kind and pulls everything the sources know about it,
# returning one flat dict that narrative/post/viz consume.


def detect_type(name):
    # @args: name - user-typed identifier
    # @return: "sun" | "transient" | "exoplanet" | "hads" | "variable" | "small_body"
    n = name.strip()
    if n.lower() in ("sol", "sun"):
        return "sun"
    if re.match(r"^(SN|AT)\s?\d{4}[a-zA-Z]{1,4}$", n, re.I):
        return "transient"
    # HADS membership BEFORE the exoplanet regex: catalog names like
    # "GP And" end in a letter that regex reads as a planet marker
    if hads.lookup(n):
        return "hads"
    # Variable-star designations (GCVS: "T CrB", "EE Cep", "V1490 Cyg"; NSV
    # catalogue) — checked BEFORE the exoplanet regex: a name ending in one
    # letter reads as a planet marker there ("T CrB" would be a false planet).
    # Exactly two tokens on purpose: "GQ Lup b" (three) stays an exoplanet.
    if _looks_like_variable(n):
        return "variable"
    # the preceding char is a word char or a dash (HD 209458 b, KELT-9b,
    # TRAPPIST-1e, 55Cnce, AUMicb); NEO/comet designations end in a digit,
    # so a trailing planet letter is a safe exoplanet marker
    if re.search(r"[\w-]\s?(b|c|d|e|f)$", n) and not re.match(r"^\d{4}", n):
        return "exoplanet"
    return "small_body"


# Variable-star designations (GCVS: "T CrB", "EE Cep", "V1490 Cyg"; NSV
# catalogue) — checked BEFORE the exoplanet regex: a name ending in one
# letter reads as a planet marker there ("T CrB" would be a false planet).
# Exactly two tokens on purpose: "GQ Lup b" (three) stays an exoplanet.
_GCVS_RE = re.compile(r"^(V\d{1,4}|[A-Z]{1,2})\s+[A-Z][a-z][A-Za-z]$")
_NSV_RE = re.compile(r"^NSV\s?\d{3,5}$", re.I)


def _looks_like_variable(n):
    # @args: n - stripped user-typed identifier
    # @return: True for GCVS/NSV designations or the name of an active local
    #          variable project (offline; the local name always wins — it is
    #          how campaign targets without a catalog entry, e.g. the WeSb 1
    #          nucleus, get their kind back)
    if _GCVS_RE.match(n) or _NSV_RE.match(n):
        return True
    try:
        from .db import db as _db
        row = _db.execute(
            "SELECT 1 FROM projects WHERE kind='variable'"
            " AND LOWER(object_name)=LOWER(?) LIMIT 1", (n,)).fetchone()
        return bool(row)
    except Exception:
        return False


def enrich(name, date=None, site="Z41", fallback_target=None):
    # Gathers every interesting fact about an object.
    # @args: name - identifier, date - reference date (today),
    #        site - MPC code, fallback_target - planner target dict used
    #        when SBDB does not know the object (unconfirmed NEOCP/PCCP)
    # @return: dict with "type" and a "data" section per type
    kind = detect_type(name)
    if kind == "sun":
        from . import solar
        return {"type": "sun", "name": "Sun", "data": solar.solar_now()}
    if kind == "transient":
        # transients have no orbit: the planner target (Rochester fields) is
        # the fallback context when SIMBAD does not know the name (ADR-027)
        return {"type": "transient", "name": name,
                "data": _enrich_transient(name, fallback_target)}
    if kind == "exoplanet":
        # the Archive knows the planet; only the planner target knows
        # TONIGHT's event (ingress/egress/depth/min telescope) — merge it
        # the ADR-027 way, never overwriting an Archive fact
        data = exoplanet_archive.planet(name) or {}
        if fallback_target:
            _merge_transit_context(data, fallback_target)
        return {"type": "exoplanet", "name": name, "data": data}
    if kind == "hads":
        # the bundled catalog knows the star; the planner target knows
        # TONIGHT's session (cycles, session_fits) — planner values win
        data = {"hads": hads.lookup(name) or {}}
        if fallback_target:
            _copy_window_context(data, fallback_target)
            if fallback_target.get("hads"):
                data["hads"] = fallback_target["hads"]
        return {"type": "hads", "name": name, "data": data}
    data = _enrich_small_body(name, date, site)
    if not data and fallback_target is not None:
        # unconfirmed object: NEOfixer may still know a preliminary
        # Find_Orb solution for it (NEOCP) — use it as sbdb-shaped data
        data = _enrich_preliminary_orbit(fallback_target, date, site)
    if not data and fallback_target is not None:
        # no orbit anywhere: tell its story with whatever the planner
        # already knows (NEOfixer/PCCP fields)
        data = {"unconfirmed": fallback_target}
        return {"type": fallback_target.get("kind", "neo"), "name": name,
                "data": data}
    out = {"type": "small_body", "name": name, "data": data}
    # hashtag hint: comets are not asteroids (see sbdb kind)
    if data and (data.get("sbdb") or {}).get("kind") in ("cn", "cu"):
        out["type"] = "comet"
    return out


def _enrich_transient(name, fallback_target=None):
    # @args: name - transient id (SN..., AT2026..., 2026...),
    #        fallback_target - planner target dict (Rochester fields), used
    #        to fill in what SIMBAD does not know for this object (ADR-027)
    # @return: dict with SIMBAD identity + host galaxy + context
    ident = simbad.query_id(name)
    host = simbad.query_around_galaxy(name)
    out = {"simbad": ident, "host": host}
    # B7: when SIMBAD does not know the SN, try TNS for the type,
    # discovery magnitude and discovery date (TNS already has these fields
    # in parse_object_page — until now only the blink resolver used them).
    if not (ident and ident.get("otype")):
        from .sources import tns
        tns_info = tns.resolve(name)
        if tns_info:
            # only set fields TNS actually has (don't let None wipe the
            # fallback_target's value downstream — setdefault won't fire)
            if tns_info.get("type"):
                out.setdefault("otype", tns_info["type"])
            if tns_info.get("mag") is not None:
                out.setdefault("mag", tns_info["mag"])
            if tns_info.get("disc_date"):
                out.setdefault("disc_date", tns_info["disc_date"])
            if tns_info.get("ra") is not None:
                out.setdefault("ra_deg", tns_info["ra"])
                out.setdefault("dec_deg", tns_info["dec"])
    if host and host.get("z"):
        # light travel time from the host redshift (small z approximation)
        d_mpc = host["z"] * 299792.458 / 70.0
        out["dist_mly"] = round(d_mpc * 3.26156, 1)
    if fallback_target:
        _copy_window_context(out, fallback_target)
        _merge_transient_context(out, fallback_target)
    return out


def _copy_window_context(out, t):
    # The night's window facts from the planner target: the data dict owns
    # the safe-window bullet (narrative._safe_window_bullets reads it from d
    # or from unconfirmed) and build_charts draws it on the sky chart.
    # @args: out - data dict to extend, t - planner target dict
    # @return: out, same dict (mutated in place)
    for key in ("safe_window", "best_time", "window_start", "window_end",
                "hours_up", "max_alt", "latest_safe_start"):
        if t.get(key) is not None:
            out.setdefault(key, t[key])
    if t.get("duration_s") is not None:
        out.setdefault("duration_s", t["duration_s"])
    return out


def _merge_transit_context(out, t):
    # Fills an exoplanet's missing facts from the planner target (ADR-027
    # pattern): the ExoClock event lives in the target's "transit" sub-dict
    # and the Archive knows nothing about tonight. Never overwrites an
    # Archive fact (setdefault only).
    # @args: out - the data dict being built, t - planner target dict
    # @return: out, same dict (mutated in place)
    if t.get("transit") is not None:
        out.setdefault("transit", t["transit"])
    if t.get("mag") is not None:
        out.setdefault("mag", t["mag"])
    if out.get("ra") is None and t.get("ra_deg") is not None:
        out["ra"] = t["ra_deg"]
        out["dec"] = t.get("dec_deg")
    _copy_window_context(out, t)
    return out


def _merge_transient_context(out, t):
    # Fills a transient's missing facts from the planner context (ADR-027):
    # the Rochester row already has host/type/magnitude/coordinates/date, so
    # when SIMBAD does not know the SN the panel still tells a real story.
    # Never overwrites a fact SIMBAD gave us, and keeps the dict shape.
    # @args: out - the data dict being built, t - planner target dict
    # @return: out, same dict (mutated in place)
    host = t.get("host")
    if host and str(host).lower() not in ("", "none", "unknown"):
        if isinstance(host, dict):
            out.setdefault("host", host)
        else:
            out["host"] = out.get("host") or {"name": str(host)}
    sn_type = (t.get("sn_type") or "").strip()
    if sn_type and not (out.get("simbad") or {}).get("otype"):
        # store as the event type: the narrative reads otype from simbad or here
        out.setdefault("otype", sn_type)
    if t.get("mag") is not None and not (out.get("simbad") or {}).get("vmag"):
        out.setdefault("mag", t["mag"])
    if t.get("ra_deg") is not None:
        out.setdefault("ra_deg", t["ra_deg"])
        out.setdefault("dec_deg", t.get("dec_deg"))
    if t.get("disc_date"):
        out.setdefault("disc_date", t["disc_date"])
    return out


def _enrich_preliminary_orbit(target, date, site):
    # Builds the same data shape as _enrich_small_body from a preliminary
    # NEOfixer orbit (unconfirmed NEOCP objects SBDB does not know yet).
    # The ephemeris is computed locally with our Kepler propagator, since
    # Horizons has no orbit for these objects. "preliminary" flags the
    # whole dict so narrative/UI can word the uncertainty.
    # @args: target - planner fallback dict, date - datetime (today),
    #        site - MPC code
    # @return: dict or None if NEOfixer has no orbit either
    packed = target.get("packed") or target.get("id") or target.get("name")
    if not packed:
        return None
    body = neofixer.orbit(packed)
    if not body:
        return None
    out = {"sbdb": body, "preliminary": True, "unconfirmed": target}
    elements = body.get("elements") or {}
    when = (date if isinstance(date, datetime.datetime)
            else datetime.datetime.now(datetime.timezone.utc))
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    jd = coords.jd_from_datetime(when)
    pos = ephem_minor.kepler_ra_dec(elements, jd)
    if pos:
        ra_deg, dec_deg, r, delta = pos
        out["ephem"] = {"ra": coords.ra_deg_to_hms(ra_deg),
                        "dec": coords.dec_deg_to_dms(dec_deg),
                        "r": r, "delta": delta}
        out["ephem_epoch"] = when.strftime("%Y-%m-%d %H:%M")
        h = (body.get("phys") or {}).get("H")
        out["mag_now"] = orbits.visual_mag(h, r, delta)
        out["dist_now_km"] = delta * orbits.AU_KM
    # CAD only tracks confirmed objects: skip it for preliminary orbits
    out["next_approach"] = None
    out["family"] = orbits.classify(elements, body.get("orbit_code"))
    return out


def _enrich_small_body(name, date, site):
    # @args: name - designation, date - reference date, site - MPC code
    # @return: dict with SBDB data, ephemeris, next approach and extras
    body = sbdb.get(name)
    if not body:
        return None
    out = {"sbdb": body}
    eph = horizons.ephemeris(body["des"] or name, center=site, step="30m")
    if eph:
        row = _nearest_ephemeris_row(eph, date)
        out["ephem"] = row
        out["ephem_epoch"] = row.get("time")
        h = body["phys"].get("H")
        out["mag_now"] = orbits.visual_mag(h, row["r"], row["delta"])
        out["dist_now_km"] = row["delta"] * orbits.AU_KM
    out["next_approach"] = cad.next_approach(body["des"] or name)
    elements = body.get("elements") or {}
    out["family"] = orbits.classify(elements, body.get("orbit_code"))
    # comet expected brightness (outburst detection feeds the narrative)
    m1, k1 = body["phys"].get("M1"), body["phys"].get("K1")
    if m1 and k1 and eph:
        out["mag_expected"] = orbits.comet_expected_mag(m1, k1, row["r"],
                                                        row["delta"])
    return out


def _nearest_ephemeris_row(rows, date=None):
    # Picks the row whose time is closest to `date` (default now). With a
    # 30-min step the nearest row is at most 15 min away — far better than
    # eph[0] (00:00 UT) for a fast mover whose displayed position would
    # otherwise be up to 24 h stale.
    # @args: rows - list from horizons.ephemeris, date - datetime or None
    # @return: the nearest row (first if none parse)
    target = (date if isinstance(date, datetime.datetime)
              else datetime.datetime.now(datetime.timezone.utc))
    if target.tzinfo is None:
        target = target.replace(tzinfo=datetime.timezone.utc)
    best, best_dt = rows[0], None
    for r in rows:
        try:
            t = datetime.datetime.strptime(r["time"], "%Y-%b-%d %H:%M")
            t = t.replace(tzinfo=datetime.timezone.utc)
        except (ValueError, KeyError):
            continue
        if best_dt is None or abs((t - target).total_seconds()) < \
                abs((best_dt - target).total_seconds()):
            best, best_dt = r, t
    return best
