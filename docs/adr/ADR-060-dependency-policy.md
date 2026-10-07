# ADR-060: Política de dependencias (reabre ADR-004)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-04

## Español

**Contexto**: ADR-004 prohibió astropy y astroquery por peso y por fragilidad de
empaquetado, y ADR-018 volvió a evitarlos para el blink (lector FITS/WCS propio).
Esa regla funcionó mientras las necesidades eran planificación y geometría
sencilla. El plan de astrometría de cuerpos menores (`docs/PLANS/astrometry-minor-planets/`)
necesita justo lo que se había evitado: FITS con extensiones, WCS con distorsión
SIP, remuestreo subpíxel de calidad, centroides subpíxel y calibración de
imágenes. Reimplementarlo a mano sería más código, más lento y peor que las
bibliotecas estándar del ecosistema. Decisión del autor: **se reabre ADR-004**.

**Decisión**:

1. **Regla nueva**: numpy primero, y una **biblioteca estándar cuando aporta y su
   coste está justificado** (peso del instalador, mantenimiento, licencia). Ya no
   hay una prohibición general de astropy o scipy.
2. **Lista blanca explícita**: `astropy`, `scipy` y `photutils` entran como
   dependencias reales del plan de astrometría. `ccdproc`, `reproject`,
   `scikit-image` y `sep` quedan **autorizadas pero no se añaden** sin necesidad
   demostrada (la calibración es aritmética simple y el apilado va sobre la
   rejilla del frame de referencia, así que `reproject` probablemente sobre).
3. **Convivencia, no migración**: los módulos que ya funcionan (`fits_io`,
   `wcs`, `register`, `photometry`, `series_measure`) **no se migran** en este
   plan. Los módulos nuevos usan las bibliotecas. Conviven, por tanto, **dos
   implementaciones de WCS** (la TAN propia y `astropy.wcs`) y **dos de
   centroide** (numpy y photutils); se acota con tests y se declara aquí para que
   no parezca un accidente. La migración de los módulos viejos queda como plan
   futuro.
   > **Cerrado el 2026-10-07 (ADR-067)**: ese plan futuro se midió y no se
   > hace. Contra photutils, la medida individual empata (los dos llegan al
   > suelo de ruido de la apertura), la serie mejora un 1,8 % de mediana y la
   > velocidad 1,43×, y el ahorro neto son 250 a 450 líneas (0,5 a 0,8 % de la
   > app, cero en `series_measure.py`). `photometry.py` y
   > `series_measure.py` **no se migran**; la convivencia sigue abierta para
   > capacidades nuevas, con ganancia medida.
   > **Closed on 2026-10-07 (ADR-067)**: that future plan was measured and is
   > not done. Against photutils, the single measurement ties (both reach the
   > aperture's noise floor), the series improves by a median 1.8 % and the
   > speed by 1.43×, and the net saving is 250 to 450 lines (0.5 to 0.8 % of
   > the app, zero in `series_measure.py`). `photometry.py` and
   > `series_measure.py` are **not migrated**; coexistence stays open for new
   > capabilities, with a measured gain.
4. **Consecuencias sobre ADR-018**: el lector FITS propio pasa a **legado** para
   lo nuevo; ADR-018 sigue vigente en su decisión de alineación por construcción
   y de no remuestrear los píxeles del usuario.
5. **Nota sobre ADR-051**: el WCS TAN propio no desaparece; ASTAP y el blink
   siguen usándolo. Lo nuevo lee SIP con `astropy.wcs` cuando el solver lo trae.

**Alternativas**: seguir con numpy puro (rechazado: más código y peor calidad en
remuestreo y centroides); usar solo `skyfield` u otra biblioteca ligera
(rechazado: no cubre FITS, WCS ni fotometría de apertura); migrar toda la app de
golpe (rechazado: rompe lo probado y convierte el plan en un diff gigante).

**Consecuencias**: el instalador crece de forma notable; `requirements.txt` y
`pyproject.toml` suman astropy, scipy y photutils; el `nightscribe.spec` de
PyInstaller necesita `collect_data_files`/`collect_submodules` para astropy, y la
descarga automática de tablas IERS se desactiva (política de tabla empaquetada
con fecha de corte, como en el plan de series). A cambio, la astrometría y la
calibración se apoyan en lo estándar y probado. Tests: un test trivial de import
con `importorskip` para no romper entornos sin las tres bibliotecas.

## English

**Context**: ADR-004 banned astropy and astroquery because of weight and
packaging fragility, and ADR-018 avoided them again for blink (own FITS/WCS
reader). That rule worked while the needs were planning and simple geometry. The
minor-planet astrometry plan (`docs/PLANS/astrometry-minor-planets/`) needs
exactly what had been avoided: FITS with extensions, WCS with SIP distortion,
quality subpixel resampling, subpixel centroids and image calibration.
Hand-rolling that would mean more code, slower and worse than the ecosystem's
standard libraries. Author's decision: **ADR-004 is reopened**.

**Decision**:

1. **New rule**: numpy first, and a **standard library when it earns its place**
   (installer weight, maintenance, licence). There is no general ban on astropy
   or scipy any more.
2. **Explicit whitelist**: `astropy`, `scipy` and `photutils` become real
   dependencies of the astrometry plan. `ccdproc`, `reproject`, `scikit-image`
   and `sep` are **authorised but not added** without demonstrated need
   (calibration is simple arithmetic and stacking runs on the reference frame's
   grid, so `reproject` probably will not).
3. **Coexistence, not migration**: the modules that already work (`fits_io`,
   `wcs`, `register`, `photometry`, `series_measure`) are **not migrated** in
   this plan. New modules use the libraries. Two **WCS implementations** (the own
   TAN one and `astropy.wcs`) and two **centroid implementations** (numpy and
   photutils) therefore coexist; tests bound them and this ADR declares it so it
   does not look like an accident. Migrating the old modules is a future plan.
4. **Effect on ADR-018**: the own FITS reader becomes **legacy** for new code;
   ADR-018 remains in force for alignment-by-construction and for never
   resampling the user's pixels.
5. **Note on ADR-051**: the own TAN WCS does not disappear; ASTAP and blink keep
   using it. New code reads SIP with `astropy.wcs` when the solver provides it.

**Alternatives**: stay on pure numpy (rejected: more code and worse quality in
resampling and centroids); use only `skyfield` or another light library
(rejected: it does not cover FITS, WCS or aperture photometry); migrate the whole
app at once (rejected: breaks what is proven and turns the plan into a huge diff).

**Consequences**: the installer grows noticeably; `requirements.txt` and
`pyproject.toml` add astropy, scipy and photutils; PyInstaller's
`nightscribe.spec` needs `collect_data_files`/`collect_submodules` for astropy,
and the automatic IERS table download is disabled (bundled table with a cut-off
date, as in the series plan). In exchange, astrometry and calibration rest on the
standard, proven tools. Tests: a trivial import test with `importorskip` so
environments without the three libraries do not break.
