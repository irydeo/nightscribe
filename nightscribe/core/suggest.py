############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Suggestion engine (scoring + why-tonight phrases)
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

from . import coords, ephem_minor

logger = logging.getLogger(__name__)

# Rule-based scoring, see docs/SCORING.md. Four weighted families:
# scientific priority (0-35), observability (0-30), urgency (0-20) and the
# outreach hook (0-15). No machine learning: explicit, testable rules.

FAMOUS_HOSTS = ("M51", "M101", "M104", "M87", "M82", "M31", "NGC")
FAMOUS_SYSTEMS = ("HD 209458", "TRAPPIST", "55 Cnc", "HD 189733", "GJ 1214",
                  "WASP", "KELT")


def _clamp(x, lo=0.0, hi=100.0):
    # @return: x clamped to [lo, hi]
    return max(lo, min(hi, x))


def _scientific(t):
    # 0-35: scientific priority per object kind.
    kind = t.get("kind")
    if kind == "neo":
        return _clamp((t.get("nf_score") or 0) / 10.0 * 35, 0, 35)
    if kind == "pccp":
        return _clamp((t.get("pccp_score") or 0) / 100.0 * 35, 0, 35)
    if kind == "sn":
        mag = t.get("mag") or 99
        return _clamp((19 - mag) / 8.0 * 25, 0, 25) + _freshness_days(t) * 0
    if kind == "comet":
        mag = t.get("mag") or 99
        return _clamp((18 - mag) / 10.0 * 30, 0, 30)
    if kind == "transit":
        return {"high": 28, "medium": 18, "low": 10}.get(
            (t.get("transit") or {}).get("priority") or "", 12)
    return 0


def _freshness_days(t):
    # Days since a transient's discovery (None if unknown).
    try:
        d = datetime.datetime.strptime(t["disc_date"].split(".")[0], "%Y/%m/%d")
        return (datetime.datetime.now() - d).days
    except (KeyError, ValueError, AttributeError):
        return None


def _observability(t, cfg):
    # 0-30: altitude, hours up, brightness vs. the user's limits, plus a soft
    # Moon penalty (ADR-020): warning, never a hard filter.
    score = 0.0
    max_alt = t.get("max_alt")
    if max_alt is not None:
        score += _clamp((max_alt - 15) / 60.0 * 18, 0, 18)
    hours = t.get("hours_up")
    if hours:
        score += _clamp(hours / 6.0 * 6, 0, 6)
    mag = t.get("mag")
    limit = float(cfg.get("limit_mag", 20.0)) if cfg else 20.0
    if mag is not None:
        score += _clamp((limit - mag) / 4.0 * 6, 0, 6)
    # soft beyond-limit penalty (ADR-025): NEO and PCCP brightness is a
    # prediction, so never drop the target — just sink it below bright
    # and easy objects
    if t.get("kind") in ("neo", "pccp") and mag is not None and mag > limit:
        score -= _clamp((mag - limit) / 2.0 * 3.0, 0, 3.0)
    score -= _moon_penalty(t, cfg, limit)
    return _clamp(score, 0, 30)


def beyond_limit(t, cfg=None):
    # Soft-limit warning for predicted-mag kinds (NEO, PCCP): the brightness
    # there is a prediction, so we warn instead of cutting (ADR-025).
    # @args: t - target dict, cfg - Config
    # @return: (is_beyond, delta_mags); (False, 0.0) outside scope
    if t.get("kind") not in ("neo", "pccp"):
        return False, 0.0
    mag = t.get("mag")
    if mag is None:
        return False, 0.0
    limit = float(cfg.get("limit_mag", 20.0)) if cfg else 20.0
    if mag > limit:
        return True, round(mag - limit, 1)
    return False, 0.0


