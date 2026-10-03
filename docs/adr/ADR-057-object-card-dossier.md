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

**Enmienda (2026-10-02, los parámetros y los gráficos, en una fila).** El
dosier apilaba los parámetros y, debajo, los gráficos. El observador pidió
que compartan fila, uno a la izquierda y otro a la derecha.

1. **Una fila, 50/50** (`row_body` en `object_panel.ui`): a la izquierda la
   columna de parámetros (la cabecera con «A fondo» y las `SectionCard`), a
   la derecha la columna de gráficos. La banda de la noche sigue a todo el
   ancho por encima y el CTA por debajo.
2. **Las columnas son widgets**, no layouts sueltos, y su visibilidad la
   manda el bloque que contienen (`_sync_body_columns`): un bloque oculto
   dentro de una columna visible dejaría la columna en pie ocupando su
   mitad para nada. Con los gráficos ocultos, los parámetros se quedan con
   todo el ancho, y al revés.
3. **Apilado por debajo de 660 px** de panel (`_BODY_STACK_W`): dos
   columnas de 390 px no caben en un panel estrecho y los gráficos tienen
   300 px de mínimo, así que se recortarían en vez de encogerse.
4. **Los gráficos arriba y el aire debajo**: cada columna termina en un
   espaciador expansivo. Medido con «A fondo»: un SN queda 384/384 con
   894 px de fila (los gráficos piden 689) y un NEO con 15 filas deja
   1244 px de columna para 529 de gráfico; el aire es el precio de no
   apilar dos bloques de altura muy distinta.
5. **Las etiquetas de las tarjetas envuelven** (`section_card.py`): el
   mínimo de un `QGridLayout` es la SUMA de los mínimos de sus columnas, y
   una etiqueta sin envolver mide su texto entero: «MOID (mínimo
   acercamiento de órbitas)» junto a un valor largo ponía el suelo de la
   ficha en 448 px, que es lo que impedía el 50/50.

**Consecuencias.** La ficha sigue pudiendo hacer scroll (el contrato de
ADR-057 no cambia) y sale más corta: un NEO con «A fondo» pedía 1785 px
apilado y pide 1377 en dos columnas. Los tests de la ficha leen la fila
(`row_body`), el colapso de una columna sola y el apilado por umbral.

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

**Amendment (2026-10-02, the parameters and the charts, in one row).** The
dossier stacked the parameters and, under them, the charts. The observer
asked for them to share a row, one left and one right.

1. **One row, 50/50** (`row_body` in `object_panel.ui`): on the left the
   parameters column (the header with "In depth" and the `SectionCard`s),
   on the right the charts column. The night band stays full width above
   and the CTA below.
2. **The columns are widgets**, not bare layouts, and the block inside
   decides whether they show (`_sync_body_columns`): a hidden block inside
   a visible column would leave the column standing, taking half the row
   for nothing. With the charts hidden the parameters get the whole width,
   and the other way round.
3. **It stacks below 660 px** of panel width (`_BODY_STACK_W`): two 390 px
   columns do not fit a narrow pane and the charts have a 300 px floor, so
   they would clip instead of shrinking.
4. **Charts at the top, air below**: each column ends in an expanding
   spacer. Measured with "In depth" on: a SN comes out 384/384 in an 894 px
   row (the charts ask for 689) and a NEO with 15 rows leaves a 1244 px
   column for a 529 px chart; the air is the price of not stacking two
   blocks of very different heights.
5. **The card labels wrap** (`section_card.py`): a `QGridLayout`'s minimum
   is the SUM of its columns' minimums, and an unwrapped label measures its
   whole text: "MOID (minimum orbit intersection distance)" next to a long
   value put the card's floor at 448 px, which is what kept the row from
   being the 50/50 it is meant to be.

**Consequences.** The card may still scroll (ADR-057's contract is
unchanged) and it comes out shorter: a NEO with "In depth" asked for
1785 px stacked and asks for 1377 in two columns. The card's tests read the
row (`row_body`), the single-column collapse and the stacking threshold.
