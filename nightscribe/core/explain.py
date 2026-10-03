############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Classification and figure explainer module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# The single home of «what does this code or this figure mean» (ADR-058).
# NightScribe shows classifications (SN types, VSX types, spectral
# classes, discovery methods, NEOfixer priorities) and figures (magnitude,
# rate, depth, distance...) all over the place: the object card's sections,
# the KPI tiles' tooltips, the narrative hooks and the social posts. Before
# this module those explanations were duplicated or missing, and a bare
# code like «SN Ia» could reach the user with no explanation at all.
#
# Every taxonomy returns TWO densities, so the same knowledge serves a
# one-line hook and a full card section without repeating text:
#   {"short": {"es","en"}, "long": {"es","en"}}
# `short` is one sentence (hooks, tooltips, tweets); `long` is a
# mini-dossier (what it is, how it is recognised, subtypes, what it tells
# us, why the observer cares). Figures carry only `short`.
#
# Fallbacks are honest and always present: an unknown code never yields an
# empty string, it yields «we still cannot classify it», which is true and
# still teaches. The guard tests in tests/unit/test_explain.py pin both the
# known entries and the fallbacks.

def _p(es_short, en_short, es_long=None, en_long=None):
    # @args: the short pair and (optionally) the long pair
    # @return: the two-density entry every taxonomy function returns; the
    #          long falls back to the short when the caller gave only one
    return {"short": {"es": es_short, "en": en_short},
            "long": {"es": es_long or es_short, "en": en_long or en_short}}


def short(entry):
    # @args: entry - a dict from this module
    # @return: the one-sentence {"es","en"} pair
    return entry["short"]


def long(entry):
    # @args: entry - a dict from this module
    # @return: the mini-dossier {"es","en"} pair (falls back to short)
    return entry.get("long") or entry["short"]


# ---------------- Supernova / transient types ----------------

