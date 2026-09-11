# Plan — HADS: estrellas δ Scuti de alta amplitud, visibles "en directo"

> **Abierto (2026-09-11)** — nuevo tipo de objetivo en NightScribe, inspirado en
> el programa fotométrico de Patrick Wils (VVS / AAVSO-VSX). Un subplan = un commit.
> **Documentación de fondo**: [docs/HADS.md](../HADS.md) (inglés) y
> [docs/HADS.es.md](../HADS.es.md) (español) — lectura obligatoria antes de
> escribir código nuevo. Decisión registrada en
> [ADR-034](../adr/ADR-034-hads-stars.md).

**rama**: `feature/hads` (nace de `feature/object-card` a día, HEAD e6880c3;
mergea de vuelta a `feature/object-card`)
**fecha**: 2026-09-11 · **autor**: FJC (con la IA)

## Objetivo

Integrar las **estrellas HADS** (High-Amplitude δ Scuti) como nuevo tipo de
objetivo de la noche. Son variables pulsantes con periodos de ~1–5 h y
amplitudes ≥ 0.3 mag en V: **se las puede ver pulsar en directo**. El usuario
apunta, hace fotometría en continuo durante ~2 periodos y obtiene varias curvas
de luz completas en una sola noche. AAVSO las recomienda como **primer objetivo**
de fotometría digital ("Your First Observing Target"). El programa de
**Patrick Wils** monitoriza el catálogo a largo plazo (cobertura mensual
verificable), y los datos se reportan a **AAVSO**.

La infraestructura a reutilizar es la de **exoplanetas** (`core/transits.py`,
el bloque de plan de tránsitos en la GUI, `Outcomes.reported_exoclock`), con
una diferencia conceptual central: **no hay fase conocida**. Para un tránsito
sabemos cuándo ocurre (`t0 + n·P`); para una HADS solo sabemos cuánto dura el
ciclo (`Period_h`), no cuándo es el máximo. Por eso no se recomienda un
"evento", sino una **captura continua de ≥ 2 ciclos**.

## Referencia real

- **Patrick Wils** — astrónomo aficionado belga, figura clave mundial en
  variables: coordina el seguimiento fotométrico HADS vinculado a la VVS
  (Vereniging Voor Sterrenkunde, Bélgica) y forma parte del equipo técnico del
  **VSX de AAVSO** (co-compilador del índice junto a Otero, Schmeer y Bernhard).
  Ref. [1] BAV Hamburg 2016 `04_HADS.pdf`; [2] AAVSO 20 millones de
  observaciones; [3] VSX «about vartypes»; [4] austriaca.at (VSX/variables);
  [5] BAA «Short Period Pulsator Program». Detalle completo y URLs verbatim en
  `docs/HADS.md`.
- **Catálogo**: `nightscribe/assets/HADS-stars.csv` (168 estrellas,
  `Name,RA,DEC,Max,Min,Period_h`), copiado del directorio de trabajo del
  observatorio (programa Wils/VVS).
- **Cobertura mensual**: `nightscribe/assets/hads-coverage/HADS-Project-YYYY.csv`
  (2011–2026) — mismas estrellas + 12 columnas mensuales con códigos de
  observador (quién midió cada estrella cada mes). Dato diferencial para un
  stretch de «urgencia por falta de cobertura».
- **Ciencia**: póster de Kotysz (PTA Proc. vol. 10, 180–182, 2020) — se guarda
  URL + extractos (no el PDF, 9.7 MB); ver `docs/HADS.md`.

## Contexto científico (resumen)

- Familia δ Scuti en la franja de inestabilidad clásica x secuencia principal.
- Periodos del orden de 1–3 h (catálogo: 1.03–4.88 h); amplitud V ≥ 0.3 mag.
- Curvas asimétricas tipo "diente de sierra" (subida rápida, bajada lenta) —
  "dwarf Cepheids".
- Modo fundamental (F) y primer overtone (1O), ratio de periodos 0.76–0.78
  (diagrama de Petersen); raras triple-modo (Wils et al. 2008 listó 4).
- Algunas son **multiperiódicas** o **no-radiales** (el catálogo las marca).
- TESS proveyó curvas superbias; Fourier + Petersen = análisis estándar
  (Kotysz 2020).
- AAVSO: observación cada ≤ 15 min para seguir la curva; amplitud < 0.5 mag
  no apta para visual.

## Contexto clave de código (exploración 2026-09-11)

El "kind" se propaga por capas. Todo lugar donde se ramifica por kind necesita
la rama `"hads"`. Mapa completo:

- **Core**:
  - `core/planner.py:28` — `PHASES` (añadir `"hads"` antes de `"scoring"`).
  - `core/suggest.py:35-51` — `_scientific`; `:162-188` `_urgency`;
    `:191-226` `_hook`; `:272-420` `_fragments`; `_observability:60-91`.
  - `core/project.py:33` — `VALID_KINDS`; `:49` `OUTCOMES`
    (par `("completed","reported_aavso","abandoned")`).
  - `core/enrich.py:27-40` — `detect_type` (rama hads: si el nombre está en el
    catálogo empaquetado → `data["hads"]`).
  - `core/narrative.py` — `hook()` y `fact_bullets()` (rama hads).
  - `core/orbits.py` — `explain_hads()` para la tabla de parámetros.
