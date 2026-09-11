# HADS — Fase B: GUI mínima (listable, configurable, ficha)

> Subplanes B.1–B.4 del plan maestro [../hads-stars.md](../hads-stars.md).
> Un subplan = un commit. Anclas verificadas a HEAD `c607b81`; si una no
> coincide: **parar y reportar**.
> Todo subplan que toca cadenas GUI ejecuta el pipeline i18n completo
> (lupdate → traducir ES/EN → lrelease; comandos en el maestro §Protocolo) —
> `test_i18n.py` falla con traducciones `unfinished` o vacías.

---

## B.1 — Listable y puntuable (theme, tabla, icono, fase)

**Lee primero**: `nightscribe/gui/theme.py:33-49` (KIND_COLORS/KIND_LABELS);
`nightscribe/gui/main_window.py` — `TABLE_COLS` (:143-166, transit
:158-161), `KIND_ORDER` (:175), `_table_value` (:1395; mapa de kind
:1398-1403; claves transit :1445-1452), `_type_pixmap` (:771-835),
`_tonight_progress` (:847-880, mapa :854-862).

**Toca**: `theme.py`, `main_window.py`; tests `test_tonight_kinds.py`,
`test_tonight_rows.py`, `test_theme.py`; i18n.

**Implementa**:
1. `theme.py`: `KIND_COLORS` += `"hads": "#e0549e",   # 320° magenta` (hueco
   mayor de la rueda; la banda ámbar 40-65° está reservada a warnings).
   Actualiza el comentario «Six well-separated hues» → seven + 320°.
   `KIND_LABELS` += `"hads": "HADS"`.
2. `main_window.py:175`: `KIND_ORDER` += `"hads"` (al final).
3. `TABLE_COLS` tras la entrada transit (:161):
   ```python
   "hads": [("Object", "name"), ("Score", "score"),
            ("Period", "period"), ("Amp", "amp"), ("Cycles", "cycles"),
            ("Max alt", "max_alt"), ("Best (UTC)", "best"),
            ("Observed", "obs")],
   ```
4. `_table_value`: mapa de kind (:1398-1403) += `"hads": self.tr("HADS star")`;
   claves nuevas (tras las de transit :1445-1452):
   ```python
   if key == "period":
       p = (t.get("hads") or {}).get("period_h")
       return f"{p:.2f} h" if p else "—"
   if key == "amp":
       a = (t.get("hads") or {}).get("amp")
       return f"Δ {a:.1f}" if a else "—"
   if key == "cycles":
       c = (t.get("hads") or {}).get("cycles")
       return f"{c:.1f}" if c else "—"
   if key == "best":
       # mismo patrón ISO→HH:MM que usen las claves vecinas (max_time)
   ```
   Para `"best"` mira cómo renderizan las claves existentes sobre
   `best_time`/`max_time` y replica exactamente ese patrón.
5. `_type_pixmap`: `elif kind == "hads":` antes de `p.end()` (:834): estrella
   de 4 puntas (mismo path que SN :785-798) + onda senoidal pequeña debajo
   (QPainterPath con `cubicTo`), en el color del kind.
6. `_tonight_progress` (:854-862): `"hads": self.tr("Checking HADS variables…"),`.
7. Tests: añadir un target hads (con sub-dict `hads` completo) a `TARGETS` de
   `test_tonight_kinds.py` (:37-55) y `test_tonight_rows.py` (:26-50);
   actualizar las listas hardcodeadas de kinds a 7 (tonight_kinds :73-74,
   :81-82, :137-138 — incluido el reset de `enabled_kinds` de la fixture);
   aserción: columna Period muestra `"1.89 h"`. `test_theme.py`: color/label
   presentes.
8. i18n: pipeline completo; cadenas nuevas ≈ 8-12 («HADS star», cabeceras de
   tabla, etiqueta de fase).

**Hecho cuando**: suite verde (N→M) incluido `test_i18n.py`; la tabla Tonight
muestra la entrada hads con sus columnas.
**Commit**: `Gui: HADS kind listable — color, icon, table columns, phase label (ADR-034, subplan B.1)`
**Estado**: **Hecho** (946→947). Notas: la columna «Best time (UTC)» reusa la
clave genérica `best_time` (ISO→HH:MM ya existente); solo 2 cadenas nuevas
(《HADS star》, fase de progreso) — las cabeceras ya existían de otros kinds.

