# AGENTS.md — NightScribe

*Guía del proyecto para personas y agentes de IA / Project guide for humans and AI agents.*

---

## Español

### Qué es esto

**NightScribe** es una aplicación de escritorio (GUI PySide6 + CLI) para observatorios
astronómicos amateur. Tres misiones:

1. **Planificar la noche**: sugiere los mejores objetivos (NEOs, cometas, candidatos PCCP,
   supernovas, tránsitos de exoplanetas) visibles desde el observatorio.
2. **Entender cada objeto**: traduce los parámetros orbitales y físicos a explicaciones
   precisas y divulgativas.
3. **Contarlo**: genera borradores de posts bilingües (ES/EN) + tuit + gráficos PNG listos
   para redes sociales.

Y entre planificar y publicar también **captura y reduce**: maneja CCDciel, y calibra,
apila y mide (astrometría, fotometría, períodos) en su editor FITS unificado.

Autor: Francisco José Calvo Fernández (Observatorio Irydeo, MPC Z41). Licencia GPL v3.

### Reglas de código (obligatorias)

- **Código siempre en inglés**: identificadores, comentarios, cabeceras. La documentación
  vive en `docs/` en español e inglés.
- **Cabecera en TODOS los ficheros `.py`** (copiar tal cual, adaptando el nombre del módulo):

```
############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - <Module name> module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################
```

- **Voz humana**: comentarios cortos sobre cada método con `# @args:` / `# @return:`,
  como en el proyecto hermano `saas/`. Nada de docstrings robóticos ni sobre-ingeniería.
  Los TODOs se escriben como `# TODO: ...` donde apliquen.
- **Código didáctico (regla permanente)**: quien lo lea tiene que entender **por qué**,
  no sólo qué. Cada bloque no obvio explica el motivo, la física o el fallo que evita;
  los números medidos se escriben en el comentario (lo que se ganó, lo que costó), y
  nada se deja «porque sí». Un comentario que no enseña nada sobra, y una decisión que
  no se explica es una decisión que se perderá: el código es también documentación.
- **Ningún código, clasificación o cifra sin explicación (regla permanente)**: al usuario
  nunca se le enseña un tipo («SN Ia», «NR+ELL»), una clase espectral, un método de
  descubrimiento ni una cifra (magnitud, MOID, profundidad, Kp) a secas: siempre va
  acompañado de qué significa y por qué importa. Las taxonomías y las cifras se explican
  una sola vez en `core/explain.py` (dos densidades: `short` para hooks/tooltips, `long`
  para fichas y posts); ningún módulo duplica ese conocimiento. Ver ADR-058.
- **Las ayudas no nombran el caso concreto (regla permanente)**: los tooltips y los
  textos de ayuda explican **por qué** y, como mucho, el **orden de magnitud**
  («pierde alrededor de un cuarto de magnitud», «una décima de magnitud»); nunca citan
  la visita, la fecha, el objeto ni el número de tomas del que salió la medida, ni
  ponen un ejemplo con nombre propio («T CrB 2026 eruption»). Las cifras exactas viven
  en el ADR y en los comentarios del código, que es donde se pueden revisar; la ayuda
  es para decidir, no para auditar. El guardián es `tests/unit/test_help_texts.py`.
- **Documentación en lenguaje natural**: nunca usar la raya «—»; escribimos con «:»,
  «,» y «;». La semirraya «–» queda reservada a los rangos numéricos (0–100).
- **Mantenible por personas**: funciones cortas, sin magia, y **numpy primero**:
  una biblioteca estándar (astropy, scipy, photutils) entra cuando aporta y su
  coste está justificado (ADR-060; reabre ADR-004).
- **La interfaz se define en `gui/ui/*.ui` (ADR-005)**: toda ventana, diálogo o pestaña
  lleva su estructura, textos y tooltips en Designer (cargado vía
  `gui/ui_loader.load_ui`, `<class>` = clase propietaria, `objectName` = atributo);
  el código cablea señales y rellena datos (combos con userData, contadores). Los
  widgets propios (canvas, histograma, filas ricas) nunca van al `.ui`: placeholder
  `QWidget` + `replaceWidget`.
