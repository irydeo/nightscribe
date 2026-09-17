# Plan — UX de proyectos y campañas: el cuadro de mando que provoca el «Ohh» (Track UX-PC)

> **Ejecutado completo el 2026-09-17**: 6 fases (U1–U6), una fase = un
> commit (`35f5a34` U1 · `6145880` U2 · `1a08e2e` U3 · `0b5f5b3` U4 ·
> `a0e09f7` U5 · cierre U6). Suite unitaria **1299** verde, i18n 876
> cadenas 0 unfinished. Decisiones registradas: **ADR-038** + revisiones
> de ADR-019 / ADR-030 / ADR-037.

**rama**: `feature/ux-projects-campaigns` — rama **independiente** que nace
de `feature/campaigns-ux` (HEAD `cb457e6`, con los tracks UX/SC/JO
completos); su destino de merge se decide con el usuario al cerrar el track
(mismo convenio que `feature/campaigns-ux`).
**fecha**: 2026-09-17 · **autor**: FJC (con la IA)

## Motivación (auditoría de usabilidad 2026-09-17)

El observador: *«Funcionalmente no tengo nada que reprochar, pero la UX me
parece excesivamente cargada y compleja; sin un manual no es intuitiva. No
quiero un rediseño menor: quiero que al abrir Proyectos o Campañas el usuario
diga "Ohh, eso es lo que necesito" — que la aplicación ayude y no moleste».*

Hallazgos verificados contra el código:

1. **Projects muestra ~20 acciones + ~20 campos a la vez** con un proyecto
   abierto: lista con 13 controles en 300 px; ciclo de vida disperso en 4
   zonas (cerrar se puede por 4 vías); cabecera con 8 bloques apilados;
   básico y avanzado al mismo nivel (CCDciel en Plan, calibración junto a
   Save plan); duplicidades (Refresh, Campaigns…, favorito ×2, Show in
   folder ×2 divergente, chip de paso + fila de toggle repetidos).
2. **Campaigns muestra 8 botones siempre visibles**, casi todos no-ops
   silenciosos sin selección; las 7 acciones duplicadas en menú contextual;
   señales globales vs detalle por campaña; `Finish/Reopen` aquí vs
   `Close/Reopen` en Projects; «New project…» con significado distinto en
   cada pestaña.
3. **La app ya sabe lo que necesita el usuario y lo tiene enterrado**:
   `project.next_action`, `campaign.project_signal` (evento ⚡ / extremo ⏳ /
   cadencia), `planner.safe_window_for` (ventana de esta noche, math local),
   `activity_for`. Nada de eso se ve al abrir la pestaña.
4. **Jerga de desarrollador en etiquetas visibles**: «Signals» (de
   `signals_report`, ADR-037), «Session products», «Quick-look». Si hay que
   leer un ADR para entender una etiqueta, la etiqueta está mal.

## La narrativa de la app queda así

| Pestaña | Pregunta que responde |
|---|---|
| Tonight | ¿Qué hay **ahí fuera** esta noche? (descubrir) |
| **Projects** | ¿**Qué me necesita** de lo mío? (tu trabajo te llama) |
| **Campaigns** | ¿Qué **está pasando** en el esfuerzo colectivo? |

## Reglas de diseño (transversales, pactadas 2026-09-17)

1. **La app habla primero**: lo que pide acción se muestra solo, con la
   razón en palabras llanas y UN botón que aterriza exactamente donde se
   actúa.
2. **Lenguaje llano (test del astrónomo)**: si hay que leer un ADR para
   entender una etiqueta, está mal. Renombres pactados:
   - `Signals` → **«Está pasando ahora»** / *"Happening now"*
   - Dashboard de Projects → **«Necesita tu atención»** / *"Needs your
     attention"* (estado de calma: «Todo en orden — noches claras ✨»)
   - `Session products` → «Lo que guardaste de la sesión»
   - `Quick-look` → «Análisis rápido»
   - `Finish` (campaña) → **«Close»** (misma palabra que proyectos)
   - `New project…` (en Campaigns) → «New project in this campaign…»
   - Se quedan (vocabulario real de astrónomo): Campaign, Follow-up
     (Seguimiento), Blink, HADS, PCCP.
   - Las filas de novedades se escriben como **frases completas**:
     «⚡ T CrB subió 0.4 mag en ZTF g (basal 10.1) — conviene medirla esta
     noche» · «⏳ WeSb 1 alcanza su máximo en ~2 días» · «👁 R CrB sigue en
     calma». El título pone el contexto; la frase hace el trabajo.
3. **Tres niveles de prominencia**: primario (visible) · secundario (menú
   `⋯`) · avanzado (subsección `Advanced ▸`, reusa `CollapsibleSection`).
   Ninguna funcionalidad se pierde: se reubica.
