# Track V — Fase B: kind visible y enriquecido

> Subplanes VB.1–VB.6 del plan maestro
> [../variables-campaigns.md](../variables-campaigns.md). Un subplan = un
> commit. Anclas verificadas a HEAD `4b7635a`; si una no coincide: **parar y
> reportar**. Lee antes `LEEME.md`.
> Precondición: fases 0 y A hechas (VB.1 solo necesita motivación; VB.5/6
> necesitan V0.4/V0.8).

---

## VB.1 — Theme: color y etiqueta del kind `variable`

**Contexto a leer (solo esto)**: `nightscribe/gui/theme.py:32-50`;
`tests/unit/test_theme.py:46-55`.

**Toca**: `nightscribe/gui/theme.py`; `tests/unit/test_theme.py` (edición
puntual, la única permitida en este fichero).

**Escribe exactamente esto**:

1. `theme.py:33-35` — el comentario sobre los tonos pasa a:
   ```python
   # Per-kind accent colors, shared by cards, icons and table names.
   # Eight well-separated hues on the wheel (0/24/100/140/185/216/268/320°),
   # none in the amber band (40-65°), all saturated, mid-value.
   ```
2. `theme.py` `KIND_COLORS` (:36-44): tras la entrada `"hads"`, añade:
   ```python
       "variable": "#65cf30",   # 100° yellow-green (the last free arc)
   ```
3. `theme.py` `KIND_LABELS` (:47-50): añade `"variable": "VAR",` al final.
4. `tests/unit/test_theme.py:49`: el set `expected` pasa a
   `{"sn", "neo", "comet", "pccp", "transit", "alert", "hads", "variable"}`.

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_theme.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui/Theme: variable kind color (yellow-green 100°) + label (ADR-035, subplan VB.1)`
**Estado**: ✅ Hecho (2026-09-11)

---

## VB.2 — `main_window.py`: icono, columnas, orden y labels

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:147-183`
(`TABLE_COLS`, `KIND_ORDER`), `:842-864` (rama hads de `_type_pixmap`),
`:877-895` (`_tonight_progress`), `:1429-1500` (`_table_value`), `:1644-1647`
y `:1811-1815` (mapas kind_label).

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_tonight_kinds.py` (edición puntual :139-144, la única
permitida en ese fichero).

**Escribe exactamente esto**:

1. `TABLE_COLS` (:148-174): tras la entrada `"hads"` (:166-169), añade:
   ```python
       "variable": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
                    ("Period (d)", "vperiod"), ("Next extremum", "vext"),
                    ("Campaign", "camp"), ("Max alt", "max_alt"),
                    ("Best time (UTC)", "best_time"), ("Observed", "obs")],
   ```
2. `KIND_ORDER` (:183) →
   `KIND_ORDER = ["neo", "sn", "comet", "pccp", "transit", "alert", "hads", "variable"]`
3. `_type_pixmap`: tras la rama `elif kind == "hads":` (termina en :863),
   añade (antes del `p.end()` de :864):
   ```python
           elif kind == "variable":
               # long-period variable: 4-point star + a slow wave underneath
               p.setBrush(QBrush(color))
               path = QPainterPath()
               path.moveTo(QPointF(cx, 4))
               path.lineTo(QPointF(cx + 3, cy - 5))
               path.lineTo(QPointF(size - 4, cy - 5))
               path.lineTo(QPointF(cx + 3, cy - 5 + 3))
               path.lineTo(QPointF(cx, cy + 1))
               path.lineTo(QPointF(cx - 3, cy - 2))
               path.lineTo(QPointF(4, cy - 5))
               path.lineTo(QPointF(cx - 3, cy - 5))
               path.closeSubpath()
               p.drawPath(path)
               p.setPen(QPen(color, 1.5))
               wave = QPainterPath()
               wave.moveTo(QPointF(3, size - 8))
               wave.cubicTo(QPointF(cx - 2, size - 2),
                            QPointF(cx + 2, size - 12),
                            QPointF(size - 3, size - 7))
               p.drawPath(wave)
   ```
4. `_tonight_progress` (:884-893): el dict `phases` gana, tras `"hads"`:
   ```python
               "campaigns": self.tr("Checking campaign targets…"),
   ```
5. `_table_value` (:1429-1436): el mapa de `key == "kind"` gana
   `"variable": self.tr("Variable star")` dentro del dict (tras `"hads"`).
6. `_table_value` (:1485-1493): tras la rama `if key == "cycles":`, añade:
   ```python
           if key == "vperiod":
               per = (t.get("variable") or {}).get("period_d")
               return f"{per:.1f} d" if per else "—"
           if key == "vext":
               nxt = (t.get("variable") or {}).get("next_extremum") or {}
               days = nxt.get("days")
               if days is None:
                   return "—"
               lab = self.tr("max") if nxt.get("kind") == "max" \
                   else self.tr("min")
               return f"{lab} ~{days:.0f} d"
           if key == "camp":
               return (t.get("campaign") or {}).get("name") or "—"
   ```
7. Mapa de `on_refresh_projects` (:1644-1647): añade `"variable":
   self.tr("Variable"),` tras `"hads": "HADS"`.
8. `_render_project_header` (:1811-1815): añade `"variable":
   self.tr("Variable star")` tras `"hads": "HADS"`.
9. `tests/unit/test_tonight_kinds.py:139-144`: el comentario dice «the eight
   enabled kinds» y la lista literal pasa a `["neo", "sn", "comet", "pccp",
   "transit", "alert", "hads", "variable"]`.

**Cadenas nuevas** (lupdate + traducir):

| Fuente | ES | EN |
|---|---|---|
| Checking campaign targets… | Comprobando objetivos de campaña… | Checking campaign targets… |
| Variable star | Estrella variable | Variable star |
| Variable | Variable | Variable |
| max | máx | max |
| min | mín | min |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_tonight_kinds.py tests/unit/test_tonight_rows.py -q` + pipeline i18n (LEEME §3)
**Hecho cuando**: verde; suite verde (N→M); `pyside6-lrelease` sin errores.
**Commit**: `Gui: variable kind listable — icon, table columns, phase label (ADR-035, subplan VB.2)`
**Estado**: ✅ Hecho (2026-09-11)
**Desviación del fixture** (necesaria para consistencia interna, la tarjeta solo permitía :139-144):
- `window` fixture (:78-89): `enabled_kinds` → 8 kinds (añade `"variable"`).
- `:224`: `count() == 8` → `count() == 9` (All + 8 kinds).