def sn_type(otype):
    # Decodes an SN/transient type string into a mini-dossier.
    # @args: otype - SIMBAD/Rochester/TNS type ("SN Ia", "II", "AT", ...)
    # @return: two-density entry (see module docstring)
    t = (otype or "").strip().lower()
    t = t[2:].strip() if t.startswith("sn") else t
    if t.startswith("ia") and not t.startswith(("iax", "iin")):
        return _p(
            "Una enana blanca que estalla por fusión termonuclear: brillo "
            "muy uniforme, la «vela estándar» que mide distancias cósmicas.",
            "A white dwarf blown up by thermonuclear fusion: a very uniform "
            "brightness, the 'standard candle' that measures cosmic "
            "distances.",
            "Una enana blanca que roba gas a una estrella compañera hasta "
            "rebasar su límite de masa y estallar por fusión termonuclear "
            "descontrolada. Como casi todas alcanzan un brillo parecido, se "
            "usan como «velas estándar» para medir distancias: con ellas se "
            "descubrió que el universo se expande aceleradamente. Su curva "
            "sube en semanas y decae de forma predecible, y las subclases "
            "(Ia normal, Iax más débil y rápida, Ia-CSM con interacción) "
            "cuentan qué había alrededor. Para ti: una Ia joven y bien "
            "muestreada en dos filtros vale oro para calibrar la relación "
            "brillo-declinación.",
            "A white dwarf that pulls gas from a companion until it crosses "
            "its mass limit and blows up in runaway thermonuclear fusion. "
            "Because nearly all reach a similar brightness, they are used as "
            "'standard candles' to measure distances: with them we discovered "
            "the accelerating expansion of the universe. Its light rises over "
            "weeks and fades predictably, and the subtypes (normal Ia, "
            "fainter and faster Iax, interacting Ia-CSM) tell what surrounded "
            "it. For you: a young, well-sampled Ia in two filters is gold to "
            "calibrate the brightness-decline relation.")
    if t.startswith("iax"):
        return _p(
            "Prima hermana de la Ia, más débil y rápida: posible explosión "
            "fallida de la enana blanca.",
            "A cousin of Ia, fainter and faster: a possible failed white-"
            "dwarf explosion.",
            "Una explosión termonuclear de enana blanca parecida a la Ia "
            "pero más débil y de evolución más rápida; se sospecha que la "
            "enana blanca no llegó a destruirse del todo (explosión parcial "
            "o fallida). Son más raras y difíciles de cazar, así que cada "
            "una bien medida ayuda a entender por qué unas Ia fallan y otras "
            "no. Para ti: la diferencia con una Ia normal se ve en los "
            "primeros días, de ahí el valor de la curva temprana.",
            "A white-dwarf thermonuclear explosion like a Ia but fainter and "
            "evolving faster; the white dwarf may not have been fully "
            "destroyed (a partial or failed explosion). They are rarer and "
            "harder to catch, so every well-measured one helps explain why "
            "some Ia fail and others do not. For you: the difference from a "
            "normal Ia shows in the first days, which is where the early "
            "curve pays off.")
    if t.startswith("iin"):
        return _p(
            "Tipo II con líneas de hidrógeno estrechas: el progenitor expulsó "
            "una capa de gas poco antes de colapsar.",
            "A Type II with narrow hydrogen lines: the progenitor shed a gas "
            "shell shortly before collapsing.",
            "El colapso de una estrella masiva que, poco antes de morir, "
            "expulsó una capa densa de gas; esa envoltura frena la onda y "
            "produce líneas de hidrógeno muy estrechas. La interacción con "
            "ese material mantiene su brillo alto y azul durante mucho "
            "tiempo, a veces con erupciones. Son laboratorios de cómo las "
            "estrellas pierden masa al final de su vida. Para ti: la "
            "fotometría multi-filtro capta el color de la interacción, que es "
            "lo que distingue una IIn.",
            "The collapse of a massive star that, shortly before dying, shed "
            "a dense gas shell; that envelope slows the shock and produces "
            "very narrow hydrogen lines. Interaction with that material keeps "
            "it bright and blue for a long time, sometimes with outbursts. "
            "They are laboratories of how stars shed mass at the end of their "
            "lives. For you: multi-filter photometry captures the colour of "
            "the interaction, which is what marks an IIn.")
    if t.startswith(("ib", "ic")):
        return _p(
            "Colapso de una estrella masiva que ya había perdido su envoltura "
            "de hidrógeno (y quizá su helio).",
            "The collapse of a massive star that had already shed its "
            "hydrogen (and maybe helium) envelope.",
            "El núcleo de una estrella masiva se derrumba cuando ya no puede "
            "sostener la fusión, pero sin la envoltura de hidrógeno (tipo Ib) "
            "ni de helio (tipo Ic) que tendría una II: un antepasado desnudo, "
            "quizá despojado por una compañera o por vientos. Su luz no "
            "muestra esas líneas y su curva decae de forma moderada. "
            "Conectan con las estrellas de Wolf-Rayet y con los brotes de "
            "rayos gamma. Para ti: seguir su color ayuda a ver la transición "
            "Ib/c.",
            "The core of a massive star collapses when it can no longer "
            "sustain fusion, but without the hydrogen (type Ib) or helium "
            "(type Ic) envelope a II would have: a stripped progenitor, "
            "perhaps robbed by a companion or by winds. Its light shows no "
            "such lines and its curve fades moderately. They link to "
            "Wolf-Rayet stars and to gamma-ray bursts. For you: tracking its "
            "colour helps see the Ib/c transition.")
    if t.startswith(("ii-p", "ii p")):
        return _p(
            "Colapso de una supergigante que conservó el hidrógeno: brillo en "
            "meseta durante semanas.",
            "The collapse of a supergiant that kept its hydrogen: brightness "
            "on a plateau for weeks.",
            "El colapso del núcleo de una supergigante que aún conservaba su "
            "hidrógeno; tras el estallido, una onda lenta en la envoltura "
            "mantiene el brillo casi plano (la meseta) durante unas cien "
            "jornadas antes del declive final. Es el tipo más común de "
            "supernova por colapso. La meseta es un reloj: su duración y su "
            "nivel dicen cuánta envoltura había y cómo se expande. Para ti: "
            "una II-P es ideal para una curva bien muestreada noche a noche.",
            "The core collapse of a supergiant that still kept its hydrogen; "
            "after the explosion a slow wave in the envelope holds the "
            "brightness almost flat (the plateau) for about a hundred days "
            "before the final decline. It is the most common core-collapse "
            "type. The plateau is a clock: its length and level tell how much "
            "envelope there was and how it expands. For you: a II-P is ideal "
            "for a well-sampled night-after-night curve.")
    if t.startswith(("ii-l", "ii l")):
        return _p(
            "Colapso de una supergigante con hidrógeno, pero sin meseta: "
            "decae en línea desde el inicio.",
            "The collapse of a hydrogen supergiant, but with no plateau: it "
            "fades linearly from the start.",
            "Como una II-P, pero con una envoltura más ligera: el brillo no "
            "se estanca, decae de forma casi lineal desde el principio. La "
            "comparación entre II-P y II-L mide cuánta masa queda en la "
            "envoltura del progenitor. La curva temprana decide el subtipo. "
            "Para ti: pocas medidas bien repartidas bastan para fijar la "
            "pendiente.",
            "Like a II-P but with a lighter envelope: the brightness never "
            "plateaus, it fades almost linearly from the start. Comparing "
            "II-P and II-L measures how much mass is left in the progenitor's "
            "envelope. The early curve decides the subtype. For you: a few "
            "well-spaced measurements fix the slope.")
    if t.startswith("ii"):
        return _p(
            "Colapso de una estrella masiva que conservaba su hidrógeno: la "
            "muerte clásica de una gigante.",
            "The collapse of a massive star that kept its hydrogen: the "
            "classic death of a giant.",
            "La muerte clásica de una estrella masiva: el núcleo colapsa y la "
            "envoltura, rica en hidrógeno, sale disparada. Según la envoltura "
            "y la época, su curva tiene meseta (II-P), decae en línea (II-L) "
            "o interactúa (IIn); el subtipo se afina con la fotometría. Es la "
            "vía por la que se forman estrellas de neutrones y agujeros "
            "negros. Para ti: cualquier medida temprana ayuda a fijar el "
            "subtipo.",
            "The classic death of a massive star: the core collapses and the "
            "hydrogen-rich envelope is blown off. Depending on the envelope "
            "and the epoch, its curve plateaus (II-P), declines linearly "
            "(II-L) or interacts (IIn); photometry refines the subtype. It is "
            "the path that forms neutron stars and black holes. For you: any "
            "early measurement helps fix the subtype.")
    if t.startswith(("sln", "slsn")):
        return _p(
            "Superluminosa: mucho más brillante que una supernova normal, con "
            "curva ancha de meses o años.",
            "Superluminous: far brighter than a normal supernova, with a "
            "broad curve lasting months or years.",
            "Una supernova extraordinariamente luminosa, decenas de veces más "
            "que una normal, con una curva ancha y lenta que dura meses o "
            "años. Las candidatas favoritas son el colapso de estrellas muy "
            "masivas con campos magnéticos intensos, o la interacción con "
            "material expulsado. Brillan tanto que se ven a distancias "
            "cosmológicas. Para ti: son raras; confirmar una y seguir su "
            "declive tiene un valor científico enorme.",
            "An extraordinarily luminous supernova, dozens of times brighter "
            "than a normal one, with a broad, slow curve lasting months or "
            "years. The favourite candidates are the collapse of very massive "
            "stars with strong magnetic fields, or interaction with ejected "
            "material. They shine so brightly they are seen at cosmological "
            "distances. For you: they are rare; confirming one and following "
            "its decline is scientifically huge.")
    if t.startswith("kilonova"):
        return _p(
            "No es la muerte de una estrella, sino la fusión de dos estrellas "
            "de neutrones: forja oro y platino.",
            "Not the death of a star but the merger of two neutron stars: it "
            "forges gold and platinum.",
            "No es una supernova: son dos estrellas de neutrones que se "
            "fusionan tras inspirarse en espiral. La colisión lanza neutrones "
            "que construyen elementos pesados (oro, platino) y produce un "
            "destello corto y rojizo, mucho más tenue y rápido que una "
            "supernova. Se detectan sobre todo por ondas gravitacionales. "
            "Para ti: la fotometría de una kilonova es contrarreloj, primeras "
            "horas.",
            "It is not a supernova: two neutron stars merge after spiralling "
            "together. The collision flings out neutrons that build heavy "
            "elements (gold, platinum) and makes a short, reddish flash, far "
            "fainter and faster than a supernova. They are found mostly "
            "through gravitational waves. For you: kilonova photometry is a "
            "race against the clock, first hours.")
    if t.startswith("i"):
        return _p(
            "Colapso de una estrella masiva sin rastro de hidrógeno en su luz.",
            "The collapse of a massive star with no hydrogen left in its "
            "light.",
            "El colapso del núcleo de una estrella masiva que ya no muestra "
            "hidrógeno en su espectro; según lo que le quede de helio y de "
            "envoltura, se afina entre Ib, Ic y otras variantes. Son "
            "progenitores desnudos, a menudo en sistemas binarios. Para ti: "
            "la clasificación fina depende del color y de la evolución "
            "temprana.",
            "The core collapse of a massive star that no longer shows "
            "hydrogen in its spectrum; depending on the helium and envelope "
            "left, it is refined into Ib, Ic and other variants. They are "
            "stripped progenitors, often in binary systems. For you: the fine "
            "classification depends on colour and early evolution.")
    if t.startswith(("cv", "nova")):
        return _p(
            "No es una supernova, sino una erupción termonuclear en la "
            "superficie de una enana blanca, mucho más tenue.",
            "Not a supernova but a thermonuclear eruption on a white dwarf's "
            "surface, far fainter.",
            "No destruye la estrella: es una erupción termonuclear en la "
            "superficie de una enana blanca que acumula hidrógeno de su "
            "compañera. Puede repetir cada años o décadas y su brillo sube y "
            "baja en semanas. Las novas recurrentes son laboratorios de la "
            "acreción. Para ti: medir su ascenso rápido y su máximo ayuda a "
            "fechar la erupción.",
            "It does not destroy the star: a thermonuclear eruption on a "
            "white dwarf's surface as it accretes hydrogen from its "
            "companion. It may repeat every years or decades and its "
            "brightness rises and falls over weeks. Recurrent novae are "
            "accretion laboratories. For you: measuring its fast rise and "
            "peak helps date the eruption.")
    return _p(
        "Una explosión estelar de tipo genérico: aún se está clasificando.",
        "A stellar explosion of generic type: still being classified.",
        "Una explosión estelar cuyo tipo exacto todavía se está clasificando "
        "a partir de su espectro y su curva de luz. La evolución del brillo y "
        "el color en los primeros días son justo lo que permite asignarle un "
        "tipo. Para ti: cada medida temprana ayuda a clasificarla.",
        "A stellar explosion whose exact type is still being classified from "
        "its spectrum and light curve. The evolution of brightness and colour "
        "in the first days is exactly what assigns it a type. For you: every "
        "early measurement helps classify it.")


