############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Engaging prose module (ES/EN)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging
import re

from . import hads, orbits

logger = logging.getLogger(__name__)

# Turns enriched data into bilingual outreach prose. Rules are explicit
# and every piece of text exists in Spanish and English (see ADR-013).


def hook(e):
    # The strongest one-line hook for an enriched object.
    # @args: e - dict from enrich.enrich()
    # @return: {"es":..., "en":...}
    kind = e.get("type")
    d = e.get("data") or {}
    if kind == "transient":
        # ADR-027: the story comes from whatever we know — SIMBAD first,
        # the planner context (host/type/mag/date) when it does not know it
        otype = _transient_otype(d)
        host = (d.get("host") or {}).get("name")
        ly = d.get("dist_mly")
        if ly:
            where = f"En {host}, " if host else ""
            txt = (f"{where}la luz de esta explosión salió hace {ly:.0f} millones de años; "
                   f"anoche la captamos desde nuestro observatorio.")
            return {"es": txt,
                    "en": (f"{'In ' + host + ', ' if host else ''}"
                           f"the light of this explosion left home "
                           f"{ly:.0f} million years ago; last night we caught "
                           f"it from our observatory.")}
        if otype and host:
            return {"es": f"Una supernova de tipo {otype} en {host}: seguimos su brillo noche a noche.",
                    "en": f"A type-{otype} supernova in {host}: we track its brightness night after night."}
        if otype:
            return {"es": f"Una explosión de tipo {otype} que seguimos desde nuestro observatorio.",
                    "en": f"A {otype}-type explosion we track from our observatory."}
        if host:
            return {"es": f"Un fenómeno explosivo en {host}, seguido desde nuestro observatorio.",
                    "en": f"An exploding object in {host}, tracked from our observatory."}
        return {"es": "Seguimiento de un fenómeno transitorio desde nuestro observatorio.",
                "en": "Follow-up of a transient event from our observatory."}
    if kind in ("small_body", "comet"):
        # ADR-027: a still-unconfirmed comet candidate (no SBDB entry) is
        # filed under this kind — it must not read as a confirmed object
        if d.get("unconfirmed"):
            t = d["unconfirmed"]
            if t.get("perihelion_date"):
                return {"es": f"Seguimos {t.get('name', 'este cometa')}: llega al perihelio cerca del {t['perihelion_date']}, la época de máximo brillo.",
                        "en": f"We are following {t.get('name', 'this comet')}: perihelion is near {t['perihelion_date']}, the time of peak brightness."}
            if t.get("kind") in ("exoplanet", "transit"):
                # a compact ExoClock name (e.g. 55Cnce) fell through detect_type
                # to small_body, but it is an exoplanet transit — use the
                # transit hook, not the comet-candidate one
                return _transit_hook(t.get("name"), t.get("transit") or {})
            if t.get("kind") == "neo":
                # an unconfirmed NEO is an asteroid candidate, not a comet
                full = t.get("name") or "este objeto"
                full_en = t.get("name") or "this object"
                return {"es": f"Seguimos {full}: un objeto cercano a la Tierra por confirmar, y sus medidas de esta noche lo definirán.",
                        "en": f"We are following {full}: a near-Earth object to be confirmed, and tonight's measurements will define it."}
            full = t.get("name") or "este cometa"
            full_en = t.get("name") or "this comet"
            return {"es": f"Seguimos {full}: un candidato a cometa por confirmar, y sus medidas de esta noche lo definirán.",
                    "en": f"We are following {full_en}: a comet candidate to be confirmed, and tonight's measurements will define it."}
        sb = d.get("sbdb") or {}
        na = d.get("next_approach")
        if na and na["dist_ld"] < 20:
            return {"es": f"Este objeto pasará a solo {na['dist_ld']:.1f} distancias lunares de la Tierra el {na['date']}.",
                    "en": f"This object will pass just {na['dist_ld']:.1f} lunar distances from Earth on {na['date']}."}
        fam = orbits.family_text(d.get("family"))
        if fam:
            return fam
        if kind == "comet" and d.get("mag_now"):
            # the outburst story beats the generic follow-up (ADR-027)
            return {"es": f"{sb.get('fullname', 'El cometa')} brilla ahora con magnitud {d['mag_now']:.1f}: su núcleo está en actividad.",
                    "en": f"{sb.get('fullname', 'The comet')} now shines at magnitude {d['mag_now']:.1f}: its nucleus is active."}
        return {"es": f"Seguimiento de {sb.get('fullname', 'este objeto')} desde nuestro observatorio.",
                "en": f"Follow-up of {sb.get('fullname', 'this object')} from our observatory."}
    if kind in ("exoplanet", "transit"):
        t = d.get("unconfirmed") or {}
        return _transit_hook(t.get("name") or e.get("name"),
                             d.get("transit") or t.get("transit") or {})
    if kind == "hads":
        return _hads_hook(e.get("name") or "", d.get("hads") or {})
    if kind == "variable":
        return _variable_hook(e.get("name") or "", d.get("variable") or {},
                              d.get("campaign") or {})
    if kind == "sun":
        return {"es": "Así amanece nuestra estrella esta semana.",
                "en": "This is how our star looks this week."}
    if d.get("unconfirmed"):
        # ADR-027: a still-unconfirmed object is not always a generic NEO —
        # if the planner filed it as a SN or a comet, say so and use the
        # context we have (host, type, magnitude, perihelion).
        t = d["unconfirmed"]
        if t.get("kind") == "sn":
            host = t.get("host")
            sn_type = (t.get("sn_type") or "").strip()
            host = str(host).strip() if host else ""
            if host.lower() in ("none", "unknown"):
                host = ""
            # AT names are transients awaiting confirmation; SN names are
            # already supernovae, so we track them. Allow an optional host in
            # parens (e.g. "SN 2026abc (NGC 1058)").
            is_at = bool(re.match(r"^AT\s?\d{4}[a-zA-Z]{1,4}\b",
                                  (t.get("name") or "").strip(), re.I))
            es = "Investigamos una posible supernova" if is_at else "Estudiamos esta supernova"
            en = "We are investigating a likely supernova" if is_at else "We are studying this supernova"
            if sn_type:
                es += f" de tipo {sn_type}"
                en += f" of type {sn_type}"
            if host:
                es += f" en {host}"
                en += f" in {host}"
            if is_at:
                es += ": aún por confirmar, cada medida de esta noche ayuda a decidirla."
                en += ": still unconfirmed, and every measurement tonight helps settle it."
            else:
                es += ": seguimos su evolución noche a noche."
                en += ": we track its evolution night after night."
            return {"es": es, "en": en}
        if t.get("kind") == "neo":
            # an unconfirmed NEO is an asteroid candidate, not a comet —
            # the generic "object" hook below would hide that
            full = t.get("name") or "este objeto"
            full_en = t.get("name") or "this object"
            return {"es": f"Seguimos {full}: un objeto cercano a la Tierra por confirmar, y sus medidas de esta noche lo definirán.",
                    "en": f"We are following {full_en}: a near-Earth object to be confirmed, and tonight's measurements will define it."}
        if t.get("kind") == "comet":
            full = t.get("name") or "este cometa"
            full_en = t.get("name") or "this comet"
            return {"es": f"Seguimos {full}: un candidato a cometa por confirmar, y sus medidas de esta noche lo definirán.",
                    "en": f"We are following {full_en}: a comet candidate to be confirmed, and tonight's measurements will define it."}
        return {"es": "Objeto aún sin confirmar: cada medida de esta noche ayuda a decidir qué es.",
                "en": "Object still unconfirmed: every measurement tonight helps decide what it is."}
    return {"es": "Observación desde nuestro observatorio.",
            "en": "Observation from our observatory."}


