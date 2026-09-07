# Plan — Ficha de objeto: enriquecer, unificar y pulir

> **CERRADO (2026-09-07)** — los 8 subplanes (0-7) están implementados y a
> commit en `feature/object-card` (`b163f6c`, `376a23c`+`67ceadf`, `02c05bf`,
> `3412c3c`, `8c4c336`, `afab280`, `03290ea` + cierre i18n/docs). Suite
> unitaria verde (555). ADR-031 recoge la decisión. Este documento queda como
> registro de diseño.

**rama**: `feature/object-card` (derivada de `dev/v0.1`)
**arranca sobre**: `b0693c4` (dev/v0.1 al día con origin)
**fecha**: 2026-09-07 · **autor**: FJC (con la IA)

## Objetivo

Enriquecer, mejorar y unificar la ficha de exploración de objetos
(`gui/overview.py::ObjectPanel`, compartida por hub y Explore) y la lista
completa de Tonight (`tbl_targets`):

0. **Coordenadas AR/DEC** visibles en la ficha, en decimal **y** sexagesimal,
   en un sitio claro y fáciles de copiar.
1. **Unificar la representación por tipo**: los NEOs ya tienen tabla de
   parámetros; SN y tránsitos no. Los chips/cuadros de color de la ficha son
   desproporcionados en los tipos con pocos datos.
2. **Tabla multilínea**: hoy el texto largo queda cortado en vertical;
   explicaciones más detalladas.
3. **"Discovered"** (columna de la lista completa) debe aplicar también a NEOs.
4. **Exoplanetas**: la ficha debe informar inicio del tránsito, profundidad y
   visibilidad desde la localización; y Tonight debe **filtrar** los tránsitos
   cuyo telescopio mínimo supera la apertura del usuario.

## Decisiones pactadas (2026-09-07)

| # | Decisión | Valor |
|---|----------|-------|
| 1 | **Ubicación coordenadas** | Línea propia en la ficha, bajo el hook, con ambos formatos y botón "Copiar" al portapapeles. |
| 2 | **"Cuadros de colores muy grandes"** | Se refiere a los **chips de la ficha** (Mag, ventana…). Se uniforman tamaño y gramática por tipo. |
| 3 | **Filtro de apertura en tránsitos** | **Duro con interruptor**: se descartan de Tonight si `min_telescope_in > aperture_inches`, con checkbox en Settings para desactivarlo. Dato ausente = no descartar. Sigue el patrón ADR-025 (duro donde el dato es medido/curado). |
| 4 | **"Discovered" en NEOs** | **Fecha exacta**: SBDB (`discovery=1`, fallback `orbit.first_obs`); NEOfixer `/orbit/` (`observations.earliest`) para NEOCP. |

## Reglas de ejecución (de WORKFLOWS)

- Un subplan = un commit; cada subplan deja la app funcional con sus tests.
- Tests offscreen, sin red, patrón `tests/unit/test_overview_panel.py`.
- Cabecera GPL en todo `.py`; código en inglés; cadenas GUI por `self.tr()`;
  pares ES/EN por `orbits.pick`.
- i18n (`lupdate`/`lrelease`) y docs en el subplan 7.
- Toda consulta de red pasa por `core/db.py` (caché); nunca `requests` fuera
  de `core/sources/`.

## Contexto clave (exploración 2026-09-07)

- La tabla de parámetros solo existe para NEO/cometa/PCCP
  (`orbits.explain_elements` / `explain_neofixer`); SN y tránsitos no tienen.
- **Bug**: la tabla no llama a `resizeRowsToContents()` → textos largos
  cortados en vertical.
- Chips ricos solo en NEO/PCCP (mag/tasa/exposición/ventana/horas/segura);
  SN/tránsito quedan con 2-3 chips desproporcionados en la tarjeta.
- **Bug**: la rama "exoplanet" de `enrich` pierde el contexto ExoClock
  (`transit` con ingress/egress/depth/`min_telescope_in`) → también rompe la
  curva de luz en nombres tipo "HD 209458 b".
- `aperture_inches` existe en Settings pero nadie lo consulta;
  `min_telescope_in` (ExoClock) ya llega a `transits.py`. ADR-015 prometió
  este filtro y nunca se implementó.
- `disc_date` solo existe para SN (Rochester). SBDB y NEOfixer tienen la
  fecha para NEOs; PCCP ya parsea `discovery` y el planner lo descarta.
- Helpers de coordenadas ya existen: `coords.ra_deg_to_hms` / `dec_deg_to_dms`.

## Subplanes