4. **Una acción = un lugar visible** (+ menú contextual como atajo
   estándar).
5. **Enablement real**: botones deshabilitados con tooltip, nada de no-ops
   silenciosos.
6. **Mismo lenguaje visual que Tonight** (filas ricas, chips, KIND_COLORS,
   tema ADR-026): la app habla con una sola voz.
7. **Estados vacíos que enseñan**: sin proyectos → «Empieza en Tonight…» +
   botón que salta allí; sin campañas → qué es una campaña + `＋ New`.
8. **Ayuda contextual `ⓘ` (patrón único)**: ningún concepto se da por
   sabido. Un botón `ⓘ` discreto junto al título abre una mini-ayuda
   emergente (2-3 frases en lenguaje llano + un ejemplo real + enlace «Más
   información» al `doc_viewer`). Se aplica igual en todas partes:
   - **Campaigns**: `ⓘ` junto a la cabecera → «Una campaña agrupa los
     proyectos de un mismo esfuerzo de observación: varias noches, varios
     observatorios, un objetivo. Ejemplo: "T CrB 2026 eruption" del grupo
     obsSN — cada noche mides T CrB con el mismo protocolo y lo reportas
     junto». Tooltip largo en la pestaña `Campaigns`. El diálogo
     *New campaign…* lleva la misma frase guía en una línea arriba. El
     **estado vacío** (lista sin campañas) enseña con el ejemplo + CTA
     `＋ New campaign…` — el concepto se explica justo cuando hace falta.
   - **Projects**: `ⓘ` junto a la cabecera → «Un proyecto es un objeto con
     sus tres pasos: planificar, procesar, publicar. Se crea desde Tonight
     y te va diciendo qué toca a continuación». Mismo patrón en el estado
     vacío del dashboard.
   - La ayuda vive en `self.tr()` con sus pares ES/EN como el resto.

## Pestaña Projects — diseño final

```
┌──────────────────────────────────────────────────────────────┐
│ Search… | Active▾ | Filters ▾ | ＋New   ┃  SIN SELECCIÓN:     │
│─────────────────── lista ────  ┃  ▶ Necesita tu atención      │
│ ● SN 2026qxy  ●●○              ┃   ⚡ T CrB subió 0.4 mag…     │
│   Measure tonight ⊕ 21:10–02:30┃      [Measure →]             │
│   ▂▃▅▃▂ (sparkline)            ┃   ⏳ SN 2026qxy — 6 noches…   │
│ ★ T CrB       ●●○              ┃      [Measure →]             │
│   Event! measure tonight ⚑obsSN┃   ○ 2026 QK — plan listo,    │
│ ○ 2026 QK     ●○○              ┃      visible 21:30–23:30 [Go→]│
│   Plan the capture ⊕ 21:30–23:30┃                             │
│                                ┃  CON SELECCIÓN: página del   │
│                                ┃  proyecto (hero + Next card) │
└──────────────────────────────────────────────────────────────┘
```

**Columna lista**: solo `Search…` + combo estado + `Filters ▾` (despliega
tipo/tag/campaña/orden/favoritos; estado recordado en
`config["projects_filters_open"]`) + `＋ New project…`. Fuera `Refresh`
(la lista ya auto-refresca) y `Campaigns…` (ya hay pestaña). **Filas
ricas**: banda de color del tipo, nombre en negrita, **siguiente acción en
palabras**, puntos de progreso ○●●, chip `⊕ HH:MM–HH:MM` (ventana de esta
noche, cálculo local con `planner.safe_window_for` — sin red), días desde
la última actividad, ⚑ campaña, y para SN/variable una **mini curva de
luz** con tus medidas. Orden: primero quien más te necesita.

**Panel derecho sin selección = el dashboard**: «Necesita tu atención» con
3-5 tarjetas (banda de urgencia: rojo ⚡ evento · ámbar ⏳
cadencia/extremo · azul ○ informativo), cada una con razón en palabras +
un botón de acción directa. Estados: calma («Todo en orden — noches
claras ✨») y vacío («Empieza en Tonight…» + salto).

**Página del proyecto (con selección)**:

- Cabecera hero: `[Tipo] Nombre` + badges (⚑, closed) + `☆` + `⋯`
  (Edit tags…, Show in folder, Change folder…, —, Close…/Reopen,
  Archive…, Delete…). Fuera: los 4 botones del pie de lista y el campo
  tags de la cabecera.
- **Tarjeta Next = centro de mando**: acción en palabras + `Go →` +
  `✔ Mark done` + `Skip` (estos dos solo cuando la acción siguiente es un
  paso real plan/process/publish) + mini-progreso
  `○ Plan · ○ Process · ○ Publish`.
