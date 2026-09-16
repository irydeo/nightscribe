# ADR-037: Campañas = consola de señales; eventos de estrellas variables en tres pisos (detectados, predichos, vigilias)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-16 · **Revisión / Review**: 2026-09-16 (re-scope de SC4, mismo día) · **rev. 2 (mismo día, hallazgo del spike)**: el backend de las vigilias se elige **por brillo** — ver abajo · **ejecutado completo el mismo día**: SC1–SC3 (`fcdf443`/`f96b2e6`/`50bdf58`) + SC4a/SC4b — suite unitaria 1244

**Ver / See**: [docs/PLANS/signals-campaigns.md](../PLANS/signals-campaigns.md)
(plan del track) · ADR-035 (variables y campañas, cuyo rol de pestaña se
enmienda aquí) · ADR-036 (decidido en la misma sesión: Diario y Sol y cielo).

## Español

**Contexto**: cerrado el Track UX, la revisión de la app con el observador
(2026-09-16) detectó dos problemas:

1. **Solapamiento funcional Proyectos ↔ Campañas**. El concepto está bien
   definido (ADR-035, `docs/CAMPAIGNS.es.md`: campaña = compromiso compartido
   con protocolo; proyecto = ciclo de trabajo de un objeto), pero la pantalla
   no lo defiende: ~80 % de la pestaña Campañas es la **tabla de miembros**,
   funcionalmente «el hub de Proyectos filtrado por campaña» — y el hub ya
   tiene filtro de campaña (persistente, U0.6). Síntoma: la pestaña necesita
   un párrafo en cursiva (`lbl_what`) *explicando* la diferencia; si hay que
   explicarla, no se sostiene sola.
2. **Los eventos de variables apenas se muestran**. El detector de eventos
   (`variables.detect_event`) solo es visible dentro de la campaña
   seleccionada (tabla de miembros) y en Tonight **solo cuando el proyecto
   está vencido** — `due_campaigns` filtra por cadencia *antes* de evaluar el
   evento, así que una caída detectada en un proyecto al día nunca sale en
   Tonight (el protocolo WeSb 1, «si ves una caída, sube la cadencia», no se
   honra). Los extremos previstos (`variables.next_extremum`, época VSX) se
   calculan cada noche pero no tienen superficie agregada. Y el add-on
   aprobado el 2026-09-12 (lista destacada + extremos predecibles + vigilias
   T CrB/R CrB) sigue sin planificar, pese a que `core/sources/surveys.py`
   (ZTF vía ALeRCE) ya existe como fuente cacheada.

**Decisión**:

1. **Campañas = consola de señales del compromiso** (no se fusiona ni se
   renombra): gana una **caja de «Señales» agregada** (eventos ⚡ y extremos
   ⏳ de todos los miembros, no solo del seleccionado) y un **resumen de
   cobertura** («N de M al día»). La tabla de miembros queda subordinada como
   vista de salud; objetivo, protocolo y URLs se conservan. La distinción se
   sostiene por función: **Proyectos = ejecutar** (un objeto, sus pasos),
   **Campañas = monitorizar** (salud y señales del esfuerzo compartido).
2. **Tonight honra la ciencia antes que la cadencia**: la fase `campaigns`
   del planner lista un proyecto de campaña cuando está vencido **o** tiene
   un evento detectado **o** un extremo inminente (ventana configurable
   `campaign_extremum_days`, defecto 3 días).
3. La regla de terminología del Track UX se mantiene intacta: un miembro de
   campaña siempre se llama *proyecto*; *target* se reserva a los candidatos
   de Tonight.

### Taxonomía de eventos de variables que se muestran

Tres pisos, todos visibles en Tonight y en la consola de Campañas:

| Piso | Tipo de evento | Qué es / ejemplos | Regla y origen del dato | Dónde se muestra |
|---|---|---|---|---|
| **Detectados** ⚡ | **Caída de brillo** | La estrella se debilita: inicio de descenso de R CrB, dip de WeSb 1, eclipse | Fotometría **propia**: por filtro, último punto vs mediana de los anteriores, ≥4 puntos, Δ ≥ `event_mag_threshold` (defecto 0,5 mag). Eje de magnitudes invertido: caída = Δ positiva. Solo fuentes propias (`manual`/`paste`/`file`/`quicklook`); nunca puntos de surveys (distinto cero fotométrico) | Fila de Tonight (frase líder «¡Posible descenso…!» +10 urgencia) **aunque el proyecto esté al día**; caja de Señales; estado del miembro (⚡) |
| | **Subida / erupción** | La estrella se intensifica: erupción de nova enana (SS Cyg), nova recurrente (T CrB) | Misma regla, Δ negativa | Ídem, con frase «¡Posible erupción…! Máxima prioridad esta noche» |
| **Predichos** ⏳ | **Máximo esperado** | Pulsantes y eruptivas (Mira, SS Cyg…) alcanzan su máximo | `next_extremum` sobre periodo + época VSX (cómputo local nocturno, sin red). **Convención VSX**: la época marca el máximo salvo en eclipsantes | Saca la fila a Tonight dentro de la ventana `campaign_extremum_days`; chip «máximo en N d»; línea en la caja de Señales; +5 de gancho (ya existente) |
| | **Mínimo esperado** | Eclipsantes (EA/EB/EW…): el mínimo primario es el momento de medir (por eso la app calcula HJD) | La época VSX marca el **mínimo** en tipos E, EA, EB, EW, E/, E-; en tipos compuestos decide el primer componente («NR+ELL» → máximo) | Ídem, chip «mínimo en N d» |
| **Externos (vigilias)** 👁 | **Vigilia de erupción** | T CrB y novas recurrentes: alerta al primer signo de subida | Última magnitud ZTF (ALeRCE, `core/sources/surveys.py`, caché 30 d) frente a la línea base de la estrella; anomalía → alerta. **Lista de vigilias configurable** | Fila de alerta en Tonight (aunque la estrella no tenga proyecto) + señal en la consola |
| | **Vigilia de caída** | R CrB y similares: alerta al inicio del descenso | Ídem, signo contrario | Ídem |

**Fuera de alcance (se mantiene del Track V)**: AAVSO Alert Notices y
ASAS-SN Sky Patrol; no hay feed genérico de «cualquier variable del cielo».
Tonight sugiere desde **tus compromisos** (campañas), el **catálogo HADS**
(fase propia) y **tu lista de vigilias** — no desde el VSX entero (~2M de
estrellas).

**Consecuencias**: enmienda el rol de la pestaña en ADR-035 (la decisión 9
ya fue superseded por el Track UX; aquí se redefine su *función*).
`suggest` apenas cambia (los boosts +10 evento / +5 extremo ya existen; solo
cambia *quién llega listado*). Núcleo nuevo: la agregación de señales
(query sobre `status_report` + `next_extremum`) y el chequeador de vigilias
(fuera de `surveys.py`, sin red en el hilo GUI — patrón `SurveyWorker` del
Track UX). El Diario de ADR-036 registrará los eventos ⚡ como entradas de
la noche. Ejecución por fases SC1→SC5 en
[docs/PLANS/signals-campaigns.md](../PLANS/signals-campaigns.md).

**Revisión (2026-09-16, re-scope de SC4 — el mismo día, decidido con el
observador)**: la expectativa del observador es *«que los eventos
relevantes de variables aparezcan en las recomendaciones nocturnas»* — más
amplio que una lista de estrellas configurada a mano. SC4 pasa a ser
**híbrido**, en dos mitades:

- **SC4a — vigilias automáticas** (sin fuente nueva): lista de guardia
  **curada, precargada y editable** (defectos: T CrB → vigilia de erupción,
  basal ~10,2 V; R CrB → vigilia de caída, basal ~5,8 V) chequeada contra
  la última magnitud ZTF vía ALeRCE (`surveys.py`). La vigilia necesita el
  *último* punto, así que usa **clave de caché propia con TTL corto
  (~12 h)** — nunca la caché de contexto de 30 días. Una anomalía levanta
  una fila en Tonight (filtrada por el horizonte, como todo) y una señal en
  la consola. **Regla de fusión**: si la estrella ya es proyecto (p. ej. el
  T CrB del observador en el grupo obsSN), la vigilia se suma a las razones
  de listado de ese proyecto con procedencia 👁 — nunca una fila duplicada.
- **SC4b — el canal editorial AAVSO** (arriba figuraba *fuera de alcance* —
  **entra en alcance** aquí): las alertas AAVSO (la categoría *Alerts* del
  foro es Discourse, con JSON nativo por categoría, parseable con la
  stdlib) y la app de Observing Campaigns. La **primera tarea de SC4b es un
  spike de validación**: si el JSON/apps no son consumibles, SC4b se acota
  a lo viable y se documenta el resultado. Las estrellas se resuelven a
  coordenadas vía VSX (ya en la app) y se filtran por horizonte; las filas
  de Tonight llevan la procedencia «AAVSO» y la misma regla de fusión.
  Sigue fuera de alcance: ASAS-SN Sky Patrol (demasiado ruido para la
  filosofía de la app).

