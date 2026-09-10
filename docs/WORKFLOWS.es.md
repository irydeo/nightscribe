# NightScribe — Flujos guiados (UX v3)

*[English version](WORKFLOWS.md)*

Documento maestro del rediseño centrado en proyectos. Decisiones: **ADR-019** (UX de
proyectos), **ADR-020** (horizonte y restricciones), **ADR-021** (exportación de
secuencias y efemérides), **ADR-022** (reporte MPC). Este documento describe **qué** se
construye y en **qué orden**; no hay código todavía (2026-08-24).

## 1. La pregunta del observador

«¿Qué puedo hacer esta noche — o ahora mismo?». La app responde sugiriendo los
objetivos más interesantes **bajo las restricciones reales del observatorio**, y de la
elección nace un **proyecto** que guía todo lo demás sin volver a preguntar nada.

## 2. Restricciones que el planificador debe respetar

| Restricción | Origen | Efecto |
|---|---|---|
| Magnitud límite | `limit_mag` en config (equipo) | **Híbrida (ADR-025)**: duro en SN/cometas/exoplanetas, aviso `⚠ mag>N` en NEO/PCCP sin descartar |
| Horizonte local | Fichero TheSkyX del usuario (ADR-020) | Altura mínima por azimut + margen de seguridad; fallback a `min_alt` plano |
| Luna | `ephem_minor` (ADR-009) | Aviso + penalización de score por separación/iluminación; **no** filtro duro |
| Viabilidad de sesión | `core/exposure.py` + horizonte | La ventana debe cubrir la duración de la sesión; se muestra «inicio seguro hasta HH:MM» |
| Escala de placa | Perfil de cámara (`pixel_um`, `focal_mm`) | Exposición máxima sin traza en NEOs |

## 3. Anatomía de un proyecto

Entidad persistente (ADR-019): tipo, objeto, estado (`active`/`done`/`archived`),
contexto JSON completo y tres pasos guiados. El contexto se captura al crear el
proyecto desde Esta noche (snapshot del objetivo: coords, mag, rate, ventana…) y se
enriquece en cada paso (secuencia exportada, FITS importado, medidas, posts).

**Pasos**: Plan & Captura → Procesado → Publicar (revisión 2026-09-06 de ADR-019: el
paso Captura se fundió en el Plan y gana el control real de CCDciel — ADR-030).

## 4. Flujo — supernova / transitorio

1. **Plan**: tarjeta con magnitud actual, edad, galaxia anfitriona, ventana sobre el
   horizonte real y «inicio seguro hasta HH:MM». El usuario define N tomas × exposición
   y filtro; la app comprueba que la sesión termina dentro del rango de seguridad.
2. **Captura**: exportar secuencia (NINA JSON / CCDciel / CSV) con nombre, coords J2000
   y tiempos; el fichero queda registrado en el proyecto. **Con CCDciel conectado**
    (ADR-030) también se puede: apuntar el telescopio, hacer un **ajuste astrométrico**
    (plate solve + corrección), enviar el plan (objeto, exposición, nº de tomas, filtro)
    e iniciar la captura desde la misma pestaña.
3. **Procesado** (externo): el usuario calibra/apila con sus programas; al volver,
   «Importar FITS resultado» — **sin preguntar objeto ni coordenadas** (ya están en el
   contexto) — y confirma con el blink, casado con PS1-g (pipeline ADR-018
   pre-rellenado), y exporta GIF/MP4/PNG con el watermark del observatorio.
4. **Publicar**: historia ES/EN + tuit con los **datos reales de la sesión** (fecha,
   N×t, filtro) + marca observado/posteado en el historial.

## 5. Flujo — NEO / candidato PCCP

1. **Plan**: tarjeta con velocidad aparente (″/min) y **exposición máxima sin traza**
   calculada con la escala de placa del equipo; número de tomas; ventana e «inicio
   seguro». Aviso si la sesión terminaría fuera de seguridad.
2. **Captura**: exportar **efemérides** a paso configurable para TheSkyX y Cartes du
   Ciel (formatos validados con importación real en la fase 5; CSV como base) +
   secuencia para el software de captura. Con CCDciel conectado (ADR-030): enviar el
   plan e iniciar la captura en vivo.
3. **Procesado**: el usuario mide fuera (Astrometrica u otro) y **pega** las medidas en
   el proyecto → validación (80-col/ADES, código MPC, designación) → fichero
   empaquetado listo para enviar al MPC (ADR-022). El envío lo hace el usuario.
4. **Publicar**: historia ES/EN + `orbit_view`/`sky_view` + observado/posteado +
   report a NEOfixer si hay clave configurada. La interpretación orbital (familia,
   MOID, tamaño desde H, próxima aproximación — reutiliza `enrich.py` + `orbits.py`)
   no es un paso: ya se pinta en la pestaña *Detalles* al abrir el proyecto.

## 6. Flujos posteriores

Cometas y tránsitos de exoplanetas reutilizan el mismo esqueleto de 3 pasos cuando los
flujos de SN y NEO estén asentados. Fuera de este rediseño inicial.

## 7. Hoja de ruta y punto de entrada

| Fase | Entregable | Estado |
|---|---|---|
| 1 | ADR-019…022 + este documento + DESIGN actualizado | **Hecho (2026-08-24)** |
| 2 | Fundación de restricciones: `core/horizon.py`, Luna, `core/exposure.py`, perfil de cámara en config, integración en planner/suggest, silueta en `sky_view`, tests | **Hecho (2026-08-24)** |
| 3 | Modelo de proyecto: migración db (`user_version` 0→1), `core/project.py`, máquina de pasos, tests | **Hecho (2026-08-24)** |
| 4 | GUI v3: 4 pestañas, hub Proyectos con stepper por tipo, blink contextual, tarjetas de Esta noche con «Crear proyecto» e «inicio seguro», Settings (Cámara/Horizonte/Sesión/Luna), i18n | **Hecho (2026-08-24)** |
| 5 | Exportadores: `core/sequence.py` (NINA/CCDciel/CSV) + efemérides (CSV + TheSkyX + CdC validados en importación real), tests | **Hecho (2026-08-24)**; CCDciel con formato real `.targets` (CONFIG v5) contra `docs/ccdciel_sequence_sample.targets` (**2026-09-06**) |
| 6 | `core/mpc_report.py` + paso en flujo NEO + subcomando CLI `project` mínimo + polish, i18n y docs finales | **Hecho (2026-08-24)** |

### 7bis. Rediseño de la pantalla de inicio (2026-08-25)

Motivación: la pantalla «Esta noche» no reflejaba la estética de la app, no
explicaba **por qué** se sugiere cada objeto (la frase «¿por qué esta noche?»
solo vivía en el tooltip) y el layout de mini-tarjetas en 4×2 se leía apretado.
Además la app no tenía tema global: tarjetas oscuras flotando sobre cromo
nativo claro.

