# Plan — UX de variables y campañas: pestaña Campaigns, enlaces, gestos y el proyecto como página única (Track UX)

> **Pendiente de ejecutar (2026-09-13): plan escrito, 23 subplanes
> autocontenidos.** Un subplan = un commit. Las tarjetas de subplan viven en
> `docs/PLANS/ux/` (un fichero por fase). Anclas verificadas a HEAD
> `4df771b` (cierre del Track V). **El ejecutor es un modelo local pequeño
> (qwen3.8)**: las tarjetas llevan todo el código y los tests ya escritos
> para copiar; leer antes `docs/PLANS/ux/LEEME.md` (patrones y errores
> frecuentes). **Decisiones registradas**: la enmienda de V-j de
> [ADR-035](../adr/ADR-035-variables-campaigns.md) (gestor modal → pestaña)
> y la de presentación de pasos de ADR-019 (pestañas+wizard → página única)
> forman parte del cierre (UC.2).

**rama**: `feature/campaigns-ux` — **rama INDEPENDIENTE** (decisión del
2026-09-13): nace de `feature/variables-campaigns` (HEAD `4df771b`) y **no
sigue la cadena de merge-back** de las ramas feature anteriores; su destino
de merge se decide al cerrar el track, con el usuario.
**fecha**: 2026-09-13 · **autor**: FJC (con la IA)

## Motivación (auditoría de usabilidad 2026-09-13)

El Track V dejó las variables y las campañas **implementadas pero
escondidas**. Hallazgos verificados contra el código (HEAD `4df771b`):

1. **El gestor de campañas es un selector, no un listado**: sus dos
   `QListWidget` (`gui/campaigns_dialog.py:75-76`) solo tienen
   `itemSelectionChanged` para habilitar botones. Sin doble-clic, sin menú
   contextual, sin botón «Abrir». Cada campaña muestra solo `nombre
   (grupo)`. **No existe ninguna vista de detalle de campaña** en toda la
   app: ni objetivo, ni protocolo legible, ni miembros, ni estado de
   cadencia por objetivo.
2. **La campaña es invisible fuera del gestor**: el badge de la cabecera
   del proyecto (`main_window.py:1897-1902`) y el chip de la tarjeta son
   texto muerto; la lista del hub no marca qué proyectos tienen campaña; el
   chip de cadencia de Tonight (`main_window.py:1055-1102`) informa pero no
   navega.
3. **Fallos silenciosos**: validaciones que retornan sin aviso
   (`campaigns_dialog.py:247-249, 349-356`), attach sin candidatos y detach
   sin miembros que no hacen nada visible (`:163-164, 181-182`). Los tests
   actuales fijan esos silencios como comportamiento.
4. **Red en el hilo GUI**: resolución VSX/SIMBAD síncrona
   (`campaigns_dialog.py:309-344`) y descarga de surveys síncrona
   (`main_window.py:4196`), contra la regla de la casa.
5. **El modelo no ofrece la query que un detalle necesita**
   («miembros con su estado de cadencia»): `due_campaigns` solo devuelve
   los vencidos; `projects_of` no trae visitas (`core/campaign.py:159-195`).
6. **Gestos inconsistentes en toda la app**: la lista de proyectos solo
   tiene selección simple (sin doble-clic, Enter, menú contextual ni cursor
   de mano); History es una tabla sin enlaces; el tooltip de la tabla de
   Tonight promete un comportamiento que ya no existe.
7. **Bugs menores localizados**: detalle de proyecto «stale» al cerrar con
   filtro Active; clic en la fila ya seleccionada = no-op (no se puede
   reintentar una carga fallida); CTA «Create project» que cierra aunque
   falle (`main_window.py:4817-4822`); registro doble de los ficheros del
   post (`:5002-5008` vs `:5014-5026`); constante muerta `_STEP_TABS`
   (`:69`); una cadena fuente en español en código (`:2122`);
   `event_mag_threshold` sin widget en Settings; el filtro de campaña del
   hub no persiste entre sesiones; campañas finalizadas no editables; sin
   botón Delete de campaña pese a `campaign.delete()`.

## Objetivo

Tres pilares, decididos en la entrevista 2026-09-13:

1. **La campaña como objeto legible**: nueva **5ª pestaña «Campaigns»**
   (entre Projects y Solar), mismo patrón maestro-detalle que el hub:
   lista con salud de un vistazo (miembros, vencidos, eventos) + detalle
   con objetivo, protocolo, URLs clicables y **tabla de miembros con su
   estado de cadencia**.
