# Track V — Fase C: ficha de objeto, proyectos y gestor de campañas

> Subplanes VC.1–VC.10 del plan maestro
> [../variables-campaigns.md](../variables-campaigns.md). Un subplan = un
> commit. Anclas verificadas a HEAD `4b7635a`; si una no coincide: **parar y
> reportar**. Lee antes `LEEME.md`.
> Precondición: fases 0, A y B hechas.
>
> **Patrón de tests GUI offscreen** (todas las tarjetas GUI de esta fase):
> mira `tests/unit/test_projects_hub.py:107-160` — el arnés redirige el
> singleton `db` a un tmp (`_point_db_at_tmpdir`), crea la `MainWindow` con
> los timers parados y `config.is_configured = lambda: False`. Copia ese
> arnés en el fichero de tests nuevo de cada tarjeta.

---

## VC.1 — `orbits.explain_variable` (tabla ES/EN de la ficha)

**Contexto a leer (solo esto)**: `nightscribe/core/orbits.py:903-1029`
(`explain_hads`, el molde exacto); `nightscribe/gui/overview.py:665-675`
(dispatch de la tabla).
**Precondición**: VB.6.

**Toca**: `nightscribe/core/orbits.py`; `nightscribe/gui/overview.py` (una
rama); `tests/unit/test_explain_variable.py` (**nuevo**).

**Escribe exactamente esto**:

1. Al final de `core/orbits.py` (tras `explain_hads`, :1029):

```python
# ---------------- variable star interpreter (ADR-035) ----------------

def _variable_family_text(var_type):
    # Didactic one-liner per variability family. The FIRST component of a
    # composite VSX type decides (same rule as the epoch, V-e).
    # @args: var_type - VSX type, e.g. "M", "NR+ELL", "E-DO", "UGSS"
    # @return: ({"es","en"}, epoch_is_minimum: bool)
    first = (var_type or "").split("+")[0].strip().upper()
    if first == "E" or first.startswith(("EA", "EB", "EW", "E/", "E-")):
        return ({"es": "Binaria eclipsante: una estrella pasa delante de la "
                       "otra en cada vuelta, y el brillo cae en cada eclipse.",
                 "en": "Eclipsing binary: one star passes in front of the "
                       "other every orbit, and the brightness dips at each "
                       "eclipse."}), True
    if first == "M":
        return ({"es": "Mira: una gigante roja que pulsa en meses — late "
                       "como un corazón lento, con cambios de varias "
                       "magnitudes.",
                 "en": "Mira: a red giant pulsating over months — a slow "
                       "heartbeat swinging several magnitudes."}), False
    if first == "NR":
        return ({"es": "Nova recurrente: un sistema binario que estalla "
                       "cada pocas décadas (esta clase ha llegado a mag 2).",
                 "en": "Recurrent nova: a binary system erupting every few "
                       "decades (members of this class have reached mag 2)."}), False
    if first == "N":
        return ({"es": "Nova: un estallido termonuclear sobre una enana "
                       "blanca en un sistema binario.",
                 "en": "Nova: a thermonuclear outburst on a white dwarf in "
                       "a binary system."}), False
    if first.startswith("UG"):
        return ({"es": "Nova enana: la acreción sobre la enana blanca se "
                       "vuelve inestable y erupciona cada pocas semanas.",
                 "en": "Dwarf nova: accretion onto the white dwarf turns "
                       "unstable and erupts every few weeks."}), False
    if first == "RCB":
        return ({"es": "R Coronae Borealis: una supergigante que se apaga "
                       "de golpe, ahogada por su propio hollín de carbono.",
                 "en": "R Coronae Borealis: a supergiant suddenly fading, "
                       "smothered by its own carbon soot."}), False
    if first == "ELL":
        return ({"es": "Elipsoidal: una estrella deformada por su compañera "
                       "que gira mostrando distinta superficie.",
                 "en": "Ellipsoidal: a star stretched by its companion, "
                       "rotating and showing different surface."}), False
    if first in ("DSCT", "HADS", "GDOR", "SXPHE"):
        return ({"es": "Pulsante de la franja de inestabilidad (familia de "
                       "las δ Scuti / Doradus).",
                 "en": "Pulsating star of the instability strip (the "
                       "δ Scuti / γ Doradus family)."}), False
    return ({"es": "Estrella variable: su brillo cambia con el tiempo.",
             "en": "Variable star: its brightness changes with time."}), False


def explain_variable(d):
    # Interprets a variable star: variability family first, then the cycle
    # (period, next extremum), the brightness range and the campaign it
    # belongs to. Read defensively: the "variable" sub-dict may come from
    # VSX (full), SIMBAD (coords only) or manual entry (nearly empty).
    # @args: d - enriched data dict with a "variable" sub-dict
    # @return: list of dicts {"param", "value", "level", "es", "en"}
    out = []
    v = d.get("variable") or {}
    c = d.get("campaign") or {}

    vt = v.get("var_type") or ""
    fam, epoch_min = _variable_family_text(vt)
    out.append({
        "param": {"es": "Tipo de variable", "en": "Variable type"},
        "value": vt or "—", "level": "basic",
        "es": fam["es"], "en": fam["en"]})

    per = v.get("period_d")
    if per:
        out.append({
            "param": {"es": "Periodo", "en": "Period"},
            "value": f"{per:.2f} d", "level": "basic",
            "es": f"Cada {per:.1f} días repite su ciclo: la curva se "
                  "construye noche a noche, no en una sesión.",
            "en": f"Every {per:.1f} days it repeats its cycle: the light "
                  "curve is built night after night, not in one session."})

    nxt = v.get("next_extremum") or {}
    if nxt.get("days") is not None:
        lab_es = "Máximo" if nxt.get("kind") == "max" else "Mínimo"
        lab_en = "Maximum" if nxt.get("kind") == "max" else "Minimum"
        out.append({
            "param": {"es": "Próximo extremo", "en": "Next extremum"},
            "value": f"~{nxt['days']:.0f} d", "level": "basic",
            "es": f"{lab_es} esperado en ~{nxt['days']:.0f} días (época del "
                  "VSX). Planifica la noche en torno a él.",
            "en": f"{lab_en} expected in ~{nxt['days']:.0f} days (VSX "
                  "epoch). Plan the night around it."})

    if v.get("max") is not None and v.get("min") is not None:
        out.append({
            "param": {"es": "Rango de brillo", "en": "Brightness range"},
            "value": f"{v['max']:.1f}–{v['min']:.1f} mag", "level": "basic",
            "es": "Del máximo al mínimo histórico del catálogo. Recuerda "
                  "que en magnitudes el número mayor es el más débil.",
            "en": "From catalogued maximum to minimum. Mind the inverted "
                  "scale: the bigger number is the fainter one."})

    amp = v.get("amp")
    if amp is None and v.get("max") is not None and v.get("min") is not None:
        amp = v["min"] - v["max"]              # inverted magnitude axis
    if amp:
        out.append({
            "param": {"es": "Amplitud", "en": "Amplitude"},
            "value": f"Δ {amp:.1f} mag", "level": "basic",
            "es": f"Cambia {amp:.1f} magnitudes de pico a valle.",
            "en": f"It swings {amp:.1f} magnitudes peak to peak."})

    if v.get("spectral"):
        out.append({
            "param": {"es": "Tipo espectral", "en": "Spectral type"},
            "value": v["spectral"], "level": "deep",
            "es": "La firma del espectro: temperatura y clases de "
                  "compañeras si las hay.",
            "en": "The spectrum's signature: temperature and companion "
                  "classes when present."})

    if c.get("name"):
        goal_es = f" Objetivo: {c['goal']}" if c.get("goal") else ""
        goal_en = f" Goal: {c['goal']}" if c.get("goal") else ""
        out.append({
            "param": {"es": "Campaña", "en": "Campaign"},
            "value": c["name"], "level": "basic",
            "es": f"La observas dentro de la campaña «{c['name']}»"
                  + (f" del grupo {c['group_name']}" if c.get("group_name")
                     else "") + "." + goal_es,
            "en": f"You observe it inside the “{c['name']}” campaign"
                  + (f" by {c['group_name']}" if c.get("group_name") else "")
                  + "." + goal_en})
    return out
```