---

## VB.3 — Config: `enabled_kinds` + migración amable + `event_mag_threshold`

**Contexto a leer (solo esto)**: `nightscribe/config.py:56-70, 83-96`;
`tests/unit/test_config.py` (entero, 52 líneas).

**Toca**: `nightscribe/config.py`; `tests/unit/test_config.py`
(**reescritura completa permitida — el contenido nuevo va aquí dado**).

**Escribe exactamente esto**:

1. `config.py:58-59` — el default pasa a ocho kinds:
   ```python
       "enabled_kinds": ["neo", "sn", "comet", "pccp", "transit", "alert",
                         "hads", "variable"],
   ```
2. `config.py`, tras `"sn_cadence_days": 3,` (:64), añade:
   ```python
       # Track V (ADR-035, V-h): brightness-jump threshold for the variable
       # event advisor (dip/outburst vs. the median of the previous points)
       "event_mag_threshold": 0.5,
   ```
3. `config.py:92-96` — el bloque de migración amable pasa a:
   ```python
           # HADS/Track V rollout: a stored whitelist equal to any previous
           # default gets the new kind(s) for free; a customised list is
           # never touched
           if self._data.get("enabled_kinds") in (
                   ["neo", "sn", "comet", "pccp", "transit", "alert"],
                   ["neo", "sn", "comet", "pccp", "transit", "alert",
                    "hads"]):
               self._data["enabled_kinds"] = list(DEFAULTS["enabled_kinds"])
   ```
4. `tests/unit/test_config.py` — contenido completo nuevo (cabecera GPL,
   «Unit tests: config defaults & kind migrations (HADS B.2, Track V VB.3)»):

