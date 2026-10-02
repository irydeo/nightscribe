# ADR-057: La ficha como dossier (hero, teselas KPI, secciones) / The object card as a dossier (hero, KPI tiles, sections)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-02 ·
**ejecutado / executed**: 2026-10-02 (suite unitaria green, i18n 2154
cadenas, 0 unfinished)

**Ver / See**: ADR-031 (la ficha unificada que esta ADR rediseña) ·
ADR-005 (los `.ui`; hero y panel son Designer, los widgets propios entran
por placeholder) · ADR-026 (la gramática visual: spine, chips sólidos,
composite) · ADR-041 (la barra de pestañas del proyecto; la Ficha se
exime aquí del contrato sin scroll)

## Español

**Contexto.** La ficha unificada (ADR-031) era un formulario: una línea de
gancho, una fila de bullets, una tabla única de parámetros y los gráficos.
El observador pidió un efecto «WoW»: más información según el tipo de
objeto, mejor estructurada, más clara, bonita y cuidada, integrada con la
gramática visual de Interfaz 1.x. Se pactó: primero la Ficha, con
respiración (scroll permitido) y evolución cuidada (misma paleta, misma
gramática), y Captura/Análisis en iteraciones siguientes.

**Decisión** (pactada con el observador, 2026-10-02): la ficha pasa de
formulario a **dossier del objeto**, vertical y con scroll permitido:

1. **Hero** (`gui/widgets/object_hero.py` + `gui/ui/object_hero.ui`):
   glifo del tipo a 44 px, nombre, chip de kind, chip PHA cuando aplica,
   designación secundaria (fullname SBDB, AUID), el gancho narrativo y la
   frase «por qué esta noche»; a la derecha, el **anillo de score 0-100**
   (`score_ring.py`) alimentado por `core/suggest.py`. El anillo solo
   aparece cuando hay señal de planificador (mag, ventana, altura...): un
   0 pelado diría «mal objeto» cuando la verdad es «no sabemos nada de
   esta noche»; ausente, no cero.
2. **Tira «Esta noche»** (`kpi_tile.py`): los números de la antigua fila
   de chips de captura como teselas valor-sobre-rótulo (mag, ventana,
   ventana segura, horas, altura máxima, Luna; por tipo: tasa y exposición
   máxima NEO, tipo y días SN, profundidad/mid/duración de tránsito,
   período/amplitud/ciclos HADS y variables). Tope de 6 teselas, ordenadas
   por peso de decisión; el aviso de seguridad «no cabe» encabeza la tira
   siempre. Las **alertas** (cambio de período, campaña, multiperiódica)
   siguen siendo píldoras: una bandera es una insignia, no una medida.
3. **Secciones temáticas** en vez de la tabla única: cada fila de
   `orbits.explain_*` lleva ahora `group`, y la ficha las agrupa en
   tarjetas tituladas (`section_card.py`): NEO en Órbita / Física /
   Solución y procedencia; SN en El evento / La galaxia anfitriona;
   tránsito en Esta noche / El planeta / La estrella; HADS en La
   pulsación / El programa / Qué es; variable en La variabilidad / Ficha
   de catálogo / La campaña. El conmutador «A fondo» filtra dentro de
   cada sección, y una sección que se queda vacía desaparece.
4. **Datos nuevos** que el modelo ya tenía y la ficha no mostraba:
   descubrimiento del cuerpo menor (SBDB), temperatura/metalicidad de la
   estrella y temperatura de equilibrio del planeta (Archive), cadencia y
   exposición recomendadas y cobertura del mes (HADS), AUID/constelación/
   bandas (VSX), la nota honesta H0 = 70 km/s/Mpc en la distancia de una
   SN, y las incertidumbres ± del Archive viajando en los valores.
5. **La tabla se va**: las secciones son listas de definición con QLabel,
   que envuelven y se dimensionan solas. La tabla necesitaba ~90 líneas
   de ajuste manual de filas porque Qt no auto-dimensiona una celda con
   wrap que abarca columnas; toda esa maquinaria (y sus ganchos de
   resize) desaparece.
