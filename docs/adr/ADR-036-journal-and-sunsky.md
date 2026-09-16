# ADR-036: Historial → Diario de observación (menú, vista derivada) y Solar → «Sol y cielo» (pestaña de divulgación)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-16

**Ver / See**: [docs/PLANS/journal-outreach.md](../PLANS/journal-outreach.md)
(plan del track) · ADR-019 (UX v3, cuya disposición de pestañas se revisa
aquí) · ADR-037 (el rol de Campañas, decidido en la misma sesión).

## Español

**Contexto**: con el Track UX cerrado (2026-09-15) la barra quedó con seis
pestañas (Tonight · Projects · Campaigns · Solar · Observatory · History) y
dos de ellas no terminaban de justificar su sitio:

- **History estaba muerta por construcción**. La tabla `observations` solo se
  escribe vía `Database.mark_observed`, y nada la llama desde el commit
  `8822ca7` (UX v3.1, 2026-08-24), donde los botones «Observed» salieron de
  Tonight «para vivir dentro del flujo de proyecto» — y nunca se
  re-integraron. Consecuencias encadenadas: la pestaña Historial siempre sale
  vacía; la columna ✔ de la tabla de Tonight (`db.is_observed`) nunca muestra
  nada; el checkbox «mostrar observados» no filtra nada; y el feedback de
  novedad del scoring (`observed_recently` → hook=0, `is_observed` → +5
  urgencia en `suggest.score_target`) jamás se ha disparado. El Track UX la
  hizo clicable (UB.2), pero clicable y vacía. Mientras tanto, el historial
  *real* ya existe y es rico, disperso por el mundo-proyecto: `projects`
  (creado/cerrado con resultado), `project_sessions` (visitas),
  `project_files` (cada artefacto con fecha), `photometry_points`,
  `campaigns`.
- **Solar era un escaparate sin flujo**: no nace proyecto (Sol/Luna/planetas
  no son `VALID_KINDS`, correcto), no hay salida a post pese a que `enrich`
  tiene tipo `sun` y el CLI ya genera el PNG del Sol para redes
  (`solar --png` → `sun_panel.draw_sun`); duplica la Luna de la cabecera de
  Tonight; y el nombre «Sistema solar» choca con NEOs/cometas, que también
  son sistema solar y viven en Tonight/Projects.

**Decisión**:

1. **History deja la barra de pestañas** y se convierte en el diálogo
   **«Diario de observación…»** del menú Herramientas (junto a
   Explorar/Parpadeo). Es una herramienta de consulta ocasional: el menú es
   su sitio natural, y la barra se queda en **cinco pestañas**:
   *Esta noche · Proyectos · Campañas · Sol y cielo · Observatorio*
   (Ctrl+1..5).
2. **El Diario es una vista derivada, de solo lectura y auto-generada** —
   ya nadie «marca observado» a mano. Se construye como UNION de eventos que
   la app ya registra sola: proyectos creados/cerrados (con su resultado),
   visitas de seguimiento (`project_sessions`), ficheros generados
   (`project_files`: secuencias, FITS importados, posts, gráficos), puntos de
   fotometría, campañas creadas/finalizadas, y las filas *legacy* de
   `observations`. Se agrupa por **noche astronómica** (mediodía → mediodía
   local), no por día civil: una noche de observación cruza medianoche.
   Cada fila enlaza a su proyecto (gestos del Track UX, UX-c/d).
3. **Sin migración destructiva**: la tabla `observations` se conserva como
   fuente legacy (las bases existentes no se rompen, ADR-002) y
   `mark_observed`/`mark_posted` siguen disponibles para la CLI.
4. **Re-cableado del feedback de observación**: `is_observed` /
   `observed_recently` (scoring) y la columna ✔ / checkbox de Tonight pasan
   a leer la **actividad de proyectos** (query nueva en core,
   `activity_for(name, fallback_id)`), no la tabla huérfana. La semántica
   exacta del ✔ (marcador de «proyecto activo») se decide en el track.
5. **Solar se renombra «Sol y cielo»** (*Sun & sky*) y pasa de escaparate a
   **pestaña de divulgación con salida**: conserva el Sol SDO + mapa de
   regiones + índices y el almanaque (Luna + planetas); gana una línea de
   **«impacto en tu noche»** (iluminación lunar → penaliza débiles → ver
   Esta noche; Kp → auroras) y el CTA **«Generar PNG para redes»** que
   reutiliza `viz/sun_panel.draw_sun` (idioma + watermark del observatorio).
   Fase final opcional: borrador bilingüe «post del cielo»
   (narrative + Luna/planetas) y/o crónica de la noche desde el Diario.