2. `gui/overview.py`, en el dispatch de la tabla (:673-674), tras la rama
   hads:
   ```python
           if e.get("type") == "variable" or d.get("variable"):
               return orbits.explain_variable(d)
   ```

**Tests a añadir** — `tests/unit/test_explain_variable.py` (cabecera GPL;
«Unit tests: explain_variable (Track V, VC.1)»):

```python
from nightscribe.core import orbits


def _d(vt="NR+ELL", **vkw):
    v = {"var_type": vt, "period_d": 227.55, "epoch_mjd": 55828.4,
         "max": 2.0, "min": 10.8, "amp": 8.8, "spectral": "M3III+WD",
         "next_extremum": {"kind": "max", "mjd": 61250.0, "days": 3.0}}
    v.update(vkw)
    d = {"variable": v}
    if vkw.pop("campaign", None):
        d["campaign"] = vkw["campaign"]
    return d


def test_full_rows_es_en():
    rows = orbits.explain_variable(_d())
    params = [r["param"]["en"] for r in rows]
    assert "Variable type" in params
    assert "Period" in params
    assert "Next extremum" in params
    assert "Brightness range" in params
    assert "Amplitude" in params
    assert "Spectral type" in params
    for r in rows:
        assert r["es"] and r["en"] and r["value"]


def test_family_texts():
    assert "Binaria eclipsante" in orbits.explain_variable(_d("E-DO"))[0]["es"]
    assert "Mira" in orbits.explain_variable(_d("M"))[0]["es"]
    assert "Nova recurrente" in orbits.explain_variable(_d("NR+ELL"))[0]["es"]
    assert "Nova enana" in orbits.explain_variable(_d("UGSS"))[0]["es"]
    assert "hollín" in orbits.explain_variable(_d("RCB"))[0]["es"]


def test_minimal_variable_still_explains():
    rows = orbits.explain_variable({"variable": {}})
    assert len(rows) == 1                       # just the generic type row
    assert rows[0]["value"] == "—"


def test_campaign_row():
    d = _d()
    d["campaign"] = {"name": "Campaña T CrB", "group_name": "obsSN",
                     "goal": "Catch the eruption"}
    rows = orbits.explain_variable(d)
    row = [r for r in rows if r["param"]["en"] == "Campaign"][0]
    assert "obsSN" in row["es"] and "Catch the eruption" in row["en"]
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_explain_variable.py tests/unit/test_overview_panel.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core/Gui: explain_variable rows ES/EN for the object card (ADR-035, subplan VC.1)`
**Estado**: Pendiente

---

## VC.2 — Chips de variable + plegado con época en la ficha

**Contexto a leer (solo esto)**: `nightscribe/gui/overview.py:455-477`
(`_inject_followup`), `:825-916` (`_extract`, rama `lightcurve`),
`:1043-1080` (chips hads).
**Precondición**: VC.1.

**Toca**: `nightscribe/gui/overview.py`;
`tests/unit/test_overview_panel.py` (ampliar — solo añadir tests al final).

**Escribe exactamente esto**:

1. `_inject_followup` (:460): la condición pasa a
   ```python
        if e.get("type") not in ("transient", "sn", "hads", "variable"):
            return
   ```
2. `_extract`, rama `lightcurve` (:892-916): tras el bloque hads (`if
   h.get("period_h"):`, :905-915) y antes del `return out` (:916), añade:
   ```python
               # ADR-035: a long-period variable folds by its VSX period
               # with the real epoch, and reuses the schematic sawtooth
               v = d.get("variable") or (self._ctx or {}).get("variable") \
                   or {}
               if "fold_period_d" not in out and v.get("period_d"):
                   out["fold_period_d"] = v["period_d"]
                   if v.get("epoch_mjd") is not None:
                       out["epoch_mjd"] = v["epoch_mjd"]
                   amp = v.get("amp")
                   if amp is None and v.get("max") is not None \
                           and v.get("min") is not None:
                       amp = v["min"] - v["max"]
                   if amp and v.get("max") is not None \
                           and v.get("min") is not None:
                       from ..core import hads as hads_mod
                       med = (v["max"] + v["min"]) / 2
                       out["schematic"] = hads_mod.sawtooth_template(
                           v["period_d"] * 24.0, amp, med)
   ```
3. Chips (:1043-1080): tras el bloque `if is_hads:` completo (termina en
   :1080), añade:
   ```python
           is_var = kind == "variable" or bool(d.get("variable"))
           if is_var:
               v = d.get("variable") or ctx.get("variable") or {}
               per = v.get("period_d")
               if per:
                   chips.append((
                       f"P {float(per):.1f} d", theme.KIND_COLORS["variable"],
                       self.tr("Variability period, in days")))
               amp = v.get("amp")
               if amp is None and v.get("max") is not None \
                       and v.get("min") is not None:
                   amp = v["min"] - v["max"]
               if amp:
                   chips.append((
                       f"Δ {float(amp):.1f} mag", theme.C_TEXT,
                       self.tr("Peak-to-peak brightness swing")))
               nxt = v.get("next_extremum") or {}
               if nxt.get("days") is not None:
                   lab = self.tr("max") if nxt.get("kind") == "max" \
                       else self.tr("min")
                   chips.append((
                       f"{lab} ~{float(nxt['days']):.0f} d",
                       theme.KIND_COLORS["variable"],
                       self.tr("Next expected extremum (VSX epoch)")))
               camp = d.get("campaign") or ctx.get("campaign") or {}
               if camp.get("name"):
                   chips.append((
                       self.tr("Campaign: %1").replace("%1", camp["name"]),
                       theme.C_OK,
                       self.tr("This object belongs to an observing campaign")))
   ```