- **Toda cadena visible en la GUI pasa por `self.tr()`** (ver CONTRIBUTING).
- **Toda consulta de red pasa por `core/db.py` (caché)**: nunca llamar a `requests` desde
  fuera de `core/sources/`.

### Estructura

```
nightscribe/
  __main__.py        # CLI: tonight | explore | post | solar | blink | history |
                     #   sequence (secuencia fotométrica + carta, ADR-042) |
                     #   inject (inyección/recuperación: hasta dónde llega de
                     #   verdad el pipeline) | project (gestión mínima) | gui
  config.py          # configuración persistente (observatorio, idioma, claves)
  paths.py           # rutas por SO (platformdirs)
  core/
    db.py            # SQLite: caché HTTP, listas, observaciones, settings
    coords.py        # alt-az, hora sidereal, crepúsculos (math puro)
    ephem_minor.py   # Sol/Luna/planetas (Schlyter) + kepler para cuerpos menores
    planner.py       # construye la lista de objetivos de la noche
    suggest.py       # score unificado 0-100 + Top N + frases "por qué esta noche"
    orbits.py        # familias orbitales + parámetros explicados
    explain.py       # la única casa de «qué significa este código o esta cifra»
                     #   (tipos de SN y VSX, clases espectrales, métodos de
                     #   descubrimiento, magnitudes): dos densidades, short para
                     #   hooks/tooltips y long para fichas y posts (ADR-058)
    kinds.py         # los tipos de objetivo (id, etiqueta, glyph, contexto) y
                     #   las frases de la ficha de cada uno
    project.py       # proyectos: registro, contexto, carpeta del proyecto y los
                     #   ficheros que cuelgan de él (project_files)
    followup.py      # visitas (sesiones) y puntos medidos: el CRUD de lo que
                     #   cuelga de un proyecto (ADR-045)
    hads.py          # HADS: catálogo híbrido (snapshot+sheet), merge, mat. de sesión
    variables.py     # variables: extremos VSX, HJD (Sol Schlyter), asesor de eventos
    campaign.py      # campañas 1:N ortogonales (CRUD, protocolo, due_campaigns,
                     #   project_signal, tonight_listable, signals_report — ADR-037)
    vigils.py        # vigilias de variables (ADR-037 SC4a): lista curada editable
                     #   (T CrB/R CrB), chequeo ZTF vs basal (caché propia 12 h)
    photometry_export.py  # reporte fotométrico: CSV + AAVSO EFF (TTL n/a, local)
    phototrans.py     # transformaciones Gaia->Johnson-Cousins (Riello 2021),
                      #   B-V directo/estimado, clase de color (ADR-042)
    photometry.py     # fotometría calibrada en una placa (pestaña Medir del
                      #   UFE): medida con guardas (meseta, techo explícito o
                      #   inferido del recorte de la propia placa), centroide
                      #   anclado al pico local robusto (local_sources: débiles
                      #   sobre galaxia), ZP por mediana+MAD, error CCD con
                      #   ganancia/RON (plan PLANS/ufe-photometry.md)
    compstars.py      # secuencias fotométricas: campo de catálogo, cruce VSX,
                      #   propuesta automática de comps con ventana de brillo
                      #   junto al objetivo (nunca las más brillantes del
                      #   campo: saturan), CSV (ADR-042)
    field_math.py     # proyección TAN de la carta, ticks de borde, escala,
                      #   anti-colisión de rótulos (compartido viz/widget, ADR-042)
    cameras.py        # presets de cámaras (perfil fotométrico): píxel, full well,
                      #   RON, oscuridad, régimen short/normal y linealidad
                      #   sugerida (datasheet; linealidad y tope de exposición
                      #   se miden por ganancia)
    calibration.py    # calibración de imágenes (ADR-061): biblioteca de masters
                      #   indexada (cámara/ganancia/temperatura/exposición/filtro),
                      #   receta declarativa (un dark ya incluye el bias), flat
                      #   normalizado, en memoria con export opcional
    track_stack.py    # track & stack (ADR-062, fase 2): ingesta con T_mid
                      #   (media exposición), solve del primer frame, WCS
                      #   compuesto por registro, posición del objeto por
                      #   frame y aviso de dithering
    astrometry.py     # medida astrométrica (ADR-062, fase 4): centroide
                      #   subpíxel (photutils) para el stack y por frame,
                      #   combinación por 1/σ², contraste de las dos vías,
                      #   presupuesto de error y magnitud (se omite sin
                      #   comparsas)
    astrometry_store.py # persistencia de la astrometría (ADR-062, fase 8):
                      #   astrometry_runs/points/frames, Undo por ejecución
    free_space.py     # liberar espacio (ADR-062, fase 9): mover los
                      #   originales de un run con éxito a procesados/ dentro
                      #   del proyecto (no borrar), registrar el movimiento y
                      #   poder restaurarlos; los calibrados se borran aparte
    findorb.py        # handoff a Find_Orb (ADR-062, fase 5.2): fichero de
                      #   observaciones, `fo` headless con entorno propio y
                      #   límite de CPU, y la decisión sobre sus residuos
    mpc_astrometry.py # generadores de reporte MPC (ADR-062, fase 6): ADES
                      #   PSV y 80 columnas, listón de envío (SNR >= 20)
    mpc_report.py     # validador y empaquetador del reporte MPC (ADR-022): el
                      #   mismo juez para lo que genera la app y para lo que
                      #   pega el observador (80 columnas o ADES PSV)
    series_measure.py # motor de serie (ADR-048): punto por frame con ZP por
                      #   frame atado por comparada, ensemble con veto MAD,
                      #   puertas que marcan y nunca borran, tiempo a media
                      #   exposición (MJD/HJD), agrupación en el dominio de la
                      #   medida, apertura óptima por noche (T3) y detrend
                      #   honesto multinoche a1·exp(a2·X)+a3 (T5)
    register.py      # registro de frames sin WCS/alineación (D44, por defecto
                      #   encendido): se quita el cielo, las estrellas votan la
                      #   transformación (traslación primero) y la calidad es
                      #   física (estrellas emparejadas + rms en px), numpy puro
    periodogram.py   # búsqueda de período (ADR-054): Lomb-Scargle generalizado
                      #   con media flotante + PDM + ventana espectral, FAP por
                      #   bootstrap con presupuesto de trabajo, ciclos cubiertos
                      #   y notas honestas
    gain.py          # ganancia y ruido de lectura medidos en las propias tomas
                      #   (par a la misma exposición: var(F1-F2) = 2·nivel/g +
                      #   2·RON²/g²; cajas de cielo robustas) y la cadena de
                      #   prioridad Ajustes → cabecera → medida (ADR-048 rev.)
    transit_fit.py   # modelo de tránsito con limb darkening cuadrático (numpy,
                      #   paridad <1e-5 vs batman) + ajuste LM con detrend
                      #   conjunto y errores OOT (plan fase 7; compuerta abierta)
    exoclock_export.py # envío manual a ExoClock (ADR-049): archivo HOPS de
                      #   3 columnas (JD_UTC de arranque + flujo + error) y
                      #   ExoClock_info.txt con Comments relleno (plan fase 8)
    solve.py          # dispatcher de resolución de placa: auto|astap|astrometry
                      #   (auto prueba ASTAP local y cae a nova; ADR-051)
    wcs_store.py      # persiste la WCS resuelta en la cabecera del FITS, atómica
                      #   (solve_save, por defecto sí; ADR-051 rev.)
    live.py           # modo en vivo (ADR-050): sondeo de carpeta, estabilidad
                      #   de tamaño, lotes por N tomas/T s por el mismo motor
                      #   (plan fase 10; opt-in, apagado por defecto)
    exotic_env.py     # entorno EXOTIC externo (orquestación, fase A): detectar
                      #   Python <=3.10, probar el import y crear el venv
    exotic_run.py     # ejecución headless de EXOTIC (fase C): `exotic -red
                      #   inits.json -ov`, log fusionado, cancelación y timeout;
                      #   localiza sus salidas (curva, parámetros, figura)
    exotic_import.py  # importa la salida de EXOTIC (fase D): curva a puntos
                      #   source="exotic" y parámetros T_mid/Rp/Rs al proyecto
    solar.py         # estado del Sol agregado
    transits.py      # tránsitos de exoplanetas (t0 + n*P, visibilidad, ventana de captura)
    exotic.py        # handoff EXOTIC: inits.json pre-rellenado (Track D; nunca embebido)
    enrich.py        # orquesta fuentes -> datos crudos de un objeto
    narrative.py     # prosa divulgativa ES/EN
    post.py          # plantillas -> post_ES / post_EN / tuit
    fits_io.py       # lector FITS mínimo (numpy, sin astropy — ADR-018)
    fits_annotate.py # FITS anotado AIJ-compatible: escribe copias y LEE
                     #   tarjetas ANNOTATE (UFE las pinta al cargar, ADR-044)
    chart_annotate.py # cajas de metadatos de las cartas (puro; reglas:
                      #   nombre siempre, posición/escala solo con WCS,
                      #   brillo solo calibrado — ADR-046)
    wcs.py           # WCS TAN mínimo (pixel<->cielo, escala, rotación)
    stretch.py       # motor de estiramiento: percentiles, lineal+gamma, invertir,
                     #   histograma, downscale 2×2 (ADR-044; blink_view re-exporta)
    blink.py         # blink de SN: resuelve nombre->coords, pareja alineada PS1-g
    viz/             # core/viz/sequence_view.py: la secuencia centrada del
                     #   track & stack (recortes del objeto con un solo
                     #   estirado, en GIF o montaje PNG; ADR-062, 5.4)
    sources/         # una clase/módulo por fuente externa (ver docs/DATA_SOURCES)
                     # + hads_sheet.py: libro HADS de P. Wils (Google Sheets XLSX,
                     #   TTL 12 h, parseo stdlib; ver ADR-034)
                      # + ccdciel.py: cliente JSON-RPC local del observatorio (ADR-030,
                      #   solo comanda con CCDciel abierto; lecturas cacheadas TTL 60s)
                      # + vsx.py: AAVSO VSX (subdominio vsx.aavso.org, TTL 7 d; ADR-035)
                      # + vizier.py: cone searches VizieR asu-tsv (Gaia EDR3,
                      #   APASS DR9, VSX B/vsx; TTL 30 d; ADR-042)
                      # + surveys.py: contexto ALeRCE/ZTF en curvas (TTL 30 d; ADR-035)
                      #   y última magnitud para vigilias (claves "vigils:", TTL 12 h)
                      # + astap.py: solver local de placa (binario del usuario,
                      #   -wcs en memoria, caché por hash; ADR-051)
                      # + aavso.py: canal editorial AAVSO — alertas del foro (JSON
                      #   Discourse) + campañas activas (TTL 12 h; ADR-037 SC4b)
                     #   + fotometría de la comunidad con token (vigilias brillantes)
                     # + mpc_obs.py: las observaciones publicadas del objeto (MPC
                     #   Observations API, o NEOCP si no está confirmado) para el
                     #   chequeo del run contra otras estaciones (TTL 6 h; ADR-062)
    journal.py       # Diario de observación: vista derivada por noche (ADR-036)
    attention.py     # «Necesita tu atención»: qué proyecto te necesita y por qué
                     #   (math local pura, sin red — ADR-038)
    skyevents.py     # calendario del cielo: motor de eventos 60 d, 100 % local
                     #   (fases, conjunciones, oposiciones por Δλ, eclipses
                     #   probables, lluvias — ADR-040)
    satellites.py    # tránsitos de galileanos + sombras sobre Júpiter para el
                     #   sitio del usuario (IAU WGCCRE + calibración Horizons,
                     #   ±10 min etiquetado — ADR-040)
   viz/               # matplotlib: style, orbit_view, sky_view, night_view,
                      # sun_panel, transit_view, sn_view, blink_view (GIF/MP4/PNG blink)
                      # + lightcurve_view (curva de luz, con las plantillas SN de
                      #   fondo cuando el proyecto es una supernova)
                      # + evolution_view (evolución SN) y motion_view (movimiento NEO —
                      #   la "prueba de fuego", Track C)
                      # + finder_view (carta de comparación: secuencia fotométrica
                      #   sobre DSS2 o el FITS del usuario — ADR-042)
                      # + phase_view (informe período+fase: periodograma con FAP
                      #   y curva plegada por noche — ADR-054)
    gui/               # app, main_window, workers (QThread), wizard, ui_loader,
                       #   ui/ (*.ui Designer);
                       # TRES pestañas: Tonight, Projects, Campaigns
                       # (ADR-019/035/036/040; ADR-043 pliega la pestaña
                       # Observatory en el paso Captura y manda el Sol y el cielo
                       # al menú Herramientas): el **Diario de observación**, el
                       # **Calendario del cielo** (skycal_dialog.py, ADR-040) y el
                       # **Editor FITS unificado** viven en el menú Herramientas;
                       # los chips de eventos del cielo viven en la cabecera de
                       # Tonight (clic → diálogo)
                       # ADR-044: el editor FITS unificado (ufe_dialog.py +
                       # ufe_state.py + ufe_host.py + widgets/ufe_image_view.py +
                       # widgets/histogram_widget.py) con sus pestañas:
                       # Fotometría (ufe_photometry_tab.py: comparar, medir y la
                       # serie), Blink (ufe_blink_tab.py), Anotar
                       # (ufe_annotate_tab.py), Calibración
                       # (ufe_calibration_tab.py, ADR-061) y Astrometría
                       # (ufe_trackstack_tab.py: el track & stack, ADR-062), más
                       # el modo manual del objeto débil
                       # (ufe_manual_stack_dialog.py, ADR-065); el panel izquierdo
                       # de la visita (ufe_visit_panel.ui: navegador de tomas +
                       # bloque EXOTIC de tránsito + el bloque de serie, ADR-048
                       # rev.) vive a la izquierda de la imagen, visible solo con
                       # visita; phase_dialog.py: período y fase del proyecto
                       # (ADR-054)
                       # ADR-038: la app habla primero — dashboard «Necesita tu atención»,
                       # prominencia a 3 niveles (primario / menú ⋯ / bloque colapsado),
                       # lenguaje llano + ayudas ⓘ, filas ricas
                       # ADR-045: el flujo del proyecto es Ficha → Captura →
                       #   Análisis → Publicación; la pestaña Análisis se
                       #   construye sobre el gestor de visitas
                       #   (widgets/visits_panel.py, para todos los tipos):
                       #   cada día es una visita y sus recursos cuelgan de
                       #   ella en project_files (session_id + meta);
                       #   el detalle de la visita vive en su propia ventana
                       #   no modal (VisitWindow, mismo módulo); el bloque de
                       #   astrometría MPC vive dentro de esa ventana (forma A:
                       #   sin visita no hay ni área de pegado), con aviso si
                       #   la fecha del reporte no cuadra con la de la visita;
                       #   la carta de comparación vive en Análisis
                       #   (seqchart_dialog.py + widgets/finder_widget.py,
                       #   picker interactivo de comps — ADR-042)
                       # + widgets/ (QGraphicsView chart widgets — ADR-029, sin matplotlib;
                       #   incl. timeline_widget: línea de tiempo del tránsito, Track D;
                       #   stack_strip: la tira de apilados de las observaciones, ADR-062;
                       #   las filas ricas project_row / campaign_row + sparkline, U2/U5;
                       #   y visits_panel: el gestor de visitas — ADR-045)
