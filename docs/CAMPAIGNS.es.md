# Campañas de observación en NightScribe

Gemelo bilingüe: [`CAMPAIGNS.md`](CAMPAIGNS.md) (inglés). Plan de implementación:
[`PLANS/variables-campaigns.md`](PLANS/variables-campaigns.md) (modelo) y
[`PLANS/ux-variables-campaigns.md`](PLANS/ux-variables-campaigns.md) (estética y UX).
Documento de decisión: [`adr/ADR-035-variables-campaigns.md`](adr/ADR-035-variables-campaigns.md).

Este fichero explica qué es una campaña en NightScribe, cómo se relaciona
con los proyectos, y dónde vive cada pieza (modelo, bucle de «Esta noche»,
pestaña y diálogos) — para que cualquier humano o agente de IA pueda seguir
trabajando sin volver a investigar.

---

## 1. Terminología (regra obligatoria de redacción)

| Término | Significado en NightScribe |
|---|---|
| **Campaña** | El compromiso *compartido* de un grupo: un objetivo científico, un protocolo (cadencia, filtros, estrellas comparación) y las URLs de informe/datos. Entidad 1:N: muchos proyectos cuelgan de ella. |
| **Proyecto** | Un objeto concreto con su ciclo de trabajo en tres pasos del flujo UX v3: **planificar, procesar, publicar** (ADR-019). Cualquier `kind` de proyecto puede unirse a una campaña. |
| **Objetivo** (*target*) | **Reservado exclusivamente para los candidatos de la pestaña «Esta noche»** (NEO, cometa, candidata SN, tránsito…). Nunca se usa para nombrar a un miembro de una campaña. |

La confusión histórica: la primera maqueta de la pestaña usaba «Add target…»
para añadir un miembro a la campaña, solapando los dos significados de
«target». Regla de redacción vigente (Track UX de ADR-035): **en la pestaña
«Campañas» un miembro de la campaña SIEMPRE se llama *proyecto***; los botones
son «New project… / Attach project… / Detach…» — es decir,
«Nuevo proyecto… / Vincular proyecto… / Quitar proyecto…». Todo texto nuevo
se redacta bajo esta regla; los botones preexistentes de «Esta noche»
(«Scoring targets…», «Show all targets») son el uso legítimo de *target*.

## 2. Qué es una campaña (modelo)

Código: `core/campaign.py` · ADR: [`adr/ADR-035`](adr/ADR-035-variables-campaigns.md)
(decisión 2) · migración v7 (`campaigns` + `projects.campaign_id` con
`ON DELETE SET NULL`): borrar una campaña **libera** sus proyectos, no los
borra.

Cada campaña tiene:

| Campo | Ejemplo |
|---|---|
| `name` | «T CrB 2026» |
| `group_name` | «WeSb 1» |
| `coordinator` | nombre o «Observatorio Irydeo (Z41)» |
| `goal` | «medir la erupción completa de T CrB» |
| `protocol` (JSON) | cadence_nights, filters, comp_stars, notes |
| `report_url` | formulario web del grupo |
| `data_url` | repo/URL donde se depositan los datos |
| `status` | `active` / `finished` (+ `closed_at`) |

El `protocol` es un diccionario libre (`protocol_get`, claves
`cadence_nights`, `filters`, `comp_stars`, `notes`); NightScribe *lee* la
cadencia para el bucle de «Esta noche» pero no intenta modelar el resto —
el protocolo de un grupo de afición vive, por diseño, fuera de la base de
datos (solo se referencia).

## 3. El bucle de «Esta noche» (V-d)

`campaign.due_campaigns()`: para cada campaña **activa**, cada proyecto
activo es *vencido* si su última sesión es ≥ `cadence_nights` noches, o si
nunca se ha observado. La fase `campaigns` del planner (100 % local, sin red)
saca esos proyectos a «Esta noche» con visibilidad; la pestaña «Campañas»
muestra la salud completa (`campaign.status_report`): miembros × cadencia ×
eventos (⚡ si `variables.detect_event` detecta algo).

Caso de uso real que inspira la feature: los programas de estrellas
variables de grupo (HADS en [`HADS.es.md`](HADS.es.md), T CrB en WeSb 1)
donde varios observatorios comparten un mismo compromiso cadenciado.

## 4. UI — pestaña «Campañas» y diálogos