**Tests a añadir** (al final de `tests/unit/test_overview_panel.py`; usa el
arnés existente del fichero — lee sus primeras 60 líneas):

```python
FAKE_VARIABLE = {
    "type": "variable", "name": "T CrB",
    "data": {"variable": {"var_type": "NR+ELL", "period_d": 227.5528,
                          "epoch_mjd": 55828.4, "max": 2.0, "min": 10.8,
                          "amp": 8.8, "spectral": "M3III+WD",
                          "next_extremum": {"kind": "max", "mjd": 61250.0,
                                            "days": 3.0}},
             "campaign": {"name": "Campaña T CrB"}},
}


def test_variable_params_table(panel):
    panel.show(FAKE_VARIABLE)
    texts = []
    for r in range(panel.tbl_params.rowCount()):
        p = panel.tbl_params.item(r, 0)
        if p:
            texts.append(p.text())
    assert any("Period" in t or "Periodo" in t for t in texts)
    assert any("Variable type" in t or "Tipo de variable" in t
               for t in texts)


def test_variable_chips(panel):
    panel.show(FAKE_VARIABLE)
    labels = [c.text() for c in panel.grp_chips.findChildren(QLabel)] \
        if hasattr(panel, "grp_chips") else []
    # fallback: walk the whole panel for chip labels
    if not labels:
        labels = [l.text() for l in panel.findChildren(QLabel)]
    assert any("P 227.6 d" in t for t in labels)
    assert any("Campaña T CrB" in t for t in labels)


def test_variable_lightcurve_extract_folds_with_epoch(panel):
    e = {"type": "variable", "name": "T CrB",
         "data": {"variable": dict(FAKE_VARIABLE["data"]["variable"]),
                  "followup": {"points": [
                      {"mjd": 61000.0, "filter": "V", "mag": 10.1,
                       "err": None, "source": "manual"},
                      {"mjd": 61010.0, "filter": "V", "mag": 10.3,
                       "err": None, "source": "manual"}]}}}
    out = panel._extract("lightcurve", e)
    assert out["fold_period_d"] == 227.5528
    assert out["epoch_mjd"] == 55828.4
    assert out["schematic"]
```

(`QLabel` ya está importado en el fichero; si no, añade el import al bloque
de arriba — es la única edición permitida fuera de los tests nuevos.)

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Variability period, in days | Periodo de variabilidad, en días | Variability period, in days |
| Peak-to-peak brightness swing | Cambio de brillo de pico a valle | Peak-to-peak brightness swing |
| Next expected extremum (VSX epoch) | Próximo extremo esperado (época del VSX) | Next expected extremum (VSX epoch) |
| Campaign: %1 | Campaña: %1 | Campaign: %1 |
| This object belongs to an observing campaign | Este objeto pertenece a una campaña de observación | This object belongs to an observing campaign |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_overview_panel.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: variable chips + epoch-folding light curve in the object card (ADR-035, subplan VC.2)`
**Estado**: Pendiente

---

## VC.3 — `_create_project`: whitelist de contexto para variable/campaña

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:4386-4417`.
**Precondición**: V0.4.

**Toca**: `nightscribe/gui/main_window.py` (una tupla);
`tests/unit/test_projects_hub.py` (ampliar — solo añadir al final).

**Escribe exactamente esto**:

1. `main_window.py:4397-4406` — la tupla de claves pasa a terminar con:
   ```python
                        "perihelion_date", "transit", "approach", "hads",
                        "variable", "campaign", "project_id")
   ```
2. Tests (al final de `test_projects_hub.py`):

```python
def test_create_project_keeps_variable_and_campaign_context(window):
    from nightscribe.core import project as proj_mod
    t = {"kind": "variable", "name": "T CrB", "mag": 10.1,
         "ra_deg": 239.9, "dec_deg": 25.9, "project_id": 7,
         "variable": {"period_d": 227.55, "var_type": "NR"},
         "campaign": {"id": 1, "name": "Campaña T CrB"}}
    p = window._create_project(t)
    assert p is not None and p["kind"] == "variable"
    ctx = proj_mod.get(window_db(window), p["id"])["context"]
    assert ctx["variable"]["period_d"] == 227.55
    assert ctx["campaign"]["name"] == "Campaña T CrB"
```

donde `window_db(window)` no existe: usa directamente el patrón del fichero
(el singleton redirigido): `from nightscribe.gui import main_window as mw`
→ `mw.db`. La línea queda:
```python
    from nightscribe.gui import main_window as mw
    from nightscribe.core import project as proj_mod
    ...
    ctx = proj_mod.get(mw.db, p["id"])["context"]
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: variable/campaign keys in the project context snapshot (ADR-035, subplan VC.3)`
**Estado**: Pendiente

---

## VC.4 — `gui/campaigns_dialog.py`: esqueleto + accesos

**Contexto a leer (solo esto)**:
`nightscribe/gui/ui/main_window.ui:41-47, 59-79` (menú Tools y acciones);
`nightscribe/gui/main_window.py:425-460` (conexiones de acciones y
`btn_refresh`); `nightscribe/gui/ui/projects_tab.ui:11-23` (filterLayout).
**Precondición**: V0.2.

**Toca**: `nightscribe/gui/campaigns_dialog.py` (**nuevo**);
`nightscribe/gui/ui/main_window.ui`; `nightscribe/gui/ui/projects_tab.ui`;
`nightscribe/gui/main_window.py` (3 puntos);
`tests/unit/test_campaigns_dialog.py` (**nuevo**).

**Escribe exactamente esto**:

1. `nightscribe/gui/campaigns_dialog.py` (**nuevo**; cabecera GPL — «Campaign
   manager dialog (ADR-035)»):