```python
import json

from nightscribe import config as cfgmod

_OLD_SIX = ["neo", "sn", "comet", "pccp", "transit", "alert"]
_OLD_SEVEN = _OLD_SIX + ["hads"]


def _cfg_with_stored(tmp_path, stored):
    # @return: a Config whose file holds the given dict
    f = tmp_path / "nightscribe.json"
    f.write_text(json.dumps(stored), encoding="utf-8")
    cfg = cfgmod.Config()
    cfg._file = f
    cfg.load()
    return cfg


def test_default_enabled_kinds_include_hads_and_variable():
    assert "hads" in cfgmod.DEFAULTS["enabled_kinds"]
    assert "variable" in cfgmod.DEFAULTS["enabled_kinds"]
    assert len(cfgmod.DEFAULTS["enabled_kinds"]) == 8


def test_pre_hads_default_migrates_for_free(tmp_path):
    cfg = _cfg_with_stored(tmp_path, {"enabled_kinds": list(_OLD_SIX)})
    assert "hads" in cfg.get("enabled_kinds")
    assert "variable" in cfg.get("enabled_kinds")


def test_pre_variable_default_migrates_for_free(tmp_path):
    cfg = _cfg_with_stored(tmp_path, {"enabled_kinds": list(_OLD_SEVEN)})
    assert "variable" in cfg.get("enabled_kinds")


def test_customised_kind_list_is_never_touched(tmp_path):
    custom = ["neo", "sn"]
    cfg = _cfg_with_stored(tmp_path, {"enabled_kinds": custom})
    assert cfg.get("enabled_kinds") == ["neo", "sn"]


def test_migration_is_not_written_back_until_a_save(tmp_path):
    f = tmp_path / "nightscribe.json"
    cfg = _cfg_with_stored(tmp_path, {"enabled_kinds": list(_OLD_SEVEN)})
    assert "variable" in cfg.get("enabled_kinds")
    # the file still holds the old list: the migration is in-memory only
    assert json.loads(f.read_text())["enabled_kinds"] == _OLD_SEVEN


def test_event_mag_threshold_default():
    assert cfgmod.DEFAULTS["event_mag_threshold"] == 0.5
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_config.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core/Config: variable in enabled_kinds with friendly migration + event threshold (ADR-035, subplan VB.3)`
**Estado**: ✅ Hecho (2026-09-11)

---

## VB.4 — Settings + combos de proyectos (ficheros `.ui`)

**Contexto a leer (solo esto)**:
`nightscribe/gui/ui/settings_dialog.ui:210-220` (grid_kinds);
`nightscribe/gui/ui/projects_tab.ui:27-35` (cmb_kind);
`nightscribe/gui/main_window.py:1608-1610` (tupla kinds del filtro).
**Precondición**: VB.2, VB.3.

**Toca**: `nightscribe/gui/ui/settings_dialog.ui`;
`nightscribe/gui/ui/projects_tab.ui`; `nightscribe/gui/main_window.py` (una
línea); `tests/unit/test_settings_tabs.py` (si falla por el checkbox nuevo,
ver abajo).

**Escribe exactamente esto**:

1. `settings_dialog.ui`: tras el `<item row="3" column="0">` de
   `chk_kind_hads` (:218), añade:
   ```xml
               <item row="3" column="1"><widget class="QCheckBox" name="chk_kind_variable"><property name="text"><string>Variable stars</string></property></widget></item>
   ```
   (El wiring es genérico: `main_window.py:565-569` y `:628-637` recorren
   `KIND_ORDER` con `getattr(dlg, f"chk_kind_{k}")` — ya llega gratis.)
2. `projects_tab.ui`: en `cmb_kind`, tras el item `HADS` (:34), añade:
   ```xml
               <item><property name="text"><string>Variable</string></property></item>
   ```
3. `main_window.py:1609` — la tupla pasa a:
   ```python
           kinds = (None, "sn", "neo", "comet", "pccp", "transit", "hads",
                    "variable")
   ```
4. Si `tests/unit/test_settings_tabs.py` falla por el checkbox nuevo,
   **lee ese fichero**, localiza la lista de checkboxes esperados y añade
   `"chk_kind_variable"` — esa es la única edición permitida ahí.

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Variable stars | Estrellas variables | Variable stars |
| Variable | Variable | Variable |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_settings_tabs.py tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui/Config: variable checkbox in Settings + project filter combo (ADR-035, subplan VB.4)`
**Estado**: ✅ Hecho (2026-09-11)
**Nota**: `test_settings_tabs.py` no falló (el wiring genérico por `KIND_ORDER` cubre el checkbox nuevo), así que no hizo falta la edición puntual prevista en el paso 4.

---

## VB.5 — `enrich.detect_type`: variables antes de la regex exoplaneta

**Contexto a leer (solo esto)**: `nightscribe/core/enrich.py:27-44`
(`detect_type`).
**Precondición**: V0.4.

**Toca**: `nightscribe/core/enrich.py`;
`tests/unit/test_enrich_variable.py` (**nuevo**).

**Escribe exactamente esto**:

1. `enrich.py`, tras la función `detect_type` (tras :44), añade el helper y
   las regex (antes: edita `detect_type` en el punto 2):

```python
# Variable-star designations (GCVS: "T CrB", "EE Cep", "V1490 Cyg"; NSV
# catalogue) — checked BEFORE the exoplanet regex: a name ending in one
# letter reads as a planet marker there ("T CrB" would be a false planet).
# Exactly two tokens on purpose: "GQ Lup b" (three) stays an exoplanet.
_GCVS_RE = re.compile(r"^(V\d{1,4}|[A-Z]{1,2})\s+[A-Z][a-z][A-Za-z]$")
_NSV_RE = re.compile(r"^NSV\s?\d{3,5}$", re.I)