**Revisión 2 (2026-09-16, hallazgo del spike en vivo)**: la fuente de las
vigilias pasa a elegirse **por brillo**. Verificado contra el catálogo
vivo: ni T CrB (10,2 V) ni R CrB (5,8 V) — ni SS Cyg/SU Tau en sus
brillos habituales — tienen objeto en ALeRCE/ZTF, porque **ZTF satura por
debajo de ~11-12 mag** (el conesearch funciona en otros campos; en esas
posiciones simplemente no hay objeto). Diseño resultante: vigilias con
basal < `BRIGHT_LIMIT` (11,5) leen la **fotometría de la comunidad AAVSO**
(`GET /v2/api/observations/photometry/`, endpoint oficial con token de API
del usuario — 401 sin él; latencia de horas, mejor que la de surveys); las
débiles siguen con ZTF/ALeRCE. Sin token configurado, las vigilias
brillantes permanecen en silencio (degradación amable, documentada en la
ayuda del editor). ASAS-SN Sky Patrol se evaluó como backend alternativo
de brillantes y estaba **inalcanzable** durante el spike (timeout); queda
como opción futura si se valida en vivo.

## English

**Context**: with the UX track closed, a review of the app with the observer
(2026-09-16) surfaced two problems:

1. **Functional overlap between Projects and Campaigns**. The concept is
   well defined (ADR-035, `docs/CAMPAIGNS.md`: campaign = shared commitment
   with a protocol; project = one object's work cycle), but the screen does
   not defend it: ~80 % of the Campaigns tab is the **members table** —
   functionally "the Projects hub filtered by campaign", and the hub already
   has a campaign filter (persisted, U0.6). Telltale symptom: the tab needs
   an italic paragraph (`lbl_what`) *explaining* the difference; if it has
   to be explained, the distinction does not stand on its own.
2. **Variable-star events are barely surfaced**. The event detector
   (`variables.detect_event`) is only visible inside the selected campaign
   (members table) and in Tonight **only when the project is due** —
   `due_campaigns` filters by cadence *before* evaluating the event, so a
   drop detected in an up-to-date project never shows in Tonight (the WeSb 1
   protocol, "if a drop is seen, raise the cadence", is not honoured).
   Predicted extrema (`variables.next_extremum`, VSX epoch) are computed
   nightly but have no aggregate surface. And the add-on approved on
   2026-09-12 (featured list + predictable extrema + T CrB/R CrB vigils) is
   still unplanned, even though `core/sources/surveys.py` (ZTF via ALeRCE)
   already exists as a cached source.

**Decision**:

1. **Campaigns = the commitment's signals console** (not merged, not
   renamed): it gains an aggregated **"Signals" box** (⚡ events and ⏳
   extrema of *all* members, not just the selected one) and a **coverage
   summary** ("N of M up to date"). The members table is subordinated as the
   health view; goal, protocol and URLs stay. The distinction now stands on
   function: **Projects = execute** (one object, its steps), **Campaigns =
   monitor** (health and signals of the shared effort).
2. **Tonight honours the science before the cadence**: the planner's
   `campaigns` phase lists a campaign project when it is due **or** has a
   detected event **or** an imminent extremum (configurable window
   `campaign_extremum_days`, default 3 days).
3. The UX track's terminology rule stands unchanged: a campaign member is
   always called a *project*; *target* is reserved for Tonight candidates.

### Taxonomy of the variable-star events that are shown

Three tiers, all surfaced in Tonight and in the Campaigns console:

| Tier | Event type | What it is / examples | Rule and data origin | Where it shows |
|---|---|---|---|---|
| **Detected** ⚡ | **Brightness drop** | The star fades: R CrB starting a decline, WeSb 1 dip, eclipse | **Own** photometry: per filter, latest point vs median of the previous ones, ≥4 points, Δ ≥ `event_mag_threshold` (default 0.5 mag). Inverted magnitude axis: drop = positive Δ. Own sources only (`manual`/`paste`/`file`/`quicklook`); never survey points (different zero point) | Tonight row (leading "Possible brightness drop…!" phrase, +10 urgency) **even when the project is up to date**; Signals box; member status (⚡) |
| | **Rise / outburst** | The star brightens: dwarf-nova outburst (SS Cyg), recurrent nova (T CrB) | Same rule, negative Δ | Same, with "Possible outburst…! Top priority tonight" |
| **Predicted** ⏳ | **Expected maximum** | Pulsating and eruptive stars (Mira, SS Cyg…) reach maximum | `next_extremum` over period + VSX epoch (local nightly maths, no network). **VSX convention**: the epoch marks the maximum except for eclipsing stars | Pulls the row into Tonight within the `campaign_extremum_days` window; "maximum in N d" chip; line in the Signals box; +5 hook (already existed) |
| | **Expected minimum** | Eclipsing binaries (EA/EB/EW…): the primary minimum is the time to measure (which is why the app computes HJD) | The VSX epoch marks the **minimum** for types E, EA, EB, EW, E/, E-; for composite types the first component decides ("NR+ELL" → maximum) | Same, "minimum in N d" chip |
| **External (vigils)** 👁 | **Eruption watch** | T CrB and recurrent novae: alert on the first sign of brightening | Latest ZTF magnitude (ALeRCE, `core/sources/surveys.py`, 30 d cache) against the star's baseline; anomaly → alert. **Configurable vigil list** | Alert row in Tonight (even if the star has no project) + signal in the console |
| | **Fade watch** | R CrB and the like: alert when the decline starts | Same, opposite sign | Same |