```python
"""The campaign manager (V-j): one modal dialog listing the active and
finished campaigns with their CRUD, reachable from the Tools menu and the
Projects hub. All persistence goes through core/campaign.py; the dialog
never touches the network.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QGroupBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout)

from ..core import campaign
from ..core.db import db

logger = logging.getLogger(__name__)


class CampaignsDialog(QDialog):
    # @args: parent - QWidget, db_obj - Database (tests inject a temp one)
    def __init__(self, parent=None, db_obj=None):
        super().__init__(parent)
        self._db = db_obj or db
        self.setWindowTitle(self.tr("Campaigns"))
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        self.grp_active = QGroupBox(self.tr("Active campaigns"))
        self.grp_active.setLayout(QVBoxLayout())
        self.lst_active = QListWidget()
        self.grp_active.layout().addWidget(self.lst_active)
        layout.addWidget(self.grp_active)
        self.grp_finished = QGroupBox(self.tr("Finished campaigns"))
        self.grp_finished.setLayout(QVBoxLayout())
        self.lst_finished = QListWidget()
        self.grp_finished.layout().addWidget(self.lst_finished)
        layout.addWidget(self.grp_finished)
        row = QHBoxLayout()
        self.btn_new = QPushButton(self.tr("New campaign…"))
        self.btn_edit = QPushButton(self.tr("Edit…"))
        self.btn_finish = QPushButton(self.tr("Finish"))
        self.btn_reopen = QPushButton(self.tr("Reopen"))
        self.btn_close = QPushButton(self.tr("Close"))
        for b in (self.btn_new, self.btn_edit, self.btn_finish,
                  self.btn_reopen):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.btn_close)
        layout.addLayout(row)
        self.btn_close.clicked.connect(self.accept)
        self.btn_finish.clicked.connect(self._finish_selected)
        self.btn_reopen.clicked.connect(self._reopen_selected)
        self.lst_active.itemSelectionChanged.connect(self._sync_buttons)
        self.lst_finished.itemSelectionChanged.connect(self._sync_buttons)
        self._reload()
        self._sync_buttons()

    # ---------------- data ----------------

    def _reload(self):
        # @return: None — refills both lists from the db
        for lst, status in ((self.lst_active, campaign.CAMPAIGN_ACTIVE),
                            (self.lst_finished, campaign.CAMPAIGN_FINISHED)):
            lst.clear()
            for c in campaign.list_campaigns(self._db, status):
                label = c["name"]
                if c.get("group_name"):
                    label += f"  ({c['group_name']})"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, c["id"])
                lst.addItem(item)

    def _selected_id(self, lst):
        # @return: campaign id of the list selection, or None
        item = lst.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    # ---------------- actions ----------------

    def _sync_buttons(self):
        self.btn_finish.setEnabled(self._selected_id(self.lst_active)
                                   is not None)
        self.btn_reopen.setEnabled(self._selected_id(self.lst_finished)
                                   is not None)
        self.btn_edit.setEnabled(self._selected_id(self.lst_active)
                                 is not None)

    def _finish_selected(self):
        cid = self._selected_id(self.lst_active)
        if cid is not None:
            campaign.finish(self._db, cid)
            self._reload()

    def _reopen_selected(self):
        cid = self._selected_id(self.lst_finished)
        if cid is not None:
            campaign.reopen(self._db, cid)
            self._reload()
```

2. `main_window.ui`: en `menu_tools` (:41-47), tras `<addaction
   name="action_blink"/>` añade `<addaction name="action_campaigns"/>`; y en
   el bloque de acciones (tras `action_blink`, :68-70) añade:
   ```xml
    <action name="action_campaigns">
     <property name="text"><string>Campaigns…</string></property>
    </action>
   ```
3. `projects_tab.ui`: en `filterLayout` (:12-22), tras el item de
   `btn_refresh`, añade:
   ```xml
          <item><widget class="QPushButton" name="btn_campaigns"><property name="text"><string>Campaigns…</string></property></widget></item>
   ```
4. `main_window.py`: tras :438 (`self._menus.action_blink...`), añade:
   ```python
           self._menus.action_campaigns.triggered.connect(
               self._tools_campaigns)
   ```
   tras :459 (`p.btn_refresh...`), añade:
   ```python
           p.btn_campaigns.clicked.connect(self._tools_campaigns)
   ```
   y el handler (junto a `_tools_blink`, :4455-4456):
   ```python
       def _tools_campaigns(self):
           # The campaign manager (ADR-035, V-j). Modal; the Tonight cadence
           # and the hub refresh themselves on the next visit.
           from .campaigns_dialog import CampaignsDialog
           CampaignsDialog(self).exec()
   ```

**Tests a añadir** — `tests/unit/test_campaigns_dialog.py` (cabecera GPL;
«Unit tests: campaigns dialog (Track V, VC.4)»; arnés offscreen mínimo —
copia el fixture `qapp` de `tests/unit/test_theme.py:35-45`):

```python
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nightscribe.core import campaign            # noqa: E402
from nightscribe.core.db import Database         # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def test_dialog_lists_active_and_finished(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    campaign.create(db, "Activa")
    cid = campaign.create(db, "Vieja")
    campaign.finish(db, cid)
    dlg = CampaignsDialog(db_obj=db)
    assert dlg.lst_active.count() == 1
    assert dlg.lst_finished.count() == 1
    assert dlg.lst_active.item(0).text().startswith("Activa")


def test_finish_and_reopen_from_the_buttons(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    campaign.create(db, "A")
    dlg = CampaignsDialog(db_obj=db)
    dlg.lst_active.setCurrentRow(0)
    dlg.btn_finish.click()
    assert dlg.lst_active.count() == 0
    assert dlg.lst_finished.count() == 1
    dlg.lst_finished.setCurrentRow(0)
    dlg.btn_reopen.click()
    assert dlg.lst_active.count() == 1


def test_empty_dialog_buttons_disabled(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    dlg = CampaignsDialog(db_obj=db)
    assert not dlg.btn_finish.isEnabled()
    assert not dlg.btn_reopen.isEnabled()
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Campaigns | Campañas | Campaigns |
| Campaigns… | Campañas… | Campaigns… |
| Active campaigns | Campañas activas | Active campaigns |
| Finished campaigns | Campañas finalizadas | Finished campaigns |
| New campaign… | Nueva campaña… | New campaign… |
| Edit… | Editar… | Edit… |
| Finish | Finalizar | Finish |
| Reopen | Reabrir | Reabrir |
| Close | Cerrar | Close |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaigns_dialog.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: campaign manager dialog skeleton + Tools/hub access (ADR-035, subplan VC.4)`
**Estado**: Pendiente

---

## VC.5 — Gestor: crear/editar campaña

**Contexto a leer (solo esto)**: tu `gui/campaigns_dialog.py` de VC.4;
`nightscribe/core/campaign.py` (`create`, `update`).
**Precondición**: VC.4.

**Toca**: `nightscribe/gui/campaigns_dialog.py`;
`tests/unit/test_campaigns_dialog.py` (ampliar).

**Escribe exactamente esto**:

1. Al final de `gui/campaigns_dialog.py`, nueva clase:

