# Track UX — Fase C: cierre (UC.1–UC.2)

> Subplanes UC.1–UC.2 del plan maestro
> [../ux-variables-campaigns.md](../ux-variables-campaigns.md). Un subplan =
> un commit. Anclas verificadas a HEAD `4df771b`; si una no coincide:
> **parar y reportar**. Lee antes `LEEME.md`.
> Precondición: todas las demás tarjetas hechas.

---

## UC.1 — i18n ES/EN completo (volcado de tablas)

**Contexto a leer (solo esto)**: `docs/PLANS/variables/LEEME.md` §3
(pipeline i18n) y §5 (errores frecuentes); las tablas «Cadenas nuevas» de
todas las tarjetas de este track.

**Precondición**: todas las tarjetas GUI (U0.1–UB.3).

**Toca**: `nightscribe/gui/i18n/nightscribe_es.ts`,
`nightscribe/gui/i18n/nightscribe_en.ts` (+ los `.qm` compilados).

**Escribe exactamente esto**:

1. Ejecuta el pipeline:
   ```bash
   pyside6-lupdate nightscribe/gui/*.py nightscribe/gui/widgets/*.py \
       nightscribe/gui/ui/*.ui \
       -ts nightscribe/gui/i18n/nightscribe_es.ts \
           nightscribe/gui/i18n/nightscribe_en.ts
   ```
2. Recorre los `.ts` y traduce TODAS las entradas `unfinished` nuevas (la
   tabla agregada de abajo es la referencia; la fuente inglesa manda). En
   el `.ts` EN la traducción suele ser idéntica a la fuente.
3. Compila: `pyside6-lrelease nightscribe/gui/i18n/nightscribe_*.ts`
4. Verifica que la cadena-fuente española vieja de U0.1 («guía, no SNR…»)
   ha desaparecido o queda solo como entrada «vanished» (bórrala a mano si
   `lupdate` la dejó marcada).

**Tabla agregada del track** (referencia — si una cadena falta aquí pero
está en una tarjeta, manda la tarjeta):