- **GUI**:
  - `gui/theme.py:36-49` — `KIND_COLORS` + `KIND_LABELS`.
  - `gui/main_window.py:175` — `KIND_ORDER`; `:143-171` `TABLE_COLS`;
    `:1399-1403` etiqueta en `_table_value`; `:771-835` `_type_pixmap`
    (icono); `:2797-2953` modelo del bloque de tránsitos para el bloque hads;
    `:2351-2365` `_ccd_coords_text` y `:2389-2400` `_ccd_point_action`
    (**hads = coordenadas fijas**, NO entra en "moving");
    `:4118-4127` whitelist de ctx en `_create_project`;
    `:1568` filtro de proyectos y `:1603` etiqueta en lista.
  - `gui/overview.py:648-673` `_orbit_rows`; `:955-1065` `_capture_chips`.
  - `gui/i18n/*.ts` + `gui/ui/settings_dialog.ui` + `gui/ui/projects_tab.ui`:
    checkbox, cadena de fase y item de combo.
- **Config**: `config.py:58` `enabled_kinds` (añadir `"hads"`; migración
  amable: si el valor guardado es el antiguo default de 6, añadir hads).
- **CLI**: `__main__.py:345` help de `project --kind`; `cmd_tonight` ya
  imprime `[kind]` genérico.
- **Assets**: patrón de carga `Path(__file__).parent.parent / "assets"`
  (usado por `gui/theme.py:29` y `gui/moon_icon.py:39`). El instalador
  (`installer/nightscribe.spec:28`) ya recoge `nightscribe/assets/*`;
  falta `pyproject.toml` `package-data` → `"nightscribe" = ["assets/*"]`.
- **Exposición**: `core/exposure.py:127` `recommended_transit_exposure`
  (reutilizable/envoltorio delgado para hads).

## Decisiones pactadas

| # | Decisión | Valor |
|---|----------|-------|
| H-a | **Sin fase conocida → captura continua** | No existe t0 ni máx predecible con el catálogo actual. La recomendación es **2×P** de captura continua (verlo repetir + plegar). Gate = visibilidad + **ventana contigua con ≥ 1 ciclo** (2 para la recomendación). |
| H-b | **Catálogo empaquetado, sin red** | `HADS-stars.csv` viaja como `nightscribe/assets/`. Funciona offline (filosofía observatorio). Refresco manual/documentado. |
| H-c | **métrica clave `cycles`** | `cycles = hours_up / Period_h` (ciclos completos que caben esta noche). Alimenta score, frases y el bloque de plan. |
| H-d | **Cadencia recomendada** | ≥ 12 puntos/ciclo → `cadence_s = Period_h·3600/12`, cap ≤ 15 min reales (regla AAVSO). |
| H-e | **mag del target = mediana** | `mag = (Max+Min)/2` para el filtro de magnitud (la fase es desconocida); el **rango Max–Min y la amplitud** siempre visibles en la ficha. |
| H-f | **Reporte → AAVSO** | Outcome `reported_aavso` (paralelo de `reported_exoclock`). Config ya tiene `aavso_code`. |
| H-g | **Proyecto = flujo genérico** | `plan → process → publish`; process v1 = enlace/instrucciones a fotometría + AAVSO WebObs. |
| H-h | **hads = coordenadas fijas** | Epoch ≈ ahora; NO va en los kinds "moving" del CCDciel. |

## Diseño del módulo núcleo (`core/hads.py`)

Plantilla: `core/transits.py` (visibilidad por `coords.samples_tonight` /
`planner._visibility`, gate con umbral del horizonte + margen, ADR-020).

- `catalog()` → dicts: `{name, alt_names, ra_deg, dec_deg, max, min, amp,
  period_h, multiperiodic, non_radial}`. Parseo del CSV con `csv`:
  **CRLF + campos con comillas** (`","` en el Name), `RA`/`DEC` sexagesimales,
  flags: `multiperiodic`, `Non-radial`, `change in amplitude?` (regex sobre
  el `Name`). Robustez: filas malformadas se saltan con `logger.debug`.
- `hads_tonight(stars, lat, lon, date=None, threshold_fn=None, min_alt=None,
  max_vmag, margin, cycles_needed=2, session_duration_s=None)` → por estrella:
  `{name, ra_deg, dec_deg, mag(mediana), max, min, amp, period_h, max_alt,
  hours_up, cycles, window_start/end, session_req_h(2P), session_fits(bool),
  cadence_s, exp_s, flags}`.
- `session_fits`: ¿cabe 2×P continua dentro de la franja segura? (mismo
  espíritu que `baseline_fits` del tránsito).
