# Track UX — Fase D: el proyecto como página única + pestaña Observatory (UD.1–UD.5)

> Subplanes UD.1–UD.5 del plan maestro
> [../ux-variables-campaigns.md](../ux-variables-campaigns.md). Un subplan =
> un commit. Anclas verificadas a HEAD `4df771b`; si una no coincide:
> **parar y reportar**. Lee antes `LEEME.md`.
> Precondición: fases 0, A y B hechas (los enlaces profundos de UA.6/UB.1
> aterrizan aquí como scroll+expandir).

**Qué cambia y por qué** (decisión UX-i del maestro): el detalle del
proyecto deja de ser «5 pestañas + wizard (Previous/Skip/Mark done/Next)»
— doble modelo de navegación, iconos ✔/●/○/– crípticos, una pestaña
Publish con un solo botón — y pasa a ser **una página con scroll**: tarjeta
«Siguiente acción» + secciones plegables con su estado en palabras y sus
botones dentro. El **modelo no cambia**: `project_steps` y sus estados
(`pending/current/done/skipped`) siguen siendo la fuente de verdad; solo
cambia la presentación (enmienda de ADR-019 en UC.2). Y el control de
CCDciel sale del paso Plan a la pestaña **Observatory** (UX-j): la
conexión ya era de ventana; ahora también su UI.

**Inventario de tests que fijan la estructura vieja** (verificado a
`4df771b`): `tests/unit/test_project_tabs.py` (7 tests — se reescriben en
UD.3), ~20 referencias a `tabs_steps` en `tests/unit/test_projects_hub.py`
(retarget en UD.4/UD.5 con la tabla de traducción), `test_hads_plan.py`
(5), `test_transit_plan.py` (6), `test_neo_process.py` (2) (retarget en
UD.5).

---

## UD.1 — `project.next_action()` + `project.reopen_step()` (core puro)

**Contexto a leer (solo esto)**: `nightscribe/core/project.py:35-38`
(STEP_*), `:205-260` (`steps` en `get`, `current_step`, `advance`,
`set_step_status`); `nightscribe/core/followup.py:93-103`
(`days_since_last_session`); `nightscribe/core/campaign.py:152-156`
(`protocol_get`).

**Precondición**: ninguna dentro de la fase.

**Toca**: `nightscribe/core/project.py` (constante movida + dos funciones);
`nightscribe/gui/main_window.py` (una línea: la constante pasa a venir del
core); `tests/unit/test_next_action.py` (**nuevo**).

**Escribe exactamente esto**:

1. `core/project.py`: añade la constante (junto a `VALID_KINDS`, :33) — es
   la misma tupla que hoy vive en la GUI:
   ```python
   # Kinds with multi-night photometry follow-up (moved here from
   # gui/main_window.py for UX-i: next_action() needs it in core)
   FOLLOWUP_KINDS = ("sn", "hads", "variable")
   ```
2. `gui/main_window.py:73`: `FOLLOWUP_KINDS = ("sn", "hads", "variable")`
   pasa a `FOLLOWUP_KINDS = project.FOLLOWUP_KINDS` (las referencias
   existentes no cambian).
3. Al final de `core/project.py`:

```python
def reopen_step(db, project_id, step):
    # Reopens a done/skipped step (the checklist's "reopen" toggle, UX-i):
    # the chosen step becomes current and any other current step goes back
    # to pending, keeping the single-current invariant.
    # @return: True if the step was found
    proj = get(db, project_id)
    if not proj:
        return False
    found = False
    for s in proj["steps"]:
        if s["step"] == step:
            found = True
        elif s["status"] == STEP_CURRENT:
            set_step_status(db, project_id, s["step"], STEP_PENDING)
    if not found:
        return False
    return set_step_status(db, project_id, step, STEP_CURRENT)


def next_action(db, proj):
    # The project's voice (UX-i): ONE next action derived from the real
    # state, never from a manual "where was I". Rule order:
    #   1. follow-up cadence due (only once observing has started: a first
    #      visit exists or the plan step is done) — the campaign does not
    #      care about step bookkeeping, but "measure tonight" with no plan
    #      is not actionable;
    #   2. plan not passed -> "plan";
    #   3. plan passed, process not passed -> "process";
    #   4. process passed, publish not passed -> "publish";
    #   5. everything passed -> "close".
    # @args: db - Database, proj - project dict from get()
    # @return: {"key": "followup"|"plan"|"process"|"publish"|"close",
    #          "overdue_days": int|None, "never_visited": bool}
    from . import campaign as _camp
    from . import followup as _fu
    steps = {s["step"]: s["status"] for s in proj.get("steps", [])}
    passed = {k: steps.get(k) in (STEP_DONE, STEP_SKIPPED)
              for k in ("plan", "process", "publish")}
    out = {"key": None, "overdue_days": None, "never_visited": False}
    if proj.get("status") == STATUS_ACTIVE \
            and proj.get("kind") in FOLLOWUP_KINDS \
            and (passed["plan"] or _fu.days_since_last_session(
                db, proj["id"]) is not None):
        cad = 3
        if proj.get("campaign_id"):
            c = _camp.get(db, proj["campaign_id"])
            if c:
                cad = int(_camp.protocol_get(c, "cadence_nights", 1) or 1)
        days = _fu.days_since_last_session(db, proj["id"])
        if days is None:
            out.update(key="followup", overdue_days=cad,
                       never_visited=True)
            return out
        if days >= cad:
            out.update(key="followup", overdue_days=days)
            return out
    for key in ("plan", "process", "publish"):
        if not passed[key]:
            out["key"] = key
            return out
    out["key"] = "close"
    return out
```

**Tests a añadir** — `tests/unit/test_next_action.py` (**nuevo**; cabecera
GPL; «Unit tests: project.next_action (UX, UD.1)»; fixture `db` =
`Database(str(tmp_path / "t.db"))`, patrón de `test_campaign.py`):