**Consecuencias**: la línea «Cuatro pestañas: Esta noche · Proyectos · Solar
· Historial» de ADR-019 y el Historial-como-pestaña del Track UX (UB.2)
quedan **superseded** por este ADR. El subcomando CLI `history` se re-cablea
a la vista derivada cuando el track se ejecute. La eliminación de la pestaña
redefine las constantes `TAB_*` (5 pestañas, `TAB_OBSERVATORY` última) y los
atajos Ctrl+1..5. La misión 3 de la app («contarlo») gana un hogar propio en
la barra: Sol y cielo es la pestaña de divulgación, frente a Tonight («qué
observo hoy»).

## English

**Context**: with the UX track closed (2026-09-15) the tab bar grew to six
tabs (Tonight · Projects · Campaigns · Solar · Observatory · History) and
two of them did not quite earn their place:

- **History was dead by construction**. The `observations` table is only
  written through `Database.mark_observed`, and nothing has called it since
  commit `8822ca7` (UX v3.1, 2026-08-24), where the "Observed" buttons left
  Tonight "to live inside the project flow" — and were never re-integrated.
  The chain of consequences: the History tab always renders empty; the ✔
  column of the Tonight table (`db.is_observed`) never shows anything; the
  "show observed" checkbox filters nothing; and the scoring novelty feedback
  (`observed_recently` → hook=0, `is_observed` → +5 urgency in
  `suggest.score_target`) has never fired. The UX track made it clickable
  (UB.2) — clickable and empty. Meanwhile the *real* history already exists,
  rich but scattered across the project world: `projects` (created/closed
  with outcome), `project_sessions` (visits), `project_files` (every
  timestamped artifact), `photometry_points`, `campaigns`.
- **Solar was a showcase with no flow**: no project can be born from it
  (Sun/Moon/planets are not `VALID_KINDS`, correctly so), there is no post
  output even though `enrich` has a `sun` type and the CLI already renders
  the social-media Sun PNG (`solar --png` → `sun_panel.draw_sun`); it
  duplicates the Moon from the Tonight header; and the name "Solar system"
  clashes with NEOs/comets, which are also solar-system bodies but live in
  Tonight/Projects.

**Decision**:

1. **History leaves the tab bar** and becomes the **"Observing journal…"**
   dialog under the Tools menu (next to Explore/Blink). It is an
   occasional-recall tool: the menu is its natural home, and the bar keeps
   **five tabs**: *Tonight · Projects · Campaigns · Sun & sky · Observatory*
   (Ctrl+1..5).
2. **The journal is a derived, read-only, auto-generated view** — nobody
   "marks observed" by hand any more. It is built as a UNION of events the
   app already records on its own: projects created/closed (with outcome),
   follow-up visits (`project_sessions`), generated files (`project_files`:
   sequences, imported FITS, posts, charts), photometry points, campaigns
   created/finished, plus the *legacy* rows of `observations`. It is grouped
   by **observing night** (noon → noon local), not by civil day: an
   observing night crosses midnight. Every row links to its project (UX
   track gesture language, UX-c/d).
3. **No destructive migration**: the `observations` table is kept as a
   legacy source (existing databases are never broken, ADR-002) and
   `mark_observed`/`mark_posted` remain available to the CLI.
4. **Observed-feedback rewiring**: `is_observed` / `observed_recently`
   (scoring) and the Tonight ✔ column / checkbox switch to reading **project
   activity** (a new core query, `activity_for(name, fallback_id)`) instead
   of the orphan table. The exact ✔ semantics ("active project" marker) is
   decided inside the track.
5. **Solar is renamed "Sun & sky"** (*Sol y cielo*) and turns from showcase
   into an **outreach tab with an output**: it keeps the SDO Sun + region
   map + indices and the almanac (Moon + planets); it gains an **"impact on
   your night"** line (moonlight → faint targets penalised → see Tonight;
   Kp → auroras) and a **"Render PNG for socials"** CTA reusing
   `viz/sun_panel.draw_sun` (language + observatory watermark). Optional
   final phase: a bilingual "sky post" draft (narrative + Moon/planets)
   and/or a night chronicle from the journal.

**Consequences**: the "Four tabs: Tonight · Projects · Solar · History" line
of ADR-019 and the History-as-a-tab outcome of the UX track (UB.2) are
**superseded** by this ADR. The `history` CLI subcommand is rewired to the
derived view when the track executes. Dropping the tab redefines the `TAB_*`
constants (5 tabs, `TAB_OBSERVATORY` last) and the Ctrl+1..5 shortcuts.
Mission 3 of the app ("report it") gains its own home on the bar: Sun & sky
is the outreach tab, as opposed to Tonight ("what do I observe today").
