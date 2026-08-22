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

from . import orbits

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
        ly = d.get("dist_mly")
        if ly:
            return {"es": f"La luz de esta explosión salió hace {ly:.0f} millones de años; anoche la captamos desde nuestro observatorio.",
                    "en": f"The light of this explosion left home {ly:.0f} million years ago; last night we caught it from our observatory."}
        return {"es": "Seguimiento de un fenómeno transitorio desde nuestro observatorio.",
                "en": "Follow-up of a transient event from our observatory."}
    if kind in ("small_body", "comet"):
        sb = d.get("sbdb") or {}
        na = d.get("next_approach")
        if na and na["dist_ld"] < 20:
            return {"es": f"Este objeto pasará a solo {na['dist_ld']:.1f} distancias lunares de la Tierra el {na['date']}.",
                    "en": f"This object will pass just {na['dist_ld']:.1f} lunar distances from Earth on {na['date']}."}
        fam = orbits.family_text(d.get("family"))
        if fam:
            return fam
        return {"es": f"Seguimiento de {sb.get('fullname', 'este objeto')} desde nuestro observatorio.",
                "en": f"Follow-up of {sb.get('fullname', 'this object')} from our observatory."}
    if kind == "exoplanet":
        return {"es": "Esta noche un planeta de otro sistema eclipsa su estrella, y podemos medirlo.",
                "en": "Tonight a planet of another system eclipses its star, and we can measure it."}
    if kind == "sun":
        return {"es": "Así amanece nuestra estrella esta semana.",
                "en": "This is how our star looks this week."}
    if d.get("unconfirmed"):
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
    if d.get("unconfirmed"):
        return _unconfirmed_facts(d["unconfirmed"])
    if kind in ("small_body", "comet"):
        return _small_body_facts(d)
    if kind == "transient":
        return _transient_facts(d)
    if kind == "sun":
        return _sun_facts(d)
    return []


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


def _transient_facts(d):
    # @args: d - data dict of a transient
    # @return: bullet list ES/EN
    out = []
    sim = d.get("simbad") or {}
    host = d.get("host") or {}
    if sim.get("otype"):
        out.append({"es": f"Tipo de evento: {sim['otype']}.",
                    "en": f"Event type: {sim['otype']}."})
    if host.get("name"):
        txt = {"es": f"Galaxia anfitriona: {host['name']}.",
               "en": f"Host galaxy: {host['name']}."}
        out.append(txt)
    if d.get("dist_mly"):
        out.append({"es": f"Ocurrió a {d['dist_mly']:.0f} millones de años luz: la luz ha viajado hasta nosotros desde mucho antes de que existiera la humanidad.",
                    "en": f"It happened {d['dist_mly']:.0f} million light-years away: its light has been travelling since long before humanity existed."})
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
        "sun": "#Sol #Sun #SpaceWeather",
    }
    return base + " " + per_kind.get(kind, "")
