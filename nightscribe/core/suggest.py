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

from . import coords, dates, ephem_minor, hads

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
        return _clamp((19 - mag) / 8.0 * 25, 0, 25) + (_freshness_days(t) or 0) * 0
    if kind == "comet":
        mag = t.get("mag") or 99
        return _clamp((18 - mag) / 10.0 * 30, 0, 30)
    if kind == "transit":
        return {"high": 28, "medium": 18, "low": 10}.get(
            (t.get("transit") or {}).get("priority") or "", 12)
    if kind == "hads":
        # amplitude is the science draw (period changes need well-sampled
        # curves); brightness makes the photometry easier
        h = t.get("hads") or {}
        return (_clamp((h.get("amp") or 0.0) / 0.9 * 20, 0, 20) +
                 _clamp((18 - (t.get("mag") or 99)) / 10.0 * 15, 0, 15))
    if kind == "variable":
        # a campaign membership is itself the science signal (someone
        # with a goal asked for this star); amplitude and brightness make
        # the measurement easier
        v = t.get("variable") or {}
        return (_clamp((v.get("amp") or 0.0) / 3.0 * 15, 0, 15) +
                _clamp((18 - (t.get("mag") or 99)) / 10.0 * 15, 0, 15))
    return 0


def _freshness_days(t):
    # Days since a transient's discovery (None if unknown). Any source
    # format counts (object-card plan, subplan 5d).
    return dates.days_since(t.get("disc_date"))


def _observability(t, cfg):
    # 0-30: altitude, hours up, brightness vs. the user's limits, plus a soft
    # Moon penalty (ADR-020): warning, never a hard filter.
    score = 0.0
    # the actually-reachable altitude (horizon-clipped) when available; the
    # raw astronomical peak is only the fallback for kinds that have no
    # local-horizon context — advertising an altitude behind an obstacle
    # would let a blocked object outscore a freely-visible one
    max_alt = t.get("safe_max_alt", t.get("max_alt"))
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
    # Track D: a transit whose full capture window (baseline + transit +
    # baseline) does not fit tonight is only capturable in part — sink it
    # below events the observer can actually bracket
    if t.get("kind") == "transit":
        tr = t.get("transit") or {}
        if tr.get("baseline_fits") is False:
            score -= 4.0
    # HADS: the more complete cycles fit tonight, the better the fold; a
    # star whose 2-period session doesn't fit only gets a partial capture
    if t.get("kind") == "hads":
        h = t.get("hads") or {}
        score += _clamp((h.get("cycles") or 0) / 5.0 * 6, 0, 6)
        if h.get("session_fits") is False:
            score -= 4.0
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
    elif kind == "hads":
        # the legend signals don't stack: the strongest one rules (H-i/k/m)
        h = t.get("hads") or {}
        color = {"period_change": 12,
                 "period_change_possible": 8}.get(h.get("priority"), 0)
        unobserved = 6 if h.get("observed") is False else 0
        coverage = 10 if h.get("covered_this_month") is False else 0
        score += max(color, unobserved, coverage)
    c = t.get("campaign") or {}
    if c:
        # the group's own commitment (V-h): being in a campaign is itself
        # urgency, then cadence lapsed grows it, then the event advisor
        score += 5
        score += _clamp((c.get("overdue_days") or 0) * 3, 0, 15)
        if c.get("event"):
            score += 10
        if c.get("vigil"):
            score += 8      # survey vigil anomaly fused in (ADR-037 SC4a)
        if c.get("aavso"):
            score += 6      # the AAVSO editorial channel asks for it
    if t.get("vigil"):
        score += 8          # standalone vigil alert (no project of its own)
    if t.get("aavso"):
        score += 6          # standalone AAVSO item (ADR-037 SC4b)
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
    elif kind == "hads":
        h = t.get("hads") or {}
        if t.get("name") in hads.FAMOUS_HADS:
            score += 6
        if (h.get("amp") or 0) >= 0.5:
            score += 4
        if h.get("multiperiodic"):
            score += 3
    elif kind == "variable":
        v = t.get("variable") or {}
        days = (v.get("next_extremum") or {}).get("days")
        if days is not None and days <= 7:
            score += 5            # an extremum within the week is a hook
        if (v.get("amp") or 0) >= 2.0:
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