def fact_bullets(e):
    # Data bullets with comparisons, ES/EN.
    # @args: e - dict from enrich.enrich()
    # @return: list of {"es":..., "en":...}
    kind = e.get("type")
    d = e.get("data") or {}
    if kind == "sun":
        return _sun_facts(d)
    if kind == "transient":
        # the safe window belongs to the object too: the same bullet the
        # other kinds get (ADR-027 consistency; ADR-020 window maths)
        return _transient_facts(d) + _safe_window_bullets(d)
    if d.get("unconfirmed"):
        return _unconfirmed_facts(d["unconfirmed"]) + _safe_window_bullets(d)
    if kind in ("small_body", "comet"):
        return _small_body_facts(d) + _safe_window_bullets(d)
    if kind == "hads":
        return _hads_facts(d) + _safe_window_bullets(d)
    if kind == "variable":
        return _variable_facts(d) + _safe_window_bullets(d)
    return _safe_window_bullets(d)


def _safe_window_bullets(d):
    # The planned capturing window is the same for every kind, so it is
    # appended here once (rather than duplicated in each *_facts helper).
    # @args: d - data dict (or the project context snapshot)
    # @return: [{"es":.., "en":..}] with at most one safe-window bullet
    out = []
    t = d if d.get("safe_window") else (d.get("unconfirmed") or {})
    swt = safe_window_text(t, duration_s=_planned_duration(d))
    if swt:
        out.append(swt)
    return out


