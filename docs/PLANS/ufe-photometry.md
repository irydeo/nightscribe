# Plan de implementación: fotometría calibrada en el UFE (pestaña Medir, fases G y H) (2026-09-22)

> **ESTADO: G Y H CERRADAS (2026-09-23).** La fase G1 la
> implementó otra IA en `ed8c9c5` y pasó revisión (notas abajo). G2 la
> hizo esta sesión: `gui/ufe_measure_tab.py` (clic → centroide → medida;
> comps de la pestaña Comparar medidas en la misma placa por su nuevo
> accesor `entries()`; ZP mediana+MAD; error CCD con GAIN/RDNOISE de
> cabecera o degradado honesto a dispersión de comps; panel con guardas
> en lenguaje llano; overlays de apertura/anillo/comps; export CSV una
> fila y EFF con la secuencia; la placa jamás se toca). G3: i18n 1227
> cadenas, PHOTOMETRY.es/en con la sección 3.3 (medida calibrada),
> UFE.es/en con la pestaña, ADR-044 rev, AGENTS.md al día. Suite 1635
> verde.
> **La fase G está completa.** La fase H (2026-09-23, misma sesión) la
> cerró con las piezas H1–H7 de `docs/PRECISION.es.md`: cielo por plano
> (H2a), apertura por FWHM (H3), término de color con rechazo MAD de
> outliers (H1+H7), saturación real por SATURATE/`ccd_saturate` (H4),
> error total con centelleo de Young + suelo de flat (H5) y semáforo
> check (H6); sustracción de la galaxia huésped sobre la referencia
> alineada del blink (H2b). Suite 1651 verde, i18n 1253 cadenas. Hallazgo
> propio: el clip por MAD colapsa cuando la mayoría ajusta exacto; el
> umbral queda con suelo de 0.06 mag y desviaciones medidas desde la
> mediana de los residuales.
> **Queda pendiente** solo el régimen de tránsitos (T1–T8), a la espera
> de la decisión sobre ADR-015, y las piezas de cámara v2 (coeficientes
> de transformación propios).
>
> **Nota previa conservada (estado tras G1):** la fase G1 la
> implementó otra IA en `ed8c9c5` (directamente sobre `feature/ufe`) y
> pasó revisión en esta sesión: `core/photometry.py` con
> `measure_point` (centroide sub-píxel, flujo neto, cielo con sigma-clip
> D3, guardas bilingües de borde/saturación/señal), `ccd_flux_error` +
> `mag_error` (ecuación CCD anclada a ganancia, D2), 
> `calibrate_zero_point` (mediana + MAD/√N, D1) y `calibrated_mag`;
> 12 tests con semilla que verifican la física de verdad (fracción
> analítica de la gaussiana, ZP a precisión de flotante, degradados);
> suite 1626 verde; humo sobre placa real correcto (guardas de borde
> saltan en la franja de artefactos del fixture).
> **La próxima sesión empieza en G2** (`gui/ufe_measure_tab.py`).
>
> Documento vivo: se actualiza al cierre de cada fase. El proceso
> fotométrico tal como existe HOY está documentado para el usuario en
> `docs/PHOTOMETRY.es.md` / `docs/PHOTOMETRY.md`; este plan añade lo que
> falta: la medida CALIBRADA sobre la placa cargada.
>
> Rama: la otra IA trabajó directamente sobre `feature/ufe` (no se creó
> `feature/ufe-photometry`); se acepta y se sigue así.
>
> **Notas de la revisión de G1** (para la próxima sesión):
> - `measure_point` reimplementa la suma de apertura y el anillo en vez
>   de llamar a `series.aperture_flux` (lo justifica el sigma-clip; reusa
>   centroide y radios). Aceptado; no tocar.
> - La guarda de saturación por meseta exige ≥25 píxeles en el máximo
>   exacto del frame: una estrella apenas al techo (marginal) no salta;
>   el camino estricto es `sat_adu` (tarjeta SATURATE o ajuste), que la
>   fase H4 ya contempla.
> - El mensaje de commit decía «D1-D6 firmadas»: D1/D5/D6 son decisiones
>   de la pestaña (G2), no del core; sin consecuencia en el código.

## Estado de la sesión (actualizado 2026-09-22, empezar AQUÍ)

**Contexto cerrado (no re-explorar)**

- El UFE está completo (fases A-F + D.5, plan hermano
  `docs/PLANS/unified-fits-editor.md`): estado con DN absolutos, vista en
  píxeles de placa, histograma con tiradores, norte/escala comunes,
  astrometría común en memoria, y las pestañas Blink / Comparar / Anotar
  reales.
