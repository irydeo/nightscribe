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
| SC-d | **Vigilias con surveys.py** | El chequeo usa la última magnitud ZTF vía ALeRCE (`core/sources/surveys.py`, caché 30 d) contra la línea base de la estrella; lista de vigilias configurable. Sin red en el hilo GUI (patrón `SurveyWorker`). |
| SC-e | **Terminología intacta** | Un miembro de campaña siempre se llama *proyecto*; *target* se reserva a los candidatos de Tonight (regla del Track UX). |
| SC-f | **Fuera de alcance** | AAVSO Alert Notices y ASAS-SN Sky Patrol (decisión mantenida del Track V). Sin feed genérico de «cualquier variable»: Tonight sugiere desde tus compromisos, el catálogo HADS y tu lista de vigilias. |

## Fases

| Fase | Entregable | Criterio de aceptación |
|---|---|---|
| **SC1** | Planner: la fase `campaigns` (`core/planner.py::_campaign_targets` + `core/campaign.py`) lista un proyecto cuando está vencido **o** hay evento (`detect_event`) **o** extremo ≤ `campaign_extremum_days`. Config nueva con su widget en Ajustes | Tests: proyecto al día con evento → listado; al día con extremo a 2 d → listado; al día sin nada → no listado; ventana configurable |
| **SC2** | Caja «Señales» en la pestaña Campañas (`campaigns_tab.ui` + handlers `_camp_*`): eventos ⚡ y extremos ⏳ agregados de todos los miembros + línea de cobertura «N de M al día». Query de agregación en `core/campaign.py` (sobre `status_report`) | Tests offscreen con fixtures: la caja lista eventos/extremos aunque la campaña no esté seleccionada a fondo; cobertura correcta |
| **SC3** | Chips de extremo en las filas de Tonight («máximo en N d» / «mínimo en N d») — el dato ya viaja en `t["variable"]["next_extremum"]` | Test de fila con `next_extremum` fake: chip visible con el tipo correcto (convención VSX de época, ADR-037) |
| **SC4** | Vigilias: lista configurable + chequeador ZTF/ALeRCE (`core/` nuevo, fuente `surveys.py`); fila de alerta en Tonight aunque la estrella no tenga proyecto (el CTA de Explorar ya ofrece «Crear proyecto») + señal en la consola | Tests con fuente monkeypatcheada: anomalía de subida → alerta; anomalía de caída → alerta; dentro de línea base → silencio; sin red → degradación amable |
| **SC5** | Cierre: i18n ES/EN completo, revisión de ADR-035 (rol de la pestaña), sección en WORKFLOWS.es/.md, suite verde | `pytest tests/unit` verde; 0 cadenas unfinished |

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
