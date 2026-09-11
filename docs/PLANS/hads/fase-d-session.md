# HADS — Fase D: flujo de sesión, fotometría y cierre

> Subplanes D.1–D.5 del plan maestro [../hads-stars.md](../hads-stars.md).
> Un subplan = un commit. Anclas verificadas a HEAD `c607b81`; si una no
> coincide: **parar y reportar**.
> Guardarraíl H-n: todo lo fotométrico se implementa **agnóstico de kind**
> (el track posterior de variables/campañas lo reutilizará).

---

## D.1 — Bloque de plan HADS (sesión 2P, cadencia, checklist)

**Lee primero**: `nightscribe/gui/main_window.py` — `_build_transit_block`
(:2797-2953) completo, dispatch en `_build_plan_tab` (:1945-1946), helpers
`_as_dt` (:2814-2824), exposición (:2878-2887), cadencia con
`_refresh_cadence` (:2888-2913), checklist persistente (:2929-2952 + guardado
:2955-2962).

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_hads_plan.py` (**nuevo**, patrón `test_transit_plan.py`);
i18n.

**Implementa**:
1. `_build_hads_block(self, layout, p, ctx, spn_exp)` tras
   `_build_transit_block` (:2953); dispatch tras :1945-1946:
   ```python
   if kind == "hads" and (ctx.get("hads") or {}):
       self._build_hads_block(layout, p, ctx, spn_exp)
   ```
2. Contenido (`QGroupBox(self.tr("HADS capture plan"))`), leyendo
   `h = ctx["hads"]` y las claves de ventana del ctx (`safe_window`,
   `best_time`, `latest_safe_start`, `max_alt`):
   - Línea resumen: periodo P h · amplitud Δ mag · **sesión recomendada
     2×P h** (`tr("Recommended session: %1 h (2 periods)")`).
   - Ventana segura: `best_time` (UTC + local) … `latest_safe_start`; «caben
     N ciclos esta noche».
   - Exposición heurística `h["exp_s"]` → etiqueta + `spn_exp.setValue(...)`
     (patrón :2878-2887).
   - Cadencia: etiqueta con closure `_refresh_cadence()` (patrón
     :2888-2913): cap de exposición = `h["cadence_s"] − overhead_s`
     (`config.get("overhead_s", 15.0)`), re-ejecutada en
     `spn_exp.valueChanged`.
   - Aviso `session_fits is False` (QLabel, `theme.C_WARN`):
     `tr("Two full cycles don't fit tonight — capture the longest
     contiguous run you can")`.
   - Checklist persistente (patrón :2929-2952, misma clave `"checklist"` en
     los datos del paso plan), 5 ítems `tr()`:
     1. `"Focus locked at imaging temperature"`
     2. `"Comparison stars identified (VSX chart)"`
     3. `"Cadence ≤ P/12 set in the capture sequence"`
     4. `"Exposure checked at MAXIMUM brightness (no saturation)"`
     5. `"Continuous run covering 2 periods planned"`
   - Sin `TransitTimeline` (no hay evento que situar; el widget es
     tránsito-específico).
3. Tests `test_hads_plan.py`: el bloque se construye con ctx fabricado; las
   etiquetas contienen P/2P/ciclos; el aviso aparece cuando
   `session_fits=False`; el checklist persiste (`update_step_data`).
4. i18n (≈15 cadenas).

**Hecho cuando**: suite verde (N→M) + `test_i18n.py`; proyecto hads muestra
su bloque de plan.
**Commit**: `Gui: HADS capture plan block — 2P session, cadence, checklist (ADR-034, subplan D.1)`
**Estado**: **Hecho** (969→974). Hallazgo al ejecutar: `lupdate` NO extrae
`self.tr()` dentro de llaves de f-string — las cadenas nuevas del bloque se
escribieron como `self.tr("...")` plano + concat; el bloque de tránsitos
tiene dos cadenas preexistentes («Recommended exposure», «honest guide…»)
con ese mismo agujero de extracción (nunca fueron traducibles): **reportado
para una corrección futura fuera de este plan**.

---

## D.2 — Secuencia CCDciel hads

**Lee primero**: `nightscribe/core/sequence.py` (`make_plan` :34-82,
`_transit_window` :121-136, `export` :398-407, `_ccdciel_times` :273-300);
`main_window.py` `_project_export_sequence` (:3781; plan :3797-3809; target
:3811-3814; bloque transit :3816-3820; nota ccdciel :3835-3841).

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_sequence.py`; i18n si hay cadena nueva.

**Implementa**:
1. En `_project_export_sequence`, tras el bloque transit (:3816-3820):
   ```python
   if self._current_project["kind"] == "hads":
       h = ctx.get("hads") or {}
       # advisory window: any contiguous 2P inside the safe span works
       if ctx.get("best_time"):
           start = <datetime de ctx["best_time"]>
           target["capture_start"] = start
           target["capture_end"] = start + timedelta(hours=h.get("session_req_h") or 0)
   ```
2. Default del spin de frames: `n_frames = int(session_req_h * 3600 /
   (exp_s + overhead_s))` (mira cómo se alimenta `make_plan` en :3797-3806 y
   replica el patrón; la exposición preferida ya la fija D.1).
3. Nota de exportación distinta de la de tránsito (:3835-3841):
   `tr("HADS: the window is advisory — any contiguous 2-period run inside
   the safe span works")`.
4. Tests `test_sequence.py`: ventana escrita en la exportación CSV/CCDciel;
   duración total del plan ≈ 2P.

**Hecho cuando**: suite verde (N→M).
**Commit**: `Gui: HADS CCDciel sequence export — 2P advisory window (ADR-034, subplan D.2)`
**Estado**: **Hecho** (974→977). Hallazgo al ejecutar: una ventana de captura
en el export CCDciel escribía siempre `MandatoryStartTime=True` (semántica de
tránsito) — semántica equivocada para HADS. Cambio mínimo: flag
`capture_advisory` en el target → tiempos escritos, inicio blando
(`_ccdciel_times`, sequence.py). El default de frames (2P/(exp+overhead)) se
fija en `_build_hads_block` (nuevo parámetro `spn_frames`).

---

## D.3 — Follow-up + process (handoff FotoDif/WebObs)

**Lee primero**: `main_window.py` — gate de Follow-up (:1891-1899),
`_build_followup_tab` (:3023-3104; recordatorio de cadencia :3033-3044;
botones :3046-3058; botones de análisis :3083-3102; quicklook con `sn_type`
:3131-3133), bloque EXOTIC `_transit_export_exotic` (:2964+, patrón de
handoff); `nightscribe/gui/overview.py` `_inject_followup` (:455-477, gate
:460-461); `nightscribe/core/photometry_import.py` (ya traga «JD - mag» de
FotoDif).

**Toca**: `main_window.py`, `overview.py`; tests `test_followup.py`,
`test_project_tabs.py`; i18n.

**Implementa**:
1. Gate (:1894) → constante de módulo (guardarraíl H-n):
   `FOLLOWUP_KINDS = ("sn", "hads")` y `if kind in FOLLOWUP_KINDS:`.
2. En `_build_followup_tab`, para `kind == "hads"`: ocultar los botones
   SN-específicos (quick-look, animación, FITS anotado — el quick-look usa
   apilados por noche, no series intra-noche) guardando refs al crearlos;
   texto de cadencia por kind (:3033-3044): hads →
   `tr("Last visit: %1 nights ago — multiperiodic stars want consecutive nights")`
   cuando `ctx["hads"]["multiperiodic"]`.
3. `overview._inject_followup` (:460): gate → `("transient", "sn", "hads")`.
4. Bloque process `_build_hads_process(layout, p, ctx)` (localiza el dispatch
   de la pestaña process; espejo del handoff EXOTIC):
   - Instrucciones `tr()` multi-línea: reducir con **FotoDif** (modo AUTO para
     seguirla en directo) o AIJ; FotoDif genera el informe **AAVSO Extended
     File Format** directamente; cadencia y exposición del bloque de plan.
   - Botón `tr("Open AAVSO WebObs")` →
     `QDesktopServices.openUrl(QUrl("https://www.aavso.org/webobs/"))`
     (mira cómo abre URLs el bloque EXOTIC y replica).
   - Muestra `config.get("aavso_code")`; si vacío, aviso con enlace a
     Settings.
   - Recuerda que la salida de FotoDif se importa con «Import photometry
     file» de la pestaña Follow-up.
5. Tests: `test_followup.py` (tab visible para hads, botones SN ocultos);
   `test_project_tabs.py`.
6. i18n (≈20 cadenas).

**Hecho cuando**: suite verde (N→M) + `test_i18n.py`.
**Commit**: `Gui: HADS follow-up tab + FotoDif/WebObs process block (ADR-034, subplan D.3)`
**Estado**: **Hecho** (977→981). Nota: la constante de módulo
`FOLLOWUP_KINDS = ("sn", "hads")` deja la puerta kind-agnóstica (H-n); la
importación FotoDif queda cubierta por un test de integración (JD mag err →
`photometry_import` → `followup`).

---

## D.4 — Plegado por fase (widget + viz)

**Lee primero**: `nightscribe/gui/widgets/lightcurve_widget.py` (`set_data`
:107-117, `_compute_bounds` :119-132, `_map_x` :134-140, `_draw_grid`
:276-277, `_probe` :300-325, plantilla SN :158); su gemelo matplotlib
`nightscribe/viz/lightcurve_view.py` (paridad obligatoria, ADR-029);
`nightscribe/gui/overview.py` — `_extract` lightcurve (:888-897),
`_rebuild_widget` (:930-936).

**Toca**: `lightcurve_widget.py`, `viz/lightcurve_view.py`, `overview.py`;
tests `test_lightcurve_widget.py`, `test_lightcurve_view.py`; i18n.

**Implementa** (agnóstico de kind — guardarraíl H-n):
1. `set_data(self, points, sn_type=None, peak_mjd=None, peak_mag=None,
   fold_period_d=None, epoch_mjd=None, schematic=None)`:
   - Plegado activo si `fold_period_d`: `x = ((mjd − epoch) / P) % 1`;
     dibujar fase 0..2 (puntos duplicados desplazados +1 ciclo); `epoch`
     default = min(mjd).
   - `_compute_bounds` sobre fase; `_map_x` lineal en fase; `_draw_grid` con
     etiquetas «Phase 0.0 … 2.0»; `_probe` muestra «phase 0.42 · MJD …».
   - La plantilla SN se omite en modo plegado; `schematic` = lista
     `(phase, mag)` dibujada en línea discontinua + entrada de leyenda
     `tr("schematic")`.
2. `viz/lightcurve_view.py`: mismos parámetros y mismo dibujo (paridad).
3. Cableado en `overview.py`: para hads, `fold_period_d =
   ctx["hads"]["period_h"] / 24` y `schematic = hads.sawtooth_template(
   period_h, amp, mag_med)` (H0.4).
4. Tests: fold math (mjd→fase conocida), doble ciclo dibujado, texto del
   probe; PNG con plegado en `test_lightcurve_view.py` (patrón existente);
   sawtooth ya cubierto en H0.4.
5. i18n (≈4 cadenas: leyenda, etiquetas de ejes).

**Hecho cuando**: suite verde (N→M) + `test_i18n.py`; la curva de un proyecto
hads con puntos se pliega en dos ciclos.
**Commit**: `Gui/Viz: light-curve phase folding + schematic sawtooth for HADS (ADR-034, subplan D.4)`
**Estado**: **Hecho** (981→988). El plegado es agnóstico de kind
(`fold_period_d`/`epoch_mjd`/`schematic` en widget y PNG, paridad ADR-029);
el cableado de overview toma el periodo de `ctx["hads"]` o `data["hads"]`.

---

## D.5 — Post con curva + cierre documental

**Lee primero**: `nightscribe/core/post.py` `build_charts` (:178-317; patrón
de curva SN :302-315); `docs/WORKFLOWS.es.md` (formato de sección: espejo de
`### 7terdecies`, línea 736; cierra con `**Estado**: suite unitaria verde
(N)`); `docs/adr/ADR-034-hads-stars.md`; `AGENTS.md` (árbol de estructura,
ES+EN).

**Toca**: `core/post.py`; `docs/WORKFLOWS.es.md` + `docs/WORKFLOWS.md`;
`docs/adr/ADR-034-hads-stars.md`; `AGENTS.md`; i18n final.

**Implementa**:
1. `post.py` (:302-315): gate de la curva → `("transient", "sn", "hads")`;
   para hads llama a `lightcurve_view.draw_lightcurve(..., fold_period_d=P/24,
   schematic=sawtooth)` con los parámetros de D.4.
2. WORKFLOWS.es.md: nueva sección
   `### 7quaterdecies. Track HADS — estrellas variables de alta amplitud
   (2026-09-XX, ADR-034)` (siguiente número libre tras 7terdecies): resumen,
   tabla de subplanes H0.1–D.5 con estado, nota de la fuente híbrida y la
   leyenda, y `**Estado**: suite unitaria verde (N)`. Gemelo en
   `docs/WORKFLOWS.md`.
3. ADR-034 revisado: H-b pasa a «fuente híbrida (sheet en runtime TTL 12 h +
   snapshot de respaldo)», añadir H-i…H-n, marca `rev. 2026-09-XX`.
4. `AGENTS.md`: añadir `core/hads.py` y `core/sources/hads_sheet.py` al árbol
   de estructura (secciones ES y EN).
5. Barrido i18n final (pipeline completo) + `pytest tests/unit` (anota N) +
   `pytest tests/functional` con red (incluye `test_hads_live`).

**Hecho cuando**: suites verdes y documentación al día; rama lista para
merge a `feature/object-card`.
**Commit**: `Docs/i18n: HADS track close — WORKFLOWS 7quaterdecies, ADR-034 rev, AGENTS.md (subplan D.5)`
**Estado**: pendiente