```python
from nightscribe.core import campaign, followup, project


def _proj(db, kind="sn", campaign_id=None):
    return project.create(db, kind, "OBJ", {"mag": 15.0},
                          campaign_id=campaign_id)


def test_fresh_project_says_plan(db):
    assert project.next_action(db, _proj(db))["key"] == "plan"


def test_plan_done_says_process(db):
    p = _proj(db)
    project.advance(db, p["id"])
    assert project.next_action(db, project.get(db, p["id"]))["key"] == \
        "process"


def test_process_done_says_publish(db):
    p = _proj(db)
    project.advance(db, p["id"])
    project.advance(db, p["id"])
    assert project.next_action(db, project.get(db, p["id"]))["key"] == \
        "publish"


def test_all_done_says_close(db):
    p = _proj(db)
    for _ in range(3):
        project.advance(db, p["id"])
    assert project.next_action(db, project.get(db, p["id"]))["key"] == \
        "close"


def test_skipped_step_counts_as_passed(db):
    p = _proj(db)
    project.set_step_status(db, p["id"], "plan", project.STEP_SKIPPED)
    assert project.next_action(db, project.get(db, p["id"]))["key"] == \
        "process"


def test_cadence_due_beats_process(db):
    p = _proj(db)
    project.advance(db, p["id"])                 # plan done
    followup.create_session(db, p["id"])
    db.execute("UPDATE project_sessions SET created=? WHERE project_id=?",
               (1_700_000_000, p["id"]))         # aged far beyond 3 d
    db.commit()
    act = project.next_action(db, project.get(db, p["id"]))
    assert act["key"] == "followup" and act["overdue_days"] >= 3


def test_no_session_and_no_plan_says_plan_not_followup(db):
    # "measure tonight" is not actionable without a plan (rule 1 guard)
    assert project.next_action(db, _proj(db, kind="variable"))["key"] == \
        "plan"


def test_never_visited_with_plan_says_followup(db):
    p = _proj(db, kind="variable")
    project.advance(db, p["id"])                 # plan done, no visits
    act = project.next_action(db, project.get(db, p["id"]))
    assert act["key"] == "followup" and act["never_visited"] is True


def test_campaign_cadence_overrides_default(db):
    cid = campaign.create(db, "Campaña lenta",
                          protocol={"cadence_nights": 10})
    p = _proj(db, campaign_id=cid)
    project.advance(db, p["id"])
    followup.create_session(db, p["id"])
    db.execute("UPDATE project_sessions SET created=? WHERE project_id=?",
               (1_700_000_000, p["id"]))
    db.commit()
    act = project.next_action(db, project.get(db, p["id"]))
    assert act["key"] == "followup" and act["overdue_days"] >= 10


def test_reopen_step_keeps_single_current(db):
    p = _proj(db)
    project.advance(db, p["id"])                 # plan done, process current
    assert project.reopen_step(db, p["id"], "plan") is True
    steps = {s["step"]: s["status"]
             for s in project.get(db, p["id"])["steps"]}
    assert steps["plan"] == "current"
    assert steps["process"] == "pending"
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_next_action.py tests/unit/test_project.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: project.next_action + reopen_step — the single-page checklist's brain (UX, subplan UD.1)`
**Estado**: Hecho (1126→1136 tests, suite verde; sin cadenas nuevas)

> Nota de ejecución: el `days is None` de la tarjeta (primera visita)
> respondía `followup` también para `sn`, lo que contradecía los propios
> tests de la tarjeta (`test_plan_done_says_process` y
> `test_process_done_says_publish` exigen `process`/`publish` para sn con
> plan hecho y sin sesiones). La rama de primera visita ahora se limita a
> los tipos de campaña (`hads`, `variable`): un SN nace de su detección y
> ya tiene su primer dato, así que el flujo de pasos manda hasta su primera
> sesión. Guardada también `days is not None` antes de `days >= cad`.

---