# ---------------- Variable-star (VSX) types ----------------

_VAR_COMPONENTS = {
    "E": _p("Binaria eclipsante", "Eclipsing binary",
            "Dos estrellas que se cruzan por delante una de otra; el brillo "
            "cae en cada eclipse con un reloj perfecto. El subtipo (EA, EB, "
            "EW) describe la forma de la caída y cuánto se deforman entre sí. "
            "Son las reglas para medir masas y radios estelares. Para ti: los "
            "mínimos son muy predecibles, ideales para cronometrar.",
            "Two stars crossing in front of each other; the brightness dips "
            "at every eclipse with clockwork precision. The subtype (EA, EB, "
            "EW) describes the dip shape and how much they deform each other. "
            "They are the rulers for stellar masses and radii. For you: the "
            "minima are very predictable, ideal for timing."),
    "M": _p("Mira", "Mira",
            "Una gigante roja al final de su vida que pulsa lenta y "
            "violentamente, con cambios de varias magnitudes en meses. Su "
            "curva es asimétrica (sube rápido, baja despacio) y cada estrella "
            "es distinta, así que hay que seguir el ciclo. Las Mira alimentan "
            "de polvo al medio interestelar. Para ti: observa cerca del "
            "máximo previsto, cuando es más fácil y más informativo.",
            "A red giant at the end of its life, pulsing slowly and "
            "violently, swinging several magnitudes over months. Its curve is "
            "asymmetric (fast rise, slow decline) and each star is different, "
            "so the cycle must be followed. Miras feed dust to the "
            "interstellar medium. For you: observe near the predicted "
            "maximum, when it is easier and more informative."),
    "NR": _p("Nova recurrente", "Recurrent nova",
             "Un sistema binario con una enana blanca que acumula material y "
             "estalla cada pocas décadas; algunas han llegado a simple vista. "
             "Entre estallido y estallido se mantiene estable y conviene "
             "vigilarla. La recurrencia mide cuánta masa acretó y cuándo "
             "volverá. Para ti: las vigilias (como la de T CrB) detectan el "
             "próximo estallido antes que nadie.",
             "A binary system with a white dwarf that accretes material and "
             "erupts every few decades; some have reached naked-eye "
             "brightness. Between outbursts it stays stable and is worth "
             "watching. The recurrence measures how much mass was accreted "
             "and when it will return. For you: vigils (like the T CrB one) "
             "catch the next outburst before anyone else."),
    "N": _p("Nova", "Nova",
            "Una erupción en la superficie de una enana blanca que roba "
            "hidrógeno a su compañera. No destruye la estrella y puede "
            "repetirse; su brillo sube en días y decae en semanas. El estudio "
            "de su máximo y su color informa de la acreción. Para ti: avisar "
            "pronto del estallido y seguir el ascenso es lo más valioso.",
            "An eruption on the surface of a white dwarf accreting hydrogen "
            "from its companion. It does not destroy the star and may repeat; "
            "its brightness rises over days and fades over weeks. Studying "
            "its peak and colour informs the accretion. For you: flagging the "
            "outburst early and following the rise is the most valuable."),
    "UG": _p("Nova enana", "Dwarf nova",
             "La acreción sobre una enana blanca se vuelve inestable y "
             "produce erupciones repetidas cada semanas o meses, con subidas "
             "rápidas de varias magnitudes. Entre erupciones descansa en un "
             "nivel más bajo. Son laboratorios de discos de acreción. Para "
             "ti: su cadencia es alta, así que cada noche suma puntos a una "
             "serie larga.",
             "Accretion onto the white dwarf turns unstable and produces "
             "repeated eruptions every weeks or months, with fast rises of "
             "several magnitudes. Between eruptions it rests at a lower "
             "level. They are accretion-disc laboratories. For you: their "
             "cadence is high, so every night adds points to a long series."),
    "RCB": _p("R Coronae Borealis", "R Coronae Borealis",
              "Una supergigante pobre en hidrógeno que, de vez en cuando, "
              "expulsa nubes de carbono que se condensan en hollín y la "
              "ocultan: su brillo cae de golpe varias magnitudes y tarda "
              "meses en recuperarse. Los mínimos son irregulares e "
              "impredecibles. Para ti: la clave está en detectar el inicio "
              "del descenso, de ahí la vigilancia.",
              "A hydrogen-poor supergiant that now and then ejects carbon "
              "clouds that condense into soot and hide it: its brightness "
              "drops by several magnitudes at once and takes months to "
              "recover. The minima are irregular and unpredictable. For you: "
              "the key is catching the start of the decline, hence the "
              "vigilance."),
    "ELL": _p("Elipsoidal", "Ellipsoidal",
              "Una estrella deformada por la marea de su compañera cercana: "
              "al girar, muestra más o menos superficie brillante y el brillo "
              "oscila suavemente con cada vuelta. No hay eclipses, sino un "
              "bamboleo de forma. Sus curvas acotan la forma y la masa de las "
              "estrellas. Para ti: una serie continua de una noche capta "
              "varios ciclos.",
              "A star stretched by the tide of its close companion: as it "
              "rotates it shows more or less bright surface and the "
              "brightness wobbles gently each turn. There are no eclipses, "
              "just a shape wobble. Its curves constrain stellar shape and "
              "mass. For you: one continuous night series captures several "
              "cycles."),
    "DSCT": _p("δ Scuti", "δ Scuti",
              "Una pulsante de la franja de inestabilidad del diagrama HR, la "
              "misma región donde reinan las cefeidas, pero pulsando en horas "
              "en vez de días. Las hay multiperiódicas y con modos no "
              "radiales; el ratio de periodos (0.76–0.78) delata el modo. "
              "Para ti: caben varios ciclos en una noche, así que una curva "
              "completa es posible en una sola sesión.",
              "A pulsator of the HR-diagram instability strip, the same "
              "region where Cepheids rule, but pulsing in hours instead of "
              "days. Some are multiperiodic and show non-radial modes; the "
              "period ratio (0.76–0.78) betrays the mode. For you: several "
              "cycles fit in one night, so a full curve is possible in a "
              "single session."),
    "HADS": _p("HADS (δ Scuti de gran amplitud)", "HADS (high-amplitude δ Scuti)",
               "Una δ Scuti de gran amplitud: pulsa en horas con un cambio de "
               "brillo que se ve en tu propia curva de una noche. Son las "
               "favoritas de la AAVSO para empezar en fotometría digital. "
               "Para ti: una curva completa cabe en una sesión.",
               "A high-amplitude δ Scuti: it pulses in hours with a "
               "brightness change visible in your own one-night curve. They "
               "are the AAVSO's favourites for starting digital photometry. "
               "For you: a full curve fits in one session."),
    "GDOR": _p("γ Doradus", "γ Doradus",
               "Una pulsante de la franja de inestabilidad, como las δ Scuti, "
               "pero con periodos de alrededor de un día. La gravedad manda "
               "en sus pulsaciones. Para ti: varias noches de serie construyen "
               "su curva.",
               "A pulsator of the instability strip, like the δ Scuti, but "
               "with periods around a day. Gravity drives its pulsations. For "
               "you: several nights of series build its curve."),
    "SXPHE": _p("SX Phoenicis", "SX Phoenicis",
               "Una pulsante rápida de población vieja, prima de las δ Scuti "
               "pero con periodos de una a pocas horas. Para ti: una noche "
               "capta muchos ciclos.",
               "A fast pulsator of old population, a cousin of the δ Scuti "
               "but with periods of one to a few hours. For you: one night "
               "captures many cycles."),
}


