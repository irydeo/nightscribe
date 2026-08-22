############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Orbital explorer module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import math

# Translates raw orbital/physical parameters into accurate, engaging
# explanations (see docs/ORBITS.md). All texts are bilingual {"es", "en"}.

AU_KM = 149597870.7
LD_KM = 384400.0

# Assumed albedo per spectral class for size estimates
ALBEDO_BY_SPEC = {"C": 0.057, "S": 0.20, "M": 0.14, "X": 0.14, "D": 0.04}
DEFAULT_ALBEDO = 0.14
COMET_ALBEDO = 0.04

# Densities (kg/m3) per spectral class, for the (careful) energy estimate
DENSITY_BY_SPEC = {"C": 1300.0, "S": 2700.0, "M": 5000.0}


# ---------------- Families ----------------

FAMILIES = {
    "Atira": {"es": "Asteroide Atira: vive por completo dentro de la órbita de la Tierra.",
              "en": "Atira asteroid: it lives entirely inside Earth's orbit."},
    "Aten": {"es": "Asteroide Aten: cruza la órbita de la Tierra desde dentro.",
             "en": "Aten asteroid: it crosses Earth's orbit from the inside."},
    "Apollo": {"es": "Asteroide Apollo: cruza la órbita de la Tierra desde fuera.",
               "en": "Apollo asteroid: it crosses Earth's orbit from the outside."},
    "Amor": {"es": "Asteroide Amor: se acerca a la órbita de la Tierra sin cruzarla.",
             "en": "Amor asteroid: it approaches Earth's orbit without crossing it."},
    "Main Belt": {"es": "Asteroide del cinturón principal, entre Marte y Júpiter.",
                  "en": "Main-belt asteroid, between Mars and Jupiter."},
    "Trojan": {"es": "Troyano: comparte la órbita de Júpiter, delante o detrás del planeta.",
               "en": "Trojan: it shares Jupiter's orbit, leading or trailing the planet."},
    "Centaur": {"es": "Centauro: vaga entre los planetas gigantes.",
                "en": "Centaur: it wanders between the giant planets."},
    "TNO": {"es": "Objeto transneptuniano: las afueras heladas del sistema solar.",
            "en": "Trans-Neptunian object: the frozen outskirts of the solar system."},
    "JFc": {"es": "Cometa de la familia de Júpiter: atrapado por el gigante, vuelve cada pocos años.",
            "en": "Jupiter-family comet: captured by the giant, it returns every few years."},
    "HTc": {"es": "Cometa tipo Halley: visitante periódico de largo aliento.",
            "en": "Halley-type comet: a long-period periodic visitor."},
    "LPC": {"es": "Cometa de largo período: viene de la nube de Oort y no volverá en milenios.",
            "en": "Long-period comet: from the Oort cloud; it will not return for millennia."},
}


def classify(elements, orbit_code=None):
    # Orbital family from elements (and the SBDB class code when given).
    # @args: elements - dict with a, q, e..., orbit_code - SBDB code
    # @return: family key of FAMILIES
    if orbit_code in ("JFc", "HTc", "CTc"):
        return orbit_code
    if orbit_code == "COM" or (elements.get("e") or 0) >= 0.9 and elements.get("a"):
        return "LPC"
    a = elements.get("a")
    q = elements.get("q")
    if a is None:
        return None
    if q is not None:
        if a < 1.0 and q is not None and (elements.get("Q") or a * (1 + elements.get("e", 0) / (1 - elements.get("e", 1)))) < 0.983:
            pass  # refined below with Q
    Q = elements.get("Q")
    if Q is None and a and elements.get("e") is not None:
        Q = a * (1 + elements["e"])
    if q is None and a and elements.get("e") is not None:
        q = a * (1 - elements["e"])
    if a < 1.0 and Q is not None and Q < 0.983:
        return "Atira"
    if a < 1.0 and Q is not None:
        return "Aten"
    if q is not None and q < 1.017 and a >= 1.0:
        return "Apollo"
    if q is not None and 1.017 <= q < 1.3:
        return "Amor"
    if 4.9 < a < 5.5:
        return "Trojan"
    if 5.5 <= a < 30:
        return "Centaur"
    if a >= 30:
        return "TNO"
    return "Main Belt"


# ---------------- Sizes and magnitudes ----------------