## UD.2 — Pestaña Observatory: CCDciel sale del paso Plan

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:274-283`
(estado CCDciel de ventana) y `:306` (auto-connect), `:2155-2240` (bloque
completo en `_build_plan_tab`: fila de conexión, grupo «Observatory
status», rueda de filtros + send/start, fila de gotos, label de coords,
registro en `_project_widgets`), `:2303-2325` (`_ccd_apply_state`),
`:2455-2476` (`_ccd_poll_tick`), `:2620-2640` (`_ccd_fill_filters`);
`nightscribe/gui/ui/main_window.ui:14-28` (tabs). Tus tarjetas UA.2
(constantes `TAB_*`).

**Precondición**: UA.2 (constantes `TAB_*`).

**Toca**: `nightscribe/gui/ui/main_window.ui`;
`nightscribe/gui/ui/observatory_tab.ui` (**nuevo**);
`nightscribe/gui/main_window.py`;
`tests/unit/test_projects_hub.py` (los 4 tests `*_ccdciel_*` se adaptan —
solo las referencias a widgets movidos);
`tests/unit/test_observatory_tab.py` (**nuevo**).

**Escribe exactamente esto**:

1. `ui/main_window.ui`: tras `tab_history` NO; el orden final de pestañas
   es Tonight, Projects, Campaigns, Solar, **Observatory**, History —
   inserta entre `tab_solar` y `tab_history`:
   ```xml
         <widget class="QWidget" name="tab_observatory">
          <attribute name="title"><string>Observatory</string></attribute>
         </widget>
   ```
2. `ui/observatory_tab.ui` (**nuevo**):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>ObservatoryTab</class>
 <widget class="QWidget" name="ObservatoryTab">
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QGroupBox" name="grp_conn">
     <property name="title"><string>CCDciel control</string></property>
     <layout class="QVBoxLayout" name="connLayout">
      <item>
       <layout class="QHBoxLayout" name="rowConn">
        <item><widget class="QPushButton" name="btn_obs_connect"><property name="text"><string>Connect CCDciel</string></property></widget></item>
        <item><widget class="QPushButton" name="btn_obs_disconnect"><property name="text"><string>Disconnect</string></property></widget></item>
        <item><widget class="QPushButton" name="btn_obs_refresh"><property name="text"><string>Refresh</string></property></widget></item>
        <item><widget class="QLabel" name="lbl_obs_status"><property name="text"><string>CCDciel: not connected</string></property></widget></item>
        <item><spacer name="hsp_conn"><property name="orientation"><enum>Qt::Horizontal</enum></property></spacer></item>
       </layout>
      </item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QGroupBox" name="grp_status">
     <property name="title"><string>Observatory status</string></property>
     <layout class="QFormLayout" name="statusLayout">
      <item row="0" column="0"><widget class="QLabel" name="lbl_obs_ver_k"><property name="text"><string>Version:</string></property></widget></item>
      <item row="0" column="1"><widget class="QLabel" name="lbl_obs_version"><property name="text"><string>—</string></property></widget></item>
      <item row="1" column="0"><widget class="QLabel" name="lbl_obs_temp_k"><property name="text"><string>CCD temperature:</string></property></widget></item>
      <item row="1" column="1"><widget class="QLabel" name="lbl_obs_temp"><property name="text"><string>—</string></property></widget></item>
      <item row="2" column="0"><widget class="QLabel" name="lbl_obs_trk_k"><property name="text"><string>Tracking:</string></property></widget></item>
      <item row="2" column="1"><widget class="QLabel" name="lbl_obs_tracking"><property name="text"><string>—</string></property></widget></item>
      <item row="3" column="0"><widget class="QLabel" name="lbl_obs_slew_k"><property name="text"><string>Slew:</string></property></widget></item>
      <item row="3" column="1"><widget class="QLabel" name="lbl_obs_slew"><property name="text"><string>—</string></property></widget></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QGroupBox" name="grp_mount">
     <property name="title"><string>Telescope</string></property>
     <layout class="QVBoxLayout" name="mountLayout">
      <item>
       <layout class="QHBoxLayout" name="rowTarget">
        <item><widget class="QLabel" name="lbl_obs_target"><property name="text"><string>Target:</string></property></widget></item>
        <item><widget class="QComboBox" name="cmb_obs_target"/></item>
       </layout>
      </item>
      <item>
       <layout class="QHBoxLayout" name="rowMount">
        <item><widget class="QPushButton" name="btn_obs_goto"><property name="text"><string>Point telescope</string></property><property name="toolTip"><string>Quick slew to the freshly-computed position of a moving target: J2000_to_Apparent + Telescope_slewasync, no plate-solve. Fast, but assumes the ephemeris is already accurate.</string></property></widget></item>
        <item><widget class="QPushButton" name="btn_obs_sync"><property name="text"><string>Astrometric Goto</string></property><property name="toolTip"><string>Slew + capture + plate-solve and correct to the true sky position. Absorbs residual ephemeris error; the reliable route for NEOCPs and preliminary orbits.</string></property></widget></item>
        <item><spacer name="hsp_mount"><property name="orientation"><enum>Qt::Horizontal</enum></property></spacer></item>
       </layout>
      </item>
      <item><widget class="QLabel" name="lbl_obs_hint"><property name="text"><string>Capture plans are sent from each project's Plan section.</string></property><property name="wordWrap"><bool>true</bool></property></widget></item>
     </layout>
    </widget>
   </item>
   <item><spacer name="vsp_obs"><property name="orientation"><enum>Qt::Vertical</enum></property></spacer></item>
  </layout>
 </widget>
</ui>
```

3. `main_window.py`:
   a. Constantes (:tras UA.2) — añade Observatory entre Solar y History:
      ```python
      TAB_TONIGHT, TAB_PROJECTS, TAB_CAMPAIGNS, TAB_SOLAR, \
          TAB_OBSERVATORY, TAB_HISTORY = range(6)
      ```
      (ajusta la definición vieja de 5; UB.2 — Ctrl+1..5 — pasa a 1..6:
      cambia su `enumerate` si ya se ejecutó; si no, su tarjeta ya queda
      escrita con 5 y el ejecutor la lee aquí: **usa 6**.)
   b. `_build_tabs`: la tupla gana `self.observatory` en la posición 4:
      ```python
          widgets = (self.tonight, self.projects, self.campaigns,
                     self.solar, self.observatory, self.history) = (
              _load_ui("tonight_tab"), _load_ui("projects_tab"),
              _load_ui("campaigns_tab"), _load_ui("solar_tab"),
              _load_ui("observatory_tab"), _load_ui("history_tab"))
      ```
      y al final llama `self._build_observatory_tab()`.
   c. Nuevo builder + registro de widgets **de ventana** (sobreviven a los
      cambios de proyecto — cierra de raíz la clase de bug de «controles
      huérfanos» del comentario de :1982):
      ```python
          def _build_observatory_tab(self):
              # The CCDciel control, window-owned (UX-j): it used to be
              # rebuilt inside every project's Plan step (and orphaned on
              # rebuild). Built ONCE here; the Plan section keeps only the
              # capture buttons (send/start), which read this connection.
              o = self.observatory
              self._obs_widgets = {
                  "ccd_connect": o.btn_obs_connect,
                  "ccd_disconnect": o.btn_obs_disconnect,
                  "ccd_refresh": o.btn_obs_refresh,
                  "ccd_status": o.lbl_obs_status,
                  "ccd_version": o.lbl_obs_version,
                  "ccd_temp": o.lbl_obs_temp,
                  "ccd_tracking": o.lbl_obs_tracking,
                  "ccd_slew": o.lbl_obs_slew,
                  "ccd_goto": o.btn_obs_goto,
                  "ccd_sync": o.btn_obs_sync,
                  "obs_target": o.cmb_obs_target,
              }
              o.btn_obs_connect.clicked.connect(self._ccd_connect)
              o.btn_obs_disconnect.clicked.connect(self._ccd_disconnect)
              o.btn_obs_refresh.clicked.connect(self._ccd_refresh)
              o.btn_obs_goto.clicked.connect(self._ccd_goto)
              o.btn_obs_sync.clicked.connect(self._ccd_astrometry_goto)
              o.cmb_obs_target.currentIndexChanged.connect(
                  lambda _i: self._ccd_apply_state())
              self._ccd_apply_state()

          def _ccd_widgets(self):
              # @return: one merged view of the CCDciel widgets — the
              # window-owned Observatory tab ones plus the per-project
              # capture ones (filter combo, send/start) when a project is
              # open. All _ccd_* methods read through here.
              w = dict(getattr(self, "_obs_widgets", {}) or {})
              w.update(self._project_widgets or {})
              return w
      ```
   d. `_ccd_apply_state` (:2303-2325), `_ccd_poll_tick` (:2455) y
      `_ccd_fill_filters` (:2620-2640): cambian su lectura de
      `self._project_widgets` a `self._ccd_widgets()` (en
      `_ccd_apply_state`: `w = self._ccd_widgets()`; el guardián
      `if not w.get("ccd_connect"): return` se queda). Los gotos
      (`_ccd_goto`, `_ccd_astrometry_goto`) leían el objetivo de
      `self._current_project`: ahora lo leen del combo `obs_target`
      (object_name + ctx del proyecto activo elegido):
      ```python
          def _obs_target_project(self):
              # @return: the active project dict chosen in the Observatory
              #          tab's target combo, or None
              from ..core import project as _p
              pid = self.observatory.cmb_obs_target.currentData()
              return _p.get(db, pid) if pid else None
      ```
      y en los dos gotos sustituye el `p = self._current_project` (o
      equivalente) por `p = self._obs_target_project()` con guardián:
      ```python
              if not p:
                  self.statusBar().showMessage(
                      self.tr("Pick a target project in the Observatory "
                              "tab"), 6000)
                  return
      ```
   e. `_refresh_obs_targets`: repuebla el combo con los proyectos activos;
      se llama desde `on_refresh_projects` (al final) y desde
      `_build_observatory_tab`:
      ```python
          def _refresh_obs_targets(self):
              # Refills the Observatory tab's target combo with the active
              # projects, keeping the selection (same keep-id pattern as
              # the campaigns list).
              cmb = self.observatory.cmb_obs_target
              current = cmb.currentData()
              cmb.blockSignals(True)
              cmb.clear()
              for p in project.list_projects(db, "active"):
                  cmb.addItem(f"[{p['kind']}] {p['object_name']}", p["id"])
              idx = cmb.findData(current)
              cmb.setCurrentIndex(idx if idx >= 0 else 0)
              cmb.blockSignals(False)
      ```
   f. El bloque de `_build_plan_tab` que se mueve (:2160-2186: label
      «CCDciel control», fila connect/disconnect/refresh/status, grupo
      «Observatory status»; y :2202-2219: la fila de gotos) **desaparece de
      Plan**. Se quedan en Plan: la rueda de filtros + Send plan + Start
      capture (:2187-2201) y el label de coords (:2220-2223), precedidos de
      un enlace cuando no hay conexión:
      ```python
          # UX-j: connection and mount live in the Observatory tab now; the
          # plan section keeps only its capture buttons + a jump link
          if not self._ccd_connected:
              btn_obs_link = QPushButton(self.tr(
                  "Not connected — open the Observatory tab →"))
              btn_obs_link.setFlat(True)
              btn_obs_link.setCursor(Qt.PointingHandCursor)
              btn_obs_link.clicked.connect(
                  lambda: self._goto_tab(TAB_OBSERVATORY))
              layout.addWidget(btn_obs_link)
      ```
      y el registro de `_project_widgets` (:2224-2239) se reduce a
      `{"cmb_ccd_filter", "ccd_push", "ccd_start", "ccd_coords"}` (los demás
      viven en `_obs_widgets`).
   g. El auto-connect del arranque (:306) y el timer (:281-283) no cambian.