def _as_float(x, default=None):
    # Tolerant float: raw source data is not always numeric yet (e.g. the
    # PCCP page hands us strings for the arc and observation count).
    # @args: x - value of any type, default - when x is not a number
    # @return: float or default
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _hm_utc(dt):
    # @args: dt - datetime or ISO-8601 string
    # @return: "HH:MM" string, or None
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt)
        except ValueError:
            return None
    if isinstance(dt, datetime.datetime):
        return dt.strftime("%H:%M")
    return None


def _fragments(t, cfg=None):
    # Object-specific reasons, heaviest first, drawn from the same data the
    # score is built from — so the phrase and the number always agree.
    # Only fragments with real data are emitted; no trailing period (it is
    # added once by why_phrase).
    # @args: t - target dict
    # @return: list of (es, en) fragment pairs
    frags = []
    kind = t.get("kind")
    if kind == "neo":
        if t.get("neocp"):
            frags.append(("Está en la página de confirmación del MPC: cada medida cuenta para su órbita",
                          "On the MPC confirmation page: every measurement counts for its orbit"))
        if t.get("impact"):
            frags.append(("Impactor potencial según JPL Sentry: las medidas de esta noche refinan el riesgo",
                          "Potential impactor on JPL Sentry: tonight's measurements refine the risk"))
        moid = _as_float(t.get("moid"))
        if moid is not None and moid < 0.05:
            frags.append((f"MOID de {moid:.3f} UA: cruce cercano con la órbita terrestre",
                          f"MOID of {moid:.3f} AU: a close crossing with Earth's orbit"))
        nf_score = _as_float(t.get("nf_score"))
        if nf_score is not None and nf_score >= 5:
            frags.append((f"Puntuación NEOfixer {nf_score:.1f}/10 para tu observatorio",
                          f"NEOfixer score of {nf_score:.1f}/10 for your site"))
        cost = _as_float(t.get("nf_cost_min"))
        if cost is not None and cost >= 10:
            frags.append((f"NEOfixer estima {cost:.0f} min de exposición para tu observatorio",
                          f"NEOfixer estimates {cost:.0f} minutes of imaging for your site"))
        urgency = _as_float(t.get("nf_urgency"))
        if urgency is not None and urgency >= 60:
            frags.append((f"Urgencia de seguimiento del {urgency:.0f}% según NEOfixer",
                          f"NEOfixer follow-up urgency of {urgency:.0f}%"))
        rate = _as_float(t.get("rate_arcsec_min"))
        if rate is not None and rate >= 0.3:
            frags.append((f"Se desplaza a {rate:.2f}″ por minuto",
                          f"Moving at {rate:.2f} arcsec per minute"))
        arc = _as_float(t.get("arc_days"))
        nobs = _as_float(t.get("nobs"))
        if arc is not None and arc < 30 and nobs is not None and nobs <= 6:
            frags.append((f"Su órbita aún es incierta: solo {nobs:.0f} observaciones en {arc:.0f} días",
                          f"Orbit still uncertain: only {nobs:.0f} observations over {arc:.0f} days"))
    elif kind == "pccp":
        s = _as_float(t.get("pccp_score"))
        if s is not None:
            frags.append((f"Candidato a cometa en el PCCP del MPC con score {s:.0f}/100",
                          f"Possible comet on the MPC's PCCP with a score of {s:.0f}/100"))
        arc = _as_float(t.get("arc_days"))
        if arc is not None and 0 < arc < 20:
            nobs = _as_float(t.get("nobs"))
            extra = f", {nobs:.0f} obs" if nobs is not None else ""
            frags.append((f"Arco corto: {arc:.0f} días{extra}",
                          f"Short arc: {arc:.0f} days{extra}"))
        mag = _as_float(t.get("mag"))
        if mag is not None:
            frags.append((f"Magnitud prevista {mag:.1f}",
                          f"Predicted magnitude {mag:.1f}"))
    elif kind == "sn":
        if any(h in (t.get("host") or "").upper() for h in
               ("M51", "M101", "M104", "M87", "M82", "M31", "NGC")):
            frags.append((f"Está en la galaxia {t['host']}",
                          f"In the galaxy {t['host']}"))
        days = _freshness_days(t)
        if days is not None and days <= 14:
            typ_es = f", tipo {t['sn_type']}" if t.get("sn_type") else ""
            typ_en = f", type {t['sn_type']}" if t.get("sn_type") else ""
            frags.append((f"Descubierta hace {days} días{typ_es}: aún evolucionando",
                          f"Discovered {days} days ago{typ_en}: still evolving"))
        mag = _as_float(t.get("mag"), default=99.0)
        if mag <= 15:
            frags.append((f"Brilla a magnitud {mag:.1f}, buena para su curva de luz",
                          f"Shining at magnitude {mag:.1f}, good for its light curve"))
    elif kind == "comet":
        mag = _as_float(t.get("mag"), default=99.0)
        if mag <= 12:
            frags.append((f"Brilla a magnitud {mag:.1f}",
                          f"Shining at magnitude {mag:.1f}"))
        dist_earth = _as_float(t.get("delta_au"))
        dist_sun = _as_float(t.get("r_au"))
        if dist_earth is not None:
            if dist_sun is not None:
                frags.append((f"a {dist_earth:.2f} UA de la Tierra y {dist_sun:.2f} UA del Sol",
                              f"{dist_earth:.2f} AU from Earth and {dist_sun:.2f} AU from the Sun"))
            else:
                frags.append((f"a {dist_earth:.2f} UA de la Tierra",
                              f"{dist_earth:.2f} AU from Earth"))
        per = (t.get("perihelion_date") or "")[:10]
        try:
            delta = ((datetime.date.fromisoformat(per)
                      - datetime.date.today()).days)
            if abs(delta) <= 30:
                if delta >= 0:
                    frags.append((f"Perihelio en {delta} días: pico de brillo cerca",
                                  f"Perihelion in {delta} days: peak brightness is near"))
                else:
                    frags.append((f"Perihelio hace {-delta} días: el pico de brillo ya pasó",
                                  f"Perihelion {-delta} days ago: peak brightness is past"))
        except ValueError:
            pass
    elif kind == "transit":
        tr = t.get("transit") or {}
        star = tr.get("star") or ""
        # Track D: the card leads with the observer's real decision — "fits
        # entirely in your night (baselines included)" and "detectable with
        # your telescope" — and the ExoClock priority is explained, because
        # a first-timer does not know that number.
        cs_hm = _hm_utc(tr.get("capture_start"))
        if cs_hm:
            if tr.get("baseline_fits") is False:
                frags.append((f"⚠ Empieza a capturar a las {cs_hm} UTC, pero la ventana completa (con baselines) no cabe esta noche",
                              f"⚠ Start capturing at {cs_hm} UTC, but the full window (baselines included) does not fit tonight"))
            else:
                frags.append((f"Cabe entero en tu noche (baselines incluidas): empieza a capturar a las {cs_hm} UTC",
                              f"Fits entirely in your night (baselines included): start capturing at {cs_hm} UTC"))
        scope = _as_float(tr.get("min_telescope_in"))
        aperture = _as_float(cfg.get("aperture_inches")) if cfg else None
        if scope is not None and aperture:
            if aperture >= scope:
                frags.append((f"Detectable con tu telescopio de {aperture:g}″ (ExoClock pide ≥ {scope:g}″)",
                              f"Detectable with your {aperture:g}-inch telescope (ExoClock asks ≥ {scope:g}″)"))
            else:
                frags.append((f"⚠ ExoClock pide un telescopio de ≥ {scope:g}″ y el tuyo es de {aperture:g}″",
                              f"⚠ ExoClock asks for a ≥ {scope:g}-inch telescope and yours is {aperture:g}″"))
        if (tr.get("priority") or "").lower() == "high":
            frags.append(("Prioridad alta en ExoClock: el catálogo que prepara la misión Ariel de la ESA necesita esta medida para afinar el horario del planeta",
                          "High priority on ExoClock: the catalogue feeding ESA's Ariel mission needs this measurement to refine the planet's schedule"))
        if star and star != t.get("name") and any(s in star for s in FAMOUS_SYSTEMS):
            frags.append((f"Su estrella es {star}",
                          f"Host star {star}"))
        depth = (_as_float(tr.get("depth_mmag")) or 0.0) / 10.0  # mmag -> %
        dur = _as_float(tr.get("duration_h")) or 0.0
        if depth > 0:
            mid_es = f", durando {dur:.0f} h" if dur else ""
            mid_en = f" for {dur:.0f} h" if dur else ""
            frags.append((f"El planeta oscurece su estrella un {depth:.1f}%{mid_es}: tu curva de luz ayuda a la misión Ariel de la ESA",
                          f"The planet dims its star by {depth:.1f}%{mid_en}: your light curve helps ESA's Ariel mission"))
    elif kind == "hads":
        # priority/coverage signals lead: why_phrase keeps the first three
        h = t.get("hads") or {}
        pr = h.get("priority")
        if pr == "period_change":
            frags.append(("Se le han detectado cambios de periodo: cada curva nueva cuenta (programa de P. Wils)",
                           "Period changes detected: every new light curve counts (P. Wils' programme)"))
        elif pr == "period_change_possible":
            frags.append(("Posible cambio de periodo: el programa de seguimiento de P. Wils la marca como prioritaria",
                           "Possible period change: P. Wils' monitoring programme flags it as a priority"))
        if h.get("observed") is False:
            frags.append(("Aún no observada en el programa de seguimiento: serías de los primeros en medirla",
                           "Not yet observed in the monitoring programme: you'd be among the first to measure it"))
        if h.get("covered_this_month") is False:
            frags.append(("Nadie la ha medido este mes: tu curva cubre el hueco",
                           "Nobody has measured it this month: your curve fills the gap"))
        cyc = _as_float(h.get("cycles"))
        if cyc is not None and cyc >= 1:
            frags.append((f"Caben {cyc:.1f} ciclos completos esta noche: la verás pulsar en directo",
                           f"{cyc:.1f} full cycles fit tonight: you'll watch it pulsate live"))
        per, amp = _as_float(h.get("period_h")), _as_float(h.get("amp"))
        if per and amp:
            frags.append((f"Pulsa con un periodo de {per:.2f} h y una amplitud de {amp:.1f} mag",
                           f"It pulsates with a {per:.2f}-hour period and a {amp:.1f}-mag amplitude"))
        if h.get("multiperiodic"):
            frags.append(("Multiperiódica: obsérvala en noches consecutivas para separar los modos",
                           "Multiperiodic: observe it on consecutive nights to separate the modes"))
        if h.get("non_radial"):
            frags.append(("Muestra modos no radiales, un caso raro entre las HADS",
                           "It shows non-radial modes, a rare case among HADS stars"))
        if h.get("session_fits") is False:
            frags.append(("⚠ No caben 2 ciclos completos de seguida esta noche: captura lo máximo posible",
                           "⚠ Two full consecutive cycles don't fit tonight: capture as much as possible"))
    elif kind == "variable":
        # standalone vigil / AAVSO rows (no campaign of their own — fused
        # rows speak in _campaign_fragments instead)
        if t.get("vigil"):
            frags.append(_vigil_fragment(t["vigil"]))
        if t.get("aavso"):
            frags.append(_aavso_fragment(t["aavso"]))
    elif kind == "alert":
        a = t.get("approach") or {}
        ld, adate = a.get("dist_ld"), a.get("date")
        if ld is not None:
            es = f"Pasará a {ld:.1f} distancias lunares el {adate}" if adate \
                else f"Pasará a {ld:.1f} distancias lunares"
            en = f"Passing at {ld:.1f} lunar distances on {adate}" if adate \
                else f"Passing at {ld:.1f} lunar distances"
            frags.append((es, en))
        mag = _as_float(t.get("mag"), default=99.0)
        if mag <= 10:
            frags.append((f"Visible a magnitud {mag:.1f}",
                          f"Visible at magnitude {mag:.1f}"))
    return _campaign_fragments(t) + frags