---

## B.2 — config + settings checkbox + combos de proyectos

**Lee primero**: `nightscribe/config.py` (DEFAULTS :22-69, `enabled_kinds`
:58, `load()` :82-90 — **no hay mecanismo de migración**: el valor guardado
manda); `nightscribe/gui/main_window.py` — `on_open_settings` (:492; carga de
checkboxes :555-561, guardado :619-629, **automático por convención de
nombre** `chk_kind_<kind>`), filtro de proyectos (:1567-1569, :1603-1605);
`nightscribe/gui/ui/settings_dialog.ui` (`grid_kinds` :210-218);
`nightscribe/gui/ui/projects_tab.ui` (`cmb_kind` :27-34).

**Toca**: `config.py`, `settings_dialog.ui`, `projects_tab.ui`,
`main_window.py`; tests; i18n.

**Implementa**:
1. `config.py:58`: default += `"hads"` (al final, como `KIND_ORDER`).
2. Migración amable al final de `Config.load()`:
   ```python
   # HADS rollout: a stored list equal to the pre-HADS default gets the new
   # kind for free; a customised list is never touched
   _OLD_KINDS = ["neo", "sn", "comet", "pccp", "transit", "alert"]
   if self._data.get("enabled_kinds") == _OLD_KINDS:
       self._data["enabled_kinds"] = list(DEFAULTS["enabled_kinds"])
   ```
   (Sin escritura a disco: se persiste en el próximo guardado de Settings.)
3. `settings_dialog.ui`: `<widget class="QCheckBox" name="chk_kind_hads">`
   «HADS variable stars» en `grid_kinds` fila 3, col 0.
4. `projects_tab.ui` `cmb_kind`: `<item>` «HADS» tras «Transit» (índice 6) —
   **a la vez** que `main_window.py:1568`: tupla → `(None, "sn", "neo",
   "comet", "pccp", "transit", "hads")` y :1603-1605 mapa += `"hads": "HADS"`.
5. Tests (patrón `test_settings_tabs.py`): el checkbox existe y guarda/carga;
   migración: config guardada con la lista antigua → 7 kinds; lista
   personalizada intacta; combo de proyectos incluye HADS y filtra.
6. i18n (~4 cadenas).

**Hecho cuando**: suite verde (N→M) + `test_i18n.py`; migración cubierta por
test.
**Commit**: `Gui/Config: HADS in enabled_kinds with friendly migration + settings/projects combos (ADR-034, subplan B.2)`
**Estado**: **Hecho** (947→953). Nota: el test de «crear proyecto hads y
filtrarlo» queda en C.1 (necesita `VALID_KINDS`); aquí se cubre el combo
posicional (.ui índice 6 ⇆ tupla de `on_refresh_projects`) y la migración
con `tests/unit/test_config.py` nuevo.

---

## B.3 — enrich (`detect_type` hads)

**Lee primero**: `nightscribe/core/enrich.py:27-81` (`detect_type` :27-40,
rama exoplanet :58-65, `_copy_window_context` :120-132);
`tests/unit/test_enrich_exoplanet.py` (patrón).

**Toca**: `nightscribe/core/enrich.py`;
`tests/unit/test_enrich_hads.py` (**nuevo**).

**Implementa**:
1. `detect_type`: rama hads tras el check transient (:34) y **ANTES de la
   regex de exoplaneta (:38)** — la regex `[\w-]\s?(b|c|d|e|f)$` se tragaría
   «GP And» (termina en «d»):
   ```python
   if hads.lookup(n):
       return "hads"
   ```
   Actualiza el comentario `@return` (:29). `hads.lookup` usa el bundle
   (offline por diseño, H0.4).
2. `enrich()`: rama tras la de exoplanet (:58-65), antes del fallthrough
   small_body:
   ```python
   if kind == "hads":
       data = {"hads": hads.lookup(name) or {}}
       if fallback_target:
           _copy_window_context(data, fallback_target)
           if fallback_target.get("hads"):
               data["hads"] = fallback_target["hads"]  # planner values win
                                                       # (tonight's cycles…)
       return {"type": "hads", "name": name, "data": data}
   ```