```python
class CampaignEditDialog(QDialog):
    # The create/edit form of one campaign. Protocol fields: cadence in
    # nights (default 1, V-l), filters and comparison stars as
    # comma-separated text (parsed on save).
    # @args: parent - QWidget, camp - campaign dict to edit or None (new),
    #        db_obj - Database
    def __init__(self, parent=None, camp=None, db_obj=None):
        super().__init__(parent)
        from PySide6.QtWidgets import (QDialogButtonBox, QFormLayout,
                                       QLineEdit, QPlainTextEdit, QSpinBox)
        self._db = db_obj or db
        self._camp = camp
        self.setWindowTitle(self.tr("Edit campaign") if camp
                            else self.tr("New campaign"))
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.edt_name = QLineEdit((camp or {}).get("name", ""))
        form.addRow(self.tr("Name:"), self.edt_name)
        self.edt_group = QLineEdit((camp or {}).get("group_name", ""))
        form.addRow(self.tr("Group:"), self.edt_group)
        self.edt_coord = QLineEdit((camp or {}).get("coordinator", ""))
        form.addRow(self.tr("Coordinator:"), self.edt_coord)
        self.edt_goal = QLineEdit((camp or {}).get("goal", ""))
        form.addRow(self.tr("Science goal:"), self.edt_goal)
        prot = (camp or {}).get("protocol") or {}
        self.spn_cadence = QSpinBox()
        self.spn_cadence.setRange(1, 30)
        self.spn_cadence.setValue(int(prot.get("cadence_nights", 1)))
        form.addRow(self.tr("Cadence (nights):"), self.spn_cadence)
        self.edt_filters = QLineEdit(", ".join(prot.get("filters", [])))
        form.addRow(self.tr("Filters:"), self.edt_filters)
        self.edt_comps = QLineEdit(", ".join(prot.get("comp_stars", [])))
        form.addRow(self.tr("Comparison stars:"), self.edt_comps)
        self.edt_report = QLineEdit((camp or {}).get("report_url", ""))
        form.addRow(self.tr("Report URL:"), self.edt_report)
        self.edt_data = QLineEdit((camp or {}).get("data_url", ""))
        form.addRow(self.tr("Data URL:"), self.edt_data)
        self.edt_notes = QPlainTextEdit(prot.get("notes", ""))
        form.addRow(self.tr("Protocol notes:"), self.edt_notes)
        layout.addLayout(form)
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _csv(self, text):
        # @return: list of non-empty comma-separated items
        return [x.strip() for x in text.split(",") if x.strip()]

    def _save(self):
        # Validates the name and persists (create or update).
        name = self.edt_name.text().strip()
        if not name:
            return
        prot = {"cadence_nights": self.spn_cadence.value(),
                "filters": self._csv(self.edt_filters.text()),
                "comp_stars": self._csv(self.edt_comps.text()),
                "notes": self.edt_notes.toPlainText().strip()}
        if self._camp is None:
            campaign.create(
                self._db, name,
                group_name=self.edt_group.text().strip(),
                coordinator=self.edt_coord.text().strip(),
                goal=self.edt_goal.text().strip(), protocol=prot,
                report_url=self.edt_report.text().strip(),
                data_url=self.edt_data.text().strip())
        else:
            campaign.update(
                self._db, self._camp["id"], name=name,
                group_name=self.edt_group.text().strip(),
                coordinator=self.edt_coord.text().strip(),
                goal=self.edt_goal.text().strip(), protocol=prot,
                report_url=self.edt_report.text().strip(),
                data_url=self.edt_data.text().strip())
        self.accept()
```

2. En `CampaignsDialog.__init__` (VC.4), conecta los botones:
   ```python
           self.btn_new.clicked.connect(self._new_campaign)
           self.btn_edit.clicked.connect(self._edit_selected)
   ```
   y añade los handlers:
   ```python
       def _new_campaign(self):
           if CampaignEditDialog(self, db_obj=self._db).exec():
               self._reload()

       def _edit_selected(self):
           cid = self._selected_id(self.lst_active)
           if cid is None:
               return
           camp = campaign.get(self._db, cid)
           if CampaignEditDialog(self, camp=camp, db_obj=self._db).exec():
               self._reload()
   ```

**Tests a añadir** (al final de `tests/unit/test_campaigns_dialog.py`):

```python
def test_new_campaign_via_form(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignEditDialog
    dlg = CampaignEditDialog(db_obj=db)
    dlg.edt_name.setText("Campaña T CrB")
    dlg.edt_group.setText("obsSN")
    dlg.edt_filters.setText("B, V")
    dlg.edt_comps.setText("000-BB0-123, 000-BB0-124")
    assert dlg.spn_cadence.value() == 1          # V-l default
    dlg._save()
    c = campaign.list_campaigns(db)[0]
    assert c["name"] == "Campaña T CrB"
    assert c["protocol"]["filters"] == ["B", "V"]
    assert c["protocol"]["comp_stars"] == ["000-BB0-123", "000-BB0-124"]


def test_edit_campaign_via_form(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignEditDialog
    cid = campaign.create(db, "A", protocol={"cadence_nights": 5})
    dlg = CampaignEditDialog(camp=campaign.get(db, cid), db_obj=db)
    assert dlg.spn_cadence.value() == 5
    dlg.edt_name.setText("A2")
    dlg._save()
    assert campaign.get(db, cid)["name"] == "A2"


def test_save_without_name_is_refused(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignEditDialog
    dlg = CampaignEditDialog(db_obj=db)
    dlg._save()
    assert campaign.list_campaigns(db) == []
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Edit campaign | Editar campaña | Edit campaign |
| New campaign | Nueva campaña | New campaign |
| Name: | Nombre: | Name: |
| Group: | Grupo: | Group: |
| Coordinator: | Coordinador: | Coordinator: |
| Science goal: | Objetivo científico: | Science goal: |
| Cadence (nights): | Cadencia (noches): | Cadence (nights): |
| Filters: | Filtros: | Filters: |
| Comparison stars: | Estrellas de comparación: | Comparison stars: |
| Report URL: | URL de reporte: | Report URL: |
| Data URL: | URL de datos: | Data URL: |
| Protocol notes: | Notas del protocolo: | Protocol notes: |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaigns_dialog.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: campaign create/edit form with protocol fields (ADR-035, subplan VC.5)`
**Estado**: Pendiente

---

## VC.6 — Gestor: badge de campaña en la cabecera del proyecto

**Contexto a leer (solo esto)**:
`nightscribe/gui/main_window.py:1811-1826` (`_render_project_header`).
**Precondición**: VC.4 (el finish/reopen ya se hizo en VC.4/VC.5), V0.4.

**Toca**: `nightscribe/gui/main_window.py` (un bloque);
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. `_render_project_header`: tras `header += f" — {self.tr('step')} ..."` /
   el `if p.get("closed_at"):` (:1819-1825), antes de
   `self.projects.lbl_header.setText(header)` (:1826), añade:
   ```python
           if p.get("campaign_id"):
               from ..core import campaign as _camp
               c = _camp.get(db, p["campaign_id"])
               if c:
                   header += (f" · <span style='color:#65cf30'>"
                              f"{self.tr('campaign')}: {c['name']}</span>")
   ```
2. Test (al final de `test_projects_hub.py`):

```python
def test_project_header_shows_campaign_badge(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña T CrB")
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 10.1},
                        campaign_id=cid)
    window._render_project_header(proj_mod.get(mw.db, p["id"]))
    assert "Campaña T CrB" in window.projects.lbl_header.text()
```