- Secciones (acordeón exclusivo intacto): chip de estado en la cabecera de
  sección; **fuera la fila de toggle duplicada**; si un paso está
  done/skipped, enlace plano discreto `Reopen step` al final de la
  sección.
- **Plan** — visible: bloque del tipo (timeline / 2P HADS / extremo
  variable / anti-traza NEO), capture plan (frames/exp/filtro, multifiltro
  sn/variable), `Save plan`, `Export sequence…` (+ `Export ephemeris…` en
  neo/pccp: es su flujo principal, no es «avanzado»). Línea-enlace de
  estado CCDciel («→ Observatory tab»). **Advanced ▸**: Calibration.
  **Se mueven a Observatory** (grupo «Live capture» + selector de proyecto
  activo): Filter on wheel, Send plan, Start capture, etiqueta de época.
- **Process** — visible: lo del tipo (MPC paste+Validate+Save / FITS+Blink
  / EXOTIC / WebObs). **Advanced ▸**: «Lo que guardaste de la sesión»
  (Register FITS/image, Motion animation + zoom).
- **Follow-up** — visible: cadencia/evento/campaña + `Add visit` +
  `Análisis rápido` + `⋯ Photometry tools` (Paste…, Import…, Export
  report…, Download surveys…) + visitas (sus 2 botones contextuales en la
  caja de la visita) + mediciones + notas. **Advanced ▸** (sn): Generate
  animation, Export annotated FITS.
- **Publish**: igual (ya es 1 botón).

## Pestaña Campaigns — diseño final («sala de guerra»)

```
┌──────────────────────────────────────────────────────────────┐
│ ▶ Está pasando ahora                    (todas tus campañas) │
│   ⚡ T CrB subió 0.4 mag en ZTF g (basal 10.1) — medirla hoy │
│   ⏳ WeSb 1 alcanza su máximo en ~2 días                      │
│   👁 R CrB sigue en calma (10.2 en V)                         │
├──────────────────────┬───────────────────────────────────────┤
│ Tarjetas de campaña  │ Detalle de la seleccionada:           │
│ ┌──────────────────┐ │ nombre + meta + [Edit…][Close][⋯]     │
│ │ T CrB 2026       │ │ (⋯ = Delete…, New project in this     │
│ │ ●●●○ 3 de 4 al día│ │  campaign…, Attach…, Detach…)        │
│ │ próxima: hoy ⚡   │ │ goal, URLs, protocolo, miembros       │
│ └──────────────────┘ │ (doble clic miembro → proyecto)       │
│ ┌──────────────────┐ │                                       │
│ │ WeSb 1 · ●●●● ✓  │ │ Sin selección: texto guía (hoy        │
│ └──────────────────┘ │ lbl_what) como estado vacío           │
│ [＋ New campaign…] ⓘ │                                       │
└──────────────────────┴───────────────────────────────────────┘
```

- **«Está pasando ahora» como titulares arriba** (ámbito global, dicho en
  el subtítulo): filas-frase con acción directa (doble clic/Enter →
  proyecto o Explore). Renombrado desde `Signals`.
- **Tarjetas de salud** por campaña: nombre, grupo, `●●●○ N de M al día`
  (puntos = miembros al día, de `status_report`), próxima acción («medir
  hoy ⚡» / «máximo en ~2 d»), finalizadas atenuadas.
- Acciones sobre la seleccionada en la **cabecera del detalle** con
  enablement real: `Edit…`, `Close`/`Reopen` según estado, `⋯` para
  Delete/Attach/Detach/New-project-in-campaign. Sin selección → todo
  deshabilitado y el detalle muestra el texto guía.
- Terminología unificada: `Close` (no `Finish`).
- Menús contextuales se conservan como atajos.

## Core nuevo (mínimo, puro, sin red — es la fuente del dashboard)

- **`core/attention.py`** (o `project.attention_report(db, cfg)`): agrega
  por proyecto activo `next_action()` + `campaign.project_signal()`
  (evento ⚡ / extremo ⏳ / cadencia) + cadencia SN (followup) + ventana de
  esta noche (`planner.safe_window_for`, math local) → lista ordenada
  `{project_id, urgency, reason_es/en, action_section}` para el dashboard
  y para ordenar la lista. 100 % testeable offscreen con db fake.
- **Sparkline**: mini-render desde `photometry_points` (los datos ya están
  en db; el widget `lightcurve_widget` existe — versión mini o pixmap
  cacheado).

## Fases (una = un commit; app funcional y `pytest tests/unit` verde al cerrar)