def _planned_duration(d):
    # The planned session length, if a capture plan was saved for this
    # object (stored in the project context; see main_window._project_save_plan).
    # @args: d - data dict / project context
    # @return: seconds (int) or None
    if d.get("duration_s"):
        return int(d["duration_s"])
    return None


def _small_body_facts(d):
    # @args: d - data dict of a small body
    # @return: bullet list ES/EN
    out = []
    sb = d.get("sbdb") or {}
    phys = sb.get("phys") or {}
    els = sb.get("elements") or {}
    fam = orbits.family_text(d.get("family"))
    if fam:
        out.append(fam)
    h = phys.get("H")
    diam = phys.get("diameter")
    if not diam and h:
        spec = str(phys.get("spec_B") or phys.get("spec_T") or "")[:1]
        diam = orbits.diameter_from_h(h, orbits.ALBEDO_BY_SPEC.get(spec,
                                      orbits.DEFAULT_ALBEDO))
    if diam:
        cmp_txt = orbits.size_comparison(diam)
        out.append({"es": f"Tamaño estimado: {cmp_txt['es']}.",
                    "en": f"Estimated size: {cmp_txt['en']}."})
    if d.get("dist_now_km"):
        dt = orbits.distance_text(d["dist_now_km"])
        out.append({"es": f"Ahora mismo está a {dt['es']} de nosotros.",
                    "en": f"Right now it is {dt['en']} away from us."})
    if d.get("mag_now"):
        if d["mag_now"] <= 21:
            out.append({"es": f"Brilla con magnitud {d['mag_now']:.1f}, al alcance de telescopios amateur.",
                        "en": f"It shines at magnitude {d['mag_now']:.1f}, within amateur reach."})
        else:
            out.append({"es": f"Ahora mismo brilla con magnitud {d['mag_now']:.1f}, demasiado débil para equipos amateur: hay que esperar a que se acerque.",
                        "en": f"Right now it shines at magnitude {d['mag_now']:.1f}, too faint for amateur setups: we must wait for it to come closer."})
    na = d.get("next_approach")
    if na:
        st = orbits.speed_text(na["v_rel"]) if na.get("v_rel") else None
        txt_es = f"Su próxima aproximación será el {na['date']}, a {na['dist_ld']:.1f} distancias lunares"
        txt_en = f"Its next close approach will be on {na['date']}, at {na['dist_ld']:.1f} lunar distances"
        if st:
            txt_es += f", a {st['es']}"
            txt_en += f", at {st['en']}"
        out.append({"es": txt_es + ".", "en": txt_en + "."})
    if d.get("mag_expected") is not None:
        out.append({"es": f"Brillo esperado ahora: magnitud {d['mag_expected']:.1f} (ley cometaria M1/K1).",
                    "en": f"Expected brightness now: magnitude {d['mag_expected']:.1f} (M1/K1 cometary law)."})
    per = els.get("per")
    if per:
        out.append({"es": f"Su «año» dura {per/365.25:.1f} años terrestres.",
                    "en": f"Its 'year' lasts {per/365.25:.1f} Earth years."})
    rot = phys.get("rot_per")
    if rot:
        out.append({"es": f"Rota sobre sí mismo cada {rot:.1f} horas.",
                    "en": f"It spins once every {rot:.1f} hours."})
    return out


