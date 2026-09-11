# Plan — HADS: estrellas δ Scuti de alta amplitud, visibles "en directo"

> **Diseño cerrado (2026-09-11), listo para ejecutar.** Un subplan = un commit.
> Las tarjetas de subplan autocontenidas viven en `docs/PLANS/hads/` (un fichero
> por fase) — para ejecutar un subplan solo hace falta leer `AGENTS.md`, este
> maestro y la tarjeta concreta. Anclas `fichero:línea` verificadas a HEAD
> `c607b81` (si una no coincide: **parar y reportar, no improvisar**).
> **Documentación de fondo**: [docs/HADS.md](../HADS.md) /
> [docs/HADS.es.md](../HADS.es.md) — lectura obligatoria. Decisión registrada en
> [ADR-034](../adr/ADR-034-hads-stars.md) (se revisa en el subplan D.5).

**rama**: `feature/hads` (nace de `feature/object-card`, HEAD `c607b81`;
mergea de vuelta a `feature/object-card`)
**fecha**: 2026-09-11 · **autor**: FJC (con la IA)

## Objetivo

Integrar las **estrellas HADS** (High-Amplitude δ Scuti) como nuevo tipo de
objetivo de la noche (`kind == "hads"`). Variables pulsantes con periodos de
~1–5 h y amplitudes ≥ 0.3 mag en V: **se las puede ver pulsar en directo**. El
usuario apunta, hace fotometría en continuo durante ~2 periodos y obtiene varias
curvas de luz completas en una sola noche. AAVSO las recomienda como **primer
objetivo** de fotometría digital. El programa de **Patrick Wils** (VVS /
AAVSO-VSX) monitoriza el catálogo a largo plazo; los datos se reportan a
**AAVSO**.

La infraestructura a reutilizar es la de **exoplanetas** (`core/transits.py`,
bloque de plan de la GUI, `OUTCOMES.reported_exoclock`) y la fotométrica del
Track B de supernovas (`core/followup.py`, `core/photometry_import.py`, widget
de curva de luz). Diferencia conceptual central: **no hay fase conocida**. Para
un tránsito sabemos cuándo ocurre (`t0 + n·P`); para una HADS solo sabemos
cuánto dura el ciclo (`Period_h`). No se recomienda un "evento", sino una
**captura continua de ≥ 2 ciclos**.

**Fuente de verdad de los datos**: el libro de cálculo de Patrick Wils
<https://docs.google.com/spreadsheets/d/1oGA2HaEHE8L6eX19ZoHqQQTu0LYV56HX3Srg7oCtOHo/>
(público, una pestaña por año, **se actualiza a diario**). Leyenda de colores
del nombre/coordenadas de cada estrella:

| Color | Significado | Prioridad |
|---|---|---|
| Rojo (nombre) | cambios de periodo encontrados | **¡Prioridad!** |
| Naranja (nombre) | cambios de periodo posibles | **¡Prioridad!** |
| Azul (coordenadas) | aún no observada en el programa | oportunidad |
| Morado (nombre) | modos múltiples de pulsación (observar en noches consecutivas) | sin prioridad |

## Decisiones (H-a … H-n)

| # | Decisión | Valor |
|---|---|---|
| H-a | **Sin fase → captura continua** | Recomendación **2×P** (verlo repetir + plegar). Gate de listado = visibilidad + **ventana contigua ≥ 1 ciclo**. |
| H-b | **Fuente híbrida** | Google Sheet en runtime (caché SQLite, TTL **12 h**) + snapshot empaquetado (`assets/HADS-stars.csv`) como respaldo offline/first-run y fuente de aliases. Runtime nunca bloquea: si falla red/parseo → snapshot puro. |
| H-c | **Métrica clave `cycles`** | `cycles = hours_up / Period_h` (ciclos completos que caben esta noche). Alimenta score, frases y el bloque de plan. |
| H-d | **Cadencia recomendada** | ≥ 12 puntos/ciclo → `cadence_s = min(P·3600/12, 900)` (cap 15 min reales, regla AAVSO). |
| H-e | **mag del target = mediana** | `mag = (Max+Min)/2` para gate y score (la fase es desconocida); rango Max–Min y amplitud siempre visibles en la ficha. |
| H-f | **Reporte → AAVSO** | Outcome de proyecto `reported_aavso` (paralelo de `reported_exoclock`); la config ya tiene `aavso_code`. |
| H-g | **Proyecto = flujo genérico** | `plan → process → publish` + pestaña Follow-up habilitada para `hads`; process = handoff FotoDif/AIJ + AAVSO WebObs. |
| H-h | **hads = coordenadas fijas** | NO entra en los kinds "moving" del goto CCDciel (cae en la rama `fixed()` sin tocar código: `main_window.py:2389-2407`). |
| H-i | **Prioridad desde la leyenda de colores** | Extraída del XLSX (color de fuente): rojo → `period_change` (+12 urgencia), naranja → `period_change_possible` (+8), azul coords → `unobserved` (+6), morado → `multiperiodic` (sin urgencia). |
| H-j | **Refresco automático, sin releases** | `core/sources/hads_sheet.py`: 1 descarga `export?format=xlsx` (workbook completo) vía `db.http_get`, TTL 12 h; parseo **solo stdlib** (`zipfile`+`xml.etree`, sin openpyxl en runtime); caché de dos niveles (XLSX crudo + JSON parseado → parseo 1 vez/día, lecturas ~5 ms). Merge por coordenadas sobre el snapshot. |
| H-k | **Azul (no observada) = urgencia moderada +6** | Dato estable que no envejece; ser de los primeros en medirla aporta valor real al programa. |
| H-l | **Fotometría en vivo = handoff FotoDif/AIJ + curva plegada** | FotoDif (modo AUTO) hace el directo y genera informe AAVSO Extended File Format; NightScribe importa su salida (el parser `photometry_import` ya admite «JD - mag»), pliega por fase con el P del catálogo y publica la curva. **Monitor nativo en vivo: aparcado** (FotoDif AUTO ya lo cubre; nota documentada sin compromiso). |
| H-m | **Cobertura mensual en v1** | Celda vacía del mes actual (pestaña del año en curso) → «nadie la cubre este mes»: +10 urgencia + fragmento. Fresca a diario gratis (mismo workbook). Si enero llega sin pestaña del año nuevo → `None` (sin bonus ni penalización). |
| H-n | **Generalización futura preparada, no incluida** | Variables de periodo largo/campañas = track posterior independiente (ver § Generalización). HADS v1 respeta los guardarraíles para no bloquearlo. |