def _moon_jd(t):
    # Julian date for the Moon evaluation: the target's best instant, else now.
    mt = t.get("max_time")
    try:
        dt = datetime.datetime.fromisoformat(mt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return coords.jd_from_datetime(dt)
    except (TypeError, ValueError):
        return coords.jd_from_datetime(
            datetime.datetime.now(datetime.timezone.utc))


def moon_info(t, cfg=None):
    # Moon context for a target, for display in Tonight cards.
    # @args: t - target dict, cfg - Config (None disables the constraint)
    # @return: {"sep_deg", "illum", "warning"} or None when unknown/disabled
    if cfg is None or not cfg.get("moon_limit_enabled", False):
        return None
    ra, dec = t.get("ra_deg"), t.get("dec_deg")
    if ra is None or dec is None:
        return None
    m = ephem_minor.moon(_moon_jd(t))
    sep = coords.angular_separation(ra, dec, m["ra"], m["dec"])
    illum = m["illum"]
    min_sep = float(cfg.get("moon_min_sep_deg", 45.0))
    max_illum = float(cfg.get("moon_max_illum", 0.5))
    warning = sep < min_sep or illum > max_illum
    return {"sep_deg": round(sep, 1), "illum": round(illum, 2),
            "warning": warning}


def _moon_penalty(t, cfg, limit_mag):
    # Soft observability penalty (capped) from Moon proximity/illumination.
    # @return: penalty points (float) to subtract from observability
    if cfg is None or not cfg.get("moon_limit_enabled", False):
        return 0.0
    info = moon_info(t, cfg)
    if info is None:
        return 0.0
    pen = 0.0
    min_sep = float(cfg.get("moon_min_sep_deg", 45.0))
    if info["sep_deg"] < min_sep:
        pen += (min_sep - info["sep_deg"]) / min_sep * 4.0
    max_illum = float(cfg.get("moon_max_illum", 0.5))
    mag = t.get("mag")
    if (info["illum"] > max_illum and mag is not None
            and mag > limit_mag - 3.0):
        pen += (info["illum"] - max_illum) / (1.0 - max_illum) * 3.0
    return _clamp(pen, 0, 7.0)


def _urgency(t):
    # 0-20: last-chance signals.
    kind = t.get("kind")
    score = 0.0
    if kind == "neo":
        if t.get("neocp"):
            score += 10
        score += _clamp((t.get("nf_urgency") or 0) / 100.0 * 10, 0, 10)
    elif kind == "pccp":
        score += 8 + _clamp((t.get("pccp_score") or 0) / 100.0 * 8, 0, 8)
    elif kind == "sn":
        days = _freshness_days(t)
        if days is not None and days <= 14:
            score += _clamp((14 - days) / 14.0 * 16, 0, 16)
    elif kind == "comet":
        per = (t.get("perihelion_date") or "")[:10]
        try:
            days = abs((datetime.date.fromisoformat(per)
                        - datetime.date.today()).days)
            if days <= 30:
                score += _clamp((30 - days) / 30.0 * 14, 0, 14)
        except ValueError:
            pass
    elif kind == "transit":
        oc = abs((t.get("transit") or {}).get("oc_min") or 0)
        score += _clamp(oc / 30.0 * 12, 0, 12)
    return _clamp(score, 0, 20)


def _hook(t):
    # 0-15: the outreach hook, our differentiator (stacked, capped).
    kind = t.get("kind")
    score = 0.0
    if kind == "neo":
        if t.get("neocp"):
            score += 6
        if t.get("impact"):
            score += 8
        if t.get("moid") is not None and t["moid"] < 0.05:
            score += 4
    elif kind == "pccp":
        if (t.get("pccp_score") or 0) > 50:
            score += 12
    elif kind == "sn":
        if (t.get("mag") or 99) < 15:
            score += 6
        if any(h in (t.get("host") or "") for h in FAMOUS_HOSTS):
            score += 5
        days = _freshness_days(t)
        if days is not None and days <= 7:
            score += 4
    elif kind == "comet":
        if (t.get("mag") or 99) < 12:
            score += 6
    elif kind == "transit":
        star = (t.get("transit") or {}).get("star") or ""
        if any(s in star for s in FAMOUS_SYSTEMS):
            score += 6
        if (t.get("transit") or {}).get("full"):
            score += 3
    elif kind == "alert":
        ld = (t.get("approach") or {}).get("dist_ld") or 99
        if ld < 10:
            score += 10
    return _clamp(score, 0, 15)


def score_target(t, cfg=None, db=None):
    # Total score for a target, with history feedback from SQLite.
    # @args: t - target dict from planner, cfg - Config, db - Database
    # @return: (score_0_100, parts dict)
    parts = {
        "scientific": _scientific(t),
        "observability": _observability(t, cfg),
        "urgency": _urgency(t),
        "hook": _hook(t),
    }
    if db is not None:
        if db.observed_recently(t.get("id", "")):
            parts["hook"] = 0.0  # novelty decay: already told
        elif db.is_observed(t.get("id", "")):
            parts["urgency"] = _clamp(parts["urgency"] + 5, 0, 20)
    total = _clamp(sum(parts.values()))
    return round(total, 1), parts


def why_phrase(t):
    # One-line "why tonight" for a target; first matching rule wins.
    # @args: t - target dict
    # @return: {"es":..., "en":...}
    kind = t.get("kind")
    if kind == "neo":
        if t.get("neocp"):
            return {"es": "Está en la página de confirmación del MPC: cada medida cuenta para su órbita.",
                    "en": "On the MPC confirmation page: every measurement counts for its orbit."}
        if t.get("impact"):
            return {"es": "Impactor potencial según JPL Sentry: las medidas de esta noche refinan el riesgo.",
                    "en": "Potential impactor on JPL Sentry: tonight's measurements refine the risk."}
        return {"es": "Prioridad de seguimiento para tu sitio según NEOfixer.",
                "en": "A follow-up priority for your site according to NEOfixer."}
    if kind == "pccp":
        s = t.get("pccp_score")
        return {"es": f"Candidato a cometa en el PCCP del MPC (score {s:.0f}/100): tu imagen podría confirmarlo.",
                "en": f"Possible comet on the MPC's PCCP (score {s:.0f}/100): your image could confirm it."}
    if kind == "sn":
        days = _freshness_days(t)
        if days is not None and days <= 14:
            return {"es": f"Descubierta hace {days} días y aún evolucionando: la fotometría temprana vale oro.",
                    "en": f"Discovered {days} days ago and still evolving: early photometry is gold."}
        return {"es": "Supernova activa y al alcance de tu equipo esta noche.",
                "en": "Active supernova within reach of your setup tonight."}
    if kind == "comet":
        per = (t.get("perihelion_date") or "")[:10]
        return {"es": f"Cometa activo con perihelio el {per}: mejor ventana de brillo.",
                "en": f"Active comet with perihelion on {per}: best brightness window."}
    if kind == "transit":
        tr = t.get("transit") or {}
        depth = (tr.get("depth_mmag") or 0) / 10.0  # mmag -> % approx
        return {"es": f"Esta noche un planeta eclipsa su estrella un {depth:.1f}%: tu curva de luz ayuda a la misión Ariel de la ESA.",
                "en": f"Tonight a planet eclipses its star by {depth:.1f}%: your light curve helps ESA's Ariel mission."}
    if kind == "alert":
        a = t.get("approach") or {}
        return {"es": f"Pasará a {a.get('dist_ld', 0):.1f} distancias lunares el {a.get('date')}: una historia que se cuenta sola.",
                "en": f"Passing at {a.get('dist_ld', 0):.1f} lunar distances on {a.get('date')}: a story that tells itself."}
    return {"es": "Buen objetivo esta noche.", "en": "A good target tonight."}


def top_n(targets, cfg=None, db=None, n=3):
    # Scores every target and returns the best ones, preferring a diverse
    # mix of kinds (a comet or a supernova next to a NEO makes a better
    # night than three NEOs).
    # @args: targets - list from planner, cfg - Config, db - Database, n - top size
    # @return: (top list, full scored list) of (target, score, parts, phrase)
    scored = []
    for t in targets:
        score, parts = score_target(t, cfg, db)
        scored.append((t, score, parts, why_phrase(t)))
    scored.sort(key=lambda x: x[1], reverse=True)

    top = []
    seen_kinds = set()
    # first pass: best of each kind
    for item in scored:
        if len(top) >= n:
            break
        if item[0]["kind"] not in seen_kinds:
            top.append(item)
            seen_kinds.add(item[0]["kind"])
    # second pass: fill with the next best whatever its kind
    for item in scored:
        if len(top) >= n:
            break
        if item not in top:
            top.append(item)
    return top, scored