4. `tests/unit/test_projects_hub.py` — los 4 tests `*_ccdciel_*`
   (:531-641): donde lean `window._project_widgets["ccd_connect" /
   "ccd_status" / "ccd_version" / …]` (widgets movidos), pasan a
   `window._obs_widgets[...]`; donde lean `"cmb_ccd_filter" / "ccd_push" /
   "ccd_start"` siguen en `_project_widgets`. Nada más cambia en ellos.

**Tests a añadir** — `tests/unit/test_observatory_tab.py` (**nuevo**;
cabecera GPL; «Unit tests: observatory tab (UX, UD.2)»; arnés MainWindow
del `LEEME.md` §2):

```python
def test_observatory_tab_exists(window):
    from PySide6.QtWidgets import QTabWidget
    from nightscribe.gui.main_window import TAB_OBSERVATORY
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.count() == 6
    assert tabs.widget(TAB_OBSERVATORY) is window.observatory


def test_ccd_widgets_are_window_owned(window):
    # UX-j: the CCDciel controls live in the Observatory tab, outside any
    # project rebuild path (the old per-project Plan block orphaned them)
    w = window._obs_widgets["ccd_connect"]
    parent = w.parentWidget()
    while parent is not None:
        assert parent is not window.projects
        parent = parent.parentWidget()


def test_disconnected_state_disables_capture(window):
    window._ccd_connected = False
    window._ccd_apply_state()
    assert not window.observatory.btn_obs_disconnect.isEnabled()
    assert not window.observatory.btn_obs_goto.isEnabled()
    assert window.observatory.btn_obs_connect.isEnabled()


def test_target_combo_lists_active_projects(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    proj_mod.create(mw.db, "sn", "SN 2099obs", {"mag": 15.0})
    window._refresh_obs_targets()
    texts = [window.observatory.cmb_obs_target.itemText(i)
             for i in range(window.observatory.cmb_obs_target.count())]
    assert any("SN 2099obs" in t for t in texts)
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Observatory | Observatorio | Observatory |
| CCDciel control | Control de CCDciel | CCDciel control |
| Observatory status | Estado del observatorio | Observatory status |
| Telescope | Telescopio | Telescope |
| Target: | Objetivo: | Target: |
| Capture plans are sent from each project's Plan section. | Los planes de captura se envían desde la sección Plan de cada proyecto. | Capture plans are sent from each project's Plan section. |
| Pick a target project in the Observatory tab | Elige un proyecto objetivo en la pestaña Observatory | Pick a target project in the Observatory tab |
| Not connected — open the Observatory tab → | Sin conexión — abre la pestaña Observatory → | Not connected — open the Observatory tab → |

(Las cadenas movidas — Connect CCDciel, Disconnect, Refresh, Version:,
CCD temperature:, Tracking:, Slew:, Point telescope, Astrometric Goto y
sus tooltips — ya existen; `lupdate` las reubica solo.)

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_observatory_tab.py tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: Observatory tab — CCDciel control leaves the project Plan step (UX, subplan UD.2)`
**Estado**: Hecho (1136→1140 tests, suite verde)

