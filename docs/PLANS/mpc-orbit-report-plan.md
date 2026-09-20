# Plan — Export MPC/Find_Orb + parallax topocéntrico + frescor

*Guardado 2026-09-08 para sesiones compactadas. Ejecutar paso a paso,
parando tras cada paso (petición del usuario).*

## Objetivo

Exportación principal = **informe orbital MPC/Find_Orb** (formato universal,
cualquier planetario: TheSkyX, Stellarium, Cartes du Ciel, Celestia…).
La tabla de posiciones CSV queda como opción secundaria de seguimiento.
`position_at()` sigue alimentando CCDciel `slew_target(ra, dec)`.

Sin Find_Orb local: todos los campos son fórmulas puras sobre los elementos
que devuelve NEOfixer (verificados Sar2911: Tisserand 2.9782 vs 2.97758 ✓).

Parallax topocéntrica cuantificada: ~86″ para Sar2911 (δ=0.102 AU),
~44–88″ para NEOCP típicos (0.1–0.2 AU).

## Orden de implementación

| # | Archivo | Cambio | Estado |
|-|---------|--------|--------|
 | 1 | `core/orbits.py` | `tisserand_earth(a,e,i)`, `encounter_velocity(v_obj, v_earth)` (`diameter_from_h` ya existe, línea 98) | ✅ |
| 2 | `core/ephem_minor.py` | `state_vector_j2000(elements, jd)` → (pos AU, vel mAU/day) J2000 equatorial; Sar2911 ref: +1.0085,-0.2462,-0.0961 AU / +4.347,+17.954,+4.906 mAU/d | ✅ |
| 3 | `core/ephem_minor.py` | `kepler_ra_dec(elements, jd, lat_deg=None, lon_deg=None, height_m=0.0)` — vector topocéntrico; None → geocéntrico (backward-compat). Lat/lon/altura de config (40.55, -3.37, 631) | ✅ |
| 4 | `core/sources/neofixer.py` | `parse_neofixer_orbit()` (línea 107) → devolver `"moids"` con los 8 planetas (hoy solo Earth) | ✅ |
 | 5 | `core/db.py` | `http_get(self, key, source, fetch_fn, force=False)` — force=True omite caché | ✅ |
| 6 | `core/ephemeris.py` | `export_fo_report(name, out, packed, force, data)`; dispatcher `export(fmt="fo")`. Validado vs `docs/Sar2911-sample-ephemerids.txt` (T 2.97758 ✓, dates ✓, P/Q ✓, state ✓) | ✅ |
| 7 | `gui/main_window.py:2277` | `_project_export_ephem()` → QDialog con QComboBox (2 opciones, tooltips vía `setData(Qt.ToolTipRole)`) + QCheckBox "Force fresh data (bypass cache)" con tooltip. Opciones: "MPC orbit report (any planetarium)" / "Position CSV (tracking)". **Sin TheSkyX/CdC (leerán el MPC report)**. fo → `.txt` `<name>_orbit_report.txt`, no necesita rows | ✅ |
| 7b | `gui/main_window.py:1635-1640` | Tooltips de botones CCDciel: **Point telescope** = "posición fresca (objetos en movimiento) → J2000_to_Apparent → Telescope_slewasync; sin plate-solve; opción rápida" · **Astrometric Goto** = "slew + captura + plate-solve + corrección; absorbe error residual de efemérides; fiable para NEOCP/órbitas preliminares" | ✅ |
| 8 | `tests/unit/test_fo_report.py` | new: tisserand, encounter_velocity, state_vector_j2000 (tol 1e-3 AU), estructura FO report, los 8 MOIDs, kepler topocéntrico ≠ geocéntrico, db force | ✅ |
 | 9 | `tests/unit/test_orbits.py` | Tisserand + encounter velocity con datos Sar2911 | ✅ |
 | 10 | `docs/adr/ADR-021-capture-exports.md` | Decision #4: export principal = MPC orbit report (universal); CSV/TheSkyX/CdC = secundarios de posición; parallax topocéntrica; frescor | ✅ |
 | 11 | `docs/UI_EXPORTS.es.md` + `docs/UI_EXPORTS.md` | nuevo (bilingüe): qué hace cada botón/exportación, para quién, por qué — MPC report vs CSV, Force fresh data, CCD Point/Astrometric, secuencias | ✅ |
 | 12 | `nightscribe/gui/i18n/nightscribe_{es,en}.ts` | strings nuevos (MPC report, Force fresh data, tooltips, botones CCD) · lupdate+lrelease · 439 finished/0 unfinished | ✅ |

## Datos de referencia (docs/Sar2911-sample-ephemerids.txt)

- elementos: a=1.4624917 e=0.2881631 i=7.94982Ω=169.16454ω=182.66687 MA=356.53233
- H=27.07 U=8.1 n=0.55726782 q=1.04105554 Q=1.88392780
- TP=2026-09-14.222631 (JD 2461297.722631), época JD 2461291.37919
- 20 obs, 21.4 h arc, rms 0.36″
- MOIDs: Me 0.6705 Ve 0.3169 Ea 0.0348 Ma 0.1846 Ju 3.5406 Sa 7.4074 Ur 16.4036 Ne 28.3056
- Pos: +1.008506846153 -0.246249758226 -0.096127752779 AU
- Vel: +4.347021406325 +17.954408927073 +4.905507244961 mAU/day
- P: +0.98977021 +0.14028155 -0.12820475  Q: -0.06259756?? (revisar sample: Q línea 2 +0.95447801, 3 +0.26323525)
- Tisserand 2.97758 · v_enc 5.5974 km/s · Ø 15.8 m (albedo 10%) · Sigmas avail: 1

## Fórmulas

- Tisserand: `T = 1/a + 2·sqrt(a·(1-e²))·cos(i)` (a_p = 1 AU)
- v_encounter (Barbee): `|v_obj - v_earth|` con velocidades heliocéntricas J2000
- Estado: posición vía `_elements_to_ecliptic()`, velocidad vis-viva en el
  plano orbital + rotación; unidades (AU, mAU/day)
- Topocéntrico: vector sitio (lat/lon/altura) en ECI → eclíptica J2000 →
  añadir al geocéntrico antes de `kepler_ra_dec` (signo: vector Tierra→observador)