def diameter_from_h(h, albedo=DEFAULT_ALBEDO):
    # @args: h - absolute magnitude, albedo - assumed geometric albedo
    # @return: estimated diameter in km
    return 1329.0 / math.sqrt(albedo) * 10 ** (-h / 5.0)


def pick(texts, lang):
    # Selects one language from a {"es", "en"} pair. The GUI always shows a
    # single language (ADR-017); only post.py keeps using both.
    # @args: texts - {"es","en"} dict, lang - "es" | "en"
    # @return: the chosen string
    if not isinstance(texts, dict):
        return str(texts)
    return texts.get(lang) or texts.get("en") or ""


def size_comparison(d_km):
    # Everyday comparison for a diameter.
    # @args: d_km - diameter in km
    # @return: {"es":..., "en":...}
    m = d_km * 1000.0
    if m < 25:
        return {"es": f"apenas {m:.0f} m: como un edificio de {max(int(m/3),2)} plantas",
                "en": f"barely {m:.0f} m: like a {max(int(m/3),2)}-storey building"}
    if m < 150:
        return {"es": f"unos {m:.0f} m: como un estadio de fútbol",
                "en": f"about {m:.0f} m: like a football stadium"}
    if m < 500:
        n = max(round(m / 105), 1)
        return {"es": f"unos {m:.0f} m: como {n} campos de fútbol",
                "en": f"about {m:.0f} m: {n} football pitches"}
    if d_km < 2:
        return {"es": f"casi {d_km:.1f} km: como la Torre Eiffel tumbada {round(m/330)} veces",
                "en": f"nearly {d_km:.1f} km: like {round(m/330)} Eiffel Towers laid down"}
    if d_km < 15:
        return {"es": f"unos {d_km:.1f} km: del tamaño de una ciudad pequeña",
                "en": f"about {d_km:.1f} km: the size of a small city"}
    return {"es": f"unos {d_km:.0f} km: comparable a una provincia pequeña",
            "en": f"about {d_km:.0f} km: comparable to a small county"}


def visual_mag(h, r_au, delta_au):
    # Rough apparent magnitude from absolute magnitude (phase neglected).
    # @args: h - absolute mag, r_au - heliocentric, delta_au - observer range
    # @return: magnitude or None
    if not h or not r_au or not delta_au or r_au <= 0 or delta_au <= 0:
        return None
    return h + 5 * math.log10(r_au * delta_au)


def comet_expected_mag(m1, k1, r_au, delta_au):
    # Expected cometary magnitude from M1/K1.
    # @args: m1, k1 - cometary absolute magnitude and activity slope,
    #        r_au, delta_au - distances
    # @return: magnitude or None
    if not m1 or not k1 or not r_au or not delta_au:
        return None
    return m1 + 5 * math.log10(delta_au) + k1 * math.log10(r_au)


def distance_text(dist_km):
    # Human distance: lunar distances when close, millions of km otherwise.
    # @args: dist_km - distance in km
    # @return: {"es":..., "en":...}
    ld = dist_km / LD_KM
    if ld < 100:
        return {"es": f"{ld:.1f} distancias lunares",
                "en": f"{ld:.1f} lunar distances"}
    return {"es": f"{dist_km/1e6:.1f} millones de km",
            "en": f"{dist_km/1e6:.1f} million km"}


def speed_text(v_kms):
    # Human speed comparison.
    # @args: v_kms - speed in km/s
    # @return: {"es":..., "en":...}
    bullets = v_kms / 1.0  # a rifle bullet is about 1 km/s
    return {"es": f"{v_kms:.1f} km/s, unas {bullets:.0f} veces una bala de rifle",
            "en": f"{v_kms:.1f} km/s, about {bullets:.0f} times a rifle bullet"}


def family_text(family):
    # @args: family - key of FAMILIES
    # @return: {"es":..., "en":...} or None
    return FAMILIES.get(family)


# ---------------- Parameter interpreter ----------------

def _crossing_text(q, Q):
    # Which planetary orbits the object crosses or approaches.
    # @args: q, Q - perihelion/aphelion in AU
    # @return: {"es","en"} or None
    planets = [(0.387, "Mercurio", "Mercury"), (0.723, "Venus", "Venus"),
               (1.0, "la Tierra", "Earth"), (1.524, "Marte", "Mars"),
               (5.2, "Júpiter", "Jupiter")]
    crosses = [(es, en) for r, es, en in planets if q <= r <= (Q or q)]
    if not crosses:
        return None
    names_es = ", ".join(c[0] for c in crosses)
    names_en = ", ".join(c[1] for c in crosses)
    return {"es": f"cruza la órbita de {names_es}",
            "en": f"crosses the orbit of {names_en}"}