> Nota de ejecución: `tests/unit/test_projects_hub.py:582` se parte en
> dos lecturas (clúster de conexión en `_obs_widgets`; fila de captura
> `cmb_ccd_filter`/`ccd_push`/`ccd_start` sigue en `_project_widgets`),
> como dice el propio punto 4 de la tarjeta. `test_campaigns_tab.py:64`
> pasa de `tabs.count() == 5` a `== 6`. `test_project_tabs.py` también
> se adapta — la tarjeta no lo nombra, pero el paso Plan perdió sus 7
> controles de conexión: `PLAN_BUTTONS` 10 → 6 (queda la fila de captura
> + el enlace a la pestaña Observatory) y `PROJECT_WIDGETS` 25 → 15
> (11 plan + 2 MPC + products + zoom). Además: el destino al que se aplica
> la posición leída es el último proyecto enviado por Goto
> (`self._ccd_point_target`), porque el combo de la pestaña Observatory
> lista los proyectos activos y no significa «el proyecto abierto»; en los
> tests fijos (llamada directa) aterriza en el proyecto del hub.

---

## UD.3 — La página del proyecto: secciones plegables en lugar de pestañas

**Contexto a leer (solo esto)**: `nightscribe/gui/ui/projects_tab.ui:84-176`
(panel de detalle completo); `nightscribe/gui/main_window.py:1961-1992`
(`_step_tab_layout`, `_clear_step_tabs`, `_wipe_layout`), `:1993-2025`
(`_build_step_tabs`), `:2027-2031` (cómo arranca `_build_plan_tab`),
`:1784-1809` (`_get_proj_panel` / `_reset_proj_panel`), `:1763-1785`
(`_ensure_proj_files_list`);
`nightscribe/gui/widgets/collapsible_section.py` (API completa, 75 líneas).

**Precondición**: UD.1.

**Toca**: `nightscribe/gui/ui/projects_tab.ui`;
`nightscribe/gui/main_window.py`;
`tests/unit/test_project_tabs.py` (**reescritura completa** — ver abajo).

**Escribe exactamente esto**:

1. `projects_tab.ui`: el `QTabWidget name="tabs_steps"` (:137-159),
   `lbl_step_status` (:163) y el layout `navBtns` con sus 4 botones
   (:169-175) **desaparecen**. En su lugar:

```xml
        <item>
         <widget class="QGroupBox" name="grp_next">
          <property name="title"><string>Next</string></property>
          <layout class="QHBoxLayout" name="nextLayout">
           <item>
            <widget class="QLabel" name="lbl_next">
             <property name="text"><string>—</string></property>
             <property name="wordWrap"><bool>true</bool></property>
             <property name="styleSheet"><string>font-size: 13px; font-weight: bold;</string></property>
            </widget>
           </item>
           <item>
            <widget class="QPushButton" name="btn_next_go">
             <property name="text"><string>Go →</string></property>
            </widget>
           </item>
          </layout>
         </widget>
        </item>
        <item>
         <widget class="QLabel" name="lbl_steps_line">
          <property name="text"><string/></property>
         </widget>
        </item>
        <item>
         <widget class="QScrollArea" name="scroll_page">
          <property name="widgetResizable"><bool>true</bool></property>
          <property name="frameShape"><enum>QFrame::NoFrame</enum></property>
          <widget class="QWidget" name="page_container">
           <layout class="QVBoxLayout" name="pageLayout"/>
          </widget>
         </widget>
        </item>
```

   (El layout `metaLayout` con favorito/tags y `lbl_advisor` se quedan
   donde están, encima de la tarjeta «Next».)