def _named(entry):
    # @args: entry - a two-density entry
    # @return: the same entry with the short NAME prefixed to the long text,
    #          so a mini-dossier always opens by naming what it explains
    #          («Nova recurrente: un sistema binario...»). A fresh dict, so
    #          the shared table entries are never mutated.
    return {"short": entry["short"],
            "long": {"es": entry["short"]["es"] + ": " + entry["long"]["es"],
                     "en": entry["short"]["en"] + ": " + entry["long"]["en"]}}


def _var_component(code):
    # @args: code - a single VSX component ("E-DO", "UGSS", "M", ...)
    # @return: a two-density entry, named
    first = (code or "").strip().upper()
    if first.startswith("EA") or first.startswith("EB") \
            or first.startswith("EW") or first == "E" \
            or first.startswith(("E/", "E-")):
        return _named(_VAR_COMPONENTS["E"])
    if first.startswith("UG"):
        return _named(_VAR_COMPONENTS["UG"])
    if first in _VAR_COMPONENTS:
        return _named(_VAR_COMPONENTS[first])
    if first.startswith("RCB"):
        return _named(_VAR_COMPONENTS["RCB"])
    if first.startswith("DSCT"):
        return _named(_VAR_COMPONENTS["DSCT"])
    if first.startswith("HADS"):
        return _named(_VAR_COMPONENTS["HADS"])
    if first.startswith("GDOR"):
        return _named(_VAR_COMPONENTS["GDOR"])
    if first.startswith("SXPHE"):
        return _named(_VAR_COMPONENTS["SXPHE"])
    return _named(_p(
        "Estrella variable",
        "Variable star",
        "una estrella cuyo brillo cambia con el tiempo por pulsación, "
        "eclipses, erupciones o rotación manchada. El tipo exacto se afina "
        "con la curva de luz y el espectro. Para ti: una serie bien "
        "muestreada permite clasificarla y seguir su ciclo.",
        "a star whose brightness changes over time through pulsation, "
        "eclipses, eruptions or spotted rotation. The exact type is refined "
        "with the light curve and the spectrum. For you: a well-sampled "
        "series lets you classify it and follow its cycle."))


