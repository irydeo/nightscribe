# HADS stars in NightScribe — field guide & references

Bilingual twin: [`HADS.es.md`](HADS.es.md) (Spanish). Implementation plan:
[`PLANS/hads-stars.md`](PLANS/hads-stars.md). Decision record:
[`adr/ADR-034-hads-stars.md`](adr/ADR-034-hads-stars.md).

This file is the *research dossier* for the HADS feature: the science, the
data files bundled in the repo, the design rationale (transits vs. HADS) and
the reference trail — so that any human or AI agent can keep working on it
without re-doing the investigation.

---

## 1. What a HADS star is

**HADS** = **H**igh-**A**mplitude **D**elta **S**cuti star, a subclass of
δ Scuti pulsating variables. They sit at the intersection of the classical
instability strip and the main sequence (early F to late A spectral types).

Key physical facts that drive the feature design:

| Property | Value | Source |
|---|---|---|
| Pulsation periods | ~1–3 h (class up to ~6 h) | Kotysz 2020; McNamara 2000 |
| Peak-to-peak amplitude | ≥ 0.3 mag in V for the HADS subclass (class δ Scuti starts at > 0.1) | AAVSO VSO; OGLE |
| Light-curve shape | Asymmetric "sawtooth": fast rise, slow decline | OGLE atlas |
| Modes | Mostly fundamental (F) radial; some double-mode F + first overtone (period ratio 0.76–0.78, Petersen diagram); very few triple-mode | Kotysz 2020; Wils et al. 2008 |
| Anything else | Some are multiperiodic / show non-radial modes | Kotysz 2020; catalog flags |
| History | Once called "dwarf Cepheids" (shapes resemble Cepheids) | OGLE |

Because periods are 1–5 h and amplitudes ≥ 0.3 mag, **a full light curve is
captured in a single short night** — you literally watch a star change
brightness in real time. AAVSO recommends a HADS star as the **perfect first
target for digital photometry** ("Your First Observing Target"), with images
every ≤ 15 min to follow the curve.

Amplitude caveat: for **visual** observers AAVSO advises ΔV ≥ 0.5 mag; smaller
amplitudes need photometry.

## 2. The reference figure: Patrick Wils

**Patrick Wils** is a Belgian amateur astronomer and a world reference in the
study of variable stars. He coordinates the long-term photometric monitoring of
HADS stars linked to the Belgian **Vereniging Voor Sterrenkunde (VVS)**, and he
is part of the technical team of the **AAVSO VSX** (International Variable
Star Index) — co-compiler, together with Sebastián Otero, Patrick Schmeer and
Klaus Bernhard, of the index's million-plus objects. His catalogues of
double-mode and triple-mode δ Scuti stars (Wils et al. 2008) are cited across
the literature. The HADS target list bundled with NightScribe comes from his
monitoring programme.

### References (verbatim)

1. **HADS** — talk, BAV meeting, Hamburg 2016:
   https://www.bav-astro.eu/images/BAV_Tagungen/Hamburg_2016/04_HADS.pdf
2. **AAVSO — 20 million observations milestone**:
   https://www.aavso.org/20-million-observations
3. **VSX — About variable types**:
   https://vsx.aavso.org/index.php?view=about.vartypes
4. **Wils / variable stars (austriaca.at)**:
   https://www.austriaca.at/0xc1aa5572%200x00166b7b.pdf
5. **BAA — Short Period Pulsator Program**:
   https://britastro.org/forums/topic/short-period-pulsator-program

### Supplementary sources consulted (for the narrative and scoring)

