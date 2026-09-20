# Plan — Señales y campañas: la consola de señales y los eventos de variables en Tonight (Track SC)

> **Abierto (2026-09-16)** — documento maestro, sin implementar. Las
> decisiones están registradas en
> [ADR-037](../adr/ADR-037-campaign-signals.md) — **léelo primero**: su
> tabla de taxonomía de eventos (detectados ⚡ / predichos ⏳ / vigilias 👁)
> es la fuente de verdad de *qué* se muestra. Las tarjetas de subplan se
> escriben al arrancar el track, con anclas frescas.

**rama**: `feature/campaigns-ux` — **decisión del usuario (2026-09-16)**:
todo el trabajo de esta era se hace en esta misma rama (no se abren ramas
nuevas por track).
**fecha**: 2026-09-16 · **autor**: FJC (con la IA)
**orden**: este track se ejecuta **antes** que
[journal-outreach.md](journal-outreach.md) (el Diario registrará los
eventos ⚡ como entradas de la noche).

## Motivación

Cerrado el Track UX quedaron dos carencias verificadas contra el código
(ver ADR-037, «Contexto»): la pestaña Campañas es funcionalmente «el hub
filtrado por campaña» (~80 % de su superficie es la tabla de miembros) y
los eventos de variables apenas se muestran — el detector solo se ve
dentro de la campaña seleccionada, y en Tonight **solo si el proyecto
está vencido** (`due_campaigns` filtra antes de evaluar el evento): una
caída detectada en un proyecto al día nunca sale en Tonight, contra el
protocolo WeSb 1 («si ves una caída, sube la cadencia»).

## Visión

- **Proyectos = ejecutar** (un objeto, sus pasos).
  **Campañas = monitorizar** (salud y señales del esfuerzo compartido).
  La distinción se sostiene por función, no por un párrafo explicativo.
- **Tonight honra la ciencia antes que la cadencia**: un proyecto de
  campaña sale listado cuando está vencido, **o** tiene un evento
  detectado, **o** un extremo inminente.
- Las vigilias (T CrB/R CrB y la lista destacada) miran el cielo fuera de
  tus propios puntos, contra ZTF/ALeRCE.

## Decisiones pactadas (2026-09-16)

| # | Decisión | Valor |
|---|---|---|
| SC-a | **Consola de señales** | La pestaña Campañas gana una caja «Señales» agregada (eventos ⚡ + extremos ⏳ de todos los miembros) y un resumen de cobertura («N de M al día»). La tabla de miembros queda subordinada como vista de salud. |
| SC-b | **Triple condición de listado** | La fase `campaigns` del planner lista un proyecto si está vencido **o** tiene evento detectado **o** extremo inminente. Ventana configurable `campaign_extremum_days` (defecto 3 d) en Ajustes. |
| SC-c | **Taxonomía de eventos = ADR-037** | Los tipos mostrados (caída / subida / máximo / mínimo / vigilia de erupción / vigilia de caída), sus reglas y sus superficies están fijados en la tabla de ADR-037; este plan no la redefine. |
| SC-d | **Vigilias con surveys.py (SC4a)** | Lista de guardia **curada, precargada y editable** (defectos: T CrB → erupción, basal ~10,2 V; R CrB → caída, basal ~5,8 V), chequeada contra la última magnitud ZTF vía ALeRCE (`core/sources/surveys.py`). La vigilia usa **clave de caché propia con TTL corto (~12 h)** — nunca la caché de contexto de 30 d. Sin red en el hilo GUI (patrón `SurveyWorker`). |
| SC-e | **Terminología intacta** | Un miembro de campaña siempre se llama *proyecto*; *target* se reserva a los candidatos de Tonight (regla del Track UX). |
| SC-f | **Fuera de alcance** | ASAS-SN Sky Patrol (ruido). Sin feed genérico de «cualquier variable»: Tonight sugiere desde tus compromisos, el catálogo HADS, tu lista de vigilias y el canal editorial AAVSO. *(Revisado 2026-09-16: el canal AAVSO **entra** en alcance como SC4b — revisión de ADR-037.)* |
| SC-g | **Regla de fusión** | Si una estrella vigilada o alertada ya es proyecto, la señal se suma a sus razones de listado (procedencia 👁/«AAVSO») — nunca una fila duplicada en Tonight. |
| SC-h | **Canal editorial AAVSO (SC4b, con spike previo)** | Alertas del foro (categoría *Alerts* de Discourse → JSON nativo) y campañas (`apps.aavso.org/v2/campaigns/`). **Primera tarea: spike de validación**; si no son consumibles con la stdlib, SC4b se acota y se documenta. Coords vía VSX (ya existe), filtro de horizonte, procedencia «AAVSO». |

## Fases