2. **Navegación bidireccional total**: toda mención de una campaña o de un
   proyecto es un enlace (badge en cabecera de proyecto, chip en tarjeta de
   Tonight, chips de cadencia → Follow-up, miembro → proyecto, History →
   proyecto/Explore).
3. **Un solo lenguaje de gestos**: en todas las listas y tablas —
   **clic = seleccionar · doble-clic/Enter = abrir/saltar · clic derecho =
   menú contextual · cursor de mano donde sea clicable**.

Y de paso, la tanda de arreglos y de feedback (fase 0) que la auditoría
localizó.

## Decisiones (UX-a … UX-h), cerradas en la entrevista 2026-09-13

| # | Decisión | Valor |
|---|---|---|
| UX-a | **Hogar de campañas = 5ª pestaña** | Sustituye al gestor modal (V-j de ADR-035 queda **superseded**; se enmienda en UC.2). La pestaña sigue el patrón maestro-detalle del hub: lista a la izquierda (máx. 360 px), detalle a la derecha. El diálogo `CampaignsDialog` desaparece; `CampaignEditDialog` y `AddTargetDialog` se conservan como sub-diálogos. |
| UX-b | **Detalle alimentado por `campaign.status_report`** | Nueva query en `core/campaign.py`: miembros (cualquier estado) × última visita × vencido sí/no × flag de evento (V-h). Es la query que `due_campaigns` no puede dar (solo vencidos). |
| UX-c | **Un solo lenguaje de gestos** | Todas las listas/tablas de la app: clic selecciona, doble-clic/Enter abre o salta, clic derecho menú contextual, cursor de mano en lo clicable. |
| UX-d | **Toda mención es un enlace** | Badge de campaña en cabecera de proyecto (`<a href>` + `linkActivated`), chip ⚑ de campaña en la tarjeta de Tonight, chips de cadencia (uno por proyecto, clicables → Follow-up), doble-clic de miembro → proyecto en el hub, doble-clic en History → proyecto o Explore. |
| UX-e | **Cero fallos silenciosos** | Toda validación/aviso vacío muestra `QMessageBox` (warning en validación, information en listas vacías). Los tests que fijaban el silencio se actualizan (tarjetas lo dicen expresamente). |
| UX-f | **La red nunca en el hilo GUI** | `ResolveWorker` (VSX/SIMBAD) y `SurveyWorker` (ALeRCE) en `gui/workers.py`, patrón TonightWorker. |
| UX-g | **Una sola lista de campañas** | Activas y finalizadas en la misma `QListWidget` (las finalizadas atenuadas y con sufijo), no dos listas independientes — elimina la ambigüedad de doble selección del gestor viejo. |
| UX-h | **La lógica de la pestaña vive en `main_window.py`** | Patrón de la casa (cada tab `.ui` es esqueleto; los handlers son métodos `_camp_*` de MainWindow). Los sub-diálogos siguen en `gui/campaigns_dialog.py`. |
| UX-i | **El proyecto es una página única** (entrevista 2026-09-13) | El detalle del proyecto pasa de «5 pestañas + wizard (Previous/Skip/Mark done/Next)» a **una página con scroll**: tarjeta «Siguiente acción» (`project.next_action()`, core puro) + secciones plegables (`CollapsibleSection`, ya existe) con el estado en palabras y sus botones dentro. **El modelo no cambia**: `project_steps` y sus estados siguen siendo la fuente de verdad — la enmienda de ADR-019 es de presentación. |
| UX-j | **CCDciel tiene hogar propio: pestaña Observatory** (6ª) | El control del observatorio sale del paso Plan (donde se reconstruía por proyecto) a una pestaña de ventana; la sección Plan conserva «Send plan»/«Start capture» + enlace de salto. Cierra la clase de bug de «controles huérfanos». |

## Arquitectura de navegación (tras el track)

```
Tonight ──tarjeta con campaña──► chip ⚑ ──► pestaña Campaigns (seleccionada)
        ──chip cadencia "SN due: X (Nd)"──► Projects → Follow-up de X
Projects (hub) ──ítem con ⚑ (tooltip: campaña)
        ──doble-clic/Enter──► abre el paso actual ●
        ──clic derecho──► menú (Abrir, Follow-up, ★, Cerrar, Archivar…)
        ──cabecera: badge "campaign: X"──► pestaña Campaigns (X seleccionada)
Campaigns ──lista──► detalle: objetivo, protocolo, URLs, miembros
        ──tabla de miembros: objeto | kind | última visita | estado
        ──doble-clic miembro──► proyecto en el hub
        ──botones: New/Edit/Finish/Reopen/Delete/Add target/Attach/Detach
Proyecto ──página única──► tarjeta «Siguiente» ──[Ir]──► sección expandida
        ──secciones plegables con estado en palabras y toggle dentro
Observatory (6ª pestaña) ──control CCDciel──► conexión, estado, gotos
        ──Plan conserva Send/Start + enlace de salto
History ──doble-clic──► proyecto activo del objeto, o Explore si no hay
Ctrl+1..6 ──► cambio de pestaña
```