def _unconfirmed_facts(t):
    # Facts for an object still awaiting confirmation (NEOCP/PCCP),
    # from planner (NEOfixer/PCCP) data only.
    # @args: t - target dict
    # @return: bullet list ES/EN
    out = []
    # --- ADR-027: context the planner had for a SN or a comet candidate ---
    if t.get("sn_type"):
        out.append({"es": f"Tipo de evento: {t['sn_type']}.",
                    "en": f"Event type: {t['sn_type']}."})
    host = t.get("host")
    if host and str(host).lower() not in ("none", "unknown"):
        out.append({"es": f"Galaxia anfitriona: {host}.",
                    "en": f"Host galaxy: {host}."})
    if t.get("disc_date"):
        out.append({"es": f"Detectada el {t['disc_date']}.",
                    "en": f"Reported on {t['disc_date']}."})
    if t.get("perihelion_date"):
        out.append({"es": f"Perihelio cercano el {t['perihelion_date']}: es la época de máximo brillo.",
                    "en": f"Perihelion near {t['perihelion_date']}: the time of peak brightness."})
    if t.get("delta_au"):
        out.append({"es": f"A {t['delta_au']:.2f} u.a. de la Tierra ahora mismo.",
                    "en": f"Now {t['delta_au']:.2f} a.u. from Earth."})
    if t.get("kind") in ("comet",) and not t.get("perihelion_date"):
        out.append({"es": "Candidato a cometa: buscamos un halo de coma o una cola.",
                    "en": "Comet candidate: looking for a coma halo or a tail."})
    # --- the classic NEO / PCCP unconfirmed bullets ---
    if t.get("neocp"):
        out.append({"es": "Figura en la NEOCP del MPC: candidato a objeto cercano a la Tierra pendiente de confirmación.",
                    "en": "Listed on the MPC's NEOCP: a near-Earth object candidate awaiting confirmation."})
    if t.get("pccp_score"):
        out.append({"es": f"Score de cometa {t['pccp_score']:.0f}/100 en la página PCCP del MPC: podría ser un cometa nuevo.",
                    "en": f"Comet score {t['pccp_score']:.0f}/100 on the MPC's PCCP: it could be a new comet."})
    if t.get("mag"):
        out.append({"es": f"Magnitud estimada: {t['mag']:.1f}.",
                    "en": f"Estimated magnitude: {t['mag']:.1f}."})
    if t.get("nobs"):
        out.append({"es": f"Observaciones acumuladas: {t['nobs']} (cuantas más, más fiable es su órbita).",
                    "en": f"Collected observations: {t['nobs']} (the more, the more reliable its orbit)."})
    return out


def _transient_otype(d):
    # The event type, from SIMBAD first and the context second (ADR-027).
    # @args: d - transient data dict
    # @return: otype string or None
    otype = (d.get("simbad") or {}).get("otype")
    if not otype:
        otype = d.get("otype")
    return otype or None


def _transient_facts(d):
    # @args: d - data dict of a transient
    # @return: bullet list ES/EN
    out = []
    sim = d.get("simbad") or {}
    otype = _transient_otype(d)
    if otype:
        out.append({"es": f"Tipo de evento: {otype}.",
                    "en": f"Event type: {otype}."})
    host = (d.get("host") or {}).get("name")
    if host:
        out.append({"es": f"Galaxia anfitriona: {host}.",
                    "en": f"Host galaxy: {host}."})
    if d.get("dist_mly"):
        out.append({"es": f"Ocurrió a {d['dist_mly']:.0f} millones de años luz: la luz ha viajado hasta nosotros desde mucho antes de que existiera la humanidad.",
                    "en": f"It happened {d['dist_mly']:.0f} million light-years away: its light has been travelling since long before humanity existed."})
    if sim.get("vmag") is not None:
        out.append({"es": f"Brilla ahora con magnitud {sim['vmag']:.1f}.",
                    "en": f"It now shines at magnitude {sim['vmag']:.1f}."})
    elif d.get("mag") is not None:
        out.append({"es": f"Magnitud estimada: {d['mag']:.1f}.",
                    "en": f"Estimated magnitude: {d['mag']:.1f}."})
    if d.get("disc_date"):
        out.append({"es": f"Detectada el {d['disc_date']}.",
                    "en": f"Reported on {d['disc_date']}."})
    return out


def _transit_hook(planet, tr):
    # The exoplanet-transit hook for a single object.
    # @args: planet - planet designation (e.g. 55Cnce) or None,
    #        tr - the ExoClock "transit" sub-dict
    # @return: {"es": str, "en": str}
    star = (tr or {}).get("star")
    detail = _transit_detail(tr or {})
    detail_es = f" ({detail['es']})" if detail else ""
    detail_en = f" ({detail['en']})" if detail else ""
    who_es = f"el exoplaneta {planet}" if planet else "un exoplaneta"
    who_en = f"the exoplanet {planet}" if planet else "an exoplanet"
    where_es = f" de {star}" if star else ""
    where_en = f" of {star}" if star else ""
    return {"es": f"Esta noche {who_es} transita la estrella{where_es} y podemos medirlo{detail_es}.",
            "en": f"Tonight {who_en} transits the star{where_en} and we can measure it{detail_en}."}