def _looks_like_variable(n):
    # @args: n - stripped user-typed identifier
    # @return: True for GCVS/NSV designations or the name of an active local
    #          variable project (offline; the local name always wins — it is
    #          how campaign targets without a catalog entry, e.g. the WeSb 1
    #          nucleus, get their kind back)
    if _GCVS_RE.match(n) or _NSV_RE.match(n):
        return True
    try:
        from .db import db as _db
        row = _db.execute(
            "SELECT 1 FROM projects WHERE kind='variable'"
            " AND LOWER(object_name)=LOWER(?) LIMIT 1", (n,)).fetchone()
        return bool(row)
    except Exception:
        return False
```

2. En `detect_type`, tras el bloque hads (:35-38) y antes del comentario de
   la regex exoplaneta (:39), añade:
   ```python
       if _looks_like_variable(n):
           return "variable"
   ```
3. `detect_type`'s `@return` comment (:29) gains `| "variable"`.

**Tests a añadir** — `tests/unit/test_enrich_variable.py` (cabecera GPL;
«Unit tests: variable detection & enrich branch (Track V, VB.5/VB.6)»):

```python
import pytest

from nightscribe.core import enrich


def test_detect_variable_gcvs_names():
    assert enrich.detect_type("T CrB") == "variable"
    assert enrich.detect_type("EE Cep") == "variable"
    assert enrich.detect_type("V1490 Cyg") == "variable"
    assert enrich.detect_type("NSV 01234") == "variable"


def test_detect_collisions_stay_put():
    assert enrich.detect_type("GP And") == "hads"         # HADS regression
    assert enrich.detect_type("GQ Lup b") == "exoplanet"  # 3 tokens: planet
    assert enrich.detect_type("SN 2026abc") == "transient"
    assert enrich.detect_type("2026 AB1") == "small_body"


def test_detect_local_variable_project_name(monkeypatch):
    class _FakeDb:
        def execute(self, sql, params=()):
            class _Cur:
                def fetchone(self):
                    return (1,)
            return _Cur()
    from nightscribe.core import db as dbmod
    monkeypatch.setattr(dbmod, "db", _FakeDb())
    assert enrich.detect_type("WeSb 1") == "variable"     # not GCVS-shaped
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_enrich_variable.py tests/unit/test_enrich_hads.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: variable detection in enrich (GCVS/NSV + local projects, before the exoplanet regex) (ADR-035, subplan VB.5)`
**Estado**: Hecho ✅

---

## VB.6 — `enrich`: rama de datos variable (VSX → SIMBAD → planner)

**Contexto a leer (solo esto)**: `nightscribe/core/enrich.py:70-94` (rama
hads y cierre), `:133-145` (`_copy_window_context`);
`nightscribe/core/sources/simbad.py:73-101` (`query_id`).
**Precondición**: VB.5, V0.8.

**Toca**: `nightscribe/core/enrich.py`;
`tests/unit/test_enrich_variable.py` (ampliar).

**Escribe exactamente esto**:

1. En `enrich()`, tras la rama `if kind == "hads":` (:70-78) y antes de
   `data = _enrich_small_body(...)` (:79), añade:
   ```python
       if kind == "variable":
           return {"type": "variable", "name": name,
                   "data": _enrich_variable(name, fallback_target)}
   ```
2. Nueva función tras `_merge_transient_context` (tras :190):

```python
def _enrich_variable(name, fallback_target=None):
    # The variable-star branch (ADR-035, V-c): VSX knows the star (cached);
    # SIMBAD anchors the coordinates when VSX does not (WeSb 1 is not in
    # VSX); the planner/project snapshot wins when present (it carries the
    # campaign-curated fields and tonight's values).
    # @return: data dict with "variable" (+ "simbad", "campaign", window)
    from .sources import vsx
    from . import variables
    v = vsx.lookup(name) or {}
    data = {"variable": v}
    if v.get("ra_deg") is None:
        ident = simbad.query_id(name)
        if ident:
            data["simbad"] = ident
            try:
                v["ra_deg"] = coords.ra_hms_to_deg(ident["ra"])
                v["dec_deg"] = coords.dec_dms_to_deg(ident["dec"])
            except (ValueError, TypeError, KeyError):
                pass
            if v.get("max") is None and ident.get("vmag") is not None:
                v["max"] = ident["vmag"]
    if fallback_target:
        _copy_window_context(data, fallback_target)
        if fallback_target.get("variable"):
            v.update(fallback_target["variable"])     # planner values win
        if fallback_target.get("campaign"):
            data["campaign"] = fallback_target["campaign"]
        if fallback_target.get("mag") is not None:
            data.setdefault("mag", fallback_target["mag"])
    if v.get("amp") is None and v.get("max") is not None \
            and v.get("min") is not None:
        v["amp"] = round(v["min"] - v["max"], 2)      # inverted axis
    if v.get("period_d"):
        v["next_extremum"] = variables.next_extremum(
            v.get("period_d"), v.get("epoch_mjd"),
            var_type=v.get("var_type", ""))
    if v.get("ra_deg") is not None:
        data["ra_deg"] = v["ra_deg"]
        data["dec_deg"] = v.get("dec_deg")
    data["variable"] = v
    return data