- La pestaña **Comparar** (`gui/ufe_compare_tab.py`) ya genera el campo
  (VizieR Gaia/APASS + veto VSX), propone la secuencia y la mantiene en
  `tab._entries` (`{"name", "kind", "star"}`; cada `star` lleva `bands`
  con las magnitudes de catálogo y `bv`).
- Las primitivas fotométricas EXISTEN y están testadas en
  `core/series.py`: `_centroid` (caja 11×11), `aperture_flux` (r=6 px,
  anillo 10–15 px, mediana), `instrumental_mag`, guarda de saturación
  `_SAT_FRAC=0.85`.
- El análisis de complejidad y precisión que el usuario aprobó está en el
  historial de la sesión y destilado en la sección 7 de
  `docs/PHOTOMETRY.es.md`.

**Pendiente**

1. ~~Firmar con el usuario las decisiones D1-D6~~ (según el mensaje de
   commit de la otra IA; D1/D5/D6 se aplican en G2: si el usuario no las
   recuerda firmadas, confirmarlas antes de G2).
2. ~~G1: `core/photometry.py` + tests.~~ (hecho y revisado, `ed8c9c5`)
3. ~~G2: `gui/ufe_measure_tab.py` + tests.~~ (hecho: 9 tests offscreen
   con placa sintética WCS + semilla; decisiones aplicadas D1/D5/D6 con
   sus recomendaciones: banda V por defecto, secuencia leída de Comparar
   por `entries()`, exports solo a archivos)
4. ~~G3: i18n + docs (PHOTOMETRY gana la sección de medida calibrada;
   UFE.es/en ganan la pestaña; AGENTS.md lista los módulos; ADR-044
   rev).~~

## Decisiones pendientes de firma (D1-D6)

Ir una por una con el usuario al arrancar; cada una trae recomendación.

- **D1. Banda de calibración**: V (APASS directa; Gaia con V derivada
  por Riello 2021, marcada «est.»), usando el catálogo que generó el
  campo. *Recomendado.* La alternativa (la banda nativa del catálogo,
  p.ej. G) es menos comparable con la fotometría clásica.
- **D2. Modelo de error CCD**: ganancia y ruido de lectura se leen de la
  cabecera FITS (`GAIN`, `RDNOISE`, `EXPTIME`); si faltan, se miran dos
  claves nuevas de Ajustes (`ccd_gain`, `ccd_read_noise`); si tampoco,
  el error reportado es solo la dispersión de las comps y el panel lo
  dice en lenguaje llano. *Recomendado.*
- **D3. Cielo con sigma-clip**: la mediana del anillo ya es robusta;
  añadir un sigma-clip (2.5σ, 2 iteraciones) protege en núcleos
  galácticos. *Recomendado ON por defecto, desactivable.*
- **D4. Ámbito: una medida = un clic en una placa.** Las series
  multi-imagen YA existen (`core/series.quicklook`, flujo Seguimiento);
  no se duplican. *Recomendado.*
- **D5. La pestaña Medir toma la secuencia de la pestaña Comparar** (el
  diálogo se la pasa como colaboradora: `UfeMeasureTab(...,
  compare_tab=self.tab_compare)`); sin secuencia, la pestaña guía a
  generar/proponer una en Comparar. *Recomendado.* La alternativa
  (secuencia propia e independiente) duplica estado y confunde.
- **D6. Export de la medida: archivos** (CSV de una fila + línea EFF
  vía `core/photometry_export`). El UFE es agnóstico de proyecto; la
  integración con proyectos sigue siendo del flujo Seguimiento.
  *Recomendado.*

## Diseño (G1-G3)

### G1: `core/photometry.py` (nuevo, numpy puro, sin Qt ni red)

Cabecera del proyecto obligatoria; comentarios `# @args:`/`# @return:` en
inglés. Nada de docstrings robóticos. Reutilizar `core/series.py` por
import (`from . import series`), no copiar sus funciones.

```
R_AP / R_ANN_IN / R_ANN_OUT    # re-export desde series (una sola verdad)

def measure_point(data, x, y, r_ap=series.R_AP, ...):
    # centroide (series._centroid) + aperture_flux + guards
    # @return: dict {"x", "y" (centradas), "flux", "sky_pp", "peak",
    #                "n_pix", "saturated", "ok", "reason"} (reason bilingüe)

def ccd_flux_error(flux, sky_pp, n_pix, gain=None, ron=None,
                   exptime=None):
    # Ecuación CCD en ADU: shot de la fuente + cielo + RON^2 por píxel.
    # gain en e-/ADU, ron en e-, exptime reservado para dark futuro.
    # @return: sigma del flujo en ADU, o None si no hay gain (el caller
    #          cae entonces a la dispersión de las comps)

def mag_error(flux, flux_err):
    # 1.086 * flux_err / flux

def calibrate_zero_point(inst_mags, cat_mags):
    # ZP = mediana(cat − inst) sobre las comps válidas;
    # err = 1.4826 * MAD / sqrt(N); residuales por comp para el panel.
    # @return: {"zp", "zp_err", "n", "residuals": [...], "used": [...]}

def calibrated_mag(inst_target, zp, zp_err, target_err):
    # mag = inst + zp; err = hypot(target_err or 0, zp_err)
    # @return: (mag, err)

def header_instrument(header):
    # @return: {"gain", "ron", "exptime"} leídos de GAIN/RDNOISE/EXPTIME
    #          (None por campo ausente); sin magia de unidades
```