| Fase | Entregable | Estado |
|---|---|---|
| A | Tema global oscuro: `gui/theme.py` (paleta + QSS cromo + `KIND_COLORS`), `apply_theme(app)` en `app.py`, ADR-026, `tests/unit/test_theme.py` | **Hecho (2026-08-25)** |
| B | «Esta noche» como **lista vertical de filas amplias**: nombre, «¿por qué?» visible, chips (mag/alt/ventana/luna/⚠), mini-barra de 4 segmentos del score, score 0-100, botón Start/Continue, podio metálico top-3, click-fila→Explorar, estados loading/vacío | **Hecho (2026-08-25)** |
| C | Tabla «Lista completa» rediseñada sobre el tema, doble-click→proyecto, regeneración i18n ES/EN de las cadenas nuevas, tests de humo | **Hecho (2026-08-26)** |

**Fase C (hecha, 2026-08-26)**: la tabla se conserva y ahora se comporta
como las filas amplias de encima — selección por fila (sin celdas 2×2, sin
números de fila), cada fila con un matiz de su tipo de objeto, el top 3
(orden de score) con el matiz más marcado como un podio discreto, nombre y
score en negrita con el color del tipo, cabecera/selección/hover del tema
global (ADR-026). El doble-click desde **cualquier** columna
crea/continúa el proyecto. Código en `nightscribe/gui/main_window.py`
(`_prepare_table`, `_fill_table`, `_table_start_project`) +
`tonight_tab.ui` (tooltip). Cadenas nuevas traducidas ES/EN y
`.ts`/`.qm` regenerados (ADR-014). Tests de humo en
`tests/unit/test_tonight_table.py` (patrón de `test_tonight_rows.py`).

### 7ter. Fase D — La vista de objeto como protagonista del hub de Proyectos (2026-08-26)

Motivación: al abrir un proyecto lo primero que se ve es el **Plan** (tomas ×
exposición), pero sin objeto no hay plan. La «carta de presentación» del objeto —
hoy solo dentro del diálogo modal *Explore…*— debe ser lo primero y siempre visible.
**No hay que construir nada nuevo**: toda la funcionalidad ya existe (enrich,
narrativa, órbitas, gráficos, exposición); toca **unificarla en un panel fijo** y
colocarla de forma atractiva e intuitiva, sin texto cortado (multilínea, todo visible).

**Decisiones pactadas (2026-08-26)**:

1. La vista de objeto es un **panel fijo por encima de las pestañas de pasos**
   (Plan/Captura/Procesado/Publicar) en el hub de Proyectos. No es un paso: no se
   salta y no se «marca hecho»; no entra en la máquina de pasos.
   *(Revisión 2026-08-27: en cambio es la **pestaña «Detalles»**, la primera y la
   que queda abierta al seleccionar el proyecto — misma garantía, el objeto siempre
   visible, pero ocupando toda la altura del panel. Revisión de nuevo 2026-08-28
   (ADR-019): la lista de pasos pasa a ser de 4 — ver revisión de ADR-019.)*
 2. Incluye (todo ya existe): **frase de enganche** + **bullets divulgativos** +
    **tabla de parámetros con explicación multilínea ES/EN** + **los gráficos**
    (órbita, cielo, campo, curva de luz — se ocultan los que no se pueden
    generar; si no hay ninguno, desaparece también el grupo) + **bloques de
    captura/ventana** (mag, tasa ″/min, exposición máx. sin traza si aplica,
    ventana inicio–fin, horas arriba).
3. Se **extrae a `gui/overview.py` un panel compartido** (`ObjectPanel`) que usan el
   hub de Proyectos **y** el diálogo *Explore…* del menú Herramientas: una sola
   fuente de verdad.
4. **No se toca** `core/` completo, la máquina de pasos (`core/project.py`,
   `_STEP_KEYS`) ni el panel *Plan* (su calculadora de exposición máxima sigue ahí).

**Piezas reutilizadas sin cambios** (con su hogar actual):

| Pieza | Origen |
|---|---|
| Enrich (red, caché) | `gui/workers.py` `ExploreWorker` → `core/enrich` |
| Frase de enganche, bullets | `core/narrative.hook`, `core/narrative.fact_bullets` |
| Parámetros + explicación ES/EN | `core/orbits.explain_elements`, `core/orbits.explain_neofixer` |
 | PNGs (órbita/cielo/campo/curva de luz) | `core/post.build_charts` (`core/post.py:172`) |
| Exposición máx. sin traza (NEO) | `core/exposure.plate_scale` + `max_exposure_no_trail` |
| Mag, tasa, ventana, horas | `project.context` (snapshot, `gui/main_window.py:1474`) |
| Clic en gráfico → zoom/export | `gui/main_window.py:74` `_ChartClickFilter` |
| Idioma de pares ES/EN | `orbits.pick` (patrón `MainWindow._txt`) |

**Estado actual que se reorganiza**: la presentación de objeto vive hoy solo en el
diálogo modal `gui/main_window.py:1504` (`_open_explore_dialog`,
`_dialog_explore_params`:1551, `_dialog_explore_charts`:1588,
`_render_object_charts`:1572), que se abre al pulsar el paso 4 *Análisis*
(`_build_analyse_tab`:1197). El hub de Proyectos muestra primero el *Plan* y una
cabecera `lbl_context` de una sola línea truncada (`gui/ui/projects_tab.ui:51`).

| Fase | Entregable | Criterio de aceptación | Estado |
|---|---|---|---|
| **D1** | `gui/overview.py`: `ObjectPanel` sin gráficos — estados *cargando / no encontrado / listo*, frase de enganche, bullets, tabla de parámetros con columna de explicación amplia (multilínea). `show(e, ctx=None)` + `loader` inyectable (offscreen sin red). Cabecera GPL, pares ES/EN | Panel construido offscreen; con `e` fake: hook visible, filas de parámetros con explicación; con `{}`: estado *no encontrado* | **Hecho (2026-08-26)** — `gui/overview.py` + `tests/unit/test_overview_panel.py` (9 tests offscreen, sin red) |
 | **D2** | `ObjectPanel` con rejilla **2×2 de gráficos** rellenos por `core/post.build_charts`; mensajes «por qué no» (hiperbólica / sin elementos / no confirmado) escalados al widget | Con `e` fake: 4 slots de gráfico o los mensajes de ausencia correctos; sin `e`: vacíos | **Hecho (2026-08-26)** — rejilla `orbit/sky/families/field` en `gui/overview.py` + 5 tests offscreen en `tests/unit/test_overview_panel.py` (14 en total, sin red; solo `field` tocaría red y queda en línea «por qué no») → **reviso 2026-08-27** — sin familias (ver abajo), slots `orbit/sky/field/transit`, tamaño `panel` (1200×675); lo que no se genera se omite en vez de línea «por qué no»; sin gráfico, el grupo desaparece → **2026-09-06** — los gráficos se agrupan en **pestañas** (`QTabWidget` en `gui/overview.py`, una por gráfico y título; con un solo gráfico la barra se auto-oculta y queda solo; adiós a la rejilla 2×2) |
