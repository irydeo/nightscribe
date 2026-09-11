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


def tisserand_earth(a, e, i_deg):
    # Tisserand parameter w.r.t. Earth (a_p = 1 AU): T = 1/a + 2*sqrt(a*(1-e^2))*cos(i).
    # T < 3 co-orbital / JFC regime for comets, T > 3 asteroid; valid for bound orbits.
    # @args: a - semi-major axis (AU), e - eccentricity, i_deg - inclination (degrees)
    # @return: T_E float, or None if elements are missing or non-bounded (a <= 0)
    if a is None or e is None or i_deg is None:
        return None
    if a <= 0.0 or not (0.0 <= e < 1.0):
        return None
    cos_i = math.cos(math.radians(i_deg))
    return 1.0 / a + 2.0 * math.sqrt(a * (1.0 - e * e)) * cos_i


def encounter_velocity(v_obj, v_earth):
    # Barbee-style encounter speed: |v_obj - v_earth| (heliocentric frame).
    # @args: v_obj - (vx, vy, vz) km/s of the object,
    #        v_earth - (vx, vy, vz) km/s of Earth
    # @return: relative speed km/s, or None if inputs incomplete
    if not v_obj or not v_earth or len(v_obj) < 3 or len(v_earth) < 3:
        return None
    dx = v_obj[0] - v_earth[0]
    dy = v_obj[1] - v_earth[1]
    dz = v_obj[2] - v_earth[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


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


def explain_elements(elements, phys=None, family=None, moid=None,
                     sigmas=None, n_resids=None, arc_days=None):
    # Translates each orbital/physical parameter into *intuitive* language.
    # Every row has a "level": "basic" rows are the handful everyone should
    # see; "deep" rows appear under the "in depth" toggle (see ADR-017).
    # @args: elements - SBDB elements dict, phys - SBDB phys dict,
    #        family - key from classify(), moid - MOID in AU if known,
    #        sigmas - per-element uncertainties (preliminary NEOfixer orbits),
    #        n_resids - number of astrometric residuals, arc_days - observed arc
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

    if sigmas:
        out.append({
            "param": {"es": "Órbita preliminar", "en": "Preliminary orbit"},
            "value": "NEOfixer / Find_Orb", "level": "basic",
            "es": "Este objeto aún no está confirmado por el MPC: la órbita es una "
                  "solución preliminar calculada por NEOfixer (Find_Orb) con las pocas "
                  "observaciones disponibles. Puede cambiar — tu medida de esta noche "
                  "es justo lo que la mejora.",
            "en": "This object is not yet MPC-confirmed: the orbit is a preliminary "
                  "solution computed by NEOfixer (Find_Orb) from the few available "
                  "observations. It can change — tonight's measurement is exactly "
                  "what improves it."})
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
    if sigmas:
        bits = []
        if a and sigmas.get("a") is not None:
            bits.append(f"a ± {sigmas['a']:.4g} UA")
        if e is not None and sigmas.get("e") is not None:
            bits.append(f"e ± {sigmas['e']:.3g}")
        if i is not None and sigmas.get("i") is not None:
            bits.append(f"i ± {sigmas['i']:.3g}°")
        if bits:
            out.append({
                "param": {"es": "Incertidumbre de los elementos (σ)",
                          "en": "Element uncertainties (σ)"},
                "value": ", ".join(bits), "level": "deep",
                "es": "Cada elemento lleva su σ (desviación típica): cuánto puede "
                      "moverse el valor real respecto al calculado. σ pequeñas = "
                      "órbita sólida; σ grandes = aún se está perfilando.",
                "en": "Each element carries its σ (standard deviation): how far the "
                      "true value may stray from the fitted one. Small σ = solid "
                      "orbit; large σ = still being pinned down."})
    if n_resids is not None or arc_days is not None:
        val = " · ".join(str(v) for v in
                         (f"{arc_days} días" if arc_days is not None else None,
                          f"{n_resids} obs." if n_resids is not None else None)
                         if v)
        out.append({
            "param": {"es": "Arco y observaciones", "en": "Arc and observations"},
            "value": val, "level": "deep",
            "es": "La órbita se ajusta a esas medidas repartidas en ese arco de "
                  "tiempo. Con arcos cortos, volverlo a medir esta noche vale oro.",
            "en": "The orbit is fitted to those measurements spread over that time "
                  "arc. With short arcs, measuring it again tonight is worth gold."})
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


# ---------------- Transient (supernova) interpreter ----------------
# (object-card plan, subplan 2: the SN card gets the same parameters
# table the small bodies already had)

def _sn_type_text(otype):
    # @args: otype - SIMBAD/Rochester/TNS type string ("SN Ia", "II", ...)
    # @return: {"es","en"} explaining the kind of explosion
    t = (otype or "").strip().lower()
    t = t[2:].strip() if t.startswith("sn") else t
    if t.startswith("ia") and not t.startswith(("iax", "iin")):
        return {"es": "una enana blanca que estalló por fusión termonuclear "
                      "descontrolada: su brillo es tan uniforme que las usamos "
                      "de «velas estándar» para medir distancias",
                "en": "a white dwarf blown up by runaway thermonuclear "
                      "fusion: their brightness is so uniform we use them as "
                      "'standard candles' to measure distances"}
    if t.startswith("iax"):
        return {"es": "una prima hermana de la Ia, pero más débil y rápida: "
                      "su curva de luz sube y baja casi igual, pero no tanto. "
                      "Puede ser una explosión fallida",
                "en": "a cousin of Ia but fainter and faster: its light "
                      "curve rises and falls almost the same, but not quite. "
                      "Possibly a failed explosion"}
    if t.startswith("iin"):
        return {"es": "una supernova de Tipo II con líneas de hidrógeno "
                      "estrechas en su espectro: la estrella progenitora "
                      "expulsó una capa de gas poco antes de colapsar",
                "en": "a Type II supernova with narrow hydrogen lines "
                      "in its spectrum: the progenitor shed a shell of "
                      "gas shortly before collapsing"}
    if t.startswith(("ib", "ic")):
        return {"es": "el colapso de una estrella masiva que ya había perdido "
                      "su envoltura de hidrógeno (y quizá de helio)",
                "en": "the collapse of a massive star that had already shed "
                      "its hydrogen (and maybe helium) envelope"}
    if t.startswith(("ii-p", "ii p")):
        return {"es": "el colapso de una supergigante que conservó su "
                      "hidrógeno: tras el estallido, su brillo se mantiene "
                      "estable semanas (la meseta) antes de decaer lentamente",
                "en": "the collapse of a supergiant that kept its "
                      "hydrogen: after the explosion, its brightness stays "
                      "flat for weeks (the plateau) before fading slowly"}
    if t.startswith(("ii-l", "ii l")):
        return {"es": "el colapso de una supergigante que conservó su "
                      "hidrógeno: su brillo decaer de forma lineal desde el "
                      "principio, sin la meseta de las II-P",
                "en": "the collapse of a supergiant that kept its "
                      "hydrogen: its brightness declines linearly from "
                      "the start, without the II-P plateau"}
    if t.startswith("ii"):
        return {"es": "el colapso de una estrella masiva que conservaba su "
                      "hidrógeno: la muerte clásica de una gigante",
                "en": "the collapse of a massive star that kept its "
                      "hydrogen: the classic death of a giant"}
    if t.startswith(("sln", "slsn")):
        return {"es": "una supernova superluminosa: mucho más "
                      "brillante que las demás y su curva de luz es "
                      "ancha y lenta, de meses o años",
                "en": "a superluminous supernova: far brighter "
                      "than the rest and its light curve is broad "
                      "and slow, lasting months or years"}
    if t.startswith("kilonova"):
        return {"es": "no la muerte de una estrella sino la "
                      "fusión de dos estrellas de neutrones: "
                      "un destello corto y rublicioso que produce "
                      "oro y platino",
                "en": "not the death of a star but the merger "
                      "of two neutron stars: a short bright "
                      "flash that forges gold and platinum"}
    if t.startswith("i"):
        return {"es": "el colapso de una estrella masiva sin rastro de "
                      "hidrógeno en su luz",
                "en": "the collapse of a massive star with no hydrogen left "
                      "in its light"}
    if t.startswith(("cv", "nova")):
        return {"es": "no una supernova sino una nova: una erupción en la "
                      "superficie de una enana blanca, mucho más tenue",
                "en": "not a supernova but a nova: an eruption on a white "
                      "dwarf's surface, far fainter"}
    return {"es": "una explosión estelar cuyo tipo exacto aún se está "
                  "clasificando (de ahí el nombre genérico)",
            "en": "a stellar explosion whose exact type is still being "
                  "classified (hence the generic name)"}


def days_since(date_str):
    # Kept for convenience: the single implementation lives in dates.py
    # (object-card plan, subplan 5d).
    # @args: date_str - any format dates.normalize_date accepts
    # @return: whole days from that date to today, or None if unparseable
    from . import dates
    return dates.days_since(date_str)


def explain_transient(d):
    # Interprets what we know about a supernova/transient: event type, host
    # galaxy, distance, redshift, current brightness, discovery date.
    # @args: d - the enriched data dict (enrich._enrich_transient shape,
    #        with the ADR-027 planner-context merge already applied)
    # @return: list of dicts {"param", "value", "level", "es", "en"}
    out = []
    sim = d.get("simbad") or {}
    host = d.get("host") or {}

    otype = (sim.get("otype") or d.get("otype") or "").strip()
    if otype:
        kind = _sn_type_text(otype)
        out.append({
            "param": {"es": "Tipo de evento", "en": "Event type"},
            "value": otype, "level": "basic",
            "es": f"Es {kind['es']}.",
            "en": f"It is {kind['en']}."})

    hname = host.get("name") if isinstance(host, dict) else None
    if hname:
        out.append({
            "param": {"es": "Galaxia anfitriona", "en": "Host galaxy"},
            "value": str(hname), "level": "basic",
            "es": "La supernova no vive sola: explotó dentro de esta galaxia. "
                  "En tus imágenes la verás como un puntito de luz nuevo junto "
                  "a ella (o dentro).",
            "en": "The supernova does not live alone: it exploded inside this "
                  "galaxy. In your images it shows as a new pinpoint of light "
                  "next to it (or within it)."})

    dist = d.get("dist_mly")
    if dist:
        out.append({
            "param": {"es": "Distancia", "en": "Distance"},
            "value": f"{dist:.0f} Mly", "level": "basic",
            "es": f"Su luz salió de viaje hace {dist:.0f} millones de años: "
                  "la estrella que ves explotar murió cuando aquí aún no "
                  "existía nada parecido a nosotros.",
            "en": f"Its light set off {dist:.0f} million years ago: the star "
                  "you see exploding died long before anything like us walked "
                  "the Earth."})

    mag = d.get("mag")
    if mag is None:
        mag = sim.get("vmag")
    if mag is not None:
        try:
            mag = float(mag)
        except (TypeError, ValueError):
            mag = None
    if mag is not None:
        out.append({
            "param": {"es": "Brillo actual", "en": "Current brightness"},
            "value": f"{mag:.1f} mag", "level": "basic",
            "es": f"Magnitud {mag:.1f}: cuanto menor el número, más fácil la "
                  "captura. Las supernovas se desvanecen en semanas — cada "
                  "noche cuenta para la curva de luz.",
            "en": f"Magnitude {mag:.1f}: the lower the number, the easier the "
                  "catch. Supernovae fade away over weeks — every night counts "
                  "for the light curve."})

    # B7: didactic note — why multi-filter matters (the observer's real
    # workflow uses Clear + NIR because bands can behave differently,
    # and colour evolution helps classify the type — interview block 2/4).
    otype = (sim.get("otype") or d.get("otype") or "").strip()
    if otype and otype.lower().startswith(("sn i", "ii", "ib", "ic")):
        out.append({
            "param": {"es": "¿Por qué varios filtros?",
                      "en": "Why multiple filters?"},
            "value": "", "level": "didactic",
            "es": "Cada banda cuenta una historia distinta: el color "
                      "(p. ej. Clear − NIR) revela cómo cambia la "
                      "temperatura del estallido con el tiempo, y eso "
                      "ayuda a clasificar la supernova. "
                      "Seguirla en dos o más filtros vale la pena.",
            "en": "Each band tells a different story: the colour "
                      "(e.g. Clear − NIR) reveals how the explosion's "
                      "temperature evolves over time, and that helps "
                      "classify the supernova. Following it in two or more "
                      "filters is worth the effort."})

    disc = (d.get("disc_date") or "").strip()
    if disc:
        days = days_since(disc)
        ago_es = f" — hace {days} días" if days is not None and days >= 0 else ""
        ago_en = f" — {days} days ago" if days is not None and days >= 0 else ""
        out.append({
            "param": {"es": "Descubierta", "en": "Discovered"},
            "value": disc, "level": "basic",
            "es": f"Fecha de descubrimiento{ago_es}. Cuanto más joven la "
                  "supernova, más valioso es medirla: la curva temprana dice "
                  "cómo era la estrella que explotó.",
            "en": f"Discovery date{ago_en}. The younger the supernova, the "
                  "more valuable your measurement: the early curve tells what "
                  "the exploded star was like."})

    z = host.get("z") if isinstance(host, dict) else None
    if z is None:
        z = sim.get("z")
    if z is not None:
        try:
            z = float(z)
        except (TypeError, ValueError):
            z = None
    if z is not None:
        out.append({
            "param": {"es": "Corrimiento al rojo (z)", "en": "Redshift (z)"},
            "value": f"z = {z:.4f}", "level": "deep",
            "es": "La expansión del universo estira su luz un "
                  f"{z*100:.2f}%. De ese estiramiento sale la distancia de "
                  "la galaxia anfitriona.",
            "en": "The expansion of the universe stretches its light by "
                  f"{z*100:.2f}%. The host galaxy's distance comes from that "
                  "stretching."})
    return out


# ---------------- Exoplanet transit interpreter ----------------
# (object-card plan, subplan 3b: the transit card tells the event of
# the night AND the planet's story, one same table idiom)

def _hm(dt):
    # @args: dt - datetime or ISO-8601 string
    # @return: "HH:MM" string, or None
    import datetime as _dt
    if isinstance(dt, str):
        try:
            dt = _dt.datetime.fromisoformat(dt)
        except ValueError:
            return None
    if isinstance(dt, _dt.datetime):
        return dt.strftime("%H:%M")
    return None


_DISC_METHOD = {
    "transit": {"es": "tránsitos (viéndola parpadear)", "en": "transits (watching it blink)"},
    "radial velocity": {"es": "velocidad radial (el bamboleo de la estrella)", "en": "radial velocity (the star's wobble)"},
    "imaging": {"es": "imagen directa (una foto del propio planeta)", "en": "direct imaging (an actual picture of the planet)"},
    "microlensing": {"es": "microlente (un alineamiento cósmico de azar)", "en": "microlensing (a chance cosmic alignment)"},
    "timing": {"es": "cronometraje (cambios en pulsos o tránsitos de otros)", "en": "timing (shifts in pulses or in other transits)"},
}


def explain_transit(d, aperture_in=None):
    # Interprets an exoplanet transit: tonight's event first (start, end,
    # depth, duration, telescope verdict), then the planet's story.
    # @args: d - enriched data dict (Exoplanet Archive fields + the
    #        planner's "transit" event merged by enrich, ADR-027 pattern),
    #        aperture_in - the user's telescope aperture in inches (or None)
    # @return: list of dicts {"param", "value", "level", "es", "en"}
    out = []
    tr = d.get("transit") or {}

    ing, mid, egr = (_hm(tr.get(k)) for k in ("ingress", "mid", "egress"))
    if ing and egr:
        mid_es = f" El momento central ({mid} UTC) es cuando más luz tapa: planifica alrededor de ese instante." if mid else ""
        mid_en = f" Mid-transit ({mid} UTC) is when it blocks the most light: plan around that instant." if mid else ""
        out.append({
            "param": {"es": "Tránsito esta noche", "en": "Transit tonight"},
            "value": f"{ing} – {egr} UTC", "level": "basic",
            "es": f"El planeta cruza hoy el disco de su estrella entre las "
                  f"{ing} y las {egr} UTC.{mid_es}",
            "en": f"The planet crosses its star's disc tonight between "
                  f"{ing} and {egr} UTC.{mid_en}"})

    dur = tr.get("duration_h")
    if dur:
        out.append({
            "param": {"es": "Duración del tránsito", "en": "Transit duration"},
            "value": f"{dur:.1f} h", "level": "basic",
            "es": f"El cruce completo dura unas {dur:.1f} horas: es la sesión "
                  "mínima para ver la bajada y la subida de luz enteras, con "
                  "un margen fuera de tránsito para comparar.",
            "en": f"The full crossing lasts about {dur:.1f} hours: the minimum "
                  "session to watch the whole dimming and recovery, plus some "
                  "out-of-transit margin to compare."})

    depth = tr.get("depth_mmag")
    if depth:
        pct = (1.0 - 10.0 ** (-float(depth) / 2500.0)) * 100.0
        out.append({
            "param": {"es": "Profundidad", "en": "Depth"},
            "value": f"{depth:.1f} mmag ({pct:.1f}%)", "level": "basic",
            "es": f"La estrella pierde un {pct:.1f}% de su brillo "
                  f"({depth:.1f} milésimas de magnitud) mientras dura el "
                  "cruce. Cualquier cosa por debajo del 1% ya pide fotometría "
                  "cuidadosa: esto es exactamente lo que vas a medir.",
            "en": f"The star loses {pct:.1f}% of its brightness "
                  f"({depth:.1f} millimagnitudes) while the crossing lasts. "
                  "Anything under 1% already calls for careful photometry: "
                  "this is exactly what you are going to measure."})

    vmag = tr.get("v_mag")
    if vmag is None:
        vmag = d.get("mag")
    if vmag is not None:
        try:
            vmag = float(vmag)
        except (TypeError, ValueError):
            vmag = None
    if vmag is not None:
        out.append({
            "param": {"es": "Brillo de la estrella", "en": "Star brightness"},
            "value": f"{vmag:.1f} mag", "level": "basic",
            "es": f"La estrella madre brilla con magnitud {vmag:.1f}: cuanto "
                  "más brillante, más fotones por segundo y más fácil sale la "
                  "pequeña caída de luz del tránsito.",
            "en": f"The host star shines at magnitude {vmag:.1f}: the "
                  "brighter it is, the more photons per second and the easier "
                  "the tiny transit dip comes out."})

    min_in = tr.get("min_telescope_in")
    if min_in:
        if aperture_in:
            ok = float(aperture_in) >= float(min_in)
            verdict_es = ("Tu equipo llega de sobra: este tránsito es para ti."
                          if ok else
                          "Tu equipo se queda corto: con mucha paciencia quizá "
                          "roces la señal, pero lo sensato es dejárselo a "
                          "telescopios mayores.")
            verdict_en = ("Your telescope is up to it: this transit is yours."
                          if ok else
                          "Your telescope falls short: with a lot of patience "
                          "you might graze the signal, but the sensible call "
                          "is leaving it to bigger scopes.")
            out.append({
                "param": {"es": "Telescopio mínimo (el tuyo)",
                          "en": "Min. telescope (yours)"},
                "value": f"{min_in:.0f}″ / {float(aperture_in):.0f}″",
                "level": "basic",
                "es": f"ExoClock estima que hacen falta al menos {min_in:.0f}″ "
                      f"de apertura para medir esta caída de luz. {verdict_es}",
                "en": f"ExoClock estimates at least {min_in:.0f}″ of aperture "
                      f"are needed to measure this dip. {verdict_en}"})
        else:
            out.append({
                "param": {"es": "Telescopio mínimo", "en": "Min. telescope"},
                "value": f"{min_in:.0f}″", "level": "basic",
                "es": f"ExoClock estima un mínimo de {min_in:.0f}″ de apertura "
                      "para este tránsito. Configura tu telescopio en Ajustes "
                      "y te diré si llegas.",
                "en": f"ExoClock estimates a minimum of {min_in:.0f}″ of "
                      "aperture for this transit. Set up your telescope in "
                      "Settings and I will tell you whether you make it."})

    per = d.get("pl_orbper")
    if per:
        out.append({
            "param": {"es": "Su año", "en": "Its year"},
            "value": f"{per:.2f} d", "level": "deep",
            "es": f"Da una vuelta a su estrella cada {per:.2f} días "
                  "terrestres: por eso los tránsitos se repiten tan a menudo "
                  "y puedes planearlos con calendario.",
            "en": f"It laps its star every {per:.2f} Earth days: that is why "
                  "transits repeat so often and you can plan them with a "
                  "calendar."})

    radj = d.get("pl_radj")
    if radj:
        out.append({
            "param": {"es": "Tamaño del planeta", "en": "Planet size"},
            "value": f"{radj:.2f} Rjup", "level": "deep",
            "es": f"Radio de {radj:.2f} veces Júpiter (unas {radj*11.21:.0f} "
                  "Tierras). Los gigantes gaseosos tapan más luz: son los "
                  "favoritos para empezar en fotometría.",
            "en": f"Radius {radj:.2f} times Jupiter (about {radj*11.21:.0f} "
                  "Earths). Gas giants block more light: they are the "
                  "favourite starters in photometry."})

    mass = d.get("pl_bmassj")
    if mass:
        out.append({
            "param": {"es": "Masa del planeta", "en": "Planet mass"},
            "value": f"{mass:.2f} Mjup", "level": "deep",
            "es": f"Pesa {mass:.2f} veces Júpiter. Junto con el radio dice si "
                  "es un gigante hinchado o denso: una pista sobre su "
                  "atmósfera.",
            "en": f"It weighs {mass:.2f} Jupiters. Together with the radius "
                  "it tells whether it is a puffy or a dense giant: a clue "
                  "about its atmosphere."})

    dist_pc = d.get("sy_dist")
    if dist_pc:
        ly = float(dist_pc) * 3.26156
        out.append({
            "param": {"es": "Distancia", "en": "Distance"},
            "value": f"{dist_pc:.0f} pc", "level": "deep",
            "es": f"A {ly:.0f} años luz ({dist_pc:.0f} pársecs): la luz que "
                  "tapa el planeta salió de allí hace esos años.",
            "en": f"{ly:.0f} light-years away ({dist_pc:.0f} parsecs): the "
                  "light the planet blocks left there that many years ago."})

    method = (d.get("discoverymethod") or "").strip()
    year = d.get("disc_year")
    if method or year:
        how = _DISC_METHOD.get(method.lower(), {"es": method, "en": method})
        out.append({
            "param": {"es": "Descubrimiento", "en": "Discovery"},
            "value": f"{method} ({year})" if year else method,
            "level": "deep",
            "es": f"Descubierto en {year} por {how['es']}." if year else
                  f"Descubierto por {how['es']}.",
            "en": f"Discovered in {year} by {how['en']}." if year else
                  f"Discovered by {how['en']}."})

    oc = tr.get("oc_min")
    if oc is not None:
        try:
            oc = float(oc)
        except (TypeError, ValueError):
            oc = None
    if oc is not None:
        out.append({
            "param": {"es": "Deriva del calendario (O-C)", "en": "Timetable drift (O-C)"},
            "value": f"{oc:+.0f} min", "level": "deep",
            "es": f"El tránsito llega {oc:+.0f} min respecto a la efeméride "
                  "de referencia. Si la deriva crece, el calendario pide "
                  "repaso: tu medida de esta noche es justo la que lo "
                  "actualiza.",
            "en": f"Mid-transit arrives {oc:+.0f} min off the reference "
                  "ephemeris. If the drift grows, the timetable needs "
                  "revision: tonight's measurement is exactly what updates "
                  "it."})
    return out


# ---------------- HADS interpreter (ADR-034) ----------------

def explain_hads(d):
    # Interprets a HADS star: the session maths first (period, amplitude,
    # range, cycles tonight), then its story (instability strip, dwarf
    # Cepheids) and the monitoring-programme flags (P. Wils' legend).
    # @args: d - enriched data dict with a "hads" sub-dict (bundle star or
    #        tonight's planner values — the shapes differ, read defensively)
    # @return: list of dicts {"param", "value", "level", "es", "en"}
    out = []
    h = d.get("hads") or {}

    per = h.get("period_h")
    if per:
        out.append({
            "param": {"es": "Periodo", "en": "Period"},
            "value": f"{per:.2f} h", "level": "basic",
            "es": f"Cada {per:.2f} horas da un pulso completo de brillo: "
                  "caben varios ciclos en una sola noche.",
            "en": f"Every {per:.2f} hours it completes one full brightness "
                  "pulse: several cycles fit in a single night."})

    amp = h.get("amp")
    if amp is None and h.get("max") is not None and h.get("min") is not None:
        amp = h["min"] - h["max"]          # inverted magnitude axis
    if amp:
        out.append({
            "param": {"es": "Amplitud", "en": "Amplitude"},
            "value": f"Δ {amp:.1f} mag", "level": "basic",
            "es": f"Cambia {amp:.1f} magnitudes de pico a valle: lo verás "
                  "variar en tu propia curva de luz de esta noche.",
            "en": f"It swings {amp:.1f} magnitudes peak to peak: you will "
                  "watch it vary in your own light curve tonight."})

    if h.get("max") is not None and h.get("min") is not None:
        out.append({
            "param": {"es": "Rango de brillo", "en": "Brightness range"},
            "value": f"{h['max']:.1f}–{h['min']:.1f} mag", "level": "basic",
            "es": "Del máximo al mínimo. La fase actual es impredecible: "
                  "cuenta la mediana y la amplitud, no la hora del pico.",
            "en": "From maximum to minimum. The current phase is "
                  "unpredictable: the median and the amplitude matter, not "
                  "when the peak happens."})

    cyc = h.get("cycles")
    if cyc:
        fits = h.get("session_fits")
        fits_es = "" if fits is None else (
            " Los 2 ciclos recomendados caben de seguida." if fits else
            " ⚠ Los 2 ciclos recomendados no caben de seguida.")
        fits_en = "" if fits is None else (
            " The recommended 2 cycles fit back to back." if fits else
            " ⚠ The recommended 2 cycles do not fit back to back.")
        out.append({
            "param": {"es": "Ciclos esta noche", "en": "Cycles tonight"},
            "value": f"{cyc:.1f}", "level": "basic",
            "es": f"Caben {cyc:.1f} ciclos completos sobre tu límite local."
                  + fits_es,
            "en": f"{cyc:.1f} full cycles fit above your local limit."
                  + fits_en})

    modes = []
    if h.get("multiperiodic"):
        modes.append({"es": "multiperiódica", "en": "multiperiodic"})
    if h.get("non_radial"):
        modes.append({"es": "modos no radiales", "en": "non-radial modes"})
    if modes:
        txt = {"es": " + ".join(m["es"] for m in modes),
               "en": " + ".join(m["en"] for m in modes)}
        out.append({
            "param": {"es": "Modos de pulsación", "en": "Pulsation modes"},
            "value": txt["en"], "level": "basic",
            "es": f"Es {txt['es']}. Las HADS pulsan en el modo fundamental o "
                  "el primer armónico (ratio de periodos 0.76–0.78, diagrama "
                  "de Petersen); si es multiperiódica, obsérvala en noches "
                  "consecutivas para separar los modos.",
            "en": f"It is {txt['en']}. HADS pulsate in the fundamental mode "
                  "or the first overtone (period ratio 0.76–0.78, Petersen "
                  "diagram); when multiperiodic, observe on consecutive "
                  "nights to separate the modes."})

    pr = h.get("priority")
    if pr in ("period_change", "period_change_possible"):
        found = pr == "period_change"
        out.append({
            "param": {"es": "Prioridad del programa", "en": "Programme priority"},
            "value": "Priority!" if True else "", "level": "basic",
            "es": ("El seguimiento de Patrick Wils (VVS/AAVSO-VSX) le ha "
                   "encontrado cambios de periodo" if found else
                   "El seguimiento de Patrick Wils (VVS/AAVSO-VSX) sospecha "
                   "cambios de periodo") +
                  ": tu curva de esta noche cuenta doble.",
            "en": ("Patrick Wils' monitoring programme (VVS/AAVSO-VSX) has "
                   "found period changes" if found else
                   "Patrick Wils' monitoring programme (VVS/AAVSO-VSX) "
                   "suspects period changes") +
                  ": tonight's curve counts double."})

    if h.get("observed") is False:
        out.append({
            "param": {"es": "Aún no observada", "en": "Not yet observed"},
            "value": "—", "level": "basic",
            "es": "El programa de seguimiento aún no tiene ninguna medida de "
                  "esta estrella: serías de los primeros en registrarla.",
            "en": "The monitoring programme has no measurement of this star "
                  "yet: you would be among the first to record it."})

    out.append({
        "param": {"es": "Qué es", "en": "What it is"}, "level": "basic",
        "value": "HADS",
        "es": "Una δ Scuti de gran amplitud: pulsa en la franja de "
              "inestabilidad del diagrama HR, la misma zona donde reinan las "
              "cefeidas. La AAVSO las recomienda como primer objetivo de "
              "fotometría digital.",
        "en": "A high-amplitude δ Scuti star: it pulsates in the HR "
              "instability strip, the same region where Cepheids rule. The "
              "AAVSO recommends them as the first digital-photometry target."})
    out.append({
        "param": {"es": "Dato histórico", "en": "Historical note"},
        "value": "dwarf Cepheid", "level": "deep",
        "es": "Antes se llamaban «cefeidas enanas»: sus curvas en diente de "
              "sierra (subida rápida, bajada lenta) recuerdan a las cefeidas "
              "clásicas, pero pulsan en horas, no en días.",
        "en": "They were once called 'dwarf Cepheids': their sawtooth light "
              "curves (fast rise, slow decline) resemble classical Cepheids, "
              "but they pulsate in hours, not days."})
    return out