**Out of scope (carried from Track V)**: AAVSO Alert Notices and ASAS-SN
Sky Patrol; no generic "any variable in the sky" feed. Tonight suggests from
**your commitments** (campaigns), the **HADS catalogue** (its own phase) and
**your vigil list** — not from the whole VSX (~2M stars).

**Consequences**: this amends the tab's role in ADR-035 (its decision 9 was
already superseded by the UX track; here the tab's *function* is redefined).
`suggest` barely changes (the +10 event / +5 extremum boosts already exist;
only *who gets listed* changes). New core pieces: the signals aggregation
(a query over `status_report` + `next_extremum`) and the vigil checker
(outside `surveys.py`, no network on the GUI thread — the UX track's
`SurveyWorker` pattern). The journal of ADR-036 will record ⚡ events as
night entries. Execution in phases SC1→SC5 per
[docs/PLANS/signals-campaigns.md](../PLANS/signals-campaigns.md).

**Review (2026-09-16, SC4 re-scope — same day, decided with the
observer)**: the observer's expectation is *"relevant variable-star events
surfaced in the nightly recommendations"*, which is broader than a
hand-configured watchlist. SC4 therefore becomes **hybrid**, in two halves:

- **SC4a — automatic vigils** (no new source): a **curated, preloaded,
  editable** watch list (defaults: T CrB → eruption watch, baseline ~10.2 V;
  R CrB → fade watch, baseline ~5.8 V) checked against the latest ZTF
  magnitude via ALeRCE (`surveys.py`). The vigil needs the *latest* point,
  so it uses its **own cache key with a short TTL (~12 h)** — never the
  30-day context cache. An anomaly raises a Tonight row (horizon-filtered
  like everything else) and a console signal. **Fusion rule**: if the star
  already is a project (e.g. the observer's T CrB from the obsSN group),
  the vigil joins that project's listing reasons with 👁 provenance — never
  a duplicate row.
- **SC4b — the AAVSO editorial channel** (was *out of scope* above — it
  **enters scope** here): AAVSO alerts (the forums' Alerts category is
  Discourse, with native per-category JSON, parseable with the stdlib) and
  the Observing Campaigns app. The **first task of SC4b is a validation
  spike**: if the JSON/apps are not consumable, SC4b is cut down to what is
  viable and the result is documented. Stars are resolved to coordinates
  via VSX (already in the app) and horizon-filtered; Tonight rows carry the
  "AAVSO" provenance and the same fusion rule. Still out of scope:
  ASAS-SN Sky Patrol (too noisy for this app's philosophy).

**Review 2 (2026-09-16, live-spike finding)**: the vigil photometry source
is now chosen **by brightness**. Verified against the live catalogue:
neither T CrB (10.2 V) nor R CrB (5.8 V) — nor SS Cyg/SU Tau at their
usual brightness — have an ALeRCE/ZTF object at all, because **ZTF
saturates brighter than ~11-12 mag** (the conesearch works on other
fields; there is simply no object at those positions). The resulting
design: vigils with a baseline below `BRIGHT_LIMIT` (11.5) read the
**AAVSO community photometry** (`GET /v2/api/observations/photometry/`,
the official endpoint, behind the user's API token — 401 without it;
hours-scale latency, better than surveys); fainter ones keep
ZTF/ALeRCE. With no token configured, bright vigils stay silent
(graceful degradation, documented in the editor's help). ASAS-SN Sky
Patrol was evaluated as the alternative bright backend and was
**unreachable** during the spike (connect timeout); it remains a future
option if validated live.