2. `main_window.py`:
   a. Nuevo gestor de secciones (sustituye a `_step_tab_layout`,
      :1961-1978 — esa función se borra):
      ```python
          def _section_layout(self, key, title):
              # One collapsible section of the project page (UX-i).
              # @args: key - "details"|"plan"|"process"|"publish"|"followup",
              #        title - the visible header
              # @return: the section's content QLayout (where the per-kind
              #          builders add their widgets, exactly as before)
              from .widgets.collapsible_section import CollapsibleSection
              sec = CollapsibleSection(title)
              self._page_sections[key] = sec
              self.projects.page_container.layout().addWidget(sec)
              inner = QWidget()
              sec.setContentWidget(inner)
              return QVBoxLayout(inner)
      ```
   b. `_clear_step_tabs` (:1979-1992) pasa a:
      ```python
          def _clear_project_page(self):
              # Wipes the project page sections (one rebuild per project
              # selection, same discipline as the old step tabs).
              self._page_sections = {}
              lay = self.projects.page_container.layout()
              while lay.count():
                  item = lay.takeAt(0)
                  w = item.widget()
                  if w is not None:
                      w.setParent(None)
                      w.deleteLater()
      ```
   c. `_build_step_tabs` (:1993-2025) pasa a `_build_project_page`:
      ```python
          def _build_project_page(self, p):
              # The project page (UX-i): one scroll with collapsible
              # sections instead of step tabs + wizard. Same per-kind
              # content builders, new container; the step state shows in
              # words and its toggle lives INSIDE each step section.
              self._clear_project_page()
              kind, ctx = p["kind"], p["context"]
              # section 0: the object card + project files (not a step)
              det = self._section_layout("details", self.tr("Object card"))
              panel = self._get_proj_panel()
              det.addWidget(panel)
              self._ensure_proj_files_list_section(det)
              self._populate_project_files(p["id"])
              # step sections keep the old builders: each one's first line
              # now asks for a section instead of a tab page
              self._build_plan_tab(p, kind, ctx)
              self._build_process_tab(p, kind, ctx)
              self._build_publish_tab(p, kind, ctx)
              if kind in FOLLOWUP_KINDS:
                  self._build_followup_tab(p, ctx)
      ```
      (La tarjeta «Next» — `_refresh_next_card` y la auto-expansión — se
      cablea en UD.4; aquí no se llama todavía.)
      donde `_ensure_proj_files_list_section(det)` es la versión retarget de
      `_ensure_proj_files_list` (:1763-1785): mismo contenido pero la
      sección «Project files» se añade al layout `det` en lugar de buscar
      `tab_details` (ajusta el método viejo: su firma ya recibe el
      contenedor — pásale el widget/ayout de la sección; mira su cuerpo y
      adapta el `tab.layout().addWidget(sec)` final a `det.addWidget(sec)`).
   d. El primer renglón de cada builder de paso cambia de tab a sección:
      - `_build_plan_tab` (:2031): `layout = self._step_tab_layout(
        "tab_plan")` → `layout = self._step_section("plan")`.
      - `_build_process_tab` y `_build_publish_tab`: igual con su clave.
      - `_build_followup_tab`: `layout = self._step_section("followup")` y
        la lógica de `setTabVisible` desaparece (la sección solo se crea
        para los kinds con follow-up, ver punto c).
      con el helper:
      ```python
          def _step_section(self, key):
              # Builds one step section with its state line + toggle inside
              # (UX-i). @return: the section's content layout
              labels = {"plan": self._step_label("plan"),
                        "process": self._step_label("process"),
                        "publish": self._step_label("publish"),
                        "followup": self.tr("Follow-up")}
              layout = self._section_layout(key, labels[key])
              p = self._current_project
              if p and key in _STEP_KEYS:
                  layout.addLayout(self._step_toggle_row(p, key))
              return layout
      ```
      y la fila de estado/toggle (reemplazo funcional del wizard):
      ```python
          def _step_toggle_row(self, p, key):
              # The step's own controls, in words (no more ✔/●/○/– icons):
              # "done on <date>" / "skipped" / pending with its buttons.
              from PySide6.QtWidgets import QHBoxLayout
              row = QHBoxLayout()
              step = next((s for s in p["steps"] if s["step"] == key), None)
              status = step["status"] if step else "pending"
              lbl = QLabel()
              row.addWidget(lbl)
              if status in ("done", "skipped"):
                  when = datetime.datetime.fromtimestamp(
                      step["updated"]).strftime("%Y-%m-%d") \
                      if step and step.get("updated") else ""
                  lbl.setText(
                      self.tr("✔ done on %1").replace("%1", when)
                      if status == "done" else self.tr("– skipped"))
                  btn_reopen = QPushButton(self.tr("Reopen step"))
                  btn_reopen.setFlat(True)
                  btn_reopen.clicked.connect(
                      lambda _=False, k=key: self._step_reopen(k))
                  row.addWidget(btn_reopen)
              else:
                  lbl.setText(self.tr("pending"))
                  btn_done = QPushButton(self.tr("Mark done"))
                  btn_done.clicked.connect(
                      lambda _=False, k=key: self._step_done(k))
                  row.addWidget(btn_done)
                  btn_skip = QPushButton(self.tr("Skip step"))
                  btn_skip.setFlat(True)
                  btn_skip.clicked.connect(
                      lambda _=False, k=key: self._step_skip(k))
                  row.addWidget(btn_skip)
              row.addStretch()
              return row

          def _step_done(self, key):
              # Marks the step done and rebuilds (advance() keeps the
              # single-current invariant); the close prompt at the last
              # step survives from the old wizard.
              p = self._current_project
              if not p:
                  return
              cur = project.current_step(db, p["id"])
              if cur != key:
                  project.set_step_status(db, p["id"], key,
                                          project.STEP_CURRENT)
              done_all = project.advance(db, p["id"])
              p = project.get(db, p["id"])
              self._current_project = p
              self.on_refresh_projects()
              self._build_project_page(p)
              self._render_project_header(p)
              if p["status"] != project.STATUS_ACTIVE:
                  from PySide6.QtWidgets import QMessageBox
                  ans = QMessageBox.question(
                      self, self.tr("Close project"),
                      self.tr("All steps are done. Close this project?"))
                  if ans == QMessageBox.Yes:
                      self._project_close()

          def _step_skip(self, key):
              project.set_step_status(db, self._current_project["id"], key,
                                      project.STEP_SKIPPED)
              p = project.get(db, self._current_project["id"])
              self._current_project = p
              self._build_project_page(p)

          def _step_reopen(self, key):
              project.reopen_step(db, self._current_project["id"], key)
              p = project.get(db, self._current_project["id"])
              self._current_project = p
              self._build_project_page(p)
      ```
      (el `advance()` viejo marca el current y activa el siguiente; por eso
      `_step_done` primero fuerza `key` como current si no lo era.)
   e. `_project_selected` (:1735-1761): borra las dos llamadas viejas
      `self.projects.tabs_steps.setCurrentIndex(0)` (:1751) y
      `self._update_step_buttons()` (:1752) — el aterrizaje en la sección
      del next-action lo añade UD.4.
      La línea `panel.explore(...)` y demás no cambian; solo que
      `_get_proj_panel` (:1784-1809) ya no se inyecta en `tab_details`:
      revisa su cuerpo — el panel se añade ahora desde
      `_build_project_page` (punto c), así que `_get_proj_panel` debe
      dejar de hacer `layout().addWidget(panel)` sobre la tab vieja y
      limitarse a crear/reusar la instancia.
   f. `_render_project_header` y demás llamadas a `_build_step_tabs(...)`
      pasan a `_build_project_page(...)` (grep: aparece también en el
      flujo de follow-up, p. ej. tras importar fotometría — el rebuild en
      el sitio lo da la sección ya construida).
3. `tests/unit/test_project_tabs.py` — **reescritura completa** (el fichero
   entero se reemplaza; cabecera GPL; «Unit tests: project page sections
   (UX, UD.3)»; mismo arnés `window`/`panel` de `test_projects_hub.py` —
   importa los fixtures con `from .test_projects_hub import *` NO: copia el
   arnés como hace el propio fichero hoy, mira sus líneas 1-95):