tests/
  unit/              # sin red
  functional/        # con red; verifican cada funcionalidad de punta a punta
docs/                # diseño, arquitectura, fuentes, scoring, órbitas, viz, ADRs
benchmarks/          # bancos de medida (track & stack, cero punto contra el
tools/bench/         #   catálogo, inyección/recuperación, combinación, flat):
                     #   de aquí salen las cifras de los comentarios y los ADR,
                     #   y no se envían con la app
website/             # la web (ADR-070): GENERADA, no escrita. La landing es el
                     #   README y el manual es docs/user, los mismos ficheros
                     #   que pinta la app; tools/build_site.py los convierte y
                     #   inyecta la paleta y los chips del tema; el HTML se
                     #   commitea y un test lo regenera y lo compara
installer/           # nightscribe.spec (PyInstaller) y nightscribe.iss (Inno Setup)
.github/workflows/   # windows-preview.yml: build Windows de preview (tests unitarios,
                     #   PyInstaller, zip portable + instalador Inno, pre-release
                     #   rodante preview-<rama>; push a main o manual)
                     # windows-tests.yml: la suite unitaria en Windows, en cada PR
                     # pages.yml: construye la web y la publica en GitHub Pages
                     #   (push a main o release/v0.1, y manual)
```

### Cómo trabajar

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest tests/unit     # rápido, sin red
.venv/bin/python -m pytest -n auto --dist loadfile tests/unit  # en paralelo (xdist)
.venv/bin/python -m pytest tests/functional  # con red, verifica funcionalidades
.venv/bin/python -m nightscribe gui    # arranca la GUI
```