| Pieza | Dónde |
|---|---|
| Pestaña maestro-detalle | `gui/ui/campaigns_tab.ui` (lista + detalle) |
| Lógica de la pestaña, botones de proyecto | `gui/main_window.py` (`_refresh_campaigns_tab`, `_camp_new_project`, `_camp_attach`, `_camp_detach`) |
| Diálogo de proyecto nuevo | `gui/campaigns_dialog.py` → `NewProjectDialog` (resuelve VSX → SIMBAD → manual, cadena en `core/enrich.py`) |
| Diálogo de edición de campaña | `gui/campaigns_dialog.py` → `CampaignEditDialog` (mantiene la ayuda de redacción) |
| Catálogos i18n (edición manual obligatoria) | `gui/i18n/nightscribe_{es,en}.ts` / `.qm` |

Detalle de la pestaña: resumen de salud por fila («N projects · M due»,
⚡ cuando algún miembro tiene evento), protocolo y URLs, tabla de proyectos
con estado y cadencia. Botones:

- **New project… (Nuevo proyecto…)** — `NewProjectDialog`: pide el nombre,
  ofrece «Resolve (VSX/SIMBAD)» y creará un proyecto `variable` vinculado a
  la campaña.
- **Attach project… (Vincular proyecto…)** — une un proyecto *ya existente*
  y activo a la campaña.
- **Detach project… (Quitar proyecto…)** — desvincula sin borrar nada.

Si un proyecto ya existe, `NewProjectDialog` dice explícitamente: use
«Attach project…». (Esa frase es el remedio directo a la confusión que
motivó esta UX; ver §1.)

### Reglas de redacción — por qué esta copia

En la pestaña de «Esta noche» el usuario ve *candidatos* («targets»: NEOs,
cometas, SN, tránsitos). En la pestaña de «Campañas» el usuario ve sus
*proyectos* en curso. Usar «target» en las dos pestañas es impreciso: un
miembro de campaña no es un candidato de hoy. La frase completa del campo
de ayuda (campo `lbl_what`) deja la regla explícita dentro de la app:

> «A campaign groups the projects of one shared observation effort —
>  several nights, several observatories, one goal (e.g. “T CrB 2026
>  eruption”). A project is one object with its three steps: plan, process,
>  publish.»

## 5. Puntos de anclaje (para no perder)

- Modelo: `core/campaign.py` — CRUD + `due_campaigns` + `status_report`.
- Planner: la fase `campaigns` vive en `core/planner.py` (solo proyectos
  vencidos de campañas activas visibles; ver `due_campaigns`).
- Pestaña: `campaigns_tab.ui` — contexto Qt `CampaignsTab` (el nombre viene
  del `<class>` del .ui; los botones de proyecto viven solo aquí, traducidos
  con ese contexto). En «Esta noche» la campaña se ve únicamente como el
  chip ⚑ del objetivo (tooltip «Part of this observing campaign — click to
  open it»), que salta a la pestaña «Campañas».
- i18n: catálogo `nightscribe_es.ts`/`nightscribe_en.ts` (edición manual,
  ¡sin `lupdate` en PySide!), recompilar con `pyside6-lrelease`.
- ADRs relacionados: [ADR-019](adr/ADR-019-projects-ux-v3.md) (flujo
  v3, las tres etapas), [ADR-034](adr/ADR-034-hads-stars.md) (fuente del
  catálogo HADS usado en campañas reales), [ADR-035](adr/ADR-035-variables-campaigns.md) (campañas).

## 6. Referencias (verbatim)

1. ADR-035, Track UX — el gestor modal se sustituye por la pestaña y la
   terminología de «target»→«project» se codifica en la UI; ver
   [`adr/ADR-035-variables-campaigns.md`](adr/ADR-035-variables-campaigns.md).
2. Plan UX —[`PLANS/ux-variables-campaigns.md`](PLANS/ux-variables-campaigns.md).
3. Modelo original —[`PLANS/variables-campaigns.md`](PLANS/variables-campaigns.md).
4. Flujo v3 (tres etapas) —[`adr/ADR-019-projects-ux-v3.md`](adr/ADR-019-projects-ux-v3.md).
5. Caso HADS real —[`HADS.es.md`](HADS.es.md) (programa de monitorización
   tipo campaña: cadencia, filtros, comparaciones — lo mismo que modela
   `protocol`).