def explain_elements(elements, phys=None, family=None, moid=None):
    # Translates each orbital/physical parameter into *intuitive* language.
    # Every row has a "level": "basic" rows are the handful everyone should
    # see; "deep" rows appear under the "in depth" toggle (see ADR-017).
    # @args: elements - SBDB elements dict, phys - SBDB phys dict,
    #        family - key from classify(), moid - MOID in AU if known
    # @return: list of dicts: {"param", "value", "level", "es", "en"}
    phys = phys or {}
    out = []
    a = elements.get("a")
    e = elements.get("e")
    i = elements.get("i")
    n = elements.get("n")
    q = elements.get("q") or (a * (1 - e) if a and e is not None else None)
    Q = elements.get("Q") or (a * (1 + e) if a and e is not None else None)
    per = elements.get("per")

    if family and family_text(family):
        out.append({"param": {"es": "Familia", "en": "Family"},
                    "value": family, "level": "basic",
                    "es": family_text(family)["es"],
                    "en": family_text(family)["en"]})
    if q is not None and Q is not None:
        out.append({
            "param": {"es": "Distancias al Sol (q / Q)", "en": "Sun distances (q / Q)"},
            "value": f"{q:.2f} — {Q:.2f} UA", "level": "basic",
            "es": f"Su «verano» (perihelio) lo pasa a {q:.2f} UA del Sol y su «invierno» "
                  f"(afelio) a {Q:.2f} UA. La Tierra vive a 1 UA: así sitúas su viaje.",
            "en": f"It spends its 'summer' (perihelion) {q:.2f} AU from the Sun and its "
                  f"'winter' (aphelion) at {Q:.2f} AU. Earth lives at 1 AU: that is your ruler."})
    h = phys.get("H")
    diam = None
    if h:
        spec = str(phys.get("spec_B") or phys.get("spec_T") or "")[:1]
        diam = phys.get("diameter") or diameter_from_h(
            h, ALBEDO_BY_SPEC.get(spec, DEFAULT_ALBEDO))
        cmp_txt = size_comparison(diam)
        out.append({
            "param": {"es": "Tamaño estimado", "en": "Estimated size"},
            "value": f"{diam * 1000:.0f} m" if diam < 1 else f"{diam:.1f} km",
            "level": "basic",
            "es": f"De su brillo absoluto (H = {h:.1f}) estimamos el tamaño: {cmp_txt['es']}.",
            "en": f"From its absolute brightness (H = {h:.1f}) we estimate the size: "
                  f"{cmp_txt['en']}."})
    if per:
        out.append({
            "param": {"es": "Su año", "en": "Its year"},
            "value": f"{per/365.25:.2f} " + ("años" if True else ""), "level": "basic",
            "es": f"Una vuelta al Sol le lleva {per:.0f} días terrestres: su calendario no se parece al nuestro.",
            "en": f"One lap around the Sun takes {per:.0f} Earth days: its calendar is nothing like ours."})
    if moid is not None:
        ld = moid * AU_KM / LD_KM
        km = moid * AU_KM
        ld_txt = f"{ld:.3f}" if ld < 1 else f"{ld:.1f}"
        base_es = (f"Imagina dos carreteras ovaladas: la de la Tierra y la suya. El MOID es el punto "
                   f"donde más se acercan: {km:,.0f} km ({ld_txt} veces la distancia a la Luna). "
                   f"Que las carreteras se crucen no significa que los coches choquen: hace falta "
                   f"llegar al cruce a la vez. ")
        base_en = (f"Picture two oval roads: Earth's and its own. The MOID is the point where they "
                   f"come closest: {km:,.0f} km ({ld_txt} times the Moon distance). Crossing roads "
                   f"do not mean crashing cars — both must reach the junction at the same time. ")
        if moid < 0.05:
            extra = ("Y este entra en la lista «PHA» (potencialmente peligroso): no es una amenaza "
                     "conocida, es simplemente uno al que vigilamos de cerca.",
                     "This one is on the 'PHA' (potentially hazardous) list: not a known threat, "
                     "just one we keep a close eye on.")
        else:
            extra = ("Hoy por hoy: ningún choque conocido en los cálculos.",
                     "As of today: no known impact in the calculations.")
        out.append({
            "param": {"es": "MOID (mínimo acercamiento de órbitas)", "en": "MOID (minimum orbit approach)"},
            "value": f"{moid:.4f} AU", "level": "basic",
            "es": base_es + extra[0],
            "en": base_en + extra[1]})
    if a:
        out.append({
            "param": {"es": "Semieje mayor (a)", "en": "Semi-major axis (a)"},
            "value": f"{a:.3f} AU", "level": "deep",
            "es": "El «tamaño» de su elipse: la mitad del eje largo. Es el parámetro que manda: fija el período orbital (tercera ley de Kepler).",
            "en": "The 'size' of its ellipse: half the long axis. It is the boss parameter: it fixes the orbital period (Kepler's third law)."})
    if e is not None:
        if e < 0.1:
            txt = ("casi un círculo", "almost a circle")
        elif e < 0.5:
            txt = ("una elipse suave, como la mayoría", "a gentle ellipse, like most")
        else:
            txt = ("una elipse muy estirada", "a very stretched ellipse")
        cross = _crossing_text(q, Q) if q is not None else None
        out.append({
            "param": {"es": "Excentricidad (e)", "en": "Eccentricity (e)"},
            "value": f"{e:.3f}", "level": "deep",
            "es": f"0 sería un círculo perfecto y casi 1 una línea; con {e:.2f} es {txt[0]}"
                  + (f" y en su camino {cross['es']}." if cross else "."),
            "en": f"0 would be a perfect circle, almost 1 a line; at {e:.2f} it is {txt[1]}"
                  + (f" and on its way it {cross['en']}." if cross else ".")})
    if i is not None:
        out.append({
            "param": {"es": "Inclinación (i)", "en": "Inclination (i)"},
            "value": f"{i:.1f}°", "level": "deep",
            "es": f"Cuánto se levanta su pista sobre la de los planetas: {i:.1f}°"
                  + (". Bastante inclinada: seguro que viene de un encuentro gravitatorio." if i > 20
                     else ". Va bastante pegada a la autopista planetaria."),
            "en": f"How tilted its track is over the planets' one: {i:.1f}°"
                  + (". Quite tilted: likely a sign of a past gravitational encounter." if i > 20
                     else ". It keeps close to the planetary highway.")})
    if n:
        out.append({
            "param": {"es": "Movimiento medio (n)", "en": "Mean motion (n)"},
            "value": f"{n:.4f} °/día", "level": "deep",
            "es": f"Avanza {n:.3f} grados al día por su órbita, siempre a ese ritmo medio.",
            "en": f"It advances {n:.3f} degrees per day along its orbit, always at that mean pace."})
    rot = phys.get("rot_per")
    if rot:
        out.append({
            "param": {"es": "Rotación", "en": "Rotation"},
            "value": f"{rot:.1f} h", "level": "deep",
            "es": f"Allí un «día» dura {rot:.1f} horas: gira sobre sí mismo a ese ritmo.",
            "en": f"Over there a 'day' lasts {rot:.1f} hours: it spins at that rate."})
    albedo = phys.get("albedo")
    if albedo is not None:
        pct = albedo * 100
        mood = ("oscuro como el carbón" if albedo < 0.08 else
                "bastante oscuro" if albedo < 0.15 else
                "intermedio" if albedo < 0.3 else "claro, casi reflectante")
        mood_en = ("dark as charcoal" if albedo < 0.08 else
                   "quite dark" if albedo < 0.15 else
                   "in-between" if albedo < 0.3 else "bright, almost reflective")
        out.append({
            "param": {"es": "Albedo", "en": "Albedo"},
            "value": f"{pct:.0f}%", "level": "deep",
            "es": f"Refleja el {pct:.0f}% de la luz que recibe: es {mood}.",
            "en": f"It reflects {pct:.0f}% of the light it gets: it is {mood_en}."})
    spec = phys.get("spec_B") or phys.get("spec_T")
    if spec:
        comp = {"C": ("carbonáceo: primitivo y oscuro, resto de los inicios del sistema solar",
                      "carbonaceous: primitive and dark, a leftover from the early solar system"),
                "S": ("rocoso/silicatado: piedra con algo de metal",
                      "rocky/silicaceous: stone with some metal"),
                "M": ("metálico: probablemente el núcleo de algo más grande que se rompió",
                      "metallic: probably the core of something bigger that broke apart"),
                "X": ("composición incierta (clase X): hacen falta más datos",
                      "uncertain composition (X class): more data needed")}
        c = comp.get(str(spec)[:1], ("de composición poco común", "of uncommon composition"))
        out.append({
            "param": {"es": "Clase espectral", "en": "Spectral class"},
            "value": str(spec), "level": "deep",
            "es": f"Tipo {spec}: {c[0]}.",
            "en": f"Type {spec}: {c[1]}."})
    if elements.get("U") is not None:
        u = elements["U"]
        out.append({
            "param": {"es": "Incertidumbre de órbita (U)", "en": "Orbit uncertainty (U)"},
            "value": str(u), "level": "deep",
            "es": f"De 0 (perfectamente conocida) a 9 (casi perdido): este tiene {u}. "
                  + ("Tu observación de esta noche ayuda a bajarlo." if u >= 5 else
                     "Su órbita está bastante bien medida."),
            "en": f"From 0 (perfectly known) to 9 (almost lost): this one has {u}. "
                  + ("Tonight's observation helps bring it down." if u >= 5 else
                     "Its orbit is fairly well measured.")})
    return out