| **D3** | `ObjectPanel` con **bloques de captura/ventana** desde `ctx`: mag, tasa ″/min, exposición máx. sin traza (solo neo/pccp con tasa + `pixel_um`/`focal_mm`), ventana inicio–fin + horas arriba; se omite lo que falta | Con `ctx` fake de neo: chips completos; de sn: sin tasa/exposición; no rompe con `ctx` vacío | **Hecho (2026-08-26)** — fila de chips en `gui/overview.py` (mag / tasa / exposición máx. sin traza / ventana / horas, desde `project.context`; tasa y exposición solo neo/pccp) + 5 tests offscreen en `tests/unit/test_overview_panel.py` (19 en total, sin red). Cadenas nuevas por `self.tr()` quedan para i18n de la fase D6 (patrón de D1/D2) |
 | **D4** | **Integración en el hub**: el hub inserta `ObjectPanel` entre `lbl_context` y `tabs_steps` (conservando la cabecera `lbl_context`). Al seleccionar proyecto → `loader` = `ExploreWorker` (mismo `fallback_target` de contexto), worker bajo `_keep`, cancel del worker en vuelo al cambiar de proyecto | Sin red: seleccionar proyecto muestra estado *cargando* y no revienta; la máquina de pasos, plan y botones siguen intactos; tests de humo offscreen | **Hecho (2026-08-26)** — `gui/main_window.py` construye `ObjectPanel` perezosamente en `_get_proj_panel()` (envuelto en `QScrollArea`, insertado antes de `tabs_steps`); `_project_selected` lo carga con `ctx` + `fallback_target` y `cancel()` al cambiar de proyecto (resultado tardío no cae sobre el siguiente) + `tests/unit/test_projects_hub.py` (6 tests offscreen, sin red) → **reviso 2026-08-27** — el panel vive ahora dentro de la pestaña **Detalles** (índice 0, nueva en `projects_tab.ui`), que es la que queda abierta al seleccionar el proyecto; prev/skip/done se desactivan ahí y next entra al paso 1 → **2026-09-06** — la lista del hub está **siempre al día sin «Actualizar»**: `on_refresh_projects()` se agenda con `QTimer.singleShot(0,…)` al abrir la app y se relanza en cada visita a la pestaña Proyectos (`_on_main_tab_changed`, `tabs.currentChanged` → índice 1); el botón **Refresh** queda como respaldo; el proyecto seleccionado se **conserva** al refrescar (se re-selecciona su `id` tras re-renderizar); +3 tests offscreen en `tests/unit/test_projects_hub.py` (carga al arranque, lista sin botón, se conserva la selección) |
| **D5** | **Diálogo *Explore…* sobre el panel compartido**: `main_window.py:1504` pasa a ser `ObjectPanel` + botón *Hacer post*; los `_dialog_explore_*` se delgan al panel; se conserva clic→zoom (el panel expone sus labels de gráfico) y `_project_explore`(paso 4) / `_tools_explore` | El diálogo *Explore…* del menú Herramientas idéntico en contenido; el paso 4 de NEO sigue abriéndolo pre-rellenado | **Hecho (2026-08-26)** — `_open_explore_dialog` ahora construye `ObjectPanel(for_post=True)` en una `QScrollArea` + botón *Create post* (señal `post_requested(name, fallback)` del panel → `_open_post_dialog` + cerrar diálogo); se eliminan `_dialog_explore*`/`_orbit_rows`/`_ChartClickFilter`/`_set_scaled_pixmap` (viven ya en `overview.py`); `_render_object_charts` queda solo para el flujo de post; `explore_tab.ui` huérfano se elimina; tests: 6 nuevos offscreen en `test_overview_panel.py` (botón post visible/oculto, señal `post_requested` con nombre + fallback, ignore en vuelo, cancel limpia) + 2 en `test_projects_hub.py` (integración `_explore_panel`) + 2 tests funcionales re-dirigidos al panel (orbit chart parábola + NEO no confirmado) |
 | **D6** | **i18n + verificación + docs**: `lupdate`/`lrelease` → `nightscribe_{es,en}.ts/.qm` (ADR-014); `pytest tests/unit` verde; esta sección con estados finales | Cadenas nuevas traducidas ES/EN; tests de humo en `tests/unit/test_overview_panel.py` (D1-D3) + humo del hub (D4) en verde | **Hecho (2026-08-26)** — `pyside6-lupdate` (fuentes `*/gui/*.py + */gui/ui/*.ui`) refresca los 2 `.ts` (+17 cadenas `ObjectPanel`, −21 obsoletas `ExploreTab`); 17 cadenas nuevas completadas manualmente ES/EN (EN passthrough, ES traducido); `pyside6-lrelease` → 2 `.qm` (306 strings, 0 unfinished); smoke i18n: `test_panel_strings_resolve_in_{spanish,english}` montan cada `.qm`, verifican `btn_post` / `grp_params` / `grp_charts` / headers de tabla / tooltips de chips → 234 tests en verde (sin red) |

**Revisión (2026-08-27)** — «Detalles» como protagonista, gráficos más limpios:

1. **Pestaña «Detalles» primero**: nueva en `projects_tab.ui` (índice 0 de
   `tabs_steps`). La carta de presentación del objeto — `ObjectPanel` — vive
   dentro de ella (`_get_proj_panel` la dobla allí) y es la pestaña que queda
   abierta al seleccionar un proyecto: toda la información del objeto a primera
   vista. El paso actual sigue marcado ● en su pestaña y se llega con *Next →*;
   *prev / Skip / Mark done* se desactivan sobre «Detalles» (no hay paso que
   actuar), *Next* sigue permitido (entra en Plan).
2. **Adiós al gráfico «¿Dónde vive?»**: `viz/families_view.py` eliminado (ya no
   tenía consumidores); `core/post.build_charts` deja de dibujarlo y
   `CHART_LABELS` pierde la entrada `families`. En el panel el slot pasa a ser
   **orbital / cielo / campo / curva de luz** (transitos de exoplanetas, ya
   cubierto por `transit_view`).
3. **Se omiten los huecos**: los slots que `build_charts` no puede generar se
   **ocultan** en vez de mostrar una línea «por qué no»; si no se genera ningún
   gráfico, el grupo completo desaparece. Los gráficos del panel usan el tamaño
   `panel` (1200×675, añadido a `style.SIZES`) para menos margen y más
   legibilidad en la ventana.
 4. **Ajuste de resolución de gráficos**: `Ajustes > Gráficos del panel` añade
    la opción *Al redimensionar la ventana* — **Rápido** (el gráfico se dibuja
    una vez al tamaño `panel` y se re-escala, el predeterminado) o **Más
    nitidez** (se redibuja a 2×, 2400×1350, para que los paneles grandes queden
    nítidos). Se guarda como `config["chart_zoom"]` (`"scale"` / `"re-render"`)
    y `ObjectPanel` lo lee antes de cada llamada a `build_charts`; cambiar el
    ajustes con un panel en pantalla lo redibuja (`rebuild_charts`).
    *(Retirado 2026-09-04: la opción `chart_zoom` y la pestaña Ajustes >
    Gráficos se eliminaron cuando llegaron los widgets vectoriales de ADR-029,
    que dibujan a resolución nativa. Ver `docs/adr/ADR-028` y el plan
    `docs/PLANS/approach-chart.md`, Slice 0.)*