| Fuente | ES |
|---|---|
| Double-click a row to explore the object | Doble-clic en una fila para explorar el objeto |
| The campaign needs a name. | La campaña necesita un nombre. |
| The target needs a name. | El objetivo necesita un nombre. |
| RA and Dec must be numbers, in degrees. | AR y Dec deben ser números, en grados. |
| No active project without a campaign. | No hay ningún proyecto activo sin campaña. |
| This campaign has no projects yet. | Esta campaña aún no tiene proyectos. |
| Resolving… | Resolviendo… |
| Event threshold (mag): | Umbral de evento (mag): |
| Brightness jump (in magnitudes) from which a variable/SN project raises the event advisor | Salto de brillo (en magnitudes) a partir del cual un proyecto de variable/SN activa el asesor de eventos |
| Campaigns | Campañas |
| Campaign detail | Detalle de la campaña |
| Select a campaign. | Selecciona una campaña. |
| Select a campaign to see its detail | Selecciona una campaña para ver su detalle |
| Double-click a row to open its project | Doble-clic en una fila para abrir su proyecto |
| Protocol | Protocolo |
| Targets | Objetivos |
| %1 targets · %2 due | %1 objetivos · %2 vencidos |
| (finished) | (finalizada) |
| active | activa |
| finished | finalizada |
| One measurement every %1 night(s) per filter | Una medida cada %1 noche(s) por filtro |
| Filters: %1 | Filtros: %1 |
| Comparison stars: %1 | Estrellas de comparación: %1 |
| Report form | Formulario de reporte |
| Data | Datos |
| Object | Objeto |
| Kind | Tipo |
| Last visit | Última visita |
| Status | Estado |
| ⚡ brightness event | ⚡ evento de brillo |
| ● never visited | ● sin visitar todavía |
| ⚠ %1 d overdue | ⚠ %1 d de retraso |
| ✓ up to date | ✓ al día |
| %1 d ago | hace %1 d |
| Open project | Abrir proyecto |
| Detach from campaign | Quitar de la campaña |
| Delete… | Eliminar… |
| Delete campaign | Eliminar campaña |
| Delete the campaign “%1”? Its projects are kept, only the link is removed. | ¿Eliminar la campaña «%1»? Sus proyectos se conservan, solo se quita el enlace. |
| Part of this observing campaign — click to open it | Parte de esta campaña de observación — clic para abrirla |
| SN due: %1 (%2 d) | SN pendiente: %1 (%2 d) |
| Due for a revisit — click to open its Follow-up | Toca revisitarla — clic para abrir su Seguimiento |
| Campaign | Campaña |
| New project… | Nuevo proyecto… |
| Open | Abrir |
| Follow-up | Seguimiento |
| Unstar | Quitar estrella |
| Star as favorite | Marcar como favorito |
| Close project… | Cerrar proyecto… |
| Archive… | Archivar… |
| Show in folder | Mostrar en la carpeta |
| Double-click a row to open its project or explore the object | Doble-clic en una fila para abrir su proyecto o explorar el objeto |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit -q` (incluye
`test_i18n.py`)
**Hecho cuando**: verde; 0 entradas `unfinished` en los `.ts`
(`grep -c 'type="unfinished"' nightscribe/gui/i18n/nightscribe_es.ts` → 0).
**Commit**: `Gui/i18n: full ES/EN pass for the campaigns-UX track (UX, subplan UC.1)`
**Estado**: Hecho (0 cadenas nuevas, 0 unfinished — las tarjetas anteriores
ya iban traduciendo al vuelo; el pase completa a 780/780; suite 1146 verde)

---

## UC.2 — Cierre documental: ADR-035 rev (V-j superseded), ADR-019 rev (pasos = página), WORKFLOWS 7sexdecies, AGENTS.md

**Contexto a leer (solo esto)**:
`docs/adr/ADR-035-variables-campaigns.md:1-10` (cabecera) y `:69-73` +
`:128-129` (decisión 9, ES/EN); `docs/adr/ADR-019-projects-ux-v3.md:1-25`
(cabecera + contexto, donde viven los «pasos guiados»);
`docs/WORKFLOWS.md:620-647` y `docs/WORKFLOWS.es.md` (sección
«7quindecies», el molde); `AGENTS.md` (bloque de estructura, línea de
`gui/`, ES y EN).

**Precondición**: todas.

**Toca**: `docs/adr/ADR-035-variables-campaigns.md`;
`docs/adr/ADR-019-projects-ux-v3.md`; `docs/WORKFLOWS.md`;
`docs/WORKFLOWS.es.md`; `AGENTS.md`; este maestro (marcar ejecutado).

**Escribe exactamente esto**:

1. **ADR-035**:
   a. Cabecera (:3): añade al final de la línea de revisiones:
      ```
       · **rev. 2026-09-13+ (Track UX)**: la decisión 9 queda **superseded**
      — el gestor modal se sustituye por la pestaña Campaigns; ver
      [docs/PLANS/ux-variables-campaigns.md](../PLANS/ux-variables-campaigns.md)
      ```
      (una sola línea física, fecha real del commit).
   b. Decisión 9 ES (:69-73): insértale al inicio:
      ```
      9. **[Superseded 2026-09, Track UX]** ~~Gestor de campañas = diálogo
      modal~~ → **pestaña «Campaigns»** (5ª pestaña, maestro-detalle como el
      hub): la auditoría de usabilidad mostró que el diálogo era un selector
      sin detalle (no se podía ni abrir una campaña). La pestaña muestra la
      salud de cada campaña (miembros × cadencia × eventos, nueva query
      `campaign.status_report`), enlaces bidireccionales (badge en la
      cabecera del proyecto, chip ⚑ en Tonight, chips de cadencia →
      Follow-up) y las acciones CRUD con feedback nunca silencioso. Los
      sub-diálogos (crear/editar, añadir objetivo) se conservan. Lo demás de
      la decisión sigue vigente:
      ```
      (deja el texto original de la decisión después de ese párrafo).
   c. Decisión 9 EN (:128-129): el mismo trato:
      ```
      9. **[Superseded 2026-09, Track UX]** ~~Campaign manager = modal
      dialog~~ → **the "Campaigns" tab** (5th tab, master-detail like the
      hub): the usability audit showed the dialog was a selector with no
      detail view. The tab shows each campaign's health (members × cadence
      × events, new `campaign.status_report` query), bidirectional links
      (project header badge, ⚑ Tonight chip, cadence chips → Follow-up)
      and CRUD actions with non-silent feedback. The sub-dialogs survive.
      Still in force:
      ```
2. **ADR-019** (la segunda enmienda del track — la fase D):
   a. Cabecera: añade a la línea de revisión: `, 2026-09 (Track UX)`.
   b. Al final de la sección «Decisión» (ES), añade:
      > **Revisión 2026-09 (Track UX, decisión UX-i/UX-j del plan)**: la
      > presentación de los pasos guiados cambia de «pestañas internas +
      > stepper (Previous/Skip/Mark done/Next)» a **página única con
      > secciones plegables** y una tarjeta «Siguiente acción» alimentada
      > por `project.next_action()`. La auditoría de usabilidad mostró el
      > doble modelo de navegación (pestañas libres + wizard) y los iconos
      > de estado ✔/●/○/– como la fuente de complejidad del flujo de
      > proyecto. **El modelo no cambia**: `project_steps` y sus estados
      > (`pending/current/done/skipped`) siguen siendo la fuente de verdad;
      > el cierre automático al completar el último paso se conserva. El
      > control de CCDciel sale del paso Plan a la pestaña **Observatory**
      > (6ª): la conexión ya era de ventana, ahora también su UI.
   c. La misma nota, traducida, al final de la sección «Decision» (EN).
3. **WORKFLOWS.md / WORKFLOWS.es.md**: nueva sección tras la 7quindecies,
   siguiendo su molde (la numeración latina sigue la serie: 7quindecies →
   7sexdecies). Texto EN literal para `WORKFLOWS.md`:

   ```markdown
   ### 7sexdecies. Track UX — variables & campaigns usability (2026-09-13, amends ADR-035 + ADR-019)

   Plan: `docs/PLANS/ux-variables-campaigns.md` (master) +
   `docs/PLANS/ux/fase-*.md` (23 subplans). Branch `feature/campaigns-ux`
   (independent: no merge-back into the feature chain).

   The usability audit (2026-09-13) found Track V's features correct but
   hidden: the campaign manager was a selector with no detail view, no
   mention of a campaign was a link, the gesture language differed per
   list, and the project flow stacked two navigation models (tabs +
   wizard). The track delivers: the **Campaigns fifth tab** (master-detail:
   per-campaign health at a glance — members × cadence × events via the
   new `campaign.status_report` query — protocol, clickable URLs, members
   table; the modal manager retires and ADR-035 decision 9 is superseded);
   **bidirectional navigation** (project header badge, ⚑ Tonight card chip,
   per-project clickable cadence chips landing on Follow-up, member
   double-click → hub, History double-click → project/Explore); **one
   gesture language** everywhere (click selects · double-click/Enter opens ·
   right-click menu · hand cursor); the **project as a single page**
   (Next-action card fed by `project.next_action()` + collapsible sections
   with plain-word state — the step tabs and wizard retire; ADR-019
   amended, lifecycle model unchanged); the **Observatory sixth tab**
   (CCDciel control leaves the Plan step); and the fixes batch (no silent
   validation, network off the GUI thread via `ResolveWorker`/
   `SurveyWorker`, `event_mag_threshold` in Settings, persisted campaign
   filter, stale detail cleared, CTA no longer closes on failure).

   | Sub | Deliverable | Status |
   |---|---|---|
   | U0.1–U0.6 | fixes & feedback batch | **Done** |
   | UA.1–UA.7 | Campaigns tab + links | **Done** |
   | UB.1–UB.3 | gesture language | **Done** |
   | UD.1–UD.5 | project single page + Observatory tab | **Done** |
   | UC.1–UC.2 | i18n + docs close (this track) | **Done** |

   **Status**: unit suite green (**N**). **Out of this iteration**:
   campaign-level photometric export, campaign sharing, the featured-
   variables discovery add-on (approved 2026-09-12, its own track).
   ```

   La versión ES para `WORKFLOWS.es.md` es la traducción fiel de ese bloque
   (mismo formato; «7sexdecies. Track UX — usabilidad de variables y
   campañas»).
4. **AGENTS.md**: en el bloque de estructura (ES y EN), la línea de `gui/`
   pasa a mencionar las pestañas — en la línea `gui/ ... ui/ (*.ui
   Designer)` añade al final: `; six main tabs: Tonight, Projects,
   **Campaigns**, Solar, **Observatory**, History (ADR-019/035 rev.)`.
   Ajusta el conector al idioma de cada bloque (ES: «seis pestañas:
   Tonight, Projects, **Campaigns**, Solar, **Observatory**, History»).
5. **Este maestro**: la cabecera pasa a `Executado (plan escrito
   2026-09-13; cerrado <fecha>): 23 subplanes autocontenidos, todos hechos,
   suite unitaria N.` (fecha y N reales).

**Ejecuta**: `.venv/bin/python -m pytest tests/unit -q` (anota N) +
`.venv/bin/python -m pytest tests/functional -q` si hay red.
**Hecho cuando**: suite unitaria verde (anota N→M); los cinco documentos
actualizados; `grep -n "superseded" docs/adr/ADR-035-variables-campaigns.md`
muestra las dos enmiendas (ES/EN) y `grep -n "Track UX"
docs/adr/ADR-019-projects-ux-v3.md` la tercera.
**Commit**: `Docs: Track UX close — ADR-035 decision 9 superseded (Campaigns tab), ADR-019 rev (project single page), WORKFLOWS 7sexdecies, AGENTS.md (UX, subplan UC.2)`
**Estado**: Pendiente