## Arquitectura de datos (híbrida)

```
Google Sheet de P. Wils (fuente de verdad; actualización diaria)
  │  GET export?format=xlsx  (workbook completo, ~100-300 KB, 1 petición)
  ▼
core/sources/hads_sheet.py
  │  db.http_get("hads:workbook", "hads", fetch)   ← TTL 12 h (SOURCE_TTL)
  │  db.cache_get/put("hads:parsed", ...)          ← JSON parseado (mismo TTL):
  │      el parseo XLSX (~1-2 s) ocurre 1 vez/día; lecturas posteriores ~5 ms
  │  error de red/parseo → None (+logger.warning)
  ▼
core/hads.py::catalog()
  │  base = snapshot empaquetado (assets/HADS-stars.csv; lru_cache; aliases)
  │  overlay online casado por coords.angular_separation < 1'
  │      (period/max/min/priority/observed/coverage del sheet;
  │       estrellas nuevas del sheet se añaden; bundle sin pareja se conserva)
  ▼
planner._hads_targets → suggest (score + frases) → GUI / CLI / enrich
```

## Protocolo de ejecución (obligatorio para cada subplan)

1. Lee `AGENTS.md` + este maestro + **solo** tu fichero de fase.
2. Baseline: `.venv/bin/python -m pytest tests/unit -q` → anota el conteo.
3. Implementa la tarjeta tal cual. Si un ancla no coincide con la realidad:
   **para y reporta; no improvises**.
4. «Hecho» = checklist de la tarjeta completo, incluido: suite unitaria verde
   (anota N→M), cabecera GPL en todo `.py` nuevo (ver AGENTS.md), código en
   inglés con comentarios `# @args:` / `# @return:`, cadenas de GUI por
   `self.tr()`, y pipeline i18n ejecutado si tocaste cadenas:
   ```bash
   pyside6-lupdate nightscribe/gui/*.py nightscribe/gui/widgets/*.py \
       nightscribe/gui/ui/*.ui \
       -ts nightscribe/gui/i18n/nightscribe_es.ts \
           nightscribe/gui/i18n/nightscribe_en.ts
   # traducir los .ts (ES y EN; EN suele ser igual a la fuente)
   pyside6-lrelease nightscribe/gui/i18n/nightscribe_*.ts
   ```
   (`test_i18n.py` falla si queda alguna traducción `unfinished` o vacía.)
5. Un commit por subplan, con el mensaje dado en la tarjeta. Marca
   **Estado: Hecho** en la tarjeta.
6. Prohibido: TODOs sin resolver, medias implementaciones, agrupar commits.

## Índice de subplanes