Tests (`tests/unit/test_photometry.py`, sin Qt): placa sintética con
estrella gaussiana de flujo conocido (con `np.random.default_rng(42)`:
semilla siempre, el flake de `test_series` no se repite), ZP recuperado
con 5 comps sintéticas a <0.01 mag, sigma-clip contra un píxel caliente
en el anillo, guards (saturada, borde, flujo nulo), degradado sin
ganancia (error = solo scatter), residuales coherentes.

### G2: `gui/ufe_measure_tab.py` (pestaña UFE «Medir»)

Convenciones UFE (ver ADR-044 rev D): el constructor recibe
`(state, lang, view=..., compare_tab=...)`; `set_active(bool)` posee
clics/overlays/sonda solo en escena; overlays por `view.add_overlay`;
invalidar en `_on_image_loaded`. Patrones a clonar: `ufe_annotate_tab.py`
(marcador + readout) y `ufe_compare_tab.py` (worker + tabla).

- **Flujo**: con la placa cargada y una secuencia en Comparar, un clic
  en la estrella/SN mide: centroide → apertura → comps medidas en la
  misma placa → ZP → magnitud calibrada ± error. Panel de resultados:
  mag instrumental, ZP ± err (N comps), mag final ± err, banda, y las
  guardas en lenguaje llano («saturada», «demasiado cerca del borde»,
  «pocas comps: la dispersión manda»).
- **Overlays en la escena**: círculo de apertura + anillo de cielo sobre
  el punto medido (radios en píxeles de placa, pen cosmético), y anillos
  finos sobre las comps usadas; se limpian al salir de la pestaña.
- **Aperturas configurables** (3 spins: r_ap, r_in, r_out con los
  defaults de series) y checkbox «sigma-clip del cielo» (D3).
- **Sonda**: la de la pestaña Comparar si hay estrella cerca; si no, la
  de píxel/DN/RA del estado (patrón ya escrito en compare).
- **Sin secuencia**: la pestaña muestra la guía («Genera o propone una
  secuencia en la pestaña Comparar») y un botón que cambia de pestaña.
- **Export**: «Exportar medida…» escribe CSV (una fila) y ofrece la
  línea EFF (con CNAME/CMAG/KNAME/KMAG desde la secuencia); el original
  nunca se toca. Nada de red.
- **Ganancia/RON**: leídos por `header_instrument(state.header)`; si
  faltan, Ajustes (añadir `ccd_gain`/`ccd_read_noise` al diálogo de
  settings SOLO si D2 se firma con esa variante); el panel indica cuál
  modelo de error se usó.

Tests (`tests/unit/test_ufe_measure_tab.py`, offscreen, patrón
`qapp`/`deleteLater` de los vecinos): placa sintética con WCS falso
(helper `_make_fits` de `test_fits_annotate.py` + tarjetas WCS a mano,
ver `test_ufe_state._FAKE_CARDS`), secuencia sintética inyectada en la
pestaña Comparar falsa (stub con `_entries`), clic → magnitud dentro de
tolerancia, guardas visibles, export CSV/EFF a `tmp_path`, invalidación
al cargar otra placa, sin secuencia → guía mostrada.

### G3: cierre

- i18n: `pyside6-lupdate` con la línea exacta de CONTRIBUTING (cubre
  `gui/*.py`, `gui/widgets/*.py`, `ui/*.ui`); rellenar ES/EN sin dejar
  `unfinished`; `pyside6-lrelease`; verde `test_i18n*`.
- `docs/PHOTOMETRY.es.md`/`PHOTOMETRY.md`: nueva sección «La medida
  calibrada en el Editor FITS» (el doc actual describe a propósito solo
  lo que existía): ZP, error con ecuación CCD, banda V, guardas; y el
  ejemplo trabajado gana la calibración completa número a número.
- `docs/UFE.es.md`/`UFE.md`: sección de la pestaña Medir.
- ADR-044: rev con la fase G (o ADR-045 nuevo si se prefiere separar;
  recomendado: rev de ADR-044, es la misma decisión de editor unificado).
