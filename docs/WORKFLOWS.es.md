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