def variable_type(var_type):
    # Decodes a VSX variability type, composite types included.
    # @args: var_type - VSX type ("M", "NR+ELL", "E-DO", "UGSS", ...)
    # @return: two-density entry; a composite explains every component
    parts = [p for p in (var_type or "").split("+") if p.strip()]
    if not parts:
        return _var_component("")
    entries = [_var_component(p) for p in parts]
    if len(entries) == 1:
        return entries[0]
    # A composite type is two phenomena at once (e.g. NR+ELL): name both and
    # join their mini-dossiers, so the user is never left with half a code.
    es_short = " + ".join(e["short"]["es"] for e in entries)
    en_short = " + ".join(e["short"]["en"] for e in entries)
    es_long = " ".join(e["long"]["es"] for e in entries)
    en_long = " ".join(e["long"]["en"] for e in entries)
    return _p(es_short, en_short, es_long, en_long)


# ---------------- Asteroid spectral class ----------------

def spectral_class(spec):
    # Decodes an asteroid spectral class.
    # @args: spec - spectral class string ("C", "S-type", "X", ...)
    # @return: two-density entry
    first = (spec or "").strip()[:1].upper()
    common = ("La clase espectral sale del color y del espectro de la luz "
              "reflejada: dice de qué está hecho el objeto. El albedo asociado "
              "a cada clase es lo que convierte su brillo absoluto H en un "
              "tamaño estimado. Para ti: conocer la clase afina el tamaño y la "
              "naturaleza del objeto.",
              "The spectral class comes from the colour and spectrum of the "
              "reflected light: it tells what the object is made of. The "
              "albedo tied to each class is what turns its absolute "
              "brightness H into an estimated size. For you: knowing the "
              "class refines the object's size and nature.")
    table = {
        "C": ("carbonáceo: primitivo y oscuro, resto de los inicios del "
              "sistema solar",
              "carbonaceous: primitive and dark, a leftover from the early "
              "solar system"),
        "S": ("rocoso/silicatado: piedra con algo de metal",
              "rocky/silicaceous: stone with some metal"),
        "M": ("metálico: probablemente el núcleo de algo más grande que se "
              "rompió",
              "metallic: probably the core of something bigger that broke "
              "apart"),
        "X": ("composición incierta (clase X): hacen falta más datos",
              "uncertain composition (X class): more data needed"),
    }
    if first in table:
        es, en = table[first]
        return _p(f"Tipo {spec}: {es}.", f"Type {spec}: {en}.",
                  f"Tipo {spec}: {es}. " + common[0],
                  f"Type {spec}: {en}. " + common[1])
    return _p("de composición poco común", "of uncommon composition",
              "De composición poco común o aún por determinar. " + common[0],
              "Of uncommon or yet-undetermined composition. " + common[1])