| Fase | Entregable | Archivos principales | Estado |
|---|---|---|---|
| **U1** | Cimiento Projects: lista con Search+estado+`Filters ▾`+＋New; fuera Refresh/Campaigns…/pie-de-lista; menú `⋯` en cabecera (tags, carpetas, ciclo de vida); ☆ queda | `ui/projects_tab.ui`, `main_window.py` | **Hecho** |
| **U2** | **El "Ohh"**: `core/attention.py` + dashboard «Necesita tu atención» (panel derecho sin selección, estados calma/vacío) + filas ricas (acción, progreso, ⊕ esta noche, actividad, ⚑, sparkline SN/var, orden por necesidad) | `core/attention.py`, `main_window.py`, widgets de fila | **Hecho** |
| **U3** | Next card centro de mando (Mark done/Skip junto a Go→; fuera fila toggle; Reopen step discreto) + `Advanced ▸` en Plan (Calibration) y Process (productos de sesión) + CCDciel → Observatory (grupo Live capture con selector de proyecto) + línea-enlace en Plan | `main_window.py`, `ui/observatory_tab.ui` | **Hecho** |
| **U4** | Follow-up despejado: primarios Add visit / Análisis rápido / `⋯ Photometry tools`; animation + FITS anotado bajo `Advanced ▸` | `main_window.py` | **Hecho** |
| **U5** | Campaigns sala de guerra: «Está pasando ahora» arriba con frases completas, tarjetas de salud, acciones en cabecera del detalle con enablement, `Close`, `lbl_what` al estado vacío, **ayudas `ⓘ`** (pestaña, cabecera, diálogo New campaign, estado vacío) | `ui/campaigns_tab.ui`, `main_window.py` | **Hecho** |
| **U6** | Pase de lenguaje llano completo + i18n ES/EN (lupdate/lrelease) + tests offscreen + **ADR-038** (prominencia + lenguaje llano + dashboard) y enmiendas ADR-019 (hub), ADR-030 (CCDciel a Observatory), ADR-035/037 (rol de Campaigns, renombre Signals) + sección nueva en WORKFLOWS.es.md/.md | `gui/i18n/*`, `tests/unit/*`, `docs/` | **Hecho** |
| **U7** | La franja «Está pasando ahora» se explica sola: subtítulo de ámbito + ⓘ ayuda, cobertura «Al día: N de M proyectos de campaña» (+tooltip), guía sin campañas, estado vacío cálido y pedagógico (adiós «No signals right now»). Especificación completa, cadena a cadena con traducciones ES pactadas, en `docs/PLANS/sky-calendar.md` §«U7» | `ui/campaigns_tab.ui`, `main_window.py`, `test_campaigns_tab.py` | **Pendiente** (decidida 2026-09-17) |

El «Ohh» llega pronto a propósito: **U2** es la primera entrega visible
tras el cimiento, para validar la dirección con el observador antes de
seguir.

## Tests (patrón offscreen existente)

- `core/attention.py`: prioridades (evento > cadencia > informativo),
  fusión con regla SC-g (señal sobre proyecto existente se suma, nunca
  duplica), calma cuando no hay nada.
- Dashboard: con db fake muestra las tarjetas correctas; botón aterriza en
  la sección correcta; estados calma/vacío.
- Filas ricas: chips correctos por tipo; sparkline presente con medidas y
  ausente sin ellas; orden por necesidad.
- Menú ⋯: contiene las acciones y respeta estado (Close solo si activo).
- Filtros ▾: muestran/ocultan y persisten en config.
- Observatory: Send plan/Start capture operan sobre el proyecto elegido.
- Campaigns: enablement sin selección; Close/Reopen alternan; tarjetas de
  salud pintan N de M.
- Actualizar los tests que referencien widgets retirados
  (`test_projects_hub`…).

## Métricas de aceptación

1. Abrir Projects sin selección muestra «Necesita tu atención» (o su
   estado de calma) **sin tocar nada**.
2. Con un proyecto SN abierto y Plan expandido: **≤10 acciones visibles**.
3. En Campaigns: **≤4 acciones visibles** (＋New + las del detalle).
4. Toda etiqueta visible pasa el test del astrónomo (sin jerga de ADR).
5. `pytest tests/unit` verde; funcionales intactos; i18n 0 unfinished.

## Fuera de alcance

- Tonight, Sun & sky, Explore y Observatory (salvo el grupo Live capture
  que recibe de Plan) no cambian. Los chips de cadencia de la cabecera de
  Tonight se quedan como están (siguen saltando al Follow-up correcto).
- No se toca la máquina de pasos ni la API de campaign (salvo el nuevo
  `attention.py`, aditivo).
- Menús contextuales de listas: se conservan en todas partes como atajo.