```

**Tests a añadir** (al final de `tests/unit/test_enrich_variable.py`):

```python
def _vsx_tcrb():
    return {"name": "T CrB", "auid": "000-BBW-825", "ra_deg": 239.87567,
            "dec_deg": 25.92017, "var_type": "NR+ELL", "period_d": 227.5528,
            "epoch_mjd": 55828.4, "max": 2.0, "min": 10.8,
            "max_band": "V", "min_band": "V", "spectral": "M3III+WD",
            "constellation": "CrB"}


def test_enrich_variable_from_vsx(monkeypatch):
    from nightscribe.core.sources import vsx
    monkeypatch.setattr(vsx, "lookup", lambda name: _vsx_tcrb())
    e = enrich.enrich("T CrB")
    assert e["type"] == "variable"
    v = e["data"]["variable"]
    assert v["amp"] == 8.8                          # min - max
    assert v["next_extremum"]["kind"] in ("max", "min")
    assert e["data"]["ra_deg"] == 239.87567


def test_enrich_variable_vsx_miss_falls_to_simbad(monkeypatch):
    from nightscribe.core.sources import simbad, vsx
    monkeypatch.setattr(vsx, "lookup", lambda name: None)
    monkeypatch.setattr(simbad, "query_id", lambda name: {
        "name": "WeSb 1", "otype": "PN?", "ra": "01 00 54.10",
        "dec": "+55 04 00.1", "vmag": 15.0, "z": None})
    e = enrich.enrich("WeSb 1")
    v = e["data"]["variable"]
    assert v["ra_deg"] == pytest.approx(15.2254, abs=1e-3)
    assert v["max"] == 15.0
    assert e["data"]["simbad"]["name"] == "WeSb 1"


def test_enrich_variable_planner_snapshot_wins(monkeypatch):
    from nightscribe.core.sources import vsx
    monkeypatch.setattr(vsx, "lookup", lambda name: _vsx_tcrb())
    fb = {"kind": "variable", "mag": 10.5,
          "variable": {"var_type": "NR", "period_d": 227.5528,
                       "epoch_mjd": 55828.4, "max": 2.0, "min": 10.8,
                       "next_extremum": {"kind": "max", "mjd": 61250.0,
                                         "days": 3.0}},
          "campaign": {"id": 1, "name": "Campaña T CrB", "overdue_days": 4,
                       "cadence_nights": 1, "never_visited": False,
                       "event": None},
          "safe_window": "2026-09-11T22:00|2026-09-12T04:00"}
    e = enrich.enrich("T CrB", fallback_target=fb)
    assert e["data"]["campaign"]["name"] == "Campaña T CrB"
    assert e["data"]["variable"]["next_extremum"]["days"] == 3.0
    assert e["data"]["safe_window"] == "2026-09-11T22:00|2026-09-12T04:00"
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_enrich_variable.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: variable enrich branch — VSX cached, SIMBAD anchor, planner wins (ADR-035, subplan VB.6)`
**Estado**: Hecho ✅

---

## Cierre de la fase B

Cuando VB.1–VB.6 estén hechas: `.venv/bin/python -m pytest tests/unit -q`
verde y anota el conteo total aquí: **1045** → **1053**.