def _vigil_fragment(vg):
    # The vigil-alert line, shared by the fused (campaign) and standalone
    # rows (ADR-037 SC4a). Mind the inverted magnitude axis: a "rise" is
    # the star BRIGHTENING past its baseline.
    # @args: vg - vigil alert dict (name, direction, baseline_mag, mag,
    #        filter, delta)
    # @return: one (es, en) fragment pair
    mag, band = vg.get("mag") or 0.0, vg.get("filter") or ""
    base = vg.get("baseline_mag") or 0.0
    delta = abs(vg.get("delta") or 0.0)
    if vg.get("direction") == "rise":
        return (f"👁 Vigilia ZTF: brilla a {mag:.1f} {band}, {delta:.1f} mag más de lo habitual (basal {base:.1f}) — posible erupción en curso",
                f"👁 ZTF vigil: shining at {mag:.1f} {band}, {delta:.1f} mag above its usual baseline ({base:.1f}) — possible outburst under way")
    return (f"👁 Vigilia ZTF: ha caído a {mag:.1f} {band}, {delta:.1f} mag bajo su basal ({base:.1f}) — posible descenso en curso",
            f"👁 ZTF vigil: faded to {mag:.1f} {band}, {delta:.1f} mag below its baseline ({base:.1f}) — possible decline under way")


