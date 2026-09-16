# Plan — Diario de observación y «Sol y cielo»: la pestaña de divulgación (Track JO)

> **Abierto (2026-09-16)** — documento maestro, sin implementar. Las
> decisiones están registradas en
> [ADR-036](../adr/ADR-036-journal-and-sunsky.md) — **léelo primero**. Las
> tarjetas de subplan se escriben al arrancar el track, con anclas frescas.

**rama**: `feature/campaigns-ux` — **decisión del usuario (2026-09-16)**:
todo el trabajo de esta era se hace en esta misma rama (no se abren ramas
nuevas por track).
**fecha**: 2026-09-16 · **autor**: FJC (con la IA)
**orden**: este track se ejecuta **después** de
[signals-campaigns.md](signals-campaigns.md) (así el Diario ya nace
registrando los eventos ⚡ de variables como entradas de la noche).

## Motivación

Verificaciones contra el código (detalle en ADR-036, «Contexto»):

- La pestaña **History está muerta por construcción**: `observations` solo
  se escribe vía `mark_observed`, sin llamadores desde `8822ca7`
  (UX v3.1). Pestaña siempre vacía, columna ✔ de Tonight muda, decay de
  novedad del scoring inerte. El historial *real* ya existe, disperso por
  el mundo-proyecto.
- La pestaña **Solar es un escaparate sin flujo**: sin salida a post (el
  PNG del Sol para redes solo existe en CLI), duplica la Luna de Tonight y
  su nombre choca con NEOs/cometas (también «sistema solar»).

## Visión

El mapa mental de la barra queda redondo — cinco pestañas con oficio
propio: **Esta noche** (decidir) · **Proyectos** (ejecutar) ·
**Campañas** (monitorizar, ADR-037) · **Sol y cielo** (divulgar) ·
**Observatorio** (operar) — y el **Diario** (recordar) en el menú
Herramientas, de consulta ocasional.

## Decisiones pactadas (2026-09-16)

| # | Decisión | Valor |
|---|---|---|
| JO-a | **El Diario no es pestaña** | Diálogo «Diario de observación…» en el menú Herramientas (junto a Explorar/Parpadeo). La barra queda en 5 pestañas; `TAB_*` se redefine (`TAB_OBSERVATORY` última) y los atajos vuelven a Ctrl+1..5. |
| JO-b | **Vista derivada, auto-generada, solo lectura** | UNION de eventos que la app ya registra: proyectos creados/cerrados (con resultado), visitas (`project_sessions`), ficheros (`project_files`), puntos de fotometría, campañas creadas/finalizadas, y las filas *legacy* de `observations`. **Sin marcado manual** — la tabla muerta deja de ser posible por diseño. |
| JO-c | **Noche astronómica** | El Diario se agrupa por noche de observación (mediodía → mediodía local), no por día civil: una noche cruza medianoche. |
| JO-d | **Sin migración destructiva** | `observations` se conserva como fuente legacy (ADR-002); `mark_observed`/`mark_posted` siguen para la CLI. |
| JO-e | **Re-cableado del feedback** | `is_observed`/`observed_recently` (scoring) y la columna ✔/checkbox de Tonight pasan a leer la actividad de proyectos (query nueva `activity_for(name, fallback_id)` en core, con el mismo emparejado nombre/`id` que `_goto_active_project`). La semántica exacta del ✔ se decide en la fase J3 con el usuario. |
| JO-f | **Solar → «Sol y cielo»** (*Sun & sky*) | Pestaña de divulgación: conserva Sol SDO + regiones + índices y el almanaque; gana la línea «impacto en tu noche» y el CTA **«Generar PNG para redes»** (`viz/sun_panel.draw_sun`, hoy solo en CLI). |
| JO-g | **Fase opcional S3** | Borrador bilingüe «post del cielo» (narrative + Luna/planetas) y/o crónica de la noche desde el Diario — se decide al llegar. |

## Fases

| Fase | Entregable | Criterio de aceptación |
|---|---|---|
| **J0** | History sale de la barra: la tabla clicable actual se mueve tal cual al diálogo «Diario de observación…» del menú Herramientas; `TAB_*` a 5; Ctrl+1..5 | Tests del Track UX retargetados (los gestos de UB.2 viven ahora en el diálogo); barra con 5 pestañas |
| **J1** | `core/journal.py`: vista derivada (UNION de las fuentes de JO-b, agrupada por noche astronómica, textos ES/EN). Puro, sin GUI | Tests: eventos sintéticos de cada fuente agrupan bien por noche (caso 23:59 y 00:30 = misma noche); legacy `observations` aparece |
| **J2** | El diálogo Diario se alimenta de `journal.py` (secciones por noche, filtro por tipo, búsqueda, doble-clic → proyecto/Explorar); CLI `history` re-cableado | Tests offscreen del diálogo + test del CLI |
| **J3** | Re-cableado (JO-e): `activity_for` en core; `suggest.score_target` lo usa; columna ✔/checkbox de Tonight redefinidos | Tests: novedad/urgencia reaccionan a la actividad de proyecto, no a `observations` |
| **S1** | Renombre a «Sol y cielo» / "Sun & sky" (título `.ui` + cadenas ES/EN) + línea «impacto en tu noche» (Luna → penaliza débiles → ver Esta noche; Kp → auroras) | Test de la línea con datos fake; tab renombrado en ambos idiomas |
| **S2** | CTA «Generar PNG para redes» en la pestaña: `sun_panel.draw_sun` con idioma y watermark, guardado en `data_dir/posts`, vista en `ChartViewer` | Test offscreen con `draw_sun` monkeypatcheado: botón → fichero registrado y mostrado |
| **S3** *(opcional, se decide al llegar)* | Borrador «post del cielo» bilingüe (extender `narrative` con Luna/planetas) y/o crónica de la noche desde el Diario | — |
| **J9** | Cierre: i18n ES/EN completo, estados de ADR-036, sección en WORKFLOWS.es/.md, suite verde | `pytest tests/unit` verde; 0 cadenas unfinished |

## Reglas de ejecución (vigentes, de WORKFLOWS)

- Una fase = un commit; cada fase deja la app funcional con sus tests.
- Tests offscreen sin red, patrón `tests/unit/test_projects_hub.py`.
- Cabecera GPL en todo `.py` nuevo; código en inglés con comentarios
  `# @args:` / `# @return:`; cadenas de GUI por `self.tr()` (nunca dentro
  de f-strings); pares ES/EN por `orbits.pick`.
- Si algo contradice JO-a…JO-g o un ancla no coincide: **para y reporta**.
  Cambios de decisión → revisión de ADR-036 antes de escribir el mínimo.

## PUNTO DE ENTRADA (para humanos o IAs que retomen esto)

1. Lee, en este orden: [ADR-036](../adr/ADR-036-journal-and-sunsky.md),
   este documento, y la revisión 2026-09-16 de
   [ADR-019](../adr/ADR-019-projects-ux-v3.md).
2. Empieza por **J0**. Anclas de partida (verifícalas antes de escribir):
   `gui/main_window.py` (`on_refresh_history`, `_history_open`,
   constantes `TAB_*`, `_connect_menu`), `gui/ui/history_tab.ui`,
   `core/db.py::history`/`mark_observed`, `core/suggest.py::score_target`,
   `viz/sun_panel.py::draw_sun`, `nightscribe/__main__.py::cmd_history` y
   `cmd_solar`.
3. No tocar: el contenido del Track UX en las demás pestañas; el esquema
   de base de datos (ninguna migración nueva en J0-J3 — el Diario es una
   *vista*; si una fase creyera necesitar tabla, para y abre decisión).
