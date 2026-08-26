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
| C | Tabla «Lista completa» rediseñada sobre el tema, doble-click→proyecto, regeneración i18n ES/EN de las cadenas nuevas, tests de humo | **Pendiente ← punto de entrada** |

**PUNTO DE ENTRADA para quien retome el rediseño (fase C)**:

1. Leer `docs/adr/ADR-026-dark-global-theme.md` (decisión vigente:
   `gui/theme.py` es la única fuente de colores base y de `KIND_COLORS`;
   el cromo —ventanas, tabs, menús, tablas, tooltips, scrollbars— ya está
   estilizado globalmente; la fase C solo toca la tabla «Lista completa»).
2. La fase C trabaja en `nightscribe/gui/main_window.py` (tabla de
   «Lista completa»: construcción de columnas, doble-click→proyecto,
   estilos de fila) y en `nightscribe/gui/ui/tonight_tab.ui` (la tabla
   vive debajo de la lista de filas).
3. Decisiones de UX confirmadas (usuario): la tabla se **conserva** (no se
   elimina); doble-click en una fila crea/continúa el proyecto; la tabla
   hereda el tema global (filas, cabecera, selección) y añade las
   cadenas nuevas por `self.tr(...)`. Al terminar, regenerar `.ts`/`.qm`
   (ver ADR-014) y añadir tests de humo (patrón
   `tests/unit/test_tonight_rows.py`).

**PUNTO DE ENTRADA (para cualquier IA o humano que retome el trabajo)**:

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