5. **Visor de gráficos abierto ajustado**: al hacer click sobre un gráfico,
   `ChartViewer` se abre ajustado a la ventana — el diálogo adopta el
   aspecto de la imagen para que la vista por defecto la llene sin
   scrollbars (rueda para zoom / arrastre para desplazar / 1:1 sin
   cambios). El último tamaño de ventana que dejó el usuario se recuerda
   por gráfico (`config["chart_viewer_sizes"]`, restaurado en la siguiente
   apertura).
6. Tests: `tests/unit/test_overview_panel.py`, `test_projects_hub.py`,
   `test_style.py` (preset panel, override de tamaño, márgenes ajustados) y
   el nuevo `test_chart_viewer.py` (ajuste sin scrollbars, ajuste que sigue
   a la ventana, botones de zoom, memoria de tamaño por gráfico)
   actualizados al contrato nuevo (6 pestañas, panel dentro de la pestaña
   «Detalles», slots ocultos sin datos, grupo oculto sin gráficos).
   `pytest tests/unit` verde (247 tests, sin red).

**Reglas por fase**: una fase = un commit; cada fase deja la app funcional con sus
tests; no mezclar dos fases sin que la anterior esté verificada (regla de este
documento, §7). Tests offscreen con el patrón de `tests/unit/test_tonight_table.py`
(QApplication + `theme.apply_theme` + panel directo + payloads fake, sin red).

**PUNTO DE ENTRADA (para cualquier IA o humano que retome la Fase D)**:

1. Leer esta sección 7ter completa, en orden.
2. Empezar por **D1** (`gui/overview.py`), validar la base, y proseguir en orden
   D2 → D3 → D4 → D5 → D6.
3. **No tocar** `core/` ni la máquina de pasos; si surge que toca, detenerse y
   abrir ADR/decisión nueva antes de escribir el mínimo.
4. Cabecera GPL obligatoria en todo `.py` nuevo, código en inglés, cadenas
   visibles en la GUI por `self.tr()` y pares ES/EN por `orbits.pick` (o `tr()`
   para los estáticos). Idioma activo: `config.get("language")` (patrón
   `MainWindow._lang`, `gui/main_window.py:227`).
5. La Fase D está **independiente** de los próximos pasos sugeridos que siguen
   más abajo (horizonte real, formatos nativos, flujos de cometas/tránsitos).

Antes de la Fase D, el **PUNTO DE ENTRADA** histórico (proyecto UX v3, fases 1-6):

1. Leer, en este orden: `docs/adr/ADR-019`, `ADR-020`, `ADR-021`, `ADR-022` y este
   documento completo.
2. Las fases 2 y 3 ya están implementadas en la rama `feature/ux-v3-projects`:
   - Fase 2: `core/horizon.py`, `core/exposure.py`, helpers en `coords.py`, penalización
     Luna en `suggest.py`, integración en `planner.py`, silueta en `viz/sky_view.py`,
     config ampliada, mock `tests/fixtures/horizon_sample.txt` + tests.
   - Fase 3: migración `core/db.py` (`user_version` 0→1: tablas `projects`,
     `project_steps`, `project_files`; `observations` += `project_id`), `core/project.py`
     (modelo + máquina de pasos Plan→Captura→Procesado→Análisis→Publicar), tests.
   - Fase 4: GUI v3 — 4 pestañas (Esta noche · Proyectos · Solar · Historial),
     `projects_tab.ui` con lista + stepper, Explore/Post/Blink como diálogos modales
     contextuales (pre-rellenados desde proyecto), acceso ad-hoc desde menú Herramientas,
     tarjetas de Esta noche con «Crear proyecto» + ventana + Luna, Settings ampliada
     con grupos Cámara/Horizonte/Sesión/Luna, `sky_view` con horizonte real, i18n
     (.ts/.qm) actualizado.
   - Fase 5: `core/sequence.py` (exportadores NINA JSON / CCDciel `.targets` / CSV genérico
     para secuencias de captura) y `core/ephemeris.py` (generación vía Horizons +
     exportadores CSV / TheSkyX / Cartes du Ciel para efemérides). Panel «Capture plan»
     en el hub de Proyectos con campos frames/exposición/filtro y botones de exportación.
     Los formatos nativos de NINA/CCDciel/TheSkyX/CdC son puntos de partida que requieren
     validación contra las versiones del usuario en importación real.
   - Fase 6: `core/mpc_report.py` (validador de medidas pegadas en MPC 80-col o ADES
     PSV: formato, código de observatorio, designación; empaquetado del fichero para
     envío al MPC). Panel «MPC report» en el hub de Proyectos. Subcomando CLI
     `nightscribe project list|create|advance|show`. i18n completo (208 cadenas ES/EN).
     **Todas las fases completas.**
     El **horizonte de seguridad TheSkyX está completo** (E1+E2, 2026-08-28):
     (E1) `core/horizon.py` interpreta la exportación de límites de SkyX
     (`docs/limits-sample.hrz` = referencia canónica) además del texto `az alt`,
     con 16 tests de seguridad y rechazo de ficheros rotos.
     (E2) El horizonte **válido manda**: en Ajustes desactiva `min_alt`
     (tooltip explicativo) y `horizon_margin_deg` suma sobre él. El **rango seguro**
     es visible en toda la app (ADR-020): `planner.safe_window_for` calcula span
     seguro + `best_time` + `latest_safe_start`; `sky_view` somorea el span y marca
     «empezar hasta HH:MM»; las tarjetas de *Esta noche* y el hub del proyecto
     muestran chip verde «⊕ HH:MM–HH:MM · ≤ HH:MM» ochip rojo «⚠ no cabe» cuando la
     sesión planificada no encaja; la prosa ES/EN incluye la ventana y su aviso
     («NO forzar el equipo»). 313 tests unitarios en verde.
   Los **formatos nativos de CCDciel** ya son reales: `export_ccdciel` escribe la lista
   `.targets` (CONFIG Version="5") fijada contra una exportación real del usuario
   (`docs/ccdciel_sequence_sample.targets`, 2026-09-06), con pasos **Light + Dark + Bias**
   (calibración configurable en la pestaña Captura del proyecto) y la ventana rise/set
   por defecto que CCDciel recalcula con su configuración del observatorio. **NINA** y
   **CSV genérico** siguen siendo puntos de partida que requieren validación contra las
   versiones del usuario en importación real (ADR-021).

  **Próximos pasos sugeridos** (fuera del rediseño inicial):
  - **`ApproachChart` (plan 2026-09-04)**: carta vectorial animada geocéntrica
    (Tierra / Luna de referencia) como 5º slot del grid del panel. El plan
    completo está en `docs/PLANS/approach-chart.md`.
  - *(Hecho 2026-08-28: el horizonte TheSkyX real ya se interpreta y manda sobre `min_alt` — E1+E2 arriba.)*
 - **Icono lunar real (2026-08-27)**: `gui/moon_icon.py` compone el disco de
   la Luna (`assets/moon_disk.png`, foto CC BY-SA 3.0 — `assets/ATTRIBUTION.txt`)
   con el terminador por geometría exacta (`r·cos E`), creciente a la derecha /
   menguante a la izquierda, según `ephem_minor.moon["elong_deg"]`. Sustituye el
   % de la cabecera de *Tonight* (tooltip: % ahora vs. al amanecer + por qué varía
   en la misma noche) y el emoji del almanac de *Solar*. Fallback a disco plano
   gris si falta el asset. 8 tests offscreen, sin red.