**Cadenas nuevas**: `campaign` → ES `campaña`, EN `campaign`.

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: campaign badge in the project header (ADR-035, subplan VC.6)`
**Estado**: Pendiente

---

## VC.7 — Gestor: añadir objetivo (VSX → SIMBAD → manual)

**Contexto a leer (solo esto)**: tu `gui/campaigns_dialog.py`;
`nightscribe/core/sources/vsx.py` (V0.8);
`nightscribe/core/sources/simbad.py:73-101` (`query_id`);
`nightscribe/core/coords.py` (`ra_hms_to_deg`, `dec_dms_to_deg` — búscalos
con grep si hace falta).
**Precondición**: VC.6, V0.8.

**Toca**: `nightscribe/gui/campaigns_dialog.py`;
`tests/unit/test_campaigns_dialog.py` (ampliar).

**Escribe exactamente esto**:

1. Al final de `gui/campaigns_dialog.py`:

```python
class AddTargetDialog(QDialog):
    # Adds a target to a campaign as a `variable` project. Resolution chain
    # (V-c): VSX (cached) -> SIMBAD (coords anchor) -> fully manual. The
    # lookups are one tiny cached GET each and run synchronously; the form
    # tells the user while it resolves.
    # @args: parent, campaign_id - int, db_obj - Database
    def __init__(self, parent=None, campaign_id=None, db_obj=None):
        super().__init__(parent)
        from PySide6.QtWidgets import (QDialogButtonBox, QFormLayout,
                                       QLineEdit)
        self._db = db_obj or db
        self._campaign_id = campaign_id
        self._resolved = {}
        self.setWindowTitle(self.tr("Add campaign target"))
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.edt_name = QLineEdit()
        form.addRow(self.tr("Object:"), self.edt_name)
        self.btn_resolve = QPushButton(self.tr("Resolve (VSX/SIMBAD)"))
        form.addRow("", self.btn_resolve)
        self.lbl_resolved = QLabel(self.tr("— not resolved yet —"))
        self.lbl_resolved.setWordWrap(True)
        form.addRow(self.lbl_resolved)
        self.edt_ra = QLineEdit()
        form.addRow(self.tr("RA (deg):"), self.edt_ra)
        self.edt_dec = QLineEdit()
        form.addRow(self.tr("Dec (deg):"), self.edt_dec)
        self.edt_mag = QLineEdit()
        form.addRow(self.tr("Mag (approx):"), self.edt_mag)
        layout.addLayout(form)
        self.btn_resolve.clicked.connect(self._resolve)
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _resolve(self):
        # Fills the form from VSX, then SIMBAD; leaves it editable always.
        from ..core.sources import simbad, vsx
        name = self.edt_name.text().strip()
        if not name:
            return
        v = vsx.lookup(name)
        if v:
            self._resolved = {"variable": v}
            self.edt_ra.setText(str(v.get("ra_deg") or ""))
            self.edt_dec.setText(str(v.get("dec_deg") or ""))
            if v.get("max") is not None:
                self.edt_mag.setText(str(v["max"]))
            self.lbl_resolved.setText(self.tr(
                "VSX: type %1, period %2 d").replace(
                    "%1", v.get("var_type") or "?").replace(
                    "%2", str(v.get("period_d") or "?")))
            return
        ident = simbad.query_id(name)
        if ident:
            from ..core import coords
            try:
                self.edt_ra.setText(str(round(
                    coords.ra_hms_to_deg(ident["ra"]), 5)))
                self.edt_dec.setText(str(round(
                    coords.dec_dms_to_deg(ident["dec"]), 5)))
            except (ValueError, TypeError, KeyError):
                pass
            if ident.get("vmag") is not None:
                self.edt_mag.setText(str(ident["vmag"]))
            self._resolved = {"simbad": ident}
            self.lbl_resolved.setText(self.tr("SIMBAD: %1").replace(
                "%1", ident.get("otype") or "?"))
            return
        self.lbl_resolved.setText(self.tr(
            "Not found — fill the coordinates by hand"))

    def _save(self):
        # Creates the variable project linked to the campaign.
        name = self.edt_name.text().strip()
        if not name or self._campaign_id is None:
            return
        from ..core import project
        try:
            ra = float(self.edt_ra.text())
            dec = float(self.edt_dec.text())
        except ValueError:
            return
        mag = None
        try:
            mag = float(self.edt_mag.text())
        except ValueError:
            pass
        ctx = {"kind": "variable", "ra_deg": ra, "dec_deg": dec}
        if mag is not None:
            ctx["mag"] = mag
        ctx.update(self._resolved)
        project.create(self._db, "variable", name, ctx,
                       campaign_id=self._campaign_id)
        self.accept()
```

2. En `CampaignsDialog.__init__`, añade el botón (tras `self.btn_reopen`):
   ```python
           self.btn_target = QPushButton(self.tr("Add target…"))
   ```
   insértalo en `row` tras `btn_reopen`, conéctalo:
   ```python
           self.btn_target.clicked.connect(self._add_target)
   ```
   actúa sobre la campaña activa seleccionada; en `_sync_buttons` añade
   `self.btn_target.setEnabled(self._selected_id(self.lst_active) is not None)`;
   y el handler:
   ```python
       def _add_target(self):
           cid = self._selected_id(self.lst_active)
           if cid is None:
               return
           AddTargetDialog(self, campaign_id=cid, db_obj=self._db).exec()
   ```

**Tests a añadir** (al final de `tests/unit/test_campaigns_dialog.py`):

```python
def test_add_target_resolves_vsx_and_creates_project(qapp, db, monkeypatch):
    from nightscribe.core import project as proj_mod
    from nightscribe.core.sources import vsx
    from nightscribe.gui.campaigns_dialog import AddTargetDialog
    monkeypatch.setattr(vsx, "lookup", lambda name: {
        "name": "T CrB", "auid": "000-BBW-825", "ra_deg": 239.87567,
        "dec_deg": 25.92017, "var_type": "NR+ELL", "period_d": 227.5528,
        "epoch_mjd": 55828.4, "max": 2.0, "min": 10.8, "max_band": "V",
        "min_band": "V", "spectral": "M3III+WD", "constellation": "CrB"})
    cid = campaign.create(db, "Campaña T CrB")
    dlg = AddTargetDialog(campaign_id=cid, db_obj=db)
    dlg.edt_name.setText("T CrB")
    dlg._resolve()
    assert dlg.edt_ra.text().startswith("239.875")
    dlg._save()
    p = proj_mod.list_projects(db, campaign_id=cid)[0]
    assert p["kind"] == "variable" and p["object_name"] == "T CrB"
    assert p["context"]["variable"]["period_d"] == 227.5528


def test_add_target_manual_when_nothing_knows_it(qapp, db, monkeypatch):
    from nightscribe.core import project as proj_mod
    from nightscribe.core.sources import simbad, vsx
    from nightscribe.gui.campaigns_dialog import AddTargetDialog
    monkeypatch.setattr(vsx, "lookup", lambda name: None)
    monkeypatch.setattr(simbad, "query_id", lambda name: None)
    cid = campaign.create(db, "Campaña WeSb 1")
    dlg = AddTargetDialog(campaign_id=cid, db_obj=db)
    dlg.edt_name.setText("WeSb 1")
    dlg._resolve()
    assert "Not found" in dlg.lbl_resolved.text()
    dlg.edt_ra.setText("15.2254")
    dlg.edt_dec.setText("55.0667")
    dlg.edt_mag.setText("15.0")
    dlg._save()
    p = proj_mod.list_projects(db, campaign_id=cid)[0]
    assert p["context"]["ra_deg"] == 15.2254
    assert p["context"]["mag"] == 15.0