## Protocolo de ejecución (obligatorio en cada subplan)

1. Lee `AGENTS.md` + `docs/PLANS/ux/LEEME.md` + **solo** tu tarjeta.
2. Baseline: `.venv/bin/python -m pytest tests/unit -q` → anota el conteo.
3. Implementa la tarjeta **tal cual** (el código y los tests ya vienen
   escritos). Si un ancla no coincide con la realidad: **para y reporta
   pegando la salida; no improvises**.
4. «Hecho» = checklist completo: el comando de test de la tarjeta en verde,
   suite unitaria verde (anota N→M), cabecera GPL en todo `.py` nuevo,
   código en inglés con comentarios `# @args:` / `# @return:`, cadenas de
   GUI por `self.tr()`, i18n ejecutado si la tarjeta tiene tabla de cadenas.
5. Un commit por subplan, con el mensaje literal de la tarjeta. Marca
   **Estado: Hecho (N→M)** en la tarjeta.
6. Prohibido: TODOs sin resolver, medias implementaciones, agrupar commits,
   editar tests no listados en la tarjeta, tocar ficheros no listados.

## Índice de subplanes (18)

| Sub | Título | Fichero | Depende de |
|---|---|---|---|
| U0.1 | Micro-fixes: tooltip Tonight, `_STEP_TABS`, cadena ES→EN, registro doble del post | [fase-0-fixes.md](ux/fase-0-fixes.md) | — |
| U0.2 | CTA Explore: no cerrar en fallo + detalle stale + re-clic reintenta | ídem | — |
| U0.3 | Feedback en diálogos de campaña (fin de los silencios) | ídem | — |
| U0.4 | Campañas: Delete con confirmación + editar finalizadas | ídem | U0.3 |
| U0.5 | Workers de red: `ResolveWorker` + `SurveyWorker` | ídem | — |
| U0.6 | Settings: `event_mag_threshold` + persistir filtro de campaña | ídem | — |
| UA.1 | `campaign.status_report` (core + tests) | [fase-a-campaigns-tab.md](ux/fase-a-campaigns-tab.md) | — |
| UA.2 | Pestaña Campaigns: `.ui`, registro, lista con salud | ídem | UA.1 |
| UA.3 | Detalle: protocolo, URLs clicables, tabla de miembros | ídem | UA.2 |
| UA.4 | Navegación y gestos en la pestaña (miembro→proyecto, menús, `_goto_campaigns`) + handlers `_camp_*` | ídem | UA.3, U0.3, U0.4 |
| UA.5 | Botones de acción visibles + jubilación del gestor modal | ídem | UA.4 |
| UA.6 | Toda mención de campaña es un enlace (badge, chip ⚑, chips de cadencia→Follow-up) | ídem | UA.4 |
| UA.7 | Hub: marca ⚑ por proyecto + columna «Campaign» en la vista All | ídem | UA.2 |
| UB.1 | Lista de proyectos: abrir en el paso actual, menú contextual, «New project…» | [fase-b-gestures.md](ux/fase-b-gestures.md) | U0.2 |
| UB.2 | History clicable + atajos Ctrl+1..5 | ídem | UA.2 |
| UB.3 | Barrido de consistencia (cursores, banner advisor, tests de gestos) | ídem | UB.1, UB.2, UA.4 |
| UD.1 | `project.next_action()` + `reopen_step()` (core puro) | [fase-d-project-flow.md](ux/fase-d-project-flow.md) | — |
| UD.2 | Pestaña Observatory: CCDciel sale del paso Plan | ídem | UA.2 |
| UD.3 | Página del proyecto: secciones plegables sustituyen a las pestañas | ídem | UD.1 |
| UD.4 | Tarjeta «Siguiente» cableada + enlaces profundos como scroll | ídem | UD.3, UA.6, UB.1 |
| UD.5 | Retirada del wizard + retarget de tests de pasos | ídem | UD.4 |
| UC.1 | i18n ES/EN completo (volcado de tablas) | [fase-c-close.md](ux/fase-c-close.md) | todas las de GUI |
| UC.2 | Cierre: ADR-035 rev (V-j superseded) + ADR-019 rev (pasos = página), WORKFLOWS 7sexdecies, AGENTS.md, suite | ídem | todas |