- Validar los formatos de exportación de secuencias y efemérides contra software real.
- Añadir flujos para cometas y tránsitos en el mismo esqueleto de 4 pasos.
- Probar la GUI a fondo y refinar la UX del stepper y los diálogos contextuales.
4. Reglas vigentes: código en inglés con cabecera GPL y comentarios `# @args:`,
   cadenas de GUI por `self.tr()`, red solo desde `core/sources/` vía `core/db.py`,
   documentación bilingüe (ADR-013), tests unitarios por módulo + funcionales de flujo.

### 7quater. Filtro de tipo de objeto sobre la pestaña «Esta noche» (2026-08-30)

Motivación: el filtro de tipo (NEO / SN / CMT / PCCP / TRN / ALT) vivía hoy solo
dentro de la **tabla colapsada** (cascada `grp_list / cmb_filter`), a la altura del
piano: las **filas amplias** del grid superior y el **podio** (anillo / color más
intenso) siempre se montaban sobre *todos* los objetivos de la noche, mezclando
clases. El observador no puede decirle a la app «hoy solo quiero ver supernovas»
ni «deja de mostrar cometas». **K1** sube el filtro a la cabecera y lo hace válido
para la vista entera (filas + tabla); **K2** convierte el tipo mostrado en una
preferencia permanente (lista blanca) en Ajustes.

**Decisiones pactadas (2026-08-30)**:

1. **Un solo filtro en la cabecera** (K1). El `cmb_filter` sale de `grp_list` y se
   instala en la fila de `Tonight` (junto a `lbl_context` y `lbl_moon`). Al
   cambiarlo, **ambas vistas se actualizan a la vez**: el grid recalcula sus filas
   con el tipo elegido **y** su podium sobre **lo visible** (los 3 primeros del
   conjunto filtrado, no de la noche completa), y la tabla se repone con las
   columnas propias del tipo (`TABLE_COLS[kind]`). Fuente de verdad única:
   `MainWindow._visible_targets()` (whitelist + filtro); grid y tabla la invocan.
2. **Lista blanca de tipos habilitados** en Ajustes (K2). Se añade
   `config["enabled_kinds"]` (defecto = 6 tipos) y un grupo «Tonight: object kinds»
   en `tab_observing` con 6 checkboxes (NEO, SN, CMT, PCCP, TRN, ALT). Al pulsar
   *Guardar*, el combo **solo muestra los tipos habilitados** + «All»; si el tipo
   activo acaba de deshabilitarse, cae a «All»; si la whitelist creció, el combo
   crece también. «All» significa **todos los tipos habilitados**, no todos los de
   la noche.
3. **`core/` no se toca**: toda la filtración vive en `gui/main_window.py` —
   `config.py` (defaults), `ui/tonight_tab.ui` (header combo), `ui/settings_dialog.ui`
   (grupo kinds), `main_window.py` (`_rebuild_kind_filters`, `_enabled_kinds`,
   `_visible_targets`, `_apply_kind_filter`). `suggest.top_n` sigue diversificando;
   `enabled_kinds` solo corta *lo que se muestra* en la pestaña, nunca el scoring.
4. **Persistencia**: `config["tonight_kind"]` ("" = All) se escribe en cada cambio
   del combo y se restaura al arrancar si sigue en la whitelist. No hay un nuevo
   ADR: es una decisión de UX local sobre el plano ya documentado en
   ADR-019/ADR-026 (fuente única de `KIND_LABELS` / `KIND_COLORS`).
5. **Tests**: `tests/unit/test_tonight_kinds.py` (offscreen): combo en la
   cabecera con los 7 items (All + 6), grid y tabla acotados al tipo, podium
   recalculado sobre lo visible, persistencia de `tonight_kind`, whitelist que
   recorta/crece el combo, fallback a «All» al deshabilitar el tipo activo.
   `pytest tests/unit` verde.

 ### 7quinquies. Tope «mejores por tipo» + anillo best-of-kind (K3, 2026-08-30)

 Motivación: con K1+K2 la «noche» puede traer 15 NEOs del NEOfixer, 90 SNs
 del Rochester, 15 cometas del COBS… y el grid los pintaba todos a la vez
 (muro de una sola clase que abocaba a filtrar por tipo para ver algo).
 **K3** introduce el tope *mejores de cada tipo* (variante configurable,
 no agrupada) directamente en el grid, y el **anillo** pasa a caer sobre el
 *mejor de cada tipo visible* — no sobre «los 3 primeros del conjunto».

 **Decisiones pactadas (2026-08-30)**:

 1. **`core/suggest.best_per_kind(scored, n)`**: entrada ya puntuada y
    ordenada por score global (la que devuelve `top_n`); mantiene como
    máximo `n` de cada tipo (defecto `config["best_per_kind_n"] = 5`,
    configurable 1..50); `n<=0` = sin tope. Devuelve `(grid, best_ids)`:
    `grid` conserva el **orden por score global** (no agrupado por tipo),
    y `best_ids` = el id del **mejor de cada tipo presente** (el anillo).
 2. **Grid «Esta noche»** (`_build_suggestion_grid`): filtra por
    «visible» (K1+K2), aplica `best_per_kind`, y pinta el resultado. El
    anillo cae al **mejor de cada tipo visible** (no a los i<3), y el
    botón de estado sigue en la derecha. El grid se reconstruye al
    cambiar `best_per_kind_n` desde Ajustes.
 3. **Tabla «Esta noche»**: **sin cambios** — la lista completa (los 6
    grupos, los scores, los filtros de observación) sigue siendo *el
    conjunto completo*; solo cambia su *orden* y su *tinte* (ya era
    best-per-rank 0/1/2), que ahora también es top-3 *global* sobre lo
    visible. `suggest.top_n` (CLI) no se toca.
 4. **Planner `_comet_targets`** (bottleneck): las 15 ephémerides
    Horizons **van en paralelo** (pool de ~4 workers, los `cobs` siguen
    siendo los 15 más brillantes). `n_comets=15` se conserva.
 5. **Config**: `config["best_per_kind_n"] = 5` (nuevo, default 5) y
    `ui/settings_dialog.ui` `tab_observing` → fila `spn_best_pk`
    (SpinBox 1..50) con traducción ES/EN.
 6. **Tests**: `tests/unit/test_best_per_kind.py` (6 casos: tope, mejor
    por tipo, sin tope, orden, id vacío, entrada vacía);
    `test_tonight_rows.py` actualizado — *ahora* toda fila del fixture
    lleva anillo (un por tipo ⇒ best-of-each);
    `test_tonight_kinds.py` actualizado — el pccp (rank 4 global) SÍ
    lleva anillo al cambiar al filtro «pccp» (y SÍ lo conserva en
    «All»). `pytest tests/unit` verde (345 tests, 13.1 s).
 7. **Idiomas**: 346 cadenas (2 nuevas), 0 unfinished.

 **Punto de entrada (para cualquier IA o humano que retome esta pantalla)**:

1. Leer esta sección 7quater, ADR-019 (hub de pestañas) y ADR-026 (fuente única
   de temas).
2. Empezar por **K1** (`tonight_tab.ui` + `main_window.py` `_apply_kind_filter` /
   `_visible_targets`), validar el contrato (grid + tabla a la vez, podium sobre
   lo visible), y proseguir con **K2** (`config.enabled_kinds` + grupo kinds en
   `settings_dialog.ui` + guardas en `on_open_settings`).
3. **No tocar** `core/` para filtrar — si surge que toca, abrir ADR nuevo antes
   de escribir el mínimo (el planificador ya devuelve los 6 grupos, el scoring
   sigue diversificando; la whitelist solo corta la vista).
4. Cabecera GPL obligatoria en todo `.py` nuevo, código en inglés, cadenas
   visibles en la GUI por `self.tr()` (patrón de `main_window.py`), pares ES/EN
   por `orbits.pick` (o `tr()` para los estáticos). Idioma activo:
   `config.get("language")` (patrón `MainWindow._lang`).

 ### 7ses. Fase E — Punto de entrada unificado (2026-09-02)

 Motivación: con las fases D y K hechas, las formas de «ir hacia un objeto»
 estaban repartidas: clic en la fila → **Explorar**, doble clic en la
 tabla → **creaba un proyecto en silencio**, botón de la fila → **proyecto**.
 El observador no podía elegir conscientemente entre explorar y trabajar
 sobre un proyecto; y la tablea (la vista más rápida) no le enseñaba el
 contenido del objeto antes de crear nada. **Fase E** unifica: un solo
 punto de entrada («Explorar») y los botones Explorar/Continuar
 son puras atajos; el proyecto se crea o se reanuda *desde dentro* del
 diálogo Explorar.

 **Decisiones pactadas (2026-09-02)**:

 1. **Clic en fila → Explorar** (ya era así; se mantiene).
 2. **Doble clic en la tabla → Explorar** (antes: creaba proyecto en
    silencio — ahora es `_table_open_explore`, mismo destino que la fila
    y que el botón Explorar).
 3. **Botón de la fila** (`_card_button`): verde **«▶ Continuar»**
    cuando ya hay un proyecto activo para ese objeto (corto a
    `_start_or_continue`, que salta al hub); naranja **«🔭 Explorar»**
    si no (abre el diálogo Explorar con ese objeto). El botón es un
    atajo, no una acción distinta de las de la fila.
  4. **Diálogo Explorar** (`_open_explore_dialog`): la única acción del
     panel es el **CTA único** (fondo de la sección de gráficos, ancho
     completo, 46 px). El **«Crear post»** de D5 desaparece: los posts
     se escriben dentro del proyecto (paso Publicar) o a demanda desde
     Herramientas. La cara del CTA depende del `project_lookup` que la
     ventana le inyecta: **verde «Continuar proyecto»** si existe un
     activo para el objeto, **naranja «Crear proyecto»** si no.
     Emite una de las dos señales nuevas, cada una con dos argumentos
     (`name, fallback`): `project_create` / `project_continue`.
     El diálogo se autoajusta al contenido con suelos de lectura
     (`resize_to_panel_content` en `gui/overview.py`: ancho ≥ 780,
     alto = sizeHint + ancla de marco) para que los textos se lean
     cómodos y el CTA quede siempre visible sin scroll vertical.
     (la anterior `project_action(name, fallback, continue_)` se
     elimina). `MainWindow` reacciona en `_on_create` (va a
     `_create_project`) y `_on_continue` (va a `_goto_active_project`;
     si el «nombre explorado» no coincide con el activo, crea uno):
     en ambos casos el diálogo se cierra después.
 5. **`_create_project` ahora retorna el `dict` creado** (o `None`,
    con un aviso en la barra de estado si el tipo no es válido para
    proyecto — p. ej. un transit ad-hoc desde el menú Herramientas
    no puede crear un proyecto, solo un post).
 6. **`_goto_active_project(name, fallback=None)`** (nuevo, privado):
    busca el proyecto activo cuyo `object_name` coincide con `name`
    o con el `id`/`name` del `fallback` (los NEOCP/PCCP guardan el
    número MPC como `id` y un nombre provisional como `name`;
    cualquiera de los dos puede ser el que quedó en el proyecto), y
    selecciona en el hub. Devuelve `True/False`.
  7. **El panel sigue siendo testeable**: el `ObjectPanel` acepta
     `project_lookup` como callable inyectado (no importa `core.db`
     directamente — `MainWindow._explore_panel` lo construye);
     `for_post=False` (hub) → el CTA se oculta; `for_post=True`
     (Explorar) → el CTA se muestra en cuanto el objeto está cargado
     y la consulta dice qué cara ponerse.

 **Tests**: `tests/unit/test_overview_panel.py` (7 nuevos: parejas ocultas
 sin lookup, «Continuar» cuando hay activo, «Crear» cuando no, señales con
 el `continue_` correcto, ignorado mientras carga, `_blank` las reseta);
 `test_tonight_rows.py` (3 nuevos: botón «Explorar» conectado a
 `_open_explore_dialog`, botón «Continuar» conectado a
 `_start_or_continue`, y la senda fallback «continuar» → «crear»);
 `test_projects_hub.py` (4 nuevos: `_goto_active_project` por nombre, por
 `fallback id`, sin coincidencia, y el `project_lookup` del diálogo
 honra el `id`/`name` del planner); `test_tonight_table.py` ya cubría el
 doble clic. `pytest tests/unit` verde.

 **Idiomas**: 4 cadenas nuevas («Continuar», «Explorar»,
 «Continuar proyecto», «Crear proyecto» + sus tooltips), pares ES/EN en
 ambos `.ts` y ambos `.qm` recompilados.

 **Punto de entrada (para quien retome esta fase)**:

 1. Leer esta sección, ADR-019 (hub) y ADR-026 (temas).
  2. Los 4 puntos de contacto con `gui/`: `_card_button`,
     `_table_open_explore`, `_open_explore_dialog`, `_explore_panel`
     (en `main_window.py`) y el constructor de `ObjectPanel` +
     `_refresh_cta` / `_cta_clicked` (en `overview.py`).
 3. **No tocar** `core/project.py` para añadir tipos — `VALID_KINDS`
    sigue siendo la fuente única; si un tipo nuevo entra, añade el
    caso a los tests de creación (el diálogo ya lo honra por el
    `kind` guardado en el target).
  4. Cabecera GPL, código inglés, `self.tr()` en la GUI, `pyside6-lrelease`
     tras cada cambio de `.ts`.

  **Corrección (2026-09-02, mismo día)**: los tests de la pareja y el
  smoke de i18n fallaban porque la API de la pareja es ahora el CTA
  único. El `ObjectPanel` expone `btn_project` (un solo botón a ancho
  completo, `min-height: 46`, fondo de la sección) y las señales
  `project_create(name, fallback)` / `project_continue(name,
  fallback)` (2 args cada una; `post_requested` y `project_action` se
  retiran). La ventana conecta los dos en `_on_create` /
  `_on_continue` (`main_window.py:1979`), el «orquestador» anterior
  (`_do_project` / `_make_post` / `_explore_post`) queda eliminado.
  Los 9 tests de `test_overview_panel.py` (CTA) + los 4 de
  `test_projects_hub.py` + los 2 de `test_tonight_rows.py` pasan.