def test_add_target_without_coordinates_is_refused(qapp, db):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import AddTargetDialog
    cid = campaign.create(db, "C")
    dlg = AddTargetDialog(campaign_id=cid, db_obj=db)
    dlg.edt_name.setText("X")
    dlg._save()
    assert proj_mod.list_projects(db) == []
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Add campaign target | Añadir objetivo a la campaña | Add campaign target |
| Object: | Objeto: | Object: |
| Resolve (VSX/SIMBAD) | Resolver (VSX/SIMBAD) | Resolve (VSX/SIMBAD) |
| — not resolved yet — | — sin resolver aún — | — not resolved yet — |
| RA (deg): | AR (°): | RA (deg): |
| Dec (deg): | Dec (°): | Dec (deg): |
| Mag (approx): | Mag (aprox): | Mag (approx): |
| VSX: type %1, period %2 d | VSX: tipo %1, periodo %2 d | VSX: type %1, period %2 d |
| SIMBAD: %1 | SIMBAD: %1 | SIMBAD: %1 |
| Not found — fill the coordinates by hand | No encontrado — rellena las coordenadas a mano | Not found — fill the coordinates by hand |
| Add target… | Añadir objetivo… | Add target… |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaigns_dialog.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: campaign target creation — VSX/SIMBAD resolution chain + manual fallback (ADR-035, subplan VC.7)`
**Estado**: Pendiente

---

## VC.8 — Adjuntar/desadjuntar proyecto existente

**Contexto a leer (solo esto)**: tu `gui/campaigns_dialog.py`;
`nightscribe/core/project.py:301-309` (`set_status`, molde de setter).
**Precondición**: VC.6.

**Toca**: `nightscribe/core/project.py` (una función);
`nightscribe/gui/campaigns_dialog.py`; `tests/unit/test_project_variable.py`
(ampliar); `tests/unit/test_campaigns_dialog.py` (ampliar).

**Escribe exactamente esto**:

1. `core/project.py`, tras `set_status` (:301-309):

```python
def set_campaign(db, project_id, campaign_id):
    # Links the project to a campaign (or unlinks it with None) — the
    # campaign is an orthogonal attribute, any kind can join (ADR-035, V-b).
    # @return: True if the project was found and updated
    cur = db.execute(
        "UPDATE projects SET campaign_id=?, updated=? WHERE id=?",
        (campaign_id, _now(), project_id),
    )
    db.commit()
    return cur.rowcount > 0
```

2. `gui/campaigns_dialog.py`, en `CampaignsDialog.__init__`, añade el botón
   `self.btn_attach = QPushButton(self.tr("Attach project…"))` tras
   `btn_target` (mismo `row`), conéctalo y en `_sync_buttons` habilítalo como
   `btn_target`. Handlers:

```python
    def _attach_project(self):
        # Links an existing active project to the selected campaign.
        cid = self._selected_id(self.lst_active)
        if cid is None:
            return
        from PySide6.QtWidgets import QInputDialog
        from ..core import project
        actives = project.list_projects(self._db, status="active")
        choices = [p for p in actives if not p.get("campaign_id")]
        if not choices:
            return
        names = [f"[{p['kind']}] {p['object_name']}" for p in choices]
        sel, ok = QInputDialog.getItem(
            self, self.tr("Attach project"), self.tr("Project:"),
            names, 0, False)
        if ok:
            idx = names.index(sel)
            project.set_campaign(self._db, choices[idx]["id"], cid)

    def _detach_project(self):
        # Unlinks a project of the selected campaign (chosen by name).
        cid = self._selected_id(self.lst_active)
        if cid is None:
            return
        from PySide6.QtWidgets import QInputDialog
        members = campaign.projects_of(self._db, cid, status=None)
        if not members:
            return
        names = [p["object_name"] for p in members]
        sel, ok = QInputDialog.getItem(
            self, self.tr("Detach project"), self.tr("Project:"),
            names, 0, False)
        if ok:
            from ..core import project
            project.set_campaign(self._db, members[names.index(sel)]["id"],
                                 None)
```

   y `self.btn_detach = QPushButton(self.tr("Detach…"))` conectado a
   `_detach_project`, mismo manejo de enable que `btn_attach`.

**Tests a añadir**:

```python
# tests/unit/test_project_variable.py
def test_set_campaign_link_and_unlink(db):
    cid = campaign.create(db, "C")
    p = project.create(db, "sn", "SN 2026abc")
    assert project.set_campaign(db, p["id"], cid) is True
    assert project.get(db, p["id"])["campaign_id"] == cid
    assert project.set_campaign(db, p["id"], None) is True
    assert project.get(db, p["id"])["campaign_id"] is None