- Wils, P. et al. 2008 — double/triple-mode HADS classification (cited in
  arXiv:2510.24444: "Wils et al. (2008) list only four known HADS that pulsate
  in three radial modes simultaneously").
- VSX founding paper bibcode: `2006SASS...25...47W`.
- AAVSO — "Delta Scuti and the Delta Scuti variables" (Variable Star of the
  Season) https://www.aavso.org/vsots_delsct
- AAVSO — "Your First Observing Target" (HADS as first photometry target)
  https://wp-test.aavso.org/your-first-observing-target
- OGLE Atlas of variable star light curves — δ Scuti
  https://ogle.astrouw.edu.pl/atlas/delta_Sct.html
- Kotysz, K. 2020, "Variability of HADS stars in TESS", PTA Proceedings, vol.
  10, 180–182, pta.edu.pl/proc/v10p180
  — URL only (PDF not committed, ~9.7 MB). Key content extracted in §4.

## 3. Data files in the repo

### Source of truth & refresh (2026-09-11, decision H-b/H-j)

The **live catalog is Patrick Wils' Google Sheets workbook**:
<https://docs.google.com/spreadsheets/d/1oGA2HaEHE8L6eX19ZoHqQQTu0LYV56HX3Srg7oCtOHo/>
— public, one tab per year (2010…now), updated daily. NightScribe downloads it
at runtime as `.xlsx` (the only export carrying the font colors), caches it
12 h via `core/db.py` and parses it stdlib-only in `core/sources/hads_sheet.py`
(two-level cache: raw XLSX + parsed JSON, so the ~1-2 s parse happens once a
day). The bundled CSV below is the **offline fallback and alias source**; the
merge lives in `core/hads.py` (`catalog()`).

**Color legend** (star name / coordinates font color in the workbook):

| Color | Meaning | Priority |
|---|---|---|
| Red name | period changes found | **Priority!** |
| Orange name | period changes possible | **Priority!** |
| Blue coordinates | not yet observed in the programme | opportunity (+6) |
| Purple name | multiple pulsation modes (observe on consecutive nights) | none |

To refresh the bundled snapshot when it drifts: run the functional test and
read its informational drift report —
`.venv/bin/python -m pytest tests/functional -k hads_live -s` — then hand-edit
the few drifted rows (periods/magnitudes; the colors never live in the CSV,
they come from the live sheet at runtime).

### `nightscribe/assets/HADS-stars.csv` (runtime catalog, v1)

168 stars. **ASCII, CRLF line endings, some `Name` fields are quoted** (they
contain commas inside `(=…=…)` aliases). Columns:

| Column | Example | Notes |
|---|---|---|
| `Name` | `GP And (=GSC 01739-01964)` | primary + parseable aliases; may carry trailing flags: `, multiperiodic?`, `-- Non-radial`, `-- change in amplitude?` |
| `RA` | `00 55 18.1` | `HH MM SS.s` → degrees |
| `DEC` | `+23 09 49` | `±DD MM SS` → degrees |
| `Max` | `10.4` | magnitude at maximum |
| `Min` | `11` | magnitude at minimum |
| `Period_h` | `1.89` | period in hours |

Derived: `amp = Max − Min`, `mag_median = (Max+Min)/2`.

Copy source: the observatory workspace `/home/boreal/Develop/astronomy/ns-hads`
(snapshot; the live sheet above is fresher and wins at runtime — see
§Source of truth & refresh).
Attribution added to `nightscribe/assets/ATTRIBUTION.txt`.

### `nightscribe/assets/hads-coverage/HADS-Project-YYYY.csv` (2011–2026, stretch data)

The same star list plus **12 monthly columns** whose cells hold comma-separated
observer codes (e.g. `JH`, `dsu08`, `pv28`, `SD28`, `CKH`). This is the real
**monthly coverage** of Wils' monitoring programme: who measured which star in
which month. Header row ends with stray `/,,,/` columns (ignore; likely an
artifact of the authoring tool). Planned use (stretch): an "nobody is covering
this star this month" urgency signal. Beware it is a **snapshot** that goes
stale; refresh = replace the asset.

## 4. Science extracted from the Kotysz poster (v10p180)

URL: https://pta.edu.pl/proc/v10p180 — "Variability of HADS stars in TESS",
Krzysztof Kotysz (Astronomical Institute, University of Wroclaw). PTA
Proceedings, Oct 2020, vol. 10, pp. 180–182.

- A sample of ~29 HADS + SX Phe stars from TESS sectors 1–4 was analyzed
  (proposal of 213 such stars for 2-min cadence).
- Pulsation types found: (i) single-mode with harmonics only; (ii) double-mode
  with period ratio 0.76–0.78 (fundamental + first overtone); (iii) single or
  double-mode with additional (likely non-radial) modes; some low-frequency
  terms interpretable as g modes.
- Example non-radial HADS: ASAS 032246-7237.8 = TIC 431589510, main frequency
  f1 = 8.1919 d⁻¹ (period ≈ 0.12207 d ≈ 2.93 h), amplitude 81.7 ppt, with at
  least three non-radial modes below 0.6 ppt.
- Light-curve shapes studied via Fourier decomposition (R21, φ31); two stars of
  the sample turned out to be RR Lyrae.
- The final sample will include ~300 HADS/SX Phe stars; the Petersen diagram
  separates them from Cepheids and RR Lyrae.

## 5. Design: transits vs. HADS

| | Exoplanet transits (existing) | HADS (new) |
|---|---|---|
| Event | Predictable `t0 + n·P` | **No known phase**: only the cycle period |
| Catalog data | `t0`, `period`, `duration_h` | `period_h`, `Max`/`Min` range |
| Observability gate | star above horizon **at mid-transit** | star up + **contiguous window with ≥ 1 full cycle** (2 recommended) |
| Capture advice | baseline + transit + baseline | **continuous 2×P** capture (confirm repeat + fold) |
| Key metric | transit coverage (ingress/mid/egress) | **complete cycles = hours_up / P** |
| Cadence | resolve ingress (≥ 3 points) | **≥ 12 points/cycle**, ≤ 15 min real (AAVSO) |
| Outcome | light curve of the transit | **watch the star pulsate live** |

Core module: `core/hads.py` (built on `core/transits.py` patterns —
`coords.samples_tonight`, horizon gate + margin per ADR-020). No `t0`, no
phase, no epoch in v1. If a future version enriches via the VSX API, VSX stores
an `Epoch` (HJD of max/min) which **would** enable transit-style maximum
prediction — a documented stretch.

See [`PLANS/hads-stars.md`](PLANS/hads-stars.md) for the full integration map
(file-by-file, scoring, GUI, projects, tests, phases).