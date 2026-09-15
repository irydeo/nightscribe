# ADR-035: Variables de largo periodo y campañas de observación — kind `variable`, campaña 1:N ortogonal, VSX/SIMBAD/manual, reporte con HJD

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-11 · **rev. 2026-09-13**: ejecutado completo — suite unitaria 1096 · **rev. 2026-09-15 (Track UX)**: la decisión 9 queda **superseded** — el gestor modal se sustituye por la pestaña Campaigns; ver [docs/PLANS/ux-variables-campaigns.md](../PLANS/ux-variables-campaigns.md)

**Ver / See**: [docs/PLANS/variables-campaigns.md](../PLANS/variables-campaigns.md)
(maestro) · [docs/PLANS/variables/](../PLANS/variables/) (40 subplanes) ·
decisiones heredadas: ADR-019 (proyectos), ADR-025 (mag híbrida), ADR-034
(HADS, guardarraíles H-n que este track consume).

## Español

**Contexto**: Las HADS (ADR-034) abrieron la fotometría de variables, pero
son la **excepción de corto periodo** (sesión única de 2P, sin fase conocida).
Las variables de largo periodo (Miras, simbióticas, novas recurrentes como
T CrB, novas enanas, RCB, irregulares tipo WeSb 1) siguen el molde
**multi-noche del Track B de supernovas** (sesiones, puntos fotométricos,
curva, cadencia). El observatorio participa en las **campañas del grupo
obsSN** (WeSb 1, T CrB, y una historia de campañas finalizadas con SNs,
novas enanas, cefeidas, EE Cep o un blázar): campañas con objetivo
científico, cadencia («cada noche posible; una medida por noche y filtro»),
estrellas de comparación prescritas y reporte fotométrico con hora juliana
heliocéntrica (HJD) vía formulario del grupo.

**Decisión** (entrevista 2026-09-11, decisiones V-a…V-n del plan maestro):

1. **Kind `variable` genérico**: toda variable fotométrica; el tipo concreto
   llega de VSX o manual y solo informa ficha/narrativa. Reutiliza sin
   cambios `followup.py`, `series.py` (quick-look, V-g),
   `photometry_import.py`, la curva con plegado por fase y la pestaña
   Follow-up (`FOLLOWUP_KINDS`).
2. **Campaña = entidad 1:N ortogonal** (tabla `campaigns`, migración
   `user_version` 7 + `projects.campaign_id` con `ON DELETE SET NULL`):
   `{name, group_name, coordinator, goal, protocol JSON {cadence_nights,
   filters[], comp_stars[], notes}, report_url, data_url, status,
   created, closed_at}`. Cualquier kind puede colgar (las campañas obsSN
   mezclan SNs y variables); los objetivos pueden no estar en ningún
   catálogo.
3. **Tonight 100 % local**: fase planner `campaigns` — solo proyectos de
   campañas **activas con cadencia vencida** (o nunca visitados) y visibles
   esta noche (`due_campaigns` + `_visibility`); sin red, sin catálogo
   genérico. Al día = no aparece.
4. **Datos de la estrella: VSX → SIMBAD → manual**. La API del VSX vive en
   el subdominio `vsx.aavso.org` (`view=api.object&ident=…&format=json`):
   **el www está tras Cloudflare y bloquea clientes** (verificado
   2026-09-11). Caché 7 días. WeSb 1 no está en VSX → SIMBAD ancla las
   coordenadas → manual si nada lo conoce. El alta nunca rompe Tonight.
5. **Predicción de extremos en v1**: `next_extremum(period_d, epoch_mjd)`
   (máximo para pulsantes; mínimo para eclipsantes — en VSX la época **es**
   el mínimo; primer componente del tipo decide: `EA/EB/EW/E…` → mínimo,
   resto (incluido `ELL`) → máximo). Eclipsantes: solo la fecha del mínimo,
   sin ventana horaria estilo tránsito.
6. **Asesor de eventos (V-h)**: `detect_event` compara el último punto
   propio con la mediana de los anteriores **por filtro** (≥4 puntos, nunca
   con `survey:*`): |Δ| ≥ `event_mag_threshold` (0.5 por defecto) → aviso en
   Follow-up + boost de urgencia en Tonight. Es el protocolo de WeSb 1 («si
   cae el brillo, sube la cadencia») hecho software.
7. **Contexto de surveys** (cierra la opción B12 de SN): botón bajo demanda
   en Follow-up → **ALeRCE ZTF API v1** (`api.alerce.online/ztf/v1/`,
   verificado 2026-09-11) → puntos grises `source="survey:ztf"` que los
   renderers ya estilizan; nunca se mezclan con los propios; descarga
   idempotente.
8. **Reporte fotométrico**: por proyecto, CSV documentado
   (`name,hjd,mag,err,filter,comp_stars,observer,notes`) y **AAVSO Extended
   File Format**, con **HJD calculado en la app**
   (`jd_to_hjd`: `HJD = JD + (n̂·ŝ)·r·τ`, Sol de Schlyter de `ephem_minor`,
   τ = 499.004784 s/UA; referencias congeladas en los tests: WeSb 1 +250.09 s,
   T CrB −196.45 s). Los puntos quick-look solo exportan con checkbox
   explícito (T6).