# tests/unit/test_campaigns_dialog.py — detach sin miembros no rompe:
def test_detach_with_no_members_is_a_noop(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    campaign.create(db, "C")
    dlg = CampaignsDialog(db_obj=db)
    dlg.lst_active.setCurrentRow(0)
    dlg._detach_project()          # no members: nothing happens, no crash
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Attach project… | Adjuntar proyecto… | Attach project… |
| Detach… | Quitar… | Detach… |
| Attach project | Adjuntar proyecto | Attach project |
| Detach project | Quitar proyecto | Detach project |
| Project: | Proyecto: | Project: |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_project_variable.py tests/unit/test_campaigns_dialog.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core/Gui: attach/detach existing projects to campaigns (ADR-035, subplan VC.8)`
**Estado**: Pendiente

---

## VC.9 — Hub: filtro por campaña

**Contexto a leer (solo esto)**:
`nightscribe/gui/ui/projects_tab.ui:24-48` (classifyLayout);
`nightscribe/gui/main_window.py:1603-1623` (`on_refresh_projects`).
**Precondición**: VC.4, V0.4.

**Toca**: `nightscribe/gui/ui/projects_tab.ui`;
`nightscribe/gui/main_window.py`; `tests/unit/test_projects_hub.py`
(ampliar).

**Escribe exactamente esto**:

1. `projects_tab.ui`: en `classifyLayout` (:25-48), tras el item de
   `edt_tag` (:42-47), añade:
   ```xml
           <item>
            <widget class="QComboBox" name="cmb_campaign">
             <item><property name="text"><string>All campaigns</string></property></item>
            </widget>
           </item>
   ```
2. `main_window.py`:
   a. Tras :459 (donde se conectó `btn_refresh` y, en VC.4, `btn_campaigns`):
      ```python
          p.cmb_campaign.currentIndexChanged.connect(
              lambda _i: self.on_refresh_projects())
      ```
   b. En `on_refresh_projects` (:1603), tras leer `tag` (:1612), añade:
      ```python
          camp_id = self.projects.cmb_campaign.currentData()
      ```
      y en la llamada a `project.list_projects` (:1621-1623) añade el
      argumento `campaign_id=camp_id`.
   c. Nueva función y llamada al inicio de `on_refresh_projects`:
      ```python
          self._rebuild_campaign_filter()
      ```
      ```python
      def _rebuild_campaign_filter(self):
          # Refills the hub's campaign combo, keeping the current selection.
          # @return: None
          from ..core import campaign as _camp
          cmb = self.projects.cmb_campaign
          current = cmb.currentData()
          cmb.blockSignals(True)
          cmb.clear()
          cmb.addItem(self.tr("All campaigns"), None)
          for c in _camp.list_campaigns(db):
              cmb.addItem(c["name"], c["id"])
          idx = cmb.findData(current)
          cmb.setCurrentIndex(idx if idx >= 0 else 0)
          cmb.blockSignals(False)
      ```
3. Test (al final de `test_projects_hub.py`):

```python
def test_hub_filters_projects_by_campaign(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña T CrB")
    proj_mod.create(mw.db, "variable", "T CrB", {}, campaign_id=cid)
    proj_mod.create(mw.db, "variable", "WeSb 1", {})
    window.on_refresh_projects()
    names = _project_names(window)         # helper exists in this file;
    assert "T CrB" in names and "WeSb 1" in names
    idx = window.projects.cmb_campaign.findText("Campaña T CrB")
    assert idx >= 1
    window.projects.cmb_campaign.setCurrentIndex(idx)
    window.on_refresh_projects()
    names = _project_names(window)
    assert "T CrB" in names and "WeSb 1" not in names
    window.projects.cmb_campaign.setCurrentIndex(0)
```

   Si `_project_names` no existe en el fichero, usa este helper local:
   ```python
   def _project_names(window):
       out = []
       for i in range(window.projects.lst_projects.count()):
           item = window.projects.lst_projects.item(i)
           if item.flags() != Qt.NoItemFlags:      # skip year headers
               out.append(item.text())
       return out
   ```
   (`Qt` ya está importado en el fichero de tests.)

**Cadenas nuevas**: `All campaigns` → ES `Todas las campañas`, EN `All campaigns`.

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: campaign filter in the projects hub (ADR-035, subplan VC.9)`
**Estado**: Pendiente

---

## VC.10 — Follow-up para `variable`: botones, protocolo y cadencia

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:72`
(`FOLLOWUP_KINDS`), `:3267-3361` (`_build_followup_tab`).
**Precondición**: V0.4, VC.7.

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. `main_window.py:72` → `FOLLOWUP_KINDS = ("sn", "hads", "variable")`
   (y su comentario ganan una línea: «Track V: variables join (V-g: the
   quick-look engine serves them unchanged)»).
2. En `_build_followup_tab`, justo tras `pid = p["id"]` (:3279), añade la
   búsqueda de campaña (se usa en los dos pasos siguientes):
   ```python
           camp = None
           if p.get("campaign_id"):
               from ..core import campaign as _camp
               camp = _camp.get(db, p["campaign_id"])
   ```
3. Cadencia (:3283): la línea del threshold pasa a:
   ```python
           threshold = int(config.get("sn_cadence_days", 3))
           if camp is not None:
               threshold = int((camp.get("protocol") or {}).get(
                   "cadence_nights") or threshold)
   ```
4. Protocolo de campaña: tras el bloque de cadencia (:3281-3296), añade:
   ```python
           if camp is not None:
               prot = camp.get("protocol") or {}
               bits = [self.tr("Campaign: %1").replace("%1", camp["name"])]
               if prot.get("cadence_nights"):
                   bits.append(self.tr("cadence every %1 night(s)").replace(
                       "%1", str(prot["cadence_nights"])))
               if prot.get("filters"):
                   bits.append(self.tr("filters: %1").replace(
                       "%1", ", ".join(prot["filters"])))
               if prot.get("comp_stars"):
                   bits.append(self.tr("comparison stars: %1").replace(
                       "%1", ", ".join(prot["comp_stars"])))
               lbl_prot = QLabel(" · ".join(bits))
               lbl_prot.setWordWrap(True)
               layout.addWidget(lbl_prot)
               if prot.get("notes"):
                   lbl_notes = QLabel("⚠ " + prot["notes"])
                   lbl_notes.setWordWrap(True)
                   lbl_notes.setStyleSheet("color: #e0c060;")
                   layout.addWidget(lbl_notes)
   ```
5. Botones de análisis (:3354-3358): sustituye el `if kind == "hads":` por:
   ```python
           if kind == "hads":
               # SN-only analysis: the quick-look engine measures stacked
               # per-night images, not an intra-night series (ADR-034, D.3)
               for b in (btn_quicklook, btn_evo, btn_annot):
                   b.hide()
           elif kind == "variable":
               # variables share the quick-look (the series engine serves
               # them unchanged, V-g) but not the SN evolution animation or
               # the annotated FITS
               for b in (btn_evo, btn_annot):
                   b.hide()
   ```

**Tests a añadir** (al final de `test_projects_hub.py`; lee antes el test
`test_followup_cadence_uses_config` (:1152) para el patrón de construcción):

```python
def test_variable_project_gets_followup_with_protocol(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(
        mw.db, "Campaña T CrB",
        protocol={"cadence_nights": 1, "filters": ["B", "V"],
                  "comp_stars": ["000-BB0-123"], "notes": "Do not saturate"})
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 10.1},
                        campaign_id=cid)
    window._build_step_tabs(proj_mod.get(mw.db, p["id"]))
    fu = window.projects.tabs_steps.findChild(QWidget, "tab_followup")
    assert window.projects.tabs_steps.isTabVisible(
        window.projects.tabs_steps.indexOf(fu))
    texts = [l.text() for l in fu.findChildren(QLabel)]
    assert any("Campaña T CrB" in t for t in texts)
    assert any("B, V" in t for t in texts)
    assert any("Do not saturate" in t for t in texts)


def test_variable_followup_keeps_quicklook_hides_animation(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "variable", "V1490 Cyg", {"mag": 12.0})
    window._build_step_tabs(proj_mod.get(mw.db, p["id"]))
    fu = window.projects.tabs_steps.findChild(QWidget, "tab_followup")
    btns = {b.text(): b for b in fu.findChildren(QPushButton)}
    assert btns["Run quick-look"].isVisibleTo(fu)
    assert not btns["Generate animation"].isVisibleTo(fu)
    assert not btns["Export annotated FITS"].isVisibleTo(fu)
```

(`QWidget`/`QPushButton` ya están importados en el fichero; si no, añade el
import — única edición permitida fuera de los tests nuevos.)

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| cadence every %1 night(s) | cadencia cada %1 noche(s) | cadence every %1 night(s) |
| filters: %1 | filtros: %1 | filters: %1 |
| comparison stars: %1 | estrellas de comparación: %1 | comparison stars: %1 |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: follow-up tab for variables — quick-look on, campaign protocol + cadence (ADR-035, subplan VC.10)`
**Estado**: Pendiente

---

## Cierre de la fase C

Cuando VC.1–VC.10 estén hechas: `.venv/bin/python -m pytest tests/unit -q`
verde y anota el conteo total aquí: ______ → ______.