# ---------------- Exoplanet discovery method ----------------

_DISC_METHOD = {
    "transit": _p(
        "tránsitos (viéndola parpadear)",
        "transits (watching it blink)",
        "Se descubrió porque el planeta cruza el disco de su estrella y la "
        "hace parpadear ligeramente: es el mismo efecto que medirás tú. "
        "ExoClock mantiene sus efemérides al día para que puedas planear el "
        "cruce. Para ti: los tránsitos se repiten con calendario, ideales "
        "para fotometría.",
        "It was found because the planet crosses its star's disc and makes "
        "it blink slightly: the very effect you will measure. ExoClock keeps "
        "its ephemeris current so you can plan the crossing. For you: "
        "transits repeat on a calendar, ideal for photometry."),
    "radial velocity": _p(
        "velocidad radial (el bamboleo de la estrella)",
        "radial velocity (the star's wobble)",
        "Se descubrió por el bamboleo que el planeta imprime a su estrella en "
        "el espectro (efecto Doppler). Da la masa, no el tamaño; combinado "
        "con los tránsitos da la densidad. Para ti: es la técnica que reveló "
        "los primeros júpiteres calientes.",
        "It was found through the wobble the planet imprints on its star's "
        "spectrum (the Doppler effect). It gives mass, not size; combined "
        "with transits it gives density. For you: it is the technique that "
        "revealed the first hot Jupiters."),
    "imaging": _p(
        "imagen directa (una foto del propio planeta)",
        "direct imaging (an actual picture of the planet)",
        "Se descubrió separando la luz del propio planeta de la de su "
        "estrella en una imagen. Solo funciona con planetas jóvenes, grandes "
        "y lejos de su estrella. Para ti: es la técnica más difícil.",
        "It was found by separating the planet's own light from its star's "
        "in an image. It only works for young, large planets far from their "
        "star. For you: it is the hardest technique."),
    "microlensing": _p(
        "microlente (un alineamiento cósmico de azar)",
        "microlensing (a chance cosmic alignment)",
        "Se descubrió por el aumento de brillo de una estrella de fondo "
        "alineada por azar con el sistema. Es un destello único que no se "
        "repite. Para ti: no es observable por seguimiento.",
        "It was found through the brightening of a background star aligned "
        "by chance with the system. It is a one-off flash that never "
        "repeats. For you: it is not follow-up observable."),
    "timing": _p(
        "cronometraje (cambios en pulsos o tránsitos de otros)",
        "timing (shifts in pulses or in other transits)",
        "Se descubrió por los cambios en los tiempos de pulsos o de otros "
        "tránsitos del sistema: un planeta invisible tira de lo que sí "
        "vemos. Para ti: mide con precisión, el reloj es la señal.",
        "It was found through shifts in the timing of pulses or of other "
        "transits in the system: an unseen planet tugs at what we do see. "
        "For you: measure precisely, the clock is the signal."),
    "astrometry": _p(
        "astrometría (el desplazamiento de la estrella en el cielo)",
        "astrometry (the star's shift across the sky)",
        "Se descubrió por el desplazamiento periódico de la estrella en el "
        "cielo, causado por el tirón del planeta. Da la masa y la órbita. "
        "Para ti: es la técnica de Gaia.",
        "It was found through the star's periodic shift across the sky, "
        "caused by the planet's pull. It gives mass and orbit. For you: it "
        "is Gaia's technique."),
}


def discovery_method(method):
    # Decodes an exoplanet discovery method.
    # @args: method - Archive discoverymethod string
    # @return: two-density entry
    key = (method or "").strip().lower()
    if key in _DISC_METHOD:
        return _DISC_METHOD[key]
    m = method or ""
    return _p(
        f"descubierto por {m}" if m else "método de descubrimiento no indicado",
        f"discovered by {m}" if m else "discovery method not given",
        f"Descubierto por {m}. Cada método entrega piezas distintas del "
        "sistema (tamaño, masa, órbita) y todos se complementan. Para ti: el "
        "método dice qué parte del planeta ya se conoce y qué puede aportar "
        "tu tránsito."
        if m else
        "El método de descubrimiento no está indicado en el catálogo. Cada "
        "método entrega piezas distintas del sistema y todos se "
        "complementan. Para ti: tu tránsito aporta el tamaño y el "
        "cronometraje.",
        f"Discovered by {m}. Each method delivers a different piece of the "
        "system (size, mass, orbit) and they all complement one another. For "
        "you: the method says which part is already known and what your "
        "transit can add."
        if m else
        "The discovery method is not given in the catalogue. Each method "
        "delivers a different piece of the system and they all complement "
        "one another. For you: your transit adds size and timing.")


# ---------------- NEOfixer priority ----------------

def neofixer_priority(priority):
    # Decodes a NEOfixer priority category.
    # @args: priority - "high"/"medium"/"low", "A"/"B"/"C" or similar
    # @return: two-density entry
    p = (str(priority) if priority is not None else "").strip().lower()
    if p in ("a", "high", "1", "urgent"):
        return _p(
            "Prioridad alta: la comunidad necesita esta medida cuanto antes.",
            "High priority: the community needs this measurement as soon as "
            "possible.",
            "Prioridad alta: la órbita de este objeto es tan reciente o tan "
            "incierta que puede perderse si nadie lo vuelve a medir pronto. "
            "Tu observación de esta noche, aunque sea breve, cuenta el doble. "
            "Para ti: si puedes, ve a por él primero.",
            "High priority: the object's orbit is so recent or so uncertain "
            "that it may be lost if nobody measures it again soon. Tonight's "
            "observation, however brief, counts double. For you: if you can, "
            "go for it first.")
    if p in ("b", "medium", "2", "normal"):
        return _p(
            "Prioridad media: útil, pero no urgente.",
            "Medium priority: useful, but not urgent.",
            "Prioridad media: la órbita ya tiene medidas suficientes para no "
            "perderse, pero cada observación nueva la afina. Es una buena "
            "segunda opción si el objeto de mayor prioridad no está "
            "disponible. Para ti: encájalo cuando puedas.",
            "Medium priority: the orbit already has enough measurements not "
            "to be lost, but each new one refines it. It is a good second "
            "choice when the higher-priority object is unavailable. For you: "
            "slot it in when you can.")
    if p in ("c", "low", "3", "routine"):
        return _p(
            "Prioridad baja: hay datos suficientes; tu medida suma sin prisa.",
            "Low priority: there is enough data; your measurement adds "
            "without urgency.",
            "Prioridad baja: la comunidad ya tiene medidas suficientes y el "
            "objeto no corre peligro de perderse. Tu observación sigue "
            "sumando, pero no es la que decide nada esta noche. Para ti: "
            "déjala para el final de la sesión.",
            "Low priority: the community already has enough measurements and "
            "the object is in no danger of being lost. Your observation still "
            "adds, but it is not what decides anything tonight. For you: "
            "leave it for the end of the session.")
    return _p(
        "Categoría de prioridad según NEOfixer.",
        "A priority category from NEOfixer.",
        "NEOfixer (Catalina/NASA) asigna a cada objeto una prioridad de "
        "seguimiento para tu sitio: alta si la órbita puede perderse, media "
        "si conviene afinarla, baja si ya hay datos de sobra. No es una "
        "medida de peligro, sino de cuánto necesita la comunidad que alguien "
        "lo mida. Para ti: ordena tu noche por ella.",
        "NEOfixer (Catalina/NASA) assigns each object a follow-up priority "
        "for your site: high if the orbit may be lost, medium if it is worth "
        "refining, low if there is already plenty of data. It is not a "
        "danger measure, but how much the community needs someone to measure "
        "it. For you: order your night by it.")


# ---------------- Solar activity ----------------

def flare_class(cls):
    # Decodes a solar X-ray flare class.
    # @args: cls - "X", "M", "C", "B", "A" (or with a value)
    # @return: two-density entry
    first = (str(cls) if cls is not None else "").strip()[:1].upper()
    table = {
        "X": ("La más potente: puede afectar a radio, GPS y satélites.",
              "The most powerful: it can affect radio, GPS and satellites."),
        "M": ("Potente, de las que producen auroras en latitudes medias.",
              "Powerful, the ones that produce auroras at mid-latitudes."),
        "C": ("Modesta y común: apenas se nota en la Tierra.",
              "Modest and common: hardly noticed on Earth."),
        "B": ("Muy pequeña, casi de fondo.",
              "Very small, nearly background."),
        "A": ("De fondo, sin interés práctico.",
              "Background level, no practical interest."),
    }
    if first in table:
        es, en = table[first]
        return _p(f"Clase {first}: {es}", f"Class {first}: {en}",
                  f"Clase {first}: {es} Las fulguraciones se ordenan de menor "
                  "a mayor como A, B, C, M y X (cada letra es diez veces la "
                  "anterior). Para ti: informan de la actividad solar, no "
                  "afectan a tu noche salvo por el brillo de fondo.",
                  f"Class {first}: {en} Flares are ordered from weakest to "
                  "strongest as A, B, C, M and X (each letter is ten times "
                  "the previous). For you: they report solar activity and do "
                  "not affect your night beyond background glow.")
    return _p("Clase de fulguración solar.",
              "Solar flare class.",
              "Las fulguraciones se ordenan de menor a mayor como A, B, C, M "
              "y X; cada letra es diez veces la anterior. Para ti: informan "
              "de la actividad solar.",
              "Flares are ordered from weakest to strongest as A, B, C, M "
              "and X; each letter is ten times the previous. For you: they "
              "report solar activity.")