- `AGENTS.md`: `core/photometry.py` en core/ y la pestaña en la línea
  del UFE.
- `docs/PLANS/unified-fits-editor.md`: la línea «Queda pendiente» apunta
  a este plan mientras dure G, y se marca al cerrar.
- Suite `tests/unit` completa verde antes de cada commit; commits al
  estilo de la casa (feat + docs separados); push solo si el usuario lo
  pide.

## Mapa de APIs (exploración ya hecha; no repetir)

- `core/series.py`: `_centroid(data, x, y, half=5)`;
  `aperture_flux(data, x, y, r_ap, r_ann_in, r_ann_out) -> (flux, sky_pp)`;
  `instrumental_mag(data, x, y, ...)`; `R_AP=6.0`, `R_ANN_IN=10.0`,
  `R_ANN_OUT=15.0`, `_SAT_FRAC=0.85`. Ojo: `aperture_flux` devuelve
  (None, None) fuera de bordes; el cielo es mediana SIN sigma-clip (eso
  es lo que añade D3 en el módulo nuevo).
- `core/compstars.py`: estrellas con `bands` (lista de
  `{"label", "value", "err", "derived"}`; Gaia: G nativa + B, V, Rc, Ic,
  B-V derivados; APASS: B, V directas + Sloan), `star["bv"]`,
  `star["mag"]`, `star["band"]`. Secuencia: `{"name", "kind", "star"}`.
- `core/phototrans.py`: `gaia_to_johnson(g, bp_rp)`, `combine_err`.
- `core/photometry_export.py`: `export_csv(points, out, name, ...,
  comp_stars=[...])`, `export_eff(points, out, name, ..., comp=, check=)`;
  un punto es `{"mjd", "filter", "mag", "err"}`. La pestaña Medir
  construye un punto de una fila; HJD por `hjd_of` si hay fecha de
  observación en la cabecera (DATE-OBS), si no, EFF omite sin drama.
- UFE: `state.data` (float32, fila 0 abajo), `state.scene_to_data /
  data_to_scene`, `state.probe_text`, `state.header`; vista:
  `add_overlay`, `clear_overlays`, `scene_clicked`, `set_hover_probe`,
  `current_factor`; diálogo: `tab_compare` expone `_entries` (leer con
  método público nuevo `entries()` mejor que el atributo; añadirlo es
  parte de G2 y es la única modificación permitida a `ufe_compare_tab.py`
  en esta fase).
- Reglas inamovibles: cabecera del proyecto en todo `.py`; código en
  inglés; `self.tr()` para toda cadena visible; red SOLO por
  `core/db.py` (esta fase no necesita red); docs sin raya «—»;
  semirraya solo en rangos numéricos; el diálogo legacy
  (`seqchart_dialog.py`, blink, anotar) NUNCA se toca.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| ADU ≠ electrones sin ganancia: el error CCD sería ficticio | D2: degradar a «solo dispersión de comps» y decirlo en el panel |
| Comps Gaia sin BP−RP (sin V derivada) | se saltan con log y cuentan en el panel («usadas 5 de 7») |
| Pocas comps: la mediana de ZP es frágil | aviso si N < 3; con 1 comp el error es honestamente grande |
| Cielo con gradiente (núcleos) sesga la mediana | D3 sigma-clip por defecto + nota en la doc |
| El usuario mide sin secuencia o sin WCS | la pestaña guía, nunca casca (tests de estado vacío) |
| Series temporales | fuera de ámbito (D4): existe `quicklook` |

## Criterios de aceptación

1. En una placa sintética con estrellas de flujo conocido, la magnitud
   calibrada se recupera a <0.01 mag y el error reportado es coherente
   con el ruido inyectado.
2. En una placa real (fixture `sn2026zji_new_image.fits` + secuencia
   sintética inyectada), la pestaña mide con un clic y muestra panel
   completo con guardas.
3. Export CSV/EFF de la medida correctos campo a campo (tests contra
   `photometry_export` ya probado).
4. Sin secuencia, sin WCS o sin ganancia: la pestaña guía en lenguaje
   llano; nada se rompe.
5. Suite `tests/unit` completa verde; i18n sin `unfinished`; los
   diálogos legacy intactos.
6. `docs/PHOTOMETRY.*` explica la medida calibrada con el ejemplo
   numérico completo.

## Lista de control por fase (cierre)

- [ ] Tests unitarios verdes (suite completa).
- [ ] Docs de usuario actualizadas (PHOTOMETRY + UFE, ambos idiomas).
- [ ] ADR-044 revisado (o ADR-045 si se decidió separar).
- [ ] Plan actualizado con los checkboxes y la línea de estado.