| Sub | Título | Fichero | Depende de | Estado |
|---|---|---|---|---|
| H0.1 | Mini-lector XLSX stdlib | [fase-0-data.md](hads/fase-0-data.md) | — | pendiente |
| H0.2 | Descarga + caché de dos niveles | ídem | H0.1 | pendiente |
| H0.3 | Workbook → estrellas (colores, cobertura) + test funcional | ídem | H0.1, H0.2 | pendiente |
| H0.4 | `core/hads.py` (catálogo, merge, derivados) | ídem | H0.3 | pendiente |
| H0.5 | Docs de datos (HADS.md/es, DATA_SOURCES) | ídem | H0.4 | pendiente |
| A.1 | package-data + planner (`_hads_targets`, gate 1 ciclo) | [fase-a-core.md](hads/fase-a-core.md) | H0.4 | pendiente |
| A.2 | Scoring (`_scientific/_observability/_urgency/_hook`) | ídem | A.1 | pendiente |
| A.3 | Fragmentos ES/EN | ídem | A.2 | pendiente |
| B.1 | GUI listable (theme, tabla, icono, fase) + i18n | [fase-b-gui.md](hads/fase-b-gui.md) | A.3 | pendiente |
| B.2 | config + settings checkbox + combos + i18n | ídem | B.1 | pendiente |
| B.3 | enrich `detect_type` (¡antes de la regex exoplaneta!) | ídem | H0.4 | pendiente |
| B.4 | Ficha de objeto (`explain_hads` + chips) + i18n | ídem | B.1, B.3 | pendiente |
| C.1 | Proyectos hads (`VALID_KINDS`/`OUTCOMES`/CLI) + i18n | [fase-c-projects.md](hads/fase-c-projects.md) | B.2 | pendiente |
| C.2 | Narrativa ES/EN (hook, facts, hashtags) | ídem | B.3 | pendiente |
| C.3 | Post/tuit (tests) | ídem | C.2 | pendiente |
| D.1 | Bloque de plan HADS (2P, cadencia, checklist) + i18n | [fase-d-session.md](hads/fase-d-session.md) | C.1 | pendiente |
| D.2 | Secuencia CCDciel hads | ídem | D.1 | pendiente |
| D.3 | Follow-up + process (FotoDif/WebObs) + i18n | ídem | C.1 | pendiente |
| D.4 | Plegado por fase (widget + viz) + i18n | ídem | D.3 | pendiente |
| D.5 | Post con curva + cierre documental | ídem | D.4 | pendiente |

## Riesgos y mitigaciones

- Google cambia el endpoint / la hoja deja de ser pública / el layout cambia →
  fallback al snapshot empaquetado + `logger.warning` (Tonight nunca se rompe).
- Color no reconocido en la hoja → se ignora con `logger.debug` (nunca rompe el
  parseo).
- La hoja y el bundle derivan (ej. GP And: 1.89 h bundle vs 2.89 h hoja) → el
  dato online manda en runtime; el test funcional imprime un informe de deriva
  (informativo, nunca falla) para refrescar el snapshot a mano cuando convenga.
- Ancla de línea desviada al ejecutar → el protocolo manda parar y reportar.

## Generalización futura: variables y campañas (NO en este plan)

Las HADS abren la puerta a la fotometría de variables, pero son la **excepción
de corto periodo** (sesión única de 2P). Las variables de largo periodo
(Miras, simbióticas, novas recurrentes como T CrB, objetos tipo WeSb 1) siguen
el molde **multi-noche del Track B de supernovas** (sesiones, puntos
fotométricos, curva, cadencia con memoria) — es un **track posterior
independiente, en su propia rama** (plan + ADR propios). Dirección pactada:

- **Campaña = atributo ortogonal del proyecto** (`{grupo/coordinador, objetivo,
  protocolo: cadencia_noches/filtros/estrellas de comparación, url_reporte,
  estado activa/finalizada}`) — las campañas reales del grupo obsSN cubren SNs
  (2017eaw) y variables (T CrB, WeSb 1) por igual.
- **Nuevo kind `variable`** hermano de `sn`; `series.py` (un apilado por noche)
  le sirve sin cambios.
- Bucle de planificación sin red: campañas activas con cadencia vencida →
  Tonight (patrón B11 «hace N noches»).
- Reporte: exportar `photometry_points` a CSV/AAVSO EFF (HJD, mag, filtro).

**Guardarraíles que HADS v1 respeta** (notas en las tarjetas afectadas):
la pestaña Follow-up se habilita kind-agnóstica (constante `FOLLOWUP_KINDS`,
no `== "hads"` a pelo); el plegado por fase y la plantilla esquemática se
implementan agnósticos de kind; `sawtooth_template` con API genérica
`(period, amp, mag_med)`; narrativa/post como una rama más sin tocar el
andamiaje genérico.

**Monitor nativo en vivo**: aparcado (H-l) — FotoDif AUTO ya cubre el directo
en el flujo real del observatorio. La nota queda en `docs/WORKFLOWS` (7decies,
«fuera de esta iteración») por si algún día cambia el flujo.

## Sin preguntas abiertas

Todas las cuestiones del diseño quedaron resueltas el 2026-09-11 (mag gate =
mediana; sesión = 2×P; cobertura mensual en v1; prioridades por color en v1;
azul = +6; refresco online TTL 12 h; handoff FotoDif + plegado; campañas =
track aparte; monitor en vivo = aparcado).