# ---------------- Figures (short only) ----------------
#
# These are the «what does this number mean» lines the KPI tiles and the
# prose attach to a figure. They are deliberately one sentence: the number
# carries the value, the sentence carries the reading.

MAGNITUDE = {"short": {
    "es": "Magnitud: escala invertida, cuanto menor el número más brillante. "
          "A ojo se llega a ~6; un telescopio pequeño a ~12-14 y uno amateur "
          "serio a ~18-20.",
    "en": "Magnitude: an inverted scale, the lower the number the brighter. "
          "The naked eye reaches ~6; a small telescope ~12-14 and a serious "
          "amateur setup ~18-20."}}

RATE = {"short": {
    "es": "Velocidad aparente en el cielo: cuánto se desplaza por minuto; "
          "marca la exposición máxima antes de que el objeto salga movido.",
    "en": "Apparent sky rate: how far it moves per minute; it sets the "
          "longest exposure before the object trails."}}

ALTITUDE = {"short": {
    "es": "Altura sobre el horizonte: por debajo de unos 30° la atmósfera "
          "emborrona y atenúa la luz.",
    "en": "Altitude above the horizon: below about 30° the atmosphere blurs "
          "and dims the light."}}

DEPTH = {"short": {
    "es": "Cuánto se oscurece la estrella: 1 mmag es una milésima de "
          "magnitud; por debajo del 1% hace falta fotometría cuidadosa.",
    "en": "How much the star dims: 1 mmag is a thousandth of a magnitude; "
          "below 1% careful photometry is required."}}

PERIOD = {"short": {
    "es": "Tiempo que tarda en repetir su ciclo.",
    "en": "Time it takes to repeat its cycle."}}

EXPOSURE = {"short": {
    "es": "Segundos de integración por toma: más señal, pero también más "
          "riesgo de saturar o de que el objeto se mueva.",
    "en": "Seconds of integration per frame: more signal, but also more risk "
          "of saturating or of the object moving."}}

MOON = {"short": {
    "es": "Separación e iluminación de la Luna: cuanto más cerca y más "
          "llena, más brillo de fondo y peor para objetos débiles.",
    "en": "Moon separation and illumination: the closer and fuller, the more "
          "background glow and the worse for faint objects."}}

DISTANCE = {"short": {
    "es": "La distancia se mide en distancias lunares (LD), unidades "
          "astronómicas (UA), años luz (ly) o millones de años luz (Mly).",
    "en": "Distance is measured in lunar distances (LD), astronomical units "
          "(AU), light-years (ly) or millions of light-years (Mly)."}}

REDSHIFT = {"short": {
    "es": "El corrimiento al rojo z mide cuánto se ha estirado la luz por la "
          "expansión del universo; de ahí sale la distancia.",
    "en": "The redshift z measures how much the universe's expansion has "
          "stretched the light; the distance follows from it."}}

EPOCH = {"short": {
    "es": "Instante de validez de la posición (UT): en objetos que se mueven, "
          "una posición vieja ya no sirve.",
    "en": "Instant the position is valid for (UT): for moving objects an old "
          "position is no longer useful."}}

SIGMA = {"short": {
    "es": "σ es la incertidumbre (desviación típica): cuánto puede desviarse "
          "el valor real del medido.",
    "en": "σ is the uncertainty (standard deviation): how far the true value "
          "may stray from the measured one."}}

COMET_LAW = {"short": {
    "es": "M1 es el brillo absoluto del cometa y K1 cómo crece su actividad "
          "al acercarse al Sol; juntos predicen la magnitud.",
    "en": "M1 is the comet's absolute brightness and K1 how its activity "
          "grows as it nears the Sun; together they predict the magnitude."}}

SIZE = {"short": {
    "es": "El tamaño se estima desde el brillo absoluto H y un albedo "
          "supuesto: un objeto oscuro parece pequeño siendo grande.",
    "en": "Size is estimated from the absolute brightness H and an assumed "
          "albedo: a dark object looks small while being large."}}

ALBEDO = {"short": {
    "es": "Fracción de luz que refleja: los carbonáceos son oscuros (poca), "
          "los rocosos más claros.",
    "en": "Fraction of light it reflects: carbonaceous ones are dark (low), "
          "rocky ones brighter."}}

KP_INDEX = {"short": {
    "es": "El índice Kp mide la perturbación geomagnética de 0 a 9; por "
          "encima de ~5 hay auroras posibles en latitudes medias.",
    "en": "The Kp index measures geomagnetic disturbance from 0 to 9; above "
          "~5 auroras are possible at mid-latitudes."}}