### 7sex. Fase F — Gráficas vectoriales en la GUI (2026-09-03)

Motivación: los charts del resumen (órbita, cielo, …) eran **PNGs de ratio fijo**
mostrados en lienzos de otro ratio (letterbox) y no se podían animar, hovernear ni
exportar "lo que se ve". Ahora son **widgets vectoriales nativos de PySide6**
(`QGraphicsView`). La **red / post** sigue en matplotlib (ADR-010, intacto para ese
ámbito); solo la capa de visualización de la GUI cambia. Ver ADR-029 (diseño) y
`docs/PLANS/qt-chart-widgets.md` (plan fase a fase).

**Decisiones pactadas (2026-09-03)**:

1. **Paquete `gui/widgets/`**: `ChartView` base (zoom bajo el cursor, pan, fit,
   export PNG, hover) + `OrbitChart` (animación por fecha + hover `r/ν/t`) + `SkyChart`
   (hover hora/altura/azimut, ventana segura, mejor hora). `core/orbit_math.py` y
   `core/sky_math.py` guardan la matemática pura **sin matplotlib** (la comparten
   `viz/*` y `gui/widgets/*`); `gui/widgets/palette.py` aporta las constantes de color.
2. **`chart_viewer.py` dual-mode**: abre el **widget** (zoom/fit → `widget.view`,
   export → `widget.export_png()`) o, para los que no tienen widget, el **PNG**
   (`QLabel+QScrollArea`, con botón 1:1). Fábricas: `open_chart_widget()` / `open_chart()`.
3. **Slots del panel**: **órbita** y **cielo** → `OrbitChart`/`SkyChart` vivos
   (zoom/pan/hover/animación). **transit** (curva de luz) y **field** (cutout SN) →
   `QLabel+QPixmap` (aún sin vectorial). `build_charts` (en `core/post.py`) sigue
   como "¿se puede?" y sigue produciendo los PNGs de redes.
4. **Panel vs viewer** (decision abierta cerrada): el **panel retiene** su instancia
   viva; un **click** reconstruye una **segunda** instancia y abre el viewer (la opción
   "dos instancias", la más simple). **No** se persiste el estado (zoom/fecha) del
   widget entre sesiones — se re-deriva de `e` al abrir.

**Estado**: las 5 fases (1 base · 2 órbita · 3 cielo · 4 integración · 5 docs) están
**hechas** (commits `fa94696`, `bedf0ce`, `f276237`, `6b66bc6`/`797173e`/`ba6d437`).
Suite verde: unit 389, functional 42 (+1 skip).

**Punto de entrada (para quien retome)**:

1. Leer ADR-029, ADR-010 (sección "Alcance") y `docs/PLANS/qt-chart-widgets.md`.
2. Los points de contacto: `gui/widgets/{base,orbit,sky}_*.py` (capa nueva),
   `gui/chart_viewer.py` (dual-mode), `gui/overview.py` (`_render_charts`,
   `_make_vector`, `_SlotClick`). Los slots **transit/field** siguen en pixmap: un
   vectorial de curva de luz (o de cutout) sería el siguiente paso.
3. **No** importar `matplotlib` dentro de `gui/widgets` (regla del plan, probada por
   test). Las fuentes de datos viven en `core/*.py` (puras) y `core/post.py`
   (PNGs de redes, intacto).
4. Cabecera GPL, código inglés, `self.tr()` en la GUI.

Cada fase deja la app funcional e incluye sus tests. No mezclar fases en un mismo
commit sin que la anterior esté verificada.

### 7septies. Ficha de objeto unificada (2026-09-07, ADR-031)

Motivación: la ficha solo daba tabla de parámetros a NEO/cometa/PCCP; SN y
tránsitos se quedaban en hook + bullets, la tabla cortaba las explicaciones
largas, las coordenadas no se veían, «Discovered» no aplicaba a NEOs y el
filtro de apertura de ADR-015 nunca se había implementado. Plan:
`docs/PLANS/object-card.md` (rama `feature/object-card`).

**Qué cambia** (un subplan = un commit):

0. **Coordenadas copiables**: bloque bajo el hook con AR/Dec en decimal y
   sexagesimal + botón «Copiar» (`_coords_from`: misma cadena de fuentes que
   la carta de cielo).
1. **Tabla multilínea**: wordWrap + auto-alto de fila que sigue a la columna
   elástica al redimensionar (ojo: `sectionResized` llega antes de que
   `columnWidth()` se actualice — el handler fuerza el ancho notificado).
2. **Tabla para SN**: `orbits.explain_transient` (tipo, galaxia, distancia,
   brillo, descubrimiento; z a fondo).
3. **Ficha de tránsitos**: bug arreglado — la rama exoplanet de `enrich`
   pierde el evento ExoClock; ahora se fusiona con el patrón ADR-027. Tabla
   `orbits.explain_transit` con inicio/fin UTC, profundidad (mmag y %),
   duración y **veredicto telescopio mínimo vs. tu apertura**.
4. **Chips por tipo con la misma gramática**: SN gana tipo y frescura
   («N d», verde si ≤14 días); tránsito gana profundidad Δmmag.
5. **«Discovered» exacto en NEOs y PCCP**: SBDB `discovery=1` (fallback
   `first_obs`), NEOfixer `/orbit/` para NEOCP, PCCP mapea su propia columna.
   Pool paralelo de 4 + caché 7 días. Nuevo `core/dates.py` único.
6. **Filtro duro de apertura en tránsitos**: `transits_tonight(aperture_in=)`
   + interruptor `transit_scope_filter` en Configuración > Observación
   (activado por defecto; sin dato ExoClock no se descarta — ADR-025).

**Estado**: subplanes 0-6 hechos; suite unitaria verde (555). Commits:
`72d66ee` (plan), `b163f6c`, `376a23c`+`67ceadf`, `02c05bf`, `3412c3c`,
`8c4c336`, `afab280`, `03290ea` + cierre i18n/docs.

**Nota i18n**: el comando `lupdate` documentado en CONTRIBUTING ahora incluye
`gui/widgets/*.py` — sin él, lupdate marca «vanished» cadenas vivas de las
cartas vectoriales y los tests de i18n fallan al regenerar.

### 7octies. Goto con efeméride fresca para cuerpos en movimiento (2026-09-07, ADR-030 rev.)

Motivación: los NEOs, cometas y PCCP no tienen coordenadas fijas (a diferencia
de SN y tránsitos). El goto usaba el **snapshot** que el planner guardó al
crear el proyecto — un NEO a 5″/min con un plan de hace 2 h acumula 10′ de
error, y el goto astrométrico resolvía el campo equivocado. La ficha además
mostraba la fila Horizons de las 00:00 UT (`eph[0]`, paso diario), hasta 24 h
stale. Plan: `docs/PLANS/goto-fresh-ephemeris.md`.

**Qué cambia** (un subplan = un commit):

0. **`core/ephemeris.py::position_at`**: consulta Horizons a paso 2 min en
   ventana ±2 h (redondeada a 30 min para reusar la caché), interpola linealmente
   a «ahora» (desenvolviendo AR en el salto 0h/24h), deriva tasa aparente (″/min)
   y PA. Fallback sin red: SBDB+Kepler → NEOfixer preliminar → `None`.
1. **Goto fresco en `main_window.py`**: para `neo`/`comet`/`pccp` la acción del
   `CcdcielWorker` resuelve `position_at` antes del slew/solve y pliega el
   resultado en el contexto (`coords_epoch`/`coords_source`/`rate`). SN y
   tránsitos siguen usando el snapshot. Etiqueta «Posición a las HH:MM:SS UT»
   + aviso si cae al snapshot.
2. **Ficha con época visible**: `_enrich_small_body` pide paso 30 m y elige la
   fila más cercana a ahora (`ephem_epoch`); el bloque de coords muestra la
   época junto al RA/Dec copiable.
3. **Cierre**: i18n ES/EN (~4 cadenas), revisión de ADR-030, esta sección,
   `pytest tests/unit` verde (582).

**Estado**: subplanes 0-3 hechos; suite unitaria verde (582). **Fuera de esta
iteración**: `SolarTracking`/`UpdateCoord=True` en el `.targets` y tasas no
siderales vía JSON-RPC (necesitan validación contra el CCDciel real); el cap
anti-traza por exposición (`max_exposure_no_trail` + `rate_arcsec_min`) ya
protege los frames.

### 7nonies. Track A — Ciclo de vida y clasificación de proyectos (2026-09-09)

Plan: `docs/PLANS/project-lifecycle.md` (hijo A de
`docs/PLANS/project-concept-v2.md`). Rama `feature/project-lifecycle`.

Los proyectos se pueden **cerrar** (con resultado final) y **reabrir** (la
revisita «un año después» es un flujo real); el hub clasifica por **año**,
**tipo**, **etiquetas**, **favoritos**, **búsqueda** y **orden**; y los
ficheros que el proyecto genera se ven en la pestaña Detalles.

| Sub | Entregable | Estado |
|---|---|---|
| A0 | Migración `user_version 4`: `closed_at`, `outcome`, `tags`, `favorite` + índice `created` | **Hecho** |
| A1 | `core/project.py`: `close()/reopen()/set_tags/set_favorite` + `OUTCOMES` por tipo | **Hecho** |
| A2 | GUI: botones cerrar/reabrir con diálogo de resultado + asesor de cierre + confirmación de archivar | **Hecho** |
| A3 | Hub: agrupación por año, filtro por tipo, búsqueda, favoritos primero, orden configurable | **Hecho** |
| A4 | `project_files` visibles en Detalles + carpeta por proyecto + registro de blink/FITS | **Hecho** |
| A5 | CLI `project close/reopen/files` + i18n ES/EN (458 cadenas) + esta sección | **Hecho** |

**Estado**: suite unitaria verde (643).

### 7decies. Track B — Supernova: seguimiento fotométrico multi-noche (2026-09-09)

Plan: `docs/PLANS/sn-followup.md` (hijo B de `docs/PLANS/project-concept-v2.md`).
Rama `feature/sn-followup`.

El proyecto SN deja de ser «una noche» y se convierte en un **seguimiento de semanas o meses** (e incluso años, con reabrirura): cada visita se registran el apilado final por filtro y la fotometría (sin fricción: solo teclear la magnitud), NightScribe calcula un **análisis de campaña indicativo** propio y dibuja la **curva de luz** frente a las **plantillas típicas** del tipo, genera la **animación de la evolución** (GIF/MP4), recomienda la **captura por brillo**, produze el **FITS anotado**, **recuerda la cadencia** («hace N noches que no la visitas») y mantiene el **post vivo**. Referencia real: la página de AT2020sum/AT2020sun en irydeo.com (fotometría AIJ, comparaciones Gaia DR2, tablas por filtro Clear/NIR, revisitas).

| Sub | Entregable | Estado |
|---|---|---|
| B0 | Migración `user_version 5`: `project_sessions`, `session_images`, `photometry_points` + `core/followup.py` CRUD | **Hecho** |
| B1 | `core/fits_meta.py`: DATE-OBS/FILTER/EXPTIME del header + MJD | **Hecho** |
| B2 | Pestaña «Seguimiento» en proyecto SN (visitas, apilados, notas, cadencia) | **Hecho** |
| B3 | Entrada fotometría sin fricción: rápida (solo magnitud) + pegado tolerante (AIJ/Tycho/CSV) + fichero | **Hecho** |
| B4 | Curva de luz: PNG + widget QGraphicsView + plantillas típicas esquemáticas (Ia, II-P/L, Ib/c, SLSN, kilonova) | **Hecho** |
| B5 | `core/series.py`: motor de series — apertura, detección, ensemble automático, Δmag, análisis de campaña con veredicto vs plantilla | **Hecho** |
| B6 | Animación de evolución: N frames alineados por afín desde WCS, GIF/MP4 | **Hecho** |
| B7 | Didáctica SN: tipos ampliados + TNS enrich cuando SIMBAD no conoce la SN | **Hecho** |
| B8 | Captura SN: `recommended_sn_exposure(mag)` + secuencias multi-filtro retrocompatibles + bloque SN en Plan tab | **Hecho** |
| B9 | Post vivo: curva de luz en `build_charts` + etiquetas de animación | **Hecho** |
| B10 | FITS anotado: copia con keywords NS_ en cabecera (Python puro, sin astropy) | **Hecho** |
| B11 | Cadencia con memoria: «hace N noches» en pestaña Seguimiento + chip en Tonight | **Hecho** |
| B12 | Contexto de surveys ASASSN/ZTF (opcional) | Pendente (opcional) |
| B13 | Cierre: i18n ES/EN (467 cadenas), ADRs, esta sección | **Hecho** |

**Estado**: suite unitaria verde (749). **Fuera de esta
iteración**: fotometría absoluta propia (términos de color), sustración de galaxia, ajuste PSF; monitor de flujo en vivo para tránsitos/variables de corto periodo (sobre `core/series.py`, tremadamente simple); importar salida de EXOTIC (O-C); lanzar EXOTIC/AIJ como subproceso.

*(Restaurada 2026-09-10: esta sección se perdió al resolver el merge
`50cd6c9` — se recupera verbatim de `d0686e4`.)*