6. **El glifo del tipo se comparte**: `widgets/kind_glyph.py` es ahora el
   único pintor (lo usaban las filas de Tonight y el masthead vía un
   método de MainWindow); el hero lo dibuja a 44 px escalando el mismo
   lienzo de 28 px.

**Consecuencias.** El contrato «ninguna pestaña hace scroll a 1360x860»
(`test_project_tabs_layout.py`) se relaja solo para la Ficha; Captura,
Análisis y Publicar lo mantienen. Los números viven en la tira KPI y las
alertas en su fila: los tests que leían chips leen ahora teselas o flags
según corresponda. i18n: 26 cadenas nuevas (ObjectHero + ObjectPanel),
.ts/.qm regenerados. El score se calcula sin db (sin feedback de
novedad): en la ficha de un proyecto activo eso es lo honesto.

## English

**Context.** The unified object card (ADR-031) was a form: a hook line, a
bullet row, one parameters table and the charts. The observer asked for a
"WoW" effect: more information per object type, better structured,
clearer, beautiful and cared for, integrated with the Interfaz 1.x visual
grammar. Agreed: the Object card first, with breathing room (scroll
allowed) and a careful evolution (same palette, same grammar); Capture and
Analysis follow in later iterations.

**Decision** (agreed with the observer, 2026-10-02): the card becomes the
object's **dossier**, vertical and allowed to scroll:

1. **Hero** (`gui/widgets/object_hero.py` + `gui/ui/object_hero.ui`):
   44 px kind glyph, name, kind chip, PHA chip when it applies, a
   secondary designation (SBDB fullname, AUID), the narrative hook and the
   "why tonight" phrase; on the right, the **0-100 score ring**
   (`score_ring.py`) fed by `core/suggest.py`. The ring only shows when
   there is planner signal (mag, window, altitude...): a bare 0 would say
   "bad object" when the truth is "we know nothing about tonight";
   absent, not zero.
2. **"Tonight" strip** (`kpi_tile.py`): the old capture-chips numbers as
   value-over-caption tiles (mag, window, safe window, hours up, max
   altitude, Moon; per kind: NEO rate and max exposure, SN type and age,
   transit depth/mid/duration, HADS and variable period/amplitude/cycles).
   Capped at 6 tiles, ordered by decision weight; the "does not fit"
   safety warning always leads the strip. **Alerts** (period change,
   campaign, multiperiodic) stay as pills: a flag is a badge, not a
   measurement.
3. **Themed sections** replace the single table: every `orbits.explain_*`
   row now carries a `group` key, and the card groups them into titled
   cards (`section_card.py`). The "In depth" toggle filters inside each
   section; an emptied section disappears.
4. **New data** the model already had but the card hid: small-body
   discovery date (SBDB), star temperature/metallicity and planet
   equilibrium temperature (Archive), HADS recommended cadence/exposure
   and monthly coverage, VSX AUID/constellation/bands, the honest
   H0 = 70 km/s/Mpc note on a SN's distance, and the Archive's ±
   uncertainties riding inside the values.
5. **The table is gone**: sections are QLabel definition lists, which
   wrap and size themselves; the ~90 lines of manual row fitting (Qt does
   not auto-size a wrapped cell spanning columns) and their resize hooks
   are deleted.
6. **The kind glyph is shared**: `widgets/kind_glyph.py` is now the
   single painter; the hero draws it at 44 px by scaling the same 28 px
   canvas.

**Consequences.** The "no tab scrolls at 1360x860" contract
(`test_project_tabs_layout.py`) is relaxed for the Object card only;
Capture, Analysis and Publish keep it. Numbers live in the KPI strip and
alerts in their own row: tests that read chips now read tiles or flags
accordingly. i18n: 26 new strings (ObjectHero + ObjectPanel), .ts/.qm
regenerated. The score is computed without db (no novelty feedback): on
an active project's card, that is the honest number.