- `recommended_hads_exposure(v_mag, plate_scale=None)` → envoltorio de
  `exposure.recommended_transit_exposure` (fotometría de comparación).

## Integración por fases

### Fase A — Núcleo (scoring + planner + tests)
1. `pyproject.toml`: `package-data` += `"nightscribe" = ["assets/*"]` (el
   instalador ya los recoge).
2. `core/hads.py` nuevo + unit tests de parseo/lógica.
3. `planner.py`: `PHASES` + `"hads"`; `_hads_targets(...)` (rama de
   `_visibility`, `on_phase` label en GUI).
4. `suggest.py` ramas:
   - `_scientific`: `clamp(amp/0.9·20) + clamp((18 − mag_med)/10·15)`.
   - `_observability`: altitud + horas + mag (genérico) + bonus
     `clamp(cycles/5·6,0,6)`; si `session_fits is False` → −4 (patrón
     `baseline_fits`).
   - `_urgency`: 0 en v1 (sin cobertura; ver stretch).
   - `_hook`: prototipos famosos en el catálogo (CY Aqr, DY Peg, SZ Lyn, XX Cyg,
     V2455 Cyg…) + `amp >= 0.5` + `multiperiodic`.
   - `_fragments`: «periodo P h, amplitud Δ», «cabrán N ciclos esta noche»,
     «la verás pulsar en directo», «multiperiódica: varias noches», nota
     no-radial, si `session_fits` falla «no caben 2 ciclos de seguida».
5. Tests unit: `test_hads.py`, `test_suggest_hads.py`, fixtures
   `test_tonight_kinds.py`/`test_best_per_kind.py`/`test_tonight_rows.py`
   (añadir un target `"hads"`). Test funcional del pipeline (sin red).

### Fase B — GUI mínima (listable y puntuable)
1. `theme.py` `KIND_COLORS` + `KIND_LABELS` (`HADS`).
2. `main_window.py`: `KIND_ORDER`, `TABLE_COLS["hads"]` (Period, Amplitude,
   Cycles, Alt, Best time), etiqueta `_table_value`, icono `_type_pixmap`
   (estrella pulsante, estilo del resto), onda de progreso de fase.
3. `config.py` `enabled_kinds` + migración amable de usuarios existentes.
4. `.ui` settings checkbox + save/load; `projects_tab.ui` item; `.ts` ES/EN
   (lupdate/lrelease; strings vía `self.tr()`).
5. `overview.py`: `orbits.explain_hads` (filas: periodo, amplitud, rango,
   modos) + chips (amplitud, ciclos, multiperiódica).

### Fase C — Proyectos y narrativa
1. `project.py`: `VALID_KINDS` + `"hads"`, `OUTCOMES`
   `("completed","reported_aavso","abandoned")`.
2. `enrich.py` detect_type + `narrative.py` hook/fact_bullets ES/EN
   (que citan Wils/VVS/AAVSO refs [1]–[5]).
3. Post/tweet: «mira esta estrella pulsar», curva, amplitud, programa Wils.

### Fase D — Flujo de sesión
1. Bloque de plan análogo al de tránsitos (modelo `:2797-2953`): duración
   recomendada 2P, cadencia ≤ P/12 (cap 15 min), exposición, «N ciclos caben
   esta noche», `session_fits` con aviso si no.
2. Exportación de secuencia CCDciel con esos campos (reusar patrón
   `_project_export_sequence`, block de tránsito `:3817-3820`).
3. process: instrucciones de fotometría + enlace AAVSO WebObs (`aavso_code`).

### Stretch (post v1, documentado)
- **Cobertura mensual**: parsear `assets/hads-coverage/` → urgencia «nadie ha
  medido esta estrella este mes» (+ hasta 10 en `_urgency`). Cuidado: dato
  snapshot que se queda viejo; refresco = sustituir asset + nota en la UI.
- **Curva sintética esquemática** (reloj de periodo): trazado 2P con forma
  diente-de-sierra normalizada; etiquetada como esquemática, nunca real.
- **Epoch vía VSX API** (red): VSX tiene `Epoch` (HJD de máximo) → podría
  **predecir máximos** como los tránsitos. Requiere `sources/vsx.py` + caché.
  AAVSO aconseja las ±0.05 mag; el app ya tiene `aavso_code`.

## Preguntas abiertas

1. ¿El stretch de cobertura mensual en esta iteración o en una futura?
   (Recomendado: futura — añade complejidad de refresco de datos.)
2. ¿mag de gate = mediana (H-e) o gate sobre el máximo (más optimista)?
   (Recomendado: mediana, consistente con el resto de familias.)
3. ¿Sesión recomendada 2×P (ver repetir + plegar) o 1×P en v1?
   (Recomendado: 2×P.)

## Docs pendientes en Fase D
- `docs/DATA_SOURCES.md` (+ es): entrada «HADS catalogue (P. Wils / VVS)».
- `docs/WORKFLOWS.md` (+ es): nueva fase + tipo de proyecto hads.
- `INSTALL.md` / README si aplica.