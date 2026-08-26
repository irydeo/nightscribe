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
contexto JSON completo y cinco pasos guiados. El contexto se captura al crear el
proyecto desde Esta noche (snapshot del objetivo: coords, mag, rate, ventana…) y se
enriquece en cada paso (secuencia exportada, FITS importado, medidas, posts).

**Pasos**: Plan → Captura → Procesado → Análisis → Publicar.

## 4. Flujo — supernova / transitorio

1. **Plan**: tarjeta con magnitud actual, edad, galaxia anfitriona, ventana sobre el
   horizonte real y «inicio seguro hasta HH:MM». El usuario define N tomas × exposición
   y filtro; la app comprueba que la sesión termina dentro del rango de seguridad.
2. **Captura**: exportar secuencia (NINA JSON / CCDciel / CSV) con nombre, coords J2000
   y tiempos; el fichero queda registrado en el proyecto.
3. **Procesado** (externo): el usuario calibra/apila con sus programas; al volver,
   «Importar FITS resultado» — **sin preguntar objeto ni coordenadas** (ya están en el
   contexto).
4. **Análisis**: blink con PS1-g casado (pipeline ADR-018 pre-rellenado), etiquetado,
   GIF/MP4/PNG con watermark del observatorio.
5. **Publicar**: historia ES/EN + tuit con los **datos reales de la sesión** (fecha,
   N×t, filtro) + marca observado/posteado en el historial.

## 5. Flujo — NEO / candidato PCCP

1. **Plan**: tarjeta con velocidad aparente (″/min) y **exposición máxima sin traza**
   calculada con la escala de placa del equipo; número de tomas; ventana e «inicio
   seguro». Aviso si la sesión terminaría fuera de seguridad.
2. **Captura**: exportar **efemérides** a paso configurable para TheSkyX y Cartes du
   Ciel (formatos validados con importación real en la fase 5; CSV como base) +
   secuencia para el software de captura.
3. **Procesado**: el usuario mide fuera (Astrometrica u otro) y **pega** las medidas en
   el proyecto → validación (80-col/ADES, código MPC, designación) → fichero
   empaquetado listo para enviar al MPC (ADR-022). El envío lo hace el usuario.
4. **Análisis**: interpretación orbital con contexto — familia, MOID, tamaño desde H,
   próxima aproximación (reutiliza `enrich.py` + `orbits.py`).
5. **Publicar**: historia ES/EN + `orbit_view`/`sky_view` + observado/posteado +
   report a NEOfixer si hay clave configurada.

## 6. Flujos posteriores

Cometas y tránsitos de exoplanetas reutilizan el mismo esqueleto de 5 pasos cuando los
flujos de SN y NEO estén asentados. Fuera de este rediseño inicial.

## 7. Hoja de ruta y punto de entrada

| Fase | Entregable | Estado |
|---|---|---|
| 1 | ADR-019…022 + este documento + DESIGN actualizado | **Hecho (2026-08-24)** |
| 2 | Fundación de restricciones: `core/horizon.py`, Luna, `core/exposure.py`, perfil de cámara en config, integración en planner/suggest, silueta en `sky_view`, tests | **Hecho (2026-08-24)** |
| 3 | Modelo de proyecto: migración db (`user_version` 0→1), `core/project.py`, máquina de pasos, tests | **Hecho (2026-08-24)** |
| 4 | GUI v3: 4 pestañas, hub Proyectos con stepper por tipo, blink contextual, tarjetas de Esta noche con «Crear proyecto» e «inicio seguro», Settings (Cámara/Horizonte/Sesión/Luna), i18n | **Hecho (2026-08-24)** |
| 5 | Exportadores: `core/sequence.py` (NINA/CCDciel/CSV) + efemérides (CSV + TheSkyX + CdC validados en importación real), tests | **Hecho (2026-08-24)** |
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

1. La vista de objeto es un **panel fijo por encima de Plan/Captura/Procesado/
   Análisis/Publicar** en el hub de Proyectos. No es un paso: no se salta y no se
   «marca hecho»; no entra en la máquina de 5 pasos.
2. Incluye (todo ya existe): **frase de enganche** + **bullets divulgativos** +
   **tabla de parámetros con explicación multilínea ES/EN** + **los 4 gráficos**
   (órbita, cielo, familias, campo) + **bloques de captura/ventana** (mag, tasa ″/min,
   exposición máx. sin traza si aplica, ventana inicio–fin, horas arriba).
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
| 4 PNG (órbita/cielo/familias/campo) | `core/post.build_charts` (`core/post.py:172`) |
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
| **D2** | `ObjectPanel` con rejilla **2×2 de gráficos** rellenos por `core/post.build_charts`; mensajes «por qué no» (hiperbólica / sin elementos / no confirmado) escalados al widget | Con `e` fake: 4 slots de gráfico o los mensajes de ausencia correctos; sin `e`: vacíos | **Pendiente** |
| **D3** | `ObjectPanel` con **bloques de captura/ventana** desde `ctx`: mag, tasa ″/min, exposición máx. sin traza (solo neo/pccp con tasa + `pixel_um`/`focal_mm`), ventana inicio–fin + horas arriba; se omite lo que falta | Con `ctx` fake de neo: chips completos; de sn: sin tasa/exposición; no rompe con `ctx` vacío | **Pendiente** |
| **D4** | **Integración en el hub**: `projects_tab.ui` inserta `ObjectPanel` entre `lbl_context` y `tabs_steps` (conservar/sustituir `lbl_context` se decide aquí). Al seleccionar proyecto → `loader` = `ExploreWorker` (mismo `fallback_target` de contexto), worker bajo `_keep`, señales desconectadas al cambiar de proyecto | Sin red: seleccionar proyecto muestra estado *cargando* y no revienta; la máquina de pasos, plan y botones siguen intactos; tests de humo offscreen | **Pendiente** |
| **D5** | **Diálogo *Explore…* sobre el panel compartido**: `main_window.py:1504` pasa a ser `ObjectPanel` + botón *Hacer post*; los `_dialog_explore_*` se delgan al panel; se conserva clic→zoom (el panel expone sus labels de gráfico) y `_project_explore`(paso 4) / `_tools_explore` | El diálogo *Explore…* del menú Herramientas idéntico en contenido; el paso 4 de NEO sigue abriéndolo pre-rellenado | **Pendiente** |
| **D6** | **i18n + verificación + docs**: `lupdate`/`lrelease` → `nightscribe_{es,en}.ts/.qm` (ADR-014); `pytest tests/unit` verde; esta sección con estados finales | Cadenas nuevas traducidas ES/EN; tests de humo en `tests/unit/test_overview_panel.py` (D1-D3) + humo del hub (D4) en verde | **Pendiente** |

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
   - Fase 5: `core/sequence.py` (exportadores NINA JSON / CCDciel XML / CSV genérico
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
   El **horizonte TheSkyX real** sigue mockeado: cuando el usuario comparta su fichero,
   sustituir el parser/fixture de `core/horizon.py` validando contra ese fichero (ADR-020).
   Los **formatos nativos de NINA/CCDciel/TheSkyX/CdC** son puntos de partida que requieren
   validación contra las versiones del usuario en importación real (ADR-021).

**Próximos pasos sugeridos** (fuera del rediseño inicial):
- Sustituir el mock del horizonte por el fichero TheSkyX real del usuario.
- Validar los formatos de exportación de secuencias y efemérides contra software real.
- Añadir flujos para cometas y tránsitos en el mismo esqueleto de 5 pasos.
- Probar la GUI a fondo y refinar la UX del stepper y los diálogos contextuales.
4. Reglas vigentes: código en inglés con cabecera GPL y comentarios `# @args:`,
   cadenas de GUI por `self.tr()`, red solo desde `core/sources/` vía `core/db.py`,
   documentación bilingüe (ADR-013), tests unitarios por módulo + funcionales de flujo.

Cada fase deja la app funcional e incluye sus tests. No mezclar fases en un mismo
commit sin que la anterior esté verificada.