```python
def _mk_project(window, kind="sn", name="SN 2099pg"):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, kind, name, {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == p["id"]:
            lst.setCurrentRow(i)
            break
    return p


def test_page_has_sections_instead_of_tabs(window, panel):
    _mk_project(window)
    assert hasattr(window.projects, "scroll_page")
    assert set(window._page_sections) >= {"details", "plan", "process",
                                          "publish", "followup"}


def test_sections_hold_exactly_one_control_set_after_rebuilds(window, panel):
    p = _mk_project(window)
    window._build_project_page(window._current_project)
    window._build_project_page(window._current_project)
    from PySide6.QtWidgets import QPushButton
    names = [b.text() for b in window.projects.page_container
             .findChildren(QPushButton)]
    assert names.count("Mark done") + names.count("Marcar hecho") == 3


def test_page_is_scroll_wrapped(window, panel):
    _mk_project(window)
    assert window.projects.scroll_page.widget() is \
        window.projects.page_container


def test_followup_section_only_for_followup_kinds(window, panel):
    _mk_project(window, kind="neo", name="2099 PG1")
    assert "followup" not in window._page_sections
    _mk_project(window, kind="sn", name="SN 2099pg2")
    assert "followup" in window._page_sections


def test_step_toggle_marks_done(window, panel):
    p = _mk_project(window)
    window._step_done("plan")
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    steps = {s["step"]: s["status"]
             for s in proj_mod.get(mw.db, p["id"])["steps"]}
    assert steps["plan"] == "done"
    assert steps["process"] == "current"


def test_step_reopen(window, panel):
    p = _mk_project(window)
    window._step_done("plan")
    window._step_reopen("plan")
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    steps = {s["step"]: s["status"]
             for s in proj_mod.get(mw.db, p["id"])["steps"]}
    assert steps["plan"] == "current"
    assert steps["process"] == "pending"
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Next | Siguiente | Next |
| Go → | Ir → | Go → |
| Object card | Ficha del objeto | Object card |
| Follow-up | Seguimiento | Follow-up |
| ✔ done on %1 | ✔ hecho el %1 | ✔ done on %1 |
| – skipped | – saltado | – skipped |
| pending | pendiente | pending |
| Mark done | Marcar hecho | Mark done |
| Skip step | Saltar paso | Skip step |
| Reopen step | Reabrir paso | Reabrir paso |
| Close project | Cerrar proyecto | Close project |
| All steps are done. Close this project? | Todos los pasos están hechos. ¿Cerrar el proyecto? | All steps are done. Close this project? |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_project_tabs.py -q` + pipeline i18n
**Hecho cuando**: verde. (La suite completa NO estará verde aún: quedan
los retargets de UD.4/UD.5 — anótalo en el estado como «verde parcial».)
**Commit**: `Gui: the project page — collapsible sections replace step tabs (UX, subplan UD.3)`
**Estado**: Pendiente

---

## UD.4 — La tarjeta «Siguiente» cableada + enlaces profundos como scroll

**Contexto a leer (solo esto)**: tu `main_window.py` de UD.3;
`nightscribe/core/project.py` (`next_action`, UD.1);
`nightscribe/gui/widgets/collapsible_section.py` (`setCollapsed`).

**Precondición**: UD.3, UA.6 (los chips de cadencia), UB.1 (abrir en el
paso actual).

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_project_tabs.py` (ampliar);
`tests/unit/test_projects_hub.py` (retarget de las ~20 referencias a
`tabs_steps` — tabla de traducción abajo).

**Escribe exactamente esto**:

1. La tarjeta «Next»:
   ```python
       def _next_target_key(self, p):
           # @return: the section key the Next card points at
           act = project.next_action(db, p)
           return {"followup": "followup", "plan": "plan",
                   "process": "process", "publish": "publish",
                   "close": None}.get(act["key"])

       def _refresh_next_card(self, p):
           # Fills the Next card from next_action() (UX-i): one bold line
           # saying what to do, one small line with the steps in words,
           # and the Go button scrolling to the right section.
           act = project.next_action(db, p)
           texts = {
               "followup": self.tr("Measure tonight — %1 d since the last "
                                   "visit").replace(
                   "%1", str(act["overdue_days"]))
               if not act["never_visited"] else
               self.tr("First measurement — it opens the series"),
               "plan": self.tr("Plan the capture"),
               "process": self.tr("Process your data"),
               "publish": self.tr("Draft the post"),
               "close": self.tr("All steps done — consider closing the "
                                "project"),
           }
           self.projects.lbl_next.setText("▶ " + texts[act["key"]])
           steps = {s["step"]: s["status"] for s in p.get("steps", [])}
           words = []
           for key in _STEP_KEYS:
               st = steps.get(key, "pending")
               mark = "✔" if st == "done" else "–" if st == "skipped" \
                   else "○"
               words.append(f"{mark} {self._step_label(key)}")
           self.projects.lbl_steps_line.setText("  ·  ".join(words))
           target = self._next_target_key(p)
           self._next_target = target
           self.projects.btn_next_go.setVisible(target is not None)

       def _scroll_to_section(self, key):
           # Expands the section and scrolls the page to it (the landing
           # spot of every deep link after UD.3, UX-i).
           if not key or key not in getattr(self, "_page_sections", {}):
               return
           sec = self._page_sections[key]
           sec.setCollapsed(False)
           from PySide6.QtCore import QTimer
           QTimer.singleShot(0, lambda: self.projects.scroll_page
                             .ensureWidgetVisible(sec))
   ```
2. En `_build_project_page` (UD.3, punto c): tras montar las secciones,
   la sección del next-action **auto-expandida** y las demás colapsadas
   (excepto `details`, siempre abierta):
   ```python
           self._refresh_next_card(p)
           target = self._next_target_key(p)
           for key, sec in self._page_sections.items():
               sec.setCollapsed(key not in ("details", target))
   ```
3. En `_connect`: `p.btn_next_go.clicked.connect(
   lambda: self._scroll_to_section(self._next_target))`.
4. Enlaces profundos retarget (sustituyen a los índices de pestaña):
   - `_goto_project_followup` (UA.6): su `tabs.isTabVisible(4) /
     setCurrentIndex(4)` pasa a:
     ```python
         self._scroll_to_section("followup")
     ```
     (sin condición: la sección solo existe para kinds con follow-up, y
     el guardián de `_scroll_to_section` ya la cubre).
   - `_project_open_activated` (UB.1): su bloque `cur in _STEP_KEYS →
     setCurrentIndex(...)` pasa a:
     ```python
         self._scroll_to_section(self._next_target_key(self._current_project))
     ```
   - El menú contextual de UB.1: su rama `act_fu` →
     `self._scroll_to_section("followup")` en lugar de
     `setCurrentIndex(4)`; y su `setEnabled(...isTabVisible(4))` pasa a
     `p["kind"] in FOLLOWUP_KINDS` a secas.
5. **Tabla de traducción para los tests viejos** (aplicar a TODAS las
   referencias restantes; el grep de verificación es
   `grep -rn "tabs_steps" tests/unit/` → 0 al terminar UD.5):

   | Viejo (tabs) | Nuevo (página) |
   |---|---|
   | `window.projects.tabs_steps.findChild(QWidget, "tab_X")` | `window._page_sections["X"]` |
   | `tabs_steps.isTabVisible(i)` | `"followup" in window._page_sections` |
   | `tabs_steps.setCurrentIndex(i)` / `currentIndex()` | `window._page_sections["X"].isCollapsed()` (inverso) o la aserción de estado en palabras |
   | `tabs_steps.count() == 5` | `len(window._page_sections) >= 4` |
   | `tabs_steps.tabText(i)` con iconos | la línea de estado de la sección (QLabel «pending/done…») |

   Los tests concretos de `test_projects_hub.py` que tocan `tabs_steps`
   (líneas ~196-199, ~303-305, ~979-989, ~1171 y las que lleguen de
   fases A/B) se reescriben con esa tabla; comportamiento esperado
   idéntico (selección → página construida; follow-up solo para sus
   kinds; notas/sesiones en su sección…). Si uno no traduce limpio:
   **para y reporta**.

**Tests a añadir** (al final de `tests/unit/test_project_tabs.py`):

```python
def test_next_card_points_at_pending_section(window, panel):
    _mk_project(window)
    assert "Plan" in window.projects.lbl_next.text() or \
        "Planifica" in window.projects.lbl_next.text()
    assert window._page_sections["plan"].isCollapsed() is False
    assert window._page_sections["process"].isCollapsed() is True