9. **[Superseded 2026-09, Track UX]** ~~Gestor de campañas = diálogo
   modal~~ → **pestaña «Campaigns»** (5ª pestaña, maestro-detalle como el
   hub): la auditoría de usabilidad mostró que el diálogo era un selector
   sin detalle (no se podía ni abrir una campaña). La pestaña muestra la
   salud de cada campaña (miembros × cadencia × eventos, nueva query
   `campaign.status_report`), enlaces bidireccionales (badge en la
   cabecera del proyecto, chip ⚑ en Tonight, chips de cadencia → Follow-up)
   y las acciones CRUD con feedback nunca silencioso. Los sub-diálogos
   (crear/editar, añadir objetivo) se conservan. Lo demás de la decisión
   sigue vigente: (menú Herramientas + botón en el hub):
   activas/finalizadas, crear/editar/finalizar/reabrir, alta de objetivos
   y adjuntar proyectos existentes. ~~Sin pestaña nueva~~ Campañas
   **personales** (sin export/import en v1).

**Alternativas consideradas**:

- *VSX en el dominio www*: descartado — Cloudflare challenge (403) para
  clientes sin navegador (verificado).
- *Campaña como JSON en `project.context`*: descartado — no consultable
  para el bucle de Tonight ni lista de campañas propia; el patrón de
  migración ya estaba establecido (v5/v6).
- *Catálogo genérico de variables con score (fase planner con red)*:
  descartado en v1 — la noche se llena por compromiso propio (campañas), no
  por descubrimiento.
- *Ventana horaria de eclipse estilo tránsito*: v2.
- *Monitor de flujo en vivo*: aparcado (ADR-034 H-l; FotoDif AUTO cubre el
  directo).

**Consecuencias**: +2 fuentes de red (ambas con caché y degradación elegante),
+1 migración (v7, guardada e idempotente), el chip de cadencia de Tonight se
restringe a SN **sin** campaña (los que la tienen ya salen en la lista vía
planner). El ejecutor del plan es un modelo local pequeño: los subplanes
llevan código y tests completos y la regla «ancla que no coincide → parar y
reportar».

## English

**Context**: HADS stars (ADR-034) opened variable-star photometry but are
the short-period exception. Long-period variables follow the **multi-night
Track-B supernova mold**. The observatory joins the **obsSN group's
campaigns** (WeSb 1, T CrB…): science goal, cadence ("one measurement per
night and filter"), prescribed comparison stars and photometric reports with
heliocentric Julian dates via the group's form.

**Decision** (interview 2026-09-11, decisions V-a…V-n of the master plan):

1. **Generic `variable` kind** reusing the Track-B machinery unchanged
   (followup, series quick-look, photometry import, phase-folded curve).
2. **Campaign = orthogonal 1:N entity** (migration v7: `campaigns` table +
   `projects.campaign_id` with `ON DELETE SET NULL`). Any kind can join;
   targets may exist in no catalogue.
3. **Tonight is 100 % local**: a `campaigns` planner phase surfaces only due
   projects of active campaigns that are visible tonight. Up to date = not
   listed.
4. **Star data: VSX → SIMBAD → manual.** The VSX API lives on the
   `vsx.aavso.org` subdomain — **www is behind Cloudflare and blocks plain
   clients** (verified 2026-09-11). 7-day cache; WeSb 1 is not in VSX, hence
   the SIMBAD anchor and manual entry.
5. **Extremum prediction in v1**: next maximum (pulsating) / minimum
   (eclipsing — the VSX epoch *is* the minimum; the first type component
   decides). No transit-style eclipse window.
6. **Event advisor**: latest own point vs. the per-filter median (≥4 points,
   never survey context) → Follow-up warning + Tonight urgency boost.
7. **Survey context** (closes the B12 option): on-demand ALeRCE ZTF points,
   grey, `source="survey:ztf"`, never mixed, idempotent.
8. **Photometric report**: per-project CSV + AAVSO EFF with **in-app HJD**
   (Schlyter Sun; frozen reference values in tests). Quick-look points only
   with an explicit checkbox.
9. **[Superseded 2026-09, Track UX]** ~~Campaign manager = modal
   dialog~~ → **the "Campaigns" tab** (5th tab, master-detail like the
   hub): the usability audit showed the dialog was a selector with no
   detail view. The tab shows each campaign's health (members × cadence
   × events, new `campaign.status_report` query), bidirectional links
   (project header badge, ⚑ Tonight chip, cadence chips → Follow-up)
   and CRUD actions with non-silent feedback. The sub-dialogs survive.
   Still in force (Tools menu + hub button): personal campaigns, no
   sharing in v1.

**Alternatives considered**: www-hosted VSX API (Cloudflare-blocked),
campaign as context JSON (not queryable), generic variable catalogue with
scoring (out of v1), transit-style eclipse windows (v2), live flux monitor
(parked, ADR-034 H-l).

**Consequences**: +2 cached network sources with graceful degradation, +1
guarded idempotent migration, the Tonight cadence chip narrows to
campaign-less SNs. The plan is executed by a small local model: subplans
carry complete code and tests, and the "anchor mismatch → stop and report"
rule applies.

**Revisión / Revision**: rev. 2026-09-13 — ejecutado completo (40
subplanes, fases V0→VE); suite unitaria verde (**1096**); i18n 714 cadenas
ES/EN sin pendientes.