def _transit_detail(tr):
    # Transit depth and duration in a short bilingual clause, from the
    # ExoClock "transit" sub-dict. The star goes in the hook sentence, so it
    # is not repeated here.
    # @args: tr - the planner target's "transit" sub-dict
    # @return: {"es": str, "en": str} or None when there is nothing to add
    bits_es, bits_en = [], []
    depth = tr.get("depth_mmag")
    dur = tr.get("duration_h")
    if depth:
        bits_es.append(f"profundidad {depth:.0f} miligram")
        bits_en.append(f"depth {depth:.0f} millimags")
    if dur:
        bits_es.append(f"duración {dur:.1f} h")
        bits_en.append(f"duration {dur:.1f} h")
    if not bits_es:
        return None
    return {"es": ", ".join(bits_es), "en": ", ".join(bits_en)}


def _hads_hook(name, h):
    # The HADS hook: a star you can watch pulsate live (ADR-034).
    # @args: name - object name, h - the "hads" sub-dict (catalog + tonight)
    # @return: {"es": str, "en": str}
    per = h.get("period_h")
    amp = h.get("amp")
    if amp is None and h.get("max") is not None and h.get("min") is not None:
        amp = h["min"] - h["max"]
    who_es = f"la estrella {name}" if name else "esta estrella"
    who_en = f"the star {name}" if name else "this star"
    if per and amp:
        txt = {"es": f"Esta noche {who_es} pulsa ante nosotros: cada {per:.2f} h "
                     f"completa un latido y cambia {amp:.1f} mag de brillo — la "
                     "verás latir en directo.",
               "en": f"Tonight {who_en} pulsates in front of us: every {per:.2f} h "
                     f"it completes one beat and swings {amp:.1f} mag — you will "
                     "watch it beat live."}
    else:
        txt = {"es": f"Esta noche seguimos {who_es}, una variable pulsante de "
                     "gran amplitud.",
               "en": f"Tonight we follow {who_en}, a high-amplitude pulsating "
                     "variable."}
    if h.get("priority") in ("period_change", "period_change_possible"):
        txt["es"] += " El programa de P. Wils la marca como prioritaria."
        txt["en"] += " P. Wils' monitoring programme flags it as a priority."
    if name in hads.FAMOUS_HADS:
        txt["es"] += " Es un prototipo de su clase."
        txt["en"] += " It is a prototype of its class."
    return txt


def _hads_facts(d):
    # @args: d - data dict of a HADS star (with the "hads" sub-dict)
    # @return: bullet list ES/EN
    out = []
    h = d.get("hads") or {}
    per = h.get("period_h")
    amp = h.get("amp")
    if amp is None and h.get("max") is not None and h.get("min") is not None:
        amp = h["min"] - h["max"]
    if per and amp is not None:
        out.append({"es": f"Pulsa con un periodo de {per:.2f} h y una amplitud "
                          f"de {amp:.1f} mag: una curva de luz completa cabe en "
                          "una sola noche.",
                    "en": f"It pulsates with a {per:.2f}-hour period and a "
                          f"{amp:.1f}-mag amplitude: a full light curve fits in "
                          "a single night."})
    out.append({"es": "Es una δ Scuti de gran amplitud (HADS): late en la franja "
                      "de inestabilidad, donde reinan las cefeidas. Antes se "
                      "llamaban «cefeidas enanas».",
                "en": "It is a high-amplitude δ Scuti star (HADS): it beats in "
                      "the instability strip, where Cepheids rule. They were "
                      "once called 'dwarf Cepheids'."})
    out.append({"es": "La AAVSO las recomienda como primer objetivo de "
                      "fotometría digital: una imagen cada 15 minutos como "
                      "máximo sigue la curva entera.",
                "en": "The AAVSO recommends them as the first digital "
                      "photometry target: one image every 15 minutes at most "
                      "follows the whole curve."})
    if h.get("multiperiodic"):
        out.append({"es": "Es multiperiódica: late en varios modos a la vez "
                          "(ratio de periodos 0.76–0.78, diagrama de Petersen). "
                          "Obsérvala en noches consecutivas para separarlos.",
                    "en": "It is multiperiodic: it beats in several modes at "
                          "once (period ratio 0.76–0.78, Petersen diagram). "
                          "Observe it on consecutive nights to separate them."})
    if h.get("priority") in ("period_change", "period_change_possible"):
        found = h["priority"] == "period_change"
        out.append({"es": ("El programa de seguimiento de Patrick Wils (VVS / "
                           "AAVSO-VSX) le ha encontrado cambios de periodo" if found
                           else "El programa de Patrick Wils (VVS / AAVSO-VSX) "
                           "sospecha cambios de periodo") +
                          ": tu curva de esta noche cuenta doble.",
                    "en": ("Patrick Wils' monitoring programme (VVS / AAVSO-VSX) "
                           "has found period changes" if found
                           else "Patrick Wils' programme (VVS / AAVSO-VSX) "
                           "suspects period changes") +
                          ": tonight's curve counts double."})
    if h.get("observed") is False:
        out.append({"es": "El programa de seguimiento aún no la ha medido "
                          "nunca: serías de los primeros.",
                    "en": "The monitoring programme has never measured it: "
                          "you would be among the first."})
    return out

    # Transit depth and duration in a short bilingual clause, from the
    # ExoClock "transit" sub-dict. The star goes in the hook sentence, so it
    # is not repeated here.
    # @args: tr - the planner target's "transit" sub-dict
    # @return: {"es": str, "en": str} or None when there is nothing to add
    bits_es, bits_en = [], []
    depth = tr.get("depth_mmag")
    dur = tr.get("duration_h")
    if depth:
        bits_es.append(f"profundidad {depth:.0f} miligram")
        bits_en.append(f"depth {depth:.0f} millimags")
    if dur:
        bits_es.append(f"duración {dur:.1f} h")
        bits_en.append(f"duration {dur:.1f} h")
    if not bits_es:
        return None
    return {"es": ", ".join(bits_es), "en": ", ".join(bits_en)}