### Decisiones

Toda decisión de arquitectura/diseño está en `docs/adr/` (ADR-000 a ADR-069, bilingües).
Antes de cambiar una decisión, lee el ADR; si la cambias, actualiza el ADR.

**Flujos y planes**: el flujo centrado en proyectos (UX v3, ADR-019 a ADR-022) está
implementado; el documento maestro con los flujos y las fases sigue siendo
`docs/WORKFLOWS.es.md`, y los planes de trabajo por tema viven en `docs/PLANS/`.
Léelos antes de escribir código nuevo.

---

## English

**NightScribe** is a desktop application (PySide6 GUI + CLI) for amateur astronomical
observatories. Three missions: **plan the night** (NEOs, comets, PCCP candidates,
supernovae, exoplanet transits), **understand each object** (orbital parameters translated
into accurate, engaging explanations), and **report it** (bilingual ES/EN social media
drafts + tweet + ready-to-attach PNG charts). And between planning and reporting it also
**captures and reduces**: it drives CCDciel, and calibrates, stacks and measures
(astrometry, photometry, periods) in its unified FITS editor.

### Code rules (mandatory)

- **Code is always English**: identifiers, comments, headers. Documentation lives in
  `docs/` in Spanish and English.
- **The header block above goes in EVERY `.py` file** (adjust module name).
- **Human voice**: short `# @args:` / `# @return:` comments above each method, in the
  spirit of the sibling project `saas/`. No robotic docstrings, no over-engineering.