3. Tests `test_enrich_hads.py`: «GP And» → `"hads"` (**regresión del regex**:
   no `"exoplanet"`); alias «GSC 01739-01964» → `"hads"`; «Ceres» →
   `"small_body"` (sin red: `detect_type` es local); `enrich` con
   `fallback_target` del planner → `data["hads"]` trae `cycles`.

**Hecho cuando**: tests verdes; suite verde (N→M). CLI `explore "GP And"`
hereda la detección gratis (cmd_explore llama a `enrich.enrich`,
`__main__.py:69`).
**Commit**: `Core: HADS detection in enrich (alias-aware, before the exoplanet regex) (ADR-034, subplan B.3)`
**Estado**: pendiente

---

## B.4 — Ficha de objeto (`explain_hads` + chips)

**Lee primero**: `nightscribe/core/orbits.py` — contrato de
`explain_transit` (:720-900: filas `{"param": {"es","en"}, "value", "level",
"es", "en"}`); `nightscribe/gui/overview.py` — `_orbit_rows` (:648-673),
`_capture_chips` (:955-1065; patrones :997-1021).

**Toca**: `nightscribe/core/orbits.py`; `nightscribe/gui/overview.py`; tests
`test_orbits.py`, `test_overview_panel.py`; i18n.

**Implementa**:
1. `orbits.explain_hads(d)` nueva, tras `explain_transit` (final del fichero,
   ~:900), mismo contrato. Filas (nivel `basic` salvo indicación):
   - Periodo: `f"{period_h:.2f} h"` — es: «Tiempo que tarda en dar un pulso
     completo: caben varios en una noche» / en: «Time for one full pulsation:
     several fit in a single night».
   - Amplitud: `f"Δ {amp:.1f} mag"` — es: «Cambio de brillo pico a pico —
     suficiente para verlo a simple vista en la curva» / en: «Peak-to-peak
     brightness swing — large enough to watch in the curve».
   - Rango: `f"{max:.1f}–{min:.1f} mag"`.
   - Modos: fundamental / multiperiódica (noches consecutivas; ratio
     Petersen 0.76–0.78 entre overtone y fundamental) / no-radial (raro).
   - Prioridad del programa (si `priority`): rojo/naranja → explicación ES/EN
     del seguimiento de P. Wils.
   - Divulgativa (`basic`): «Es una δ Scuti de gran amplitud (HADS): pulsa en
     la franja de inestabilidad, donde antes reinaban las cefeidas» /
     «A high-amplitude δ Scuti (HADS): it pulsates in the instability strip,
     where Cepheids rule».
   - Histórica (`deep`): «Antes se llamaban 'cefidas enanas' por sus curvas en
     diente de sierra» / «They were once called 'dwarf Cepheids' for their
     sawtooth light curves».
2. `overview._orbit_rows`: rama tras la de transit (:669-672):
   `if e.get("type") == "hads" or d.get("hads"): return orbits.explain_hads(d)`.
3. `_capture_chips`: `is_hads = kind == "hads" or bool(d.get("hads"))`
   (patrón :999); chips `(texto, color, tooltip con tr())`:
   Periodo (color `KIND_COLORS["hads"]`), Amplitud, Ciclos (desde
   `ctx["hads"]`); `period_change` → («Period change!», `theme.C_WARN`);
   `unobserved` → («Not yet observed», `theme.C_OK`); multiperiodic →
   («Multiperiodic», color hads).
4. Tests: `test_orbits.py` (filas presentes, ES/EN, niveles);
   `test_overview_panel.py` (chips hads con ctx fabricado).
5. i18n (chips/tooltips ≈ 10 cadenas; las filas `explain_hads` son dicts
   es/en en core — no pasan por `tr()`).

**Hecho cuando**: suite verde (N→M) + `test_i18n.py`; la ficha de «GP And»
muestra filas y chips.
**Commit**: `Gui: HADS object card — explain_hads rows + capture chips (ADR-034, subplan B.4)`
**Estado**: pendiente