def test_next_card_followup_when_cadence_due(window, panel):
    p = _mk_project(window)
    window._step_done("plan")
    from nightscribe.core import followup as fu
    from nightscribe.gui import main_window as mw
    fu.create_session(mw.db, p["id"])
    mw.db.execute("UPDATE project_sessions SET created=? WHERE"
                  " project_id=?", (1_700_000_000, p["id"]))
    mw.db.commit()
    window._build_project_page(window._current_project)
    assert "Measure" in window.projects.lbl_next.text() or \
        "Mide" in window.projects.lbl_next.text()
    assert window._page_sections["followup"].isCollapsed() is False


def test_go_button_expands_target(window, panel):
    _mk_project(window)
    window._page_sections["plan"].setCollapsed(True)
    window.projects.btn_next_go.click()
    assert window._page_sections["plan"].isCollapsed() is False
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Measure tonight — %1 d since the last visit | Mide esta noche — %1 d desde la última visita | Measure tonight — %1 d since the last visit |
| First measurement — it opens the series | Primera medida — abre la serie | First measurement — it opens the series |
| Plan the capture | Planifica la captura | Plan the capture |
| Process your data | Procesa tus datos | Process your data |
| Draft the post | Redacta el post | Draft the post |
| All steps done — consider closing the project | Todos los pasos hechos — considera cerrar el proyecto | All steps done — consider closing the project |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_project_tabs.py tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M) salvo los ficheros de
hads/transit/neo que retargeta UD.5 (anótalo).
**Commit**: `Gui: the Next card drives the project page — deep links scroll to sections (UX, subplan UD.4)`
**Estado**: Pendiente

---

## UD.5 — Retirada del wizard + retarget de los tests de pasos por kind

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:4215-4290`
(`_project_step_changed`, `_update_step_status`, `_update_step_buttons`,
`_project_prev/_next/_skip/_mark_done`); tus tarjetas UD.3/UD.4;
`tests/unit/test_hads_plan.py`, `tests/unit/test_transit_plan.py`,
`tests/unit/test_neo_process.py` (cómo localizan hoy el contenido del paso
— la mayoría usa `tabs_steps.findChild(QWidget, "tab_plan")` o selecciona y
busca widgets).

**Precondición**: UD.4.

**Toca**: `nightscribe/gui/main_window.py` (borrados);
`tests/unit/test_hads_plan.py`, `tests/unit/test_transit_plan.py`,
`tests/unit/test_neo_process.py`, `tests/unit/test_projects_hub.py`
(retarget con la tabla de UD.4).

**Escribe exactamente esto**:

1. `main_window.py` — borra estas funciones completas (sus roles ya los
   cubren la tarjeta Next y los toggles de sección):
   - `_project_step_changed` (:4215-4220)
   - `_update_step_status` (:4222-4235)
   - `_update_step_buttons` (:4237-4248)
   - `_project_prev`, `_project_next` (:4250-4260)
   - `_project_skip`, `_project_mark_done` (:4262-4290)
   - `_step_key_idx` (:3967-3977)
   - `_step_tab_layout` si sobrevivió a UD.3
   Y sus conexiones en `_connect`: `p.tabs_steps.currentChanged…`,
   `p.btn_prev…`, `p.btn_next…`, `p.btn_skip…`, `p.btn_mark_done…`
   (:473-477). También cualquier llamada residual a
   `self._update_step_buttons()` / `self._update_step_status(...)`
   (grep de verificación abajo).
2. Retarget de tests (tabla de UD.4): en `test_hads_plan.py` (5 refs),
   `test_transit_plan.py` (6), `test_neo_process.py` (2) y lo que quede en
   `test_projects_hub.py`. Ejemplo del patrón:
   ```python
   # viejo:
   tab = window.projects.tabs_steps.findChild(QWidget, "tab_plan")
   # nuevo:
   tab = window._page_sections["plan"]
   ```
   Los tests de contenido (checklist HADS, timeline de tránsito, reporte
   MPC…) no cambian de aserciones, solo de localizador.
3. Grep de cierre (debe dar 0 en código vivo):
   `grep -rn "tabs_steps\|_update_step_buttons\|_update_step_status\|_project_mark_done\|_step_key_idx" nightscribe/ tests/`

**Tests a añadir**: ninguno nuevo (esta tarjeta es retirada + retarget).

**Cadenas nuevas**: ninguna (las cadenas del wizard mueren; `lupdate` las
marca vanished y se limpian en UC.1).

**Ejecuta**: `.venv/bin/python -m pytest tests/unit -q`
**Hecho cuando**: suite verde completa (N→M); los greps de la tarjeta en 0.
**Commit**: `Gui: the step wizard retires — page sections carry their own state (UX, subplan UD.5)`
**Estado**: Pendiente