def _variable_hook(name, v, camp):
    # The variable hook: the campaign that watches it and its next extremum.
    # @args: name - object name, v - "variable" sub-dict, camp - "campaign"
    # @return: {"es": str, "en": str}
    who_es = f"la estrella {name}" if name else "esta estrella"
    who_en = f"the star {name}" if name else "this star"
    if camp.get("name"):
        es = f"Seguimos {who_es} dentro de la campaña «{camp['name']}»."
        en = (f"We are following {who_en} inside the “{camp['name']}” "
              "campaign.")
    else:
        es = f"Seguimos {who_es}, una estrella variable."
        en = f"We are following {who_en}, a variable star."
    nxt = v.get("next_extremum") or {}
    if nxt.get("days") is not None:
        lab_es = "máximo" if nxt.get("kind") == "max" else "mínimo"
        lab_en = "maximum" if nxt.get("kind") == "max" else "minimum"
        es += f" Su próximo {lab_es} se espera en ~{nxt['days']:.0f} días."
        en += f" Its next {lab_en} is expected in ~{nxt['days']:.0f} days."
    return {"es": es, "en": en}


def _variable_facts(d):
    # @args: d - data dict of a variable star
    # @return: bullet list ES/EN
    out = []
    v = d.get("variable") or {}
    fam, _epoch_min = orbits._variable_family_text(v.get("var_type"))
    out.append({"es": fam["es"], "en": fam["en"]})
    per, amp = v.get("period_d"), v.get("amp")
    if amp is None and v.get("max") is not None and v.get("min") is not None:
        amp = v["min"] - v["max"]
    if per:
        out.append({"es": f"Varía con un periodo de {per:.1f} días"
                          + (f" y una amplitud de {amp:.1f} mag."
                             if amp else "."),
                    "en": f"It varies with a {per:.1f}-day period"
                          + (f" and a {amp:.1f}-mag amplitude."
                             if amp else ".")})
    c = d.get("campaign") or {}
    if c.get("name"):
        out.append({"es": f"Forma parte de la campaña «{c['name']}»: "
                          "cada noche cuenta.",
                    "en": f"It belongs to the “{c['name']}” campaign: "
                          "every night counts."})
    return out