def _aavso_fragment(av):
    # The AAVSO-channel line, shared by the fused (campaign) and
    # standalone rows (ADR-037 SC4b).
    # @args: av - aavso item dict (kind "alert"|"campaign", title, date,
    #        end, url)
    # @return: one (es, en) fragment pair
    title = (av.get("title") or "").strip()
    if av.get("kind") == "campaign":
        end = av.get("end") or ""
        return (f"📣 Campaña AAVSO activa hasta el {end}: «{title}»",
                f"📣 Active AAVSO campaign until {end}: “{title}”")
    date = av.get("date") or ""
    return (f"📣 La AAVSO la señala como de interés: «{title}» ({date})",
            f"📣 AAVSO flags it as a target of interest: “{title}” ({date})")


def _campaign_fragments(t):
    # Campaign signals, heaviest first (ADR-035). They lead the why-phrase:
    # the campaign is the reason the target is listed at all (V-d).
    # @args: t - target dict with a "campaign" sub-dict (maybe empty)
    # @return: list of (es, en) fragment pairs
    c = t.get("campaign") or {}
    if not c:
        return []
    frags = []
    ev = c.get("event") or {}
    if ev:
        d = ev.get("delta_mag") or 0.0
        if ev.get("direction") == "drop":
            frags.append((f"¡Posible descenso de brillo (Δ≈+{d:.1f} mag en tu última medida)! El protocolo pide subir la cadencia",
                          f"Possible brightness drop (Δ≈+{d:.1f} mag on your latest point)! The protocol calls for a higher cadence"))
        else:
            frags.append((f"¡Posible erupción o subida de brillo (Δ≈−{d:.1f} mag)! Máxima prioridad esta noche",
                          f"Possible outburst (Δ≈−{d:.1f} mag)! Top priority tonight"))
    vg = c.get("vigil") or {}
    if vg:
        frags.append(_vigil_fragment(vg))
    if c.get("aavso"):
        frags.append(_aavso_fragment(c["aavso"]))
    if c.get("never_visited"):
        frags.append((f"Campaña {c['name']}: sin ninguna visita todavía — la primera medida abre la serie",
                      f"Campaign {c['name']}: no visits yet — the first measurement opens the series"))
    elif c.get("overdue_days"):
        frags.append((f"Campaña {c['name']}: {c['overdue_days']} noches sin medida (cadencia: {c['cadence_nights']})",
                      f"Campaign {c['name']}: {c['overdue_days']} nights without a measurement (cadence: {c['cadence_nights']})"))
    v = t.get("variable") or {}
    nxt = v.get("next_extremum") or {}
    if nxt.get("days") is not None:
        if nxt.get("kind") == "max":
            frags.append((f"Máximo esperado en ~{nxt['days']:.0f} días",
                          f"Maximum expected in ~{nxt['days']:.0f} days"))
        else:
            frags.append((f"Mínimo esperado en ~{nxt['days']:.0f} días",
                          f"Minimum expected in ~{nxt['days']:.0f} days"))
    if v.get("period_d"):
        frags.append((f"Varía con un periodo de {v['period_d']:.1f} días",
                      f"It varies with a {v['period_d']:.1f}-day period"))
    return frags