### Subplan 0 — Coordenadas AR/DEC copiables
Bloque bajo el hook en `ObjectPanel`: `RA 210.91070° = 14h 03m 38.6s` /
`Dec +54.31170° = +54° 18′ 42″` + botón "Copiar". Oculto sin coords (alertas
ESA sin posición). Extraer la cadena de fallbacks de `_extract("sky")` a un
helper `_coords_from(e)` reutilizable (bloque + gráfico).
**Tests**: visible con coords; formatos correctos; `QClipboard` recibe el
texto; ausente sin coords.

### Subplan 1 — Tabla multilínea legible
`tbl_params.setWordWrap(True)` + `resizeRowsToContents()` tras
`_refill_params()`; tope de ancho en columnas 0-1 para dar aire a
"What it means".
**Tests**: fila con explicación larga tiene altura > altura por defecto.

### Subplan 2 — Tabla de parámetros para supernovas
`orbits.explain_transient(data)` (pares ES/EN): tipo de SN, galaxia
anfitriona, distancia (Mly), corrimiento z, mag actual, fecha de
descubrimiento. Niveles basic/deep. Rama nueva en `_orbit_rows`.
**Tests**: SN fake → ≥4 filas con explicación >40 chars (patrón del test NEO).

### Subplan 3 — Ficha de tránsitos rica
- **3a (bug)**: rama exoplanet de `enrich` fusiona `fallback_target` con
  `setdefault` (patrón ADR-027) → llega `transit` y se arregla la curva de
  luz para nombres "HD 209458 b".
- **3b**: `orbits.explain_transit(data)`: inicio del tránsito (UTC), fin,
  duración, profundidad (mmag y % de flujo), mag V de la estrella,
  **telescopio mínimo vs. tu apertura** (fila-veredicto), periodo orbital,
  distancia, método y año de descubrimiento.
**Tests**: 3a con Archive mockeado + ctx; 3b con tránsito fake → filas con
ingress/depth/veredicto.

### Subplan 4 — Chips uniformes y completos por tipo
Misma gramática visual: chips alineados a la izquierda sin estirar; SN gana
tipo/edad; tránsito gana ingress–egress, profundidad y duración; cometa
mag/ventana igual que NEO. Tamaño/padding único vía `theme.chip_style`.
**Tests**: un test por tipo con el set de chips esperado.

### Subplan 5 — "Discovered" para NEOs y PCCP
- **5a**: `sbdb.get()` pide `discovery=1`; `parse_sbdb()` exporta `disc_date`
  (`discovery.date`, fallback `orbit.first_obs`) normalizado a `YYYY-MM-DD`.
- **5b**: `neofixer.parse_neofixer_orbit()` exporta `earliest` (primera
  observación MPC) para NEOCP.
- **5c**: `planner._neo_targets()` resuelve `disc_date` por objeto **en
  paralelo** (pool ~4, patrón de `_comet_targets`); NEOCP usa 5b como
  fallback. Bonus: `_pccp_targets` mapea el `discovery` ya parseado.
- **5d**: helper único de parseo de fechas (`YYYY/MM/DD` Rochester,
  `YYYY-MM-DD` TNS, `YYYY-MMM-DD` SBDB) usado por `_table_value` y
  `suggest._freshness_days`.
**Tests**: parsers con fixtures existentes + tabla mostrando fecha en un NEO;
sin red en unit.

### Subplan 6 — Filtro duro por apertura en tránsitos
`config["transit_scope_filter"]` (default `True`); `transits_tonight()`
descarta eventos con `min_telescope_in > aperture_inches` (dato ausente = no
descartar); checkbox en Settings > Observing. Actualizar ADR-015 (consecuencia
ya implementada).
**Tests**: 71″ requerido vs 10″ propio → descartado; interruptor off →
aparece; sin dato → aparece.

### Subplan 7 — Cierre
`lupdate`/`lrelease` ES/EN · ADR-031 bilingüe (unificación de ficha +
discovered NEO + filtro apertura) · sección nueva en `WORKFLOWS.es/.md` con
estados finales · `pytest tests/unit` verde + funcionales relevantes.

## Orden de ejecución

0 → 1 → 2 → 3a → 3b → 4 → 5a…5d → 6 → 7
(0, 1, 4 y 6 son independientes entre sí; 3a es prerrequisito de 3b).

## Riesgos conocidos

- 5c añade ~15 llamadas SBDB la primera noche (caché 7 días + paralelismo lo
  amortiguan).
- SIMBAD sigue intermitente → los tests de ficha SN deben mockear.