| Fase | Entregable | Criterio de aceptación | Estado |
|---|---|---|---|
| **SC1** | Planner: la fase `campaigns` (`core/planner.py::_campaign_targets` + `core/campaign.py`) lista un proyecto cuando está vencido **o** hay evento (`detect_event`) **o** extremo ≤ `campaign_extremum_days`. Config nueva con su widget en Ajustes | Tests: proyecto al día con evento → listado; al día con extremo a 2 d → listado; al día sin nada → no listado; ventana configurable | **Hecho (2026-09-16, `fcdf443`)** — `project_signal`/`tonight_listable` en `core/campaign.py` |
| **SC2** | Caja «Señales» en la pestaña Campañas (`campaigns_tab.ui` + handlers `_camp_*`): eventos ⚡ y extremos ⏳ agregados de todos los miembros + línea de cobertura «N de M al día». Query de agregación en `core/campaign.py` (sobre `status_report`) | Tests offscreen con fixtures: la caja lista eventos/extremos aunque la campaña no esté seleccionada a fondo; cobertura correcta | **Hecho (2026-09-16, `f96b2e6`)** — `signals_report` + consola |
| **SC3** | Chips de extremo en las filas de Tonight («máximo en N d» / «mínimo en N d») — el dato ya viaja en `t["variable"]["next_extremum"]` | Test de fila con `next_extremum` fake: chip visible con el tipo correcto (convención VSX de época, ADR-037) | **Hecho (2026-09-16, `50bdf58`)** |
| **SC4a** | **Vigilias automáticas** (SC-d/SC-g): lista curada precargada (T CrB erupción ~10,2 V; R CrB caída ~5,8 V) editable en Ajustes; `core/vigils.py` con chequeo contra basal (**caché propia TTL ~12 h**); fila de alerta en Tonight (horizonte incluido) **o fusión** con el proyecto existente; señal en la consola leyendo solo la caché. **Rev. 2 (hallazgo del spike)**: el backend se elige por brillo — basal < 11,5 → fotometría comunitaria AAVSO con token (`aavso_api_token` en Ajustes); ≥ 11,5 → ZTF/ALeRCE | Tests con fuente monkeypatcheada: anomalía de subida → alerta; caída → alerta; dentro de basal → silencio; sin red/caché → degradación amable; fusión sin fila duplicada; enrutador por brillo; parseo tolerante del endpoint con token | **Hecho (2026-09-16)** — `core/vigils.py`, TTLs `vigils`/`aavso` 12 h, fase planner + fusión (`_fuse_external`), chip 👁, consola solo-caché, editor + token en Ajustes; 32 tests en `test_vigils.py`; funcional: ZTF débil en vivo ✅, AAVSO-token pendiente del token del usuario |
| **SC4b** | **Canal editorial AAVSO** (SC-h): **primera tarea = spike** de validación (JSON Discourse de la categoría *Alerts* + `apps.aavso.org/v2/campaigns/`); si es viable: fuente `core/sources/` con caché vía `db.py`, resolución VSX, filtro de horizonte, filas en Tonight con procedencia «AAVSO» + enlace, fusión (SC-g) | Spike documentado en la tarjeta; tests con payload fake; degradación amable sin red | **Hecho (2026-09-16)** — spike ✅ (Discourse JSON + tabla de campañas parseable; resultado: ambos canales viables); `core/sources/aavso.py`, fase planner + fusión, chip 📣, checkbox en Ajustes; 17 tests en `test_aavso.py` con títulos reales del spike |
| **SC5** | Cierre: i18n ES/EN completo, revisión de ADR-035 (rol de la pestaña), sección en WORKFLOWS.es/.md, suite verde | `pytest tests/unit` verde; 0 cadenas unfinished | **Hecho (2026-09-16)** — 809 cadenas 0 unfinished, suite 1236 |

## Reglas de ejecución (vigentes, de WORKFLOWS)

- Una fase = un commit; cada fase deja la app funcional con sus tests.
- Tests offscreen sin red, patrón `tests/unit/test_projects_hub.py`.
- Cabecera GPL en todo `.py` nuevo; código en inglés con comentarios
  `# @args:` / `# @return:`; cadenas de GUI por `self.tr()` (nunca dentro
  de f-strings — `tr()` plano + `.replace("%1", …)`); pares ES/EN por
  `orbits.pick`.
- Red solo desde `core/sources/` vía `core/db.py` (caché); nunca en el
  hilo GUI.
- Si algo contradice SC-a…SC-f o un ancla no coincide: **para y reporta**;
  no improvises. Cambios de decisión → revisión de ADR-037 antes de
  escribir el mínimo.

## PUNTO DE ENTRADA (para humanos o IAs que retomen esto)

1. Lee, en este orden: [ADR-037](../adr/ADR-037-campaign-signals.md)
   (taxonomía incluida), este documento, y
   [docs/CAMPAIGNS.es.md](../CAMPAIGNS.es.md) (terminología y modelo).
2. Empieza por **SC1**. Anclas de partida (verifícalas antes de escribir):
   `core/campaign.py::due_campaigns` y `status_report`,
   `core/planner.py::_campaign_targets`, `core/variables.py::detect_event`
   y `next_extremum`, `core/suggest.py::_campaign_fragments`,
   `gui/main_window.py::_refresh_campaigns_tab` y `_campaign_selected`.
3. No tocar: la máquina de pasos del proyecto, el modelo de campaña
   (migración v7 ya hecha), `suggest` salvo la puerta de listado de SC1.