## Riesgos y mitigaciones

- **El salto de índices de pestaña** (Solar 2→3, History 3→4): la app usa
  `_goto_tab(n)` con literales y `_on_main_tab_changed` con `index == 1`.
  UA.2 introduce constantes con nombre (`TAB_TONIGHT…TAB_HISTORY`) y migra
  todos los usos; la tarjeta trae el `grep` de verificación. Los tests del
  hub usan índices de combos internos, no de pestañas principales.
- **`lbl_header` mezcla texto plano y enlaces**: el badge usa
  `<a href="campaign://ID">`; `QLabel` emite `linkActivated` por defecto
  (sin `openExternalLinks`). Conectar una sola vez en `_connect`.
- **El chip ⚑ vive dentro de una fila clicable** (`_ClickableFrame` abre
  Explore): el chip consume su `mousePressEvent` (clase `_LinkChip`, UA.6)
  para que el clic no propague a la fila.
- **`lupdate` no extrae `self.tr()` dentro de f-strings** (error frecuente
  nº 1 del LEEME de variables): todas las cadenas de las tarjetas van con
  `tr()` plano + `.replace("%1", …)`.
- **`status_report` corre `detect_event` por miembro**: es SQL local +
  estadística en memoria, coste despreciable; se refresca al entrar a la
  pestaña y tras cada acción, nunca en un timer.
- **Los tests GUI existentes del gestor** (`test_campaigns_dialog.py`):
  UA.5 retira la clase `CampaignsDialog`; las tarjetas dicen exactamente
  qué tests se mueven a `test_campaigns_tab.py` y cuáles se quedan (los de
  formulario y de alta de objetivo).
- **La fase D rompe tests que fijan las pestañas internas** (inventario
  verificado: `test_project_tabs.py` entero, ~20 referencias en
  `test_projects_hub.py`, 5 en `test_hads_plan.py`, 6 en
  `test_transit_plan.py`, 2 en `test_neo_process.py`): las tarjetas UD
  traen la tabla de traducción tabs→secciones y los tests de reemplazo;
  UD.3 se cierra en «verde parcial» a sabiendas (la suite completa vuelve
  en UD.5) — es la única tarjeta del track con esa licencia.
- **El salto de índices vuelve a ocurrir en UD.2** (6 pestañas: entra
  Observatory en la posición 4): las constantes `TAB_*` de UA.2 se
  redefinen una sola vez y Ctrl+1..5 pasa a Ctrl+1..6.

## Fuera de alcance (v2+)

- Export fotométrico **a nivel de campaña** (hoy es por proyecto, VD.6).
- Compartir campañas (export/import JSON) — ya era v2 del Track V.
- El add-on de **descubrimiento de variables** (lista destacada + extremos
  predecibles + vigilias T CrB/R CrB; aprobado 2026-09-12): es otro track
  (VF), se apoyará en esta pestaña.
- «Modo foco» (colapsar la lista del hub al abrir un proyecto).
- Notificaciones de bandeja de sistema.

## PUNTO DE ENTRADA (para el ejecutor local)

0. **Rama independiente (obligatorio)**: sitúate en el HEAD de
   `feature/variables-campaigns` (incluye este plan; las anclas de código
   se verificaron a `4df771b`, el cierre del Track V) y crea la rama del
   track:
   ```bash
   git switch -c feature/campaigns-ux
   ```
   Trabaja entera en ella; **no** la merges de vuelta a ninguna cadena de
   ramas feature al cerrar — el destino del merge lo decide el usuario.
1. Lee `AGENTS.md`, `docs/PLANS/ux/LEEME.md` y este maestro.
2. Ejecuta en orden: U0.1 → … → U0.6 → UA.1 → … → UA.7 → UB.1 → UB.3 →
   UD.1 → … → UD.5 → UC.1 → UC.2. Una tarjeta por sesión, con contexto
   fresco. No abras `gui/main_window.py` entero: trabaja siempre con los
   rangos de línea de la tarjeta.
3. Si algo contradice una decisión UX-a…UX-j o un ancla no coincide:
   **para y reporta**; no escribas el mínimo sin reportar.