- **Didactic code (permanent rule)**: whoever reads it must understand **why**, not just
  what. Every non-obvious block explains its reason, the physics, or the failure it
  prevents; measured numbers go in the comment (what was gained, what it cost), and
  nothing is left as "just because". A comment that teaches nothing is noise, and a
  decision that is not explained is a decision that will be lost: the code is
  documentation too.
- **No code, classification or figure without an explanation (permanent rule)**: the user
  is never shown a type ("SN Ia", "NR+ELL"), a spectral class, a discovery method or a
  figure (magnitude, MOID, depth, Kp) on its own: it always comes with what it means and
  why it matters. Taxonomies and figures are explained once in `core/explain.py` (two
  densities: `short` for hooks/tooltips, `long` for cards and posts); no module
  duplicates that knowledge. See ADR-058.
- **The help texts name no concrete case (permanent rule)**: tooltips and help strings
  explain **why** and, at most, the **order of magnitude** ("loses about a quarter of a
  magnitude", "a tenth of a magnitude"); they never cite the visit, the date, the
  object or the number of frames the measurement came from, nor give an example with a
  proper name ("T CrB 2026 eruption"). The exact figures live in the ADR and in the
  code's comments, which is where they can be checked; the help is for deciding, not
  for auditing. The guard is `tests/unit/test_help_texts.py`.
- **Docs in natural language**: never use the em dash ("—"); we write with ":", ","
  and ";". The en dash ("–") stays reserved for numeric ranges (0–100).
- **The interface is defined in `gui/ui/*.ui` (ADR-005)**: every window, dialog or tab
  carries its structure, texts and tooltips in Designer (loaded via
  `gui/ui_loader.load_ui`, `<class>` = owning class, `objectName` = attribute); code
  wires signals and fills data (combos with userData, counters). Custom widgets
  (canvases, histogram, rich rows) never enter a `.ui`: placeholder `QWidget` +
  `replaceWidget`.
- **Every GUI-visible string goes through `self.tr()`** (see CONTRIBUTING).
- **All network access goes through `core/db.py` (cache)**: never call `requests`
  outside `core/sources/`.

### Layout, workflow, decisions

See the Spanish section above (structure and commands are identical). All design
decisions live in `docs/adr/` (ADR-000 to ADR-069, bilingual). Read the ADR before
changing a decision; update it if you do.

**Flows and plans**: the project-centric flow (UX v3, ADR-019 to ADR-022) is
implemented; the master document with the flows and the phases is still
`docs/WORKFLOWS.md`, and the per-topic work plans live in `docs/PLANS/`. Read them
before writing new code.