def explain_neofixer(t):
    # Interprets what NEOfixer knows about an unconfirmed candidate.
    # @args: t - planner target dict (NEOfixer fields)
    # @return: list of dicts {"param", "value", "level", "es", "en"}
    out = []
    if t.get("nf_score") is not None:
        out.append({
            "param": {"es": "Score NEOfixer", "en": "NEOfixer score"},
            "value": f"{t['nf_score']}", "level": "basic",
            "es": "De 0 a 10: cuánto necesita la comunidad astronómica que ALGUIEN lo mida esta noche. Lo calcula NEOfixer (Catalina/NASA) para tu telescopio concreto.",
            "en": "From 0 to 10: how much the astronomical community needs SOMEONE to measure it tonight. Computed by NEOfixer (Catalina/NASA) for your exact site."})
    if t.get("nf_priority"):
        out.append({
            "param": {"es": "Prioridad", "en": "Priority"},
            "value": str(t["nf_priority"]), "level": "basic",
            "es": f"Su categoría de prioridad: {t['nf_priority']}.",
            "en": f"Its priority category: {t['nf_priority']}."})
    if t.get("nobs") is not None:
        out.append({
            "param": {"es": "Observaciones acumuladas", "en": "Collected observations"},
            "value": str(t["nobs"]), "level": "basic",
            "es": f"Lleva {t['nobs']} medidas. Pocas: órbita preliminar, tu medida pesa mucho. Muchas: órbita ya fiable.",
            "en": f"It has {t['nobs']} measurements. Few: preliminary orbit, your measurement weighs a lot. Many: orbit already reliable."})
    if t.get("nf_cost_min") is not None:
        out.append({
            "param": {"es": "Coste de observación", "en": "Observing cost"},
            "value": f"{t['nf_cost_min']:.0f} min", "level": "basic",
            "es": f"Unos {t['nf_cost_min']:.0f} minutos de telescopio bastan para una medida útil (3 imágenes).",
            "en": f"About {t['nf_cost_min']:.0f} telescope minutes are enough for a useful measurement (3 images)."})
    if t.get("arc_days") is not None:
        out.append({
            "param": {"es": "Arco observado", "en": "Observed arc"},
            "value": f"{t['arc_days']} " + ("días" if True else ""), "level": "deep",
            "es": f"Llevamos siguiéndolo {t['arc_days']} días. Un arco corto corre el riesgo de perderse para siempre.",
            "en": f"We have been tracking it for {t['arc_days']} days. A short arc risks getting lost forever."})
    if t.get("moid") is not None:
        out.append({
            "param": {"es": "MOID (preliminar)", "en": "MOID (preliminary)"},
            "value": f"{t['moid']:.4f} AU", "level": "deep",
            "es": "Mínimo acercamiento teórico entre su órbita y la terrestre, aún por confirmar.",
            "en": "Minimum theoretical approach between its orbit and Earth's, still to be confirmed."})
    return out