def _sun_facts(d):
    # @args: d - data dict of the Sun
    # @return: bullet list ES/EN
    out = []
    if d.get("ssn") is not None:
        out.append({"es": f"Número de manchas solares: {d['ssn']:.0f} (ciclo 25).",
                    "en": f"Sunspot number: {d['ssn']:.0f} (cycle 25)."})
    if d.get("n_regions") is not None:
        out.append({"es": f"Regiones activas numeradas hoy: {d['n_regions']}.",
                    "en": f"Numbered active regions today: {d['n_regions']}."})
    fl = d.get("flare_7d")
    if fl:
        out.append({"es": f"Fulguración más intensa de la semana: clase {fl['class']}{fl['value']}.",
                    "en": f"Strongest flare of the week: class {fl['class']}{fl['value']}."})
    if d.get("kp") is not None:
        aur = {"possible": ("posibles auroras en latitudes medias",
                            "auroras possible at mid-latitudes"),
               "unlikely": ("sin auroras previstas en latitudes medias",
                            "no mid-latitude auroras expected")}.get(d.get("aurora"), ("", ""))
        out.append({"es": f"Índice Kp {d['kp']:.1f}: {aur[0]}.",
                    "en": f"Kp index {d['kp']:.1f}: {aur[1]}."})
    return out


def sky_draft(sun, moon, planets):
    # The "sky today" outreach draft (ADR-036, S3): hook + Sun + Moon +
    # naked-eye planets at dusk, bilingual markdown ready to paste. Built
    # from the same data the "Sun & sky" tab shows.
    # @args: sun - solar.solar_now() dict (may be {}), moon -
    #        ephem_minor.moon() dict, planets - ["Venus (mag -4.2, 18°)",
    #        ...] visible at dusk (may be empty)
    # @return: {"es": str, "en": str}
    es, en = [], []
    es.append("**El cielo de hoy**")
    en.append("**Today's sky**")
    for b in _sun_facts(sun or {}):
        es.append("• " + b["es"])
        en.append("• " + b["en"])
    if moon:
        es.append("• La Luna está al "
                  f"{moon['illum'] * 100:.0f}% (edad {moon['phase_age_days']:.0f} días)."
                  )
        en.append(f"• The Moon is {moon['illum'] * 100:.0f}% lit "
                  f"(age {moon['phase_age_days']:.0f} days).")
    if planets:
        es.append("• Al anochecer: " + ", ".join(planets) + ".")
        en.append("• At dusk: " + ", ".join(planets) + ".")
    return {"es": "\n".join(es), "en": "\n".join(en)}


def safe_window_text(t, duration_s=None):
    # The session-safe observing window (ADR-020): when the planned sequence
    # still clears the local horizon and the latest safe start. Bilingual so
    # the post prose and the GUI chips say the same thing.
    # @args: t - planner target (safe_window, best_time, window_*),
    #        duration_s - planned session seconds (for the "does not fit" note)
    # @return: {"es": str, "en": str} or None when there is no window
    hm = lambda iso: iso[11:16] if iso else None
    if not t.get("safe_window"):
        return None
    s0, s1 = t["safe_window"].split("|")
    w = f"{hm(s0)}–{hm(s1)} UTC"
    bt = hm(t.get("best_time"))
    es = f"Ventana de observación segura: {w}; empezar a lo último a las {bt}." \
        if bt else f"Ventana de observación segura: {w}."
    en = f"Safe observing window: {w}; start by {bt}." \
        if bt else f"Safe observing window: {w}."
    if duration_s and t.get("window_start") and t.get("window_end"):
        import datetime as _dt
        span = (_dt.datetime.fromisoformat(t["window_end"])
                - _dt.datetime.fromisoformat(t["window_start"])).total_seconds()
        if span < float(duration_s):
            mins = int(round(float(duration_s) / 60))
            es += f" La sesión de {mins} min no cabe esta noche: no forzar el equipo."
            en += (f" A {mins} min session does not fit tonight: "
                   f"do not force the instrument.")
    return {"es": es, "en": en}


def hashtags(kind):
    # Fixed + per-type bilingual hashtags.
    # @args: kind - object kind
    # @return: single string
    base = "#astronomia #astronomy #CitizenScience"
    per_kind = {
        "small_body": "#asteroide #asteroid #NEO #cometa #comet",
        "neo": "#asteroide #asteroid #NEO",
        "comet": "#cometa #comet",
        "pccp": "#cometa #comet",
        "transient": "#supernova",
        "sn": "#supernova",
        "exoplanet": "#exoplanet #exoplaneta",
        "transit": "#exoplanet #exoplaneta",
        "hads": "#VariableStars #HADS #AAVSO",
        "variable": "#VariableStars #AAVSO",
        "sun": "#Sol #Sun #SpaceWeather",
    }
    return base + " " + per_kind.get(kind, "")