def why_phrase(t, cfg=None):
    # One-line "why here" for a target: up to three object-specific
    # fragments joined with a middot, in priority order.
    # @args: t - target dict, cfg - Config (enables the aperture verdict
    #        on transits, Track D)
    # @return: {"es":..., "en":...}
    frags = _fragments(t, cfg)[:3]
    if not frags:
        return {"es": "Buen objetivo esta noche.", "en": "A good target tonight."}
    return {"es": "  ·  ".join(f[0] for f in frags) + ".",
            "en": "  ·  ".join(f[1] for f in frags) + "."}


def top_n(targets, cfg=None, db=None, n=3):
    # Scores every target and returns the best ones, preferring a diverse
    # mix of kinds (a comet or a supernova next to a NEO makes a better
    # night than three NEOs).
    # @args: targets - list from planner, cfg - Config, db - Database, n - top size
    # @return: (top list, full scored list) of (target, score, parts, phrase)
    scored = []
    for t in targets:
        score, parts = score_target(t, cfg, db)
        scored.append((t, score, parts, why_phrase(t, cfg)))
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


def best_per_kind(scored, n=5):
    # For the Tonight grid (WORKFLOWS 7quater K3): keep at most the n best
    # targets of every kind, so one kind cannot drown the other six — the
    # input is already in global-score order, so the output stays sorted by
    # global score (variety without grouping).
    # @args: scored - list of (target, score, parts, phrase) tuples,
    #        n - per-kind cap (<=0 means no cap)
    # @return: (grid list, best ids) where grid is the capped, score-sorted
    #          list and best ids holds the id of the BEST target of each
    #          kind present (the "rings" of the grid)
    if n <= 0:
        # with no cap the grid is the whole night, and the best of each kind
        # is simply its first (highest scoring) member (scored is sorted)
        firsts = {}
        for item in scored:
            firsts.setdefault(item[0].get("kind") or "", item[0].get("id"))
        return list(scored), set(firsts.values())

    per_kind_count = {}
    grid = []
    best_per_kind = {}   # kind -> best id (input is global-score order)
    for t, _score, _parts, _phrase in scored:
        kind = t.get("kind") or ""
        if per_kind_count.get(kind, 0) >= n:
            continue
        per_kind_count[kind] = per_kind_count.get(kind, 0) + 1
        if kind not in best_per_kind:
            best_per_kind[kind] = t.get("id")
        grid.append((t, _score, _parts, _phrase))
    return grid, set(best_per_kind.values())
