# Observation campaigns in NightScribe

Bilingual twin: [`CAMPAIGNS.es.md`](CAMPAIGNS.es.md) (Spanish). Implementation
plan: [`PLANS/variables-campaigns.md`](PLANS/variables-campaigns.md) (model) and
[`PLANS/ux-variables-campaigns.md`](PLANS/ux-variables-campaigns.md) (look & feel).
Decision record: [`adr/ADR-035-variables-campaigns.md`](adr/ADR-035-variables-campaigns.md).

This file explains what a campaign is in NightScribe, how it relates to
projects, and where each piece lives (model, the "Tonight" loop, the tab and
the dialogs) — so any human or AI agent can keep working without re-researching.

---

## 1. Terminology (mandatory wording rule)

| Term | Meaning in NightScribe |
|---|---|
| **Campaign** | The group's *shared commitment*: a science goal, a protocol (cadence, filters, comparison stars) and the report/data URLs. A 1:N entity — many projects hang from it. |
| **Project** | One concrete object with its three-step working cycle from the UX v3 flow: **plan, process, publish** (ADR-019). Any project `kind` can join a campaign. |
| **Target** | **Reserved exclusively for the candidates of the "Tonight" tab** (NEOs, comets, SN candidates, transits…). Never used for a campaign member. |

Historical confusion: the first mock of the tab used "Add target…" to add a
member to a campaign, overloading the two meanings of "target". The wording
rule in force (Track UX of ADR-035): **in the "Campaigns" tab a campaign
member is ALWAYS a *project***; the buttons read "New project… / Attach
project… / Detach…". All new copy is written under this rule; the pre-existing
"Tonight" wording ("Scoring targets…", "Show all targets") is the legitimate
use of *target*.

## 2. What a campaign is (model)

Code: `core/campaign.py` · ADR: [`adr/ADR-035`](adr/ADR-035-variables-campaigns.md)
(decision 2) · migration v7 (`campaigns` + `projects.campaign_id` with
`ON DELETE SET NULL`): deleting a campaign **frees** its projects, it does
not delete them.

Each campaign has:

| Field | Example |
|---|---|
| `name` | "T CrB 2026" |
| `group_name` | "WeSb 1" |
| `coordinator` | a name, or "Observatorio Irydeo (Z41)" |
| `goal` | "measure the full eruption of T CrB" |
| `protocol` (JSON) | cadence_nights, filters, comp_stars, notes |
| `report_url` | the group's web form |
| `data_url` | the repo/URL where data is deposited |
| `status` | `active` / `finished` (+ `closed_at`) |

The `protocol` is a free-form dict (`protocol_get`, keys `cadence_nights`,
`filters`, `comp_stars`, `notes`); NightScribe *reads* the cadence for the
"Tonight" loop but does not try to model the rest — an amateur group's
protocol lives, by design, outside the database (it is only referenced).

## 3. The "Tonight" loop (V-d)

`campaign.due_campaigns()`: for each **active** campaign, each active project
is *due* when its last session is ≥ `cadence_nights` nights old, or when it
was never observed. The planner's `campaigns` phase (100 % local, no net)
surfaces those projects in "Tonight" with visibility; the "Campaigns" tab
shows the full health (`campaign.status_report`): members × cadence × events
(⚡ when `variables.detect_event` flags one).

Real use case that inspired the feature: group variable-star programs (HADS,
see [`HADS.es.md`](HADS.es.md); T CrB in WeSb 1) where several observatories
share one cadenced commitment.

## 4. UI — the "Campaigns" tab and dialogs

| Piece | Where |
|---|---|
| Master-detail tab | `gui/ui/campaigns_tab.ui` (list + detail) |
| Tab logic, project buttons | `gui/main_window.py` (`_refresh_campaigns_tab`, `_camp_new_project`, `_camp_attach`, `_camp_detach`) |
| New-project dialog | `gui/campaigns_dialog.py` → `NewProjectDialog` (resolution chain VSX → SIMBAD → manual, in `core/enrich.py`) |
| Campaign edit dialog | `gui/campaigns_dialog.py` → `CampaignEditDialog` (keeps the wording guidance) |
| i18n catalogs (manual editing mandatory) | `gui/i18n/nightscribe_{es,en}.ts` / `.qm` |

Tab detail: per-row health summary ("N projects · M due", ⚡ when any member
has an event), protocol and URLs, and the projects table with status and
cadence. Buttons:

- **New project…** — `NewProjectDialog`: asks for the name, offers
  "Resolve (VSX/SIMBAD)", and creates a `variable` project linked to the
  campaign.
- **Attach project…** — links an *existing* active project to the campaign.
- **Detach project…** — unlinks without deleting anything.

If a project already exists, `NewProjectDialog` says so explicitly: use
"Attach project…". (That sentence is the direct relief for the confusion
that motivated this UX; see §1.)

### Wording guidelines — why this copy

In the "Tonight" tab the user sees *candidates* ("targets": NEOs, comets, SNs,
transits). In the "Campaigns" tab the user sees their ongoing *projects*.
Using "target" in both tabs is imprecise: a campaign member is not a candidate
for tonight. The help text (the `lbl_what` field) states the rule explicitly
inside the app:

> "A campaign groups the projects of one shared observation effort — several
>  nights, several observatories, one goal (e.g. "T CrB 2026 eruption"). A
>  project is one object with its three steps: plan, process, publish."

## 5. Anchor points (so nothing is lost)

- Model: `core/campaign.py` — CRUD + `due_campaigns` + `status_report`.
- Planner: the `campaigns` phase lives in `core/planner.py` (only due
  projects of active campaigns that are visible; see `due_campaigns`).
- Tab: `campaigns_tab.ui` — Qt context `CampaignsTab` (the name comes from
  the `<class>` in the .ui; the project buttons live only here, translated
  under that context). In "Tonight" a campaign only ever appears as the ⚑
  chip on a target card (tooltip "Part of this observing campaign — click
  to open it"), which jumps to the "Campaigns" tab.
- i18n: `nightscribe_es.ts`/`nightscribe_en.ts` catalogs (hand-edited,
  **do not run `lupdate` in PySide!**), recompile with `pyside6-lrelease`.
- Related ADRs: [ADR-019](adr/ADR-019-projects-ux-v3.md) (the v3 flow,
  the three steps), [ADR-034](adr/ADR-034-hads-stars.md) (the HADS catalogue
  used in real campaigns), [ADR-035](adr/ADR-035-variables-campaigns.md)
  (campaigns).

## 6. References (verbatim)

1. ADR-035, Track UX — the modal manager is replaced by the tab and the
   "targets"→"projects" wording is enforced in the UI; see
   [`adr/ADR-035-variables-campaigns.md`](adr/ADR-035-variables-campaigns.md).
2. UX plan —[`PLANS/ux-variables-campaigns.md`](PLANS/ux-variables-campaigns.md).
3. Original model —[`PLANS/variables-campaigns.md`](PLANS/variables-campaigns.md).
4. v3 flow (the three steps) —[`adr/ADR-019-projects-ux-v3.md`](adr/ADR-019-projects-ux-v3.md).
5. Real HADS case —[`HADS.es.md`](HADS.es.md) (a campaign-style monitoring
   program: cadence, filters, comparisons — exactly what `protocol` models).
