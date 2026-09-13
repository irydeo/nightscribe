# Track UX — Fase A: la pestaña Campaigns (UA.1–UA.7)

> Subplanes UA.1–UA.7 del plan maestro
> [../ux-variables-campaigns.md](../ux-variables-campaigns.md). Un subplan =
> un commit. Anclas verificadas a HEAD `4df771b`; si una no coincide:
> **parar y reportar**. Lee antes `LEEME.md`.
> Precondición: fase 0 hecha (UA.4 depende de U0.3/U0.4; el resto no).

---

## UA.1 — `campaign.status_report` (la query del detalle)

**Contexto a leer (solo esto)**: `nightscribe/core/campaign.py:149-195`
(`protocol_get`, `projects_of`, `due_campaigns`);
`nightscribe/core/followup.py:93-103` (`days_since_last_session`);
`nightscribe/core/variables.py:115-141` (`detect_event`);
`tests/unit/test_campaign.py` (el arnés).

**Precondición**: ninguna.

**Toca**: `nightscribe/core/campaign.py` (una función);
`tests/unit/test_campaign.py` (ampliar — solo añadir al final).

**Escribe exactamente esto**:

1. Al final de `nightscribe/core/campaign.py`:

```python
def status_report(db, campaign_id):
    # The Campaigns tab data (UX-b): EVERY member project with its cadence
    # health and event flag, so the tab shows the whole campaign at a
    # glance — due_campaigns' narrower job is the Tonight loop (due only).
    # @args: db - Database, campaign_id - int
    # @return: {"campaign": camp, "members": [{"id", "object_name", "kind",
    #          "status", "days_since", "due", "overdue_days", "event"}]},
    #          or None when the campaign does not exist
    from . import followup, variables
    camp = get(db, campaign_id)
    if not camp:
        return None
    cad = int(protocol_get(camp, "cadence_nights", 1) or 1)
    rows = db.execute(
        "SELECT id, object_name, kind, status FROM projects"
        " WHERE campaign_id=? ORDER BY object_name COLLATE NOCASE",
        (campaign_id,)).fetchall()
    members = []
    for pid, name, kind, pstatus in rows:
        days = followup.days_since_last_session(db, pid)
        due = pstatus == "active" and (days is None or days >= cad)
        ev = None
        if kind in ("variable", "sn"):
            ev = variables.detect_event(followup.list_points(db, pid))
        members.append({"id": pid, "object_name": name, "kind": kind,
                        "status": pstatus, "days_since": days, "due": due,
                        "overdue_days": days if days is not None else cad,
                        "event": ev})
    return {"campaign": camp, "members": members}
```

**Tests a añadir** (al final de `tests/unit/test_campaign.py`):

```python
def test_status_report_health_per_member(db):
    from nightscribe.core import followup, project
    cid = campaign.create(db, "Campaña WeSb 1",
                          protocol={"cadence_nights": 2})
    p_new = project.create(db, "variable", "WeSb 1",
                           {"ra_deg": 15.2, "dec_deg": 55.0},
                           campaign_id=cid)
    p_ok = project.create(db, "sn", "SN 2099aa", {}, campaign_id=cid)
    followup.create_session(db, p_ok["id"])        # visited today
    rep = campaign.status_report(db, cid)
    assert rep["campaign"]["name"] == "Campaña WeSb 1"
    by_name = {m["object_name"]: m for m in rep["members"]}
    assert by_name["WeSb 1"]["due"] is True        # never visited
    assert by_name["WeSb 1"]["days_since"] is None
    assert by_name["SN 2099aa"]["due"] is False    # visited today
    assert by_name["SN 2099aa"]["days_since"] == 0
    assert by_name["SN 2099aa"]["event"] is None


def test_status_report_flags_events(db):
    from nightscribe.core import followup, project
    cid = campaign.create(db, "C")
    p = project.create(db, "variable", "R CrB", {}, campaign_id=cid)
    # >= 4 own points, latest one a >0.5 mag jump (inverted axis: mag up
    # = brightness drop)
    for i, mag in enumerate((11.0, 11.1, 11.0, 11.05, 12.0)):
        followup.add_point(db, p["id"], 60100.0 + i, "V", mag,
                           source="manual")
    rep = campaign.status_report(db, cid)
    assert rep["members"][0]["event"]["direction"] == "drop"


def test_status_report_unknown_campaign(db):
    assert campaign.status_report(db, 9999) is None
```

(si el fixture `db` de `test_campaign.py` no existe con ese nombre, usa el
que use el fichero — mira sus primeras 40 líneas; si difiere, **para y
reporta**.)

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaign.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: campaign.status_report — members with cadence health and event flag (UX, subplan UA.1)`
**Estado**: Hecho (1107→1110)

---

## UA.2 — Pestaña Campaigns: `.ui`, registro y lista con salud

**Contexto a leer (solo esto)**: `nightscribe/gui/ui/main_window.ui:14-28`
(los 4 tabs); `nightscribe/gui/main_window.py:186-190` (KIND_ORDER — sitio
de las constantes nuevas), `:387-423` (`_goto_tab` + `_build_tabs`),
`:448-496` (`_connect`), `:1643-1651` (`_on_main_tab_changed`);
`nightscribe/gui/ui/projects_tab.ui` (el molde maestro-detalle).

**Precondición**: UA.1.

**Toca**: `nightscribe/gui/ui/main_window.ui`;
`nightscribe/gui/ui/campaigns_tab.ui` (**nuevo**);
`nightscribe/gui/main_window.py`;
`tests/unit/test_campaigns_tab.py` (**nuevo**).

**Escribe exactamente esto**:

1. `ui/main_window.ui`: entre `tab_projects` y `tab_solar` inserta:
   ```xml
         <widget class="QWidget" name="tab_campaigns">
          <attribute name="title"><string>Campaigns</string></attribute>
         </widget>
   ```
2. `ui/campaigns_tab.ui` (**nuevo** — maestro-detalle como el hub; los
   botones se conectan en UA.5, como hizo VC.4 en el Track V):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>CampaignsTab</class>
 <widget class="QWidget" name="CampaignsTab">
  <layout class="QHBoxLayout" name="mainLayout">
   <item>
    <widget class="QGroupBox" name="grp_list">
     <property name="title"><string>Campaigns</string></property>
     <property name="maximumWidth"><number>360</number></property>
     <layout class="QVBoxLayout" name="listLayout">
      <item>
       <widget class="QListWidget" name="lst_campaigns">
        <property name="toolTip"><string>Select a campaign to see its detail</string></property>
       </widget>
      </item>
      <item>
       <layout class="QHBoxLayout" name="rowLife">
        <item><widget class="QPushButton" name="btn_new"><property name="text"><string>New campaign…</string></property></widget></item>
        <item><widget class="QPushButton" name="btn_edit"><property name="text"><string>Edit…</string></property></widget></item>
        <item><widget class="QPushButton" name="btn_delete"><property name="text"><string>Delete…</string></property></widget></item>
       </layout>
      </item>
      <item>
       <layout class="QHBoxLayout" name="rowTargets">
        <item><widget class="QPushButton" name="btn_finish"><property name="text"><string>Finish</string></property></widget></item>
        <item><widget class="QPushButton" name="btn_reopen"><property name="text"><string>Reopen</string></property></widget></item>
        <item><widget class="QPushButton" name="btn_add_target"><property name="text"><string>Add target…</string></property></widget></item>
       </layout>
      </item>
      <item>
       <layout class="QHBoxLayout" name="rowLink">
        <item><widget class="QPushButton" name="btn_attach"><property name="text"><string>Attach…</string></property></widget></item>
        <item><widget class="QPushButton" name="btn_detach"><property name="text"><string>Detach…</string></property></widget></item>
       </layout>
      </item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QGroupBox" name="grp_detail">
     <property name="title"><string>Campaign detail</string></property>
     <layout class="QVBoxLayout" name="detailLayout">
      <item>
       <widget class="QLabel" name="lbl_cname">
        <property name="text"><string>Select a campaign.</string></property>
        <property name="styleSheet"><string>font-size: 15px; font-weight: bold;</string></property>
       </widget>
      </item>
      <item><widget class="QLabel" name="lbl_cmeta"><property name="text"><string>—</string></property></widget></item>
      <item>
       <widget class="QLabel" name="lbl_cgoal">
        <property name="text"><string/></property>
        <property name="wordWrap"><bool>true</bool></property>
       </widget>
      </item>
      <item>
       <widget class="QLabel" name="lbl_urls">
        <property name="text"><string/></property>
        <property name="wordWrap"><bool>true</bool></property>
       </widget>
      </item>
      <item>
       <widget class="QGroupBox" name="grp_protocol">
        <property name="title"><string>Protocol</string></property>
        <layout class="QVBoxLayout" name="protocolLayout">
         <item>
          <widget class="QLabel" name="lbl_protocol">
           <property name="text"><string>—</string></property>
           <property name="wordWrap"><bool>true</bool></property>
          </widget>
         </item>
        </layout>
       </widget>
      </item>
      <item>
       <widget class="QGroupBox" name="grp_members">
        <property name="title"><string>Targets</string></property>
        <layout class="QVBoxLayout" name="membersLayout">
         <item>
          <widget class="QTableWidget" name="tbl_members">
           <property name="toolTip"><string>Double-click a row to open its project</string></property>
          </widget>
         </item>
        </layout>
       </widget>
      </item>
     </layout>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
```

3. `main_window.py`:
   a. Constantes de pestaña (tras `KIND_ORDER`, :188-189):
      ```python
      # Top-level tab indices (ui/main_window.ui order, UX track): never
      # use literals for the main tabs.
      TAB_TONIGHT, TAB_PROJECTS, TAB_CAMPAIGNS, TAB_SOLAR, TAB_HISTORY = \
          range(5)
      ```
   b. `_build_tabs` (:396-399) — la tupla gana la pestaña en la posición 2:
      ```python
          widgets = (self.tonight, self.projects, self.campaigns,
                     self.solar, self.history) = (
              _load_ui("tonight_tab"), _load_ui("projects_tab"),
              _load_ui("campaigns_tab"), _load_ui("solar_tab"),
              _load_ui("history_tab"))
      ```
      (el bucle `for i, w in enumerate(widgets)` no cambia.)
   c. `_goto_tab(1)` de :4720 y :4750 → `_goto_tab(TAB_PROJECTS)`.
   d. `_on_main_tab_changed` (:1643-1651) — actualiza comentario y lógica:
      ```python
          def _on_main_tab_changed(self, index):
              # @args: index - the newly selected top-level tab index
              #        (TAB_PROJECTS == the hub, TAB_CAMPAIGNS == the
              #        campaigns manager, per main_window.ui order)
              # @return: None
              # Keep both master-detail tabs always fresh on every visit.
              if index == TAB_PROJECTS:
                  self.on_refresh_projects()
              elif index == TAB_CAMPAIGNS:
                  self._refresh_campaigns_tab()
      ```
   e. En `_connect` (tras :472, la conexión de `lst_projects`):
      ```python
          c = self.campaigns
          c.lst_campaigns.itemSelectionChanged.connect(
              self._campaign_selected)
      ```
   f. Los handlers nuevos (junto a `_rebuild_campaign_filter`):

      ```python
          # ---------------- campaigns tab (UX-a) ----------------

          def _refresh_campaigns_tab(self):
              # Refills the single campaign list (UX-g: finished ones dimmed
              # and suffixed), keeping the selection. Each row carries the
              # health summary from status_report (UX-b).
              from ..core import campaign as _camp
              lst = self.campaigns.lst_campaigns
              sel = lst.currentItem()
              keep_id = sel.data(Qt.UserRole) if sel is not None else None
              lst.clear()
              for c in _camp.list_campaigns(db):
                  rep = _camp.status_report(db, c["id"])
                  members = rep["members"] if rep else []
                  due = sum(1 for m in members if m["due"])
                  text = c["name"]
                  if c.get("group_name"):
                      text += f"  ({c['group_name']})"
                  text += "  —  " + self.tr("%1 targets · %2 due").replace(
                      "%1", str(len(members))).replace("%2", str(due))
                  if any(m.get("event") for m in members):
                      text += "  ⚡"
                  if c["status"] == _camp.CAMPAIGN_FINISHED:
                      text += "  " + self.tr("(finished)")
                  item = QListWidgetItem(text)
                  item.setData(Qt.UserRole, c["id"])
                  if c["status"] == _camp.CAMPAIGN_FINISHED:
                      item.setForeground(QColor(theme.C_TEXT_DIM))
                  lst.addItem(item)
                  if c["id"] == keep_id:
                      lst.setCurrentItem(item)
              if lst.count() == 0:
                  self._campaign_selected()     # clears the detail side

          def _selected_campaign_id(self):
              # @return: campaign id selected in the tab's list, or None
              item = self.campaigns.lst_campaigns.currentItem()
              return item.data(Qt.UserRole) if item is not None else None

          def _campaign_selected(self):
              # Fills the detail header (name, meta, goal); UA.3 fills the
              # protocol block, the URLs and the members table.
              w = self.campaigns
              cid = self._selected_campaign_id()
              from ..core import campaign as _camp
              c = _camp.get(db, cid) if cid is not None else None
              if c is None:
                  w.lbl_cname.setText(self.tr("Select a campaign."))
                  w.lbl_cmeta.setText("—")
                  w.lbl_cgoal.setText("")
                  return
              w.lbl_cname.setText(c["name"])
              status = self.tr("active") if c["status"] == \
                  _camp.CAMPAIGN_ACTIVE else self.tr("finished")
              meta = [status]
              if c.get("group_name"):
                  meta.append(c["group_name"])
              if c.get("coordinator"):
                  meta.append(c["coordinator"])
              w.lbl_cmeta.setText(" · ".join(meta))
              w.lbl_cgoal.setText(c.get("goal") or "")
      ```
      (`QColor` ya está importado en :20; `QListWidgetItem` y `theme` ya se
      usan en el fichero.)

**Tests a añadir** — `tests/unit/test_campaigns_tab.py` (**nuevo**;
cabecera GPL; «Unit tests: campaigns tab (UX, UA.x)»; arnés MainWindow del
`LEEME.md` §2 — cópialo de `test_projects_hub.py:107-160`):

```python
def test_campaigns_tab_exists(window):
    from PySide6.QtWidgets import QTabWidget
    from nightscribe.gui.main_window import TAB_CAMPAIGNS
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.count() == 5
    assert tabs.widget(TAB_CAMPAIGNS) is window.campaigns


def test_campaign_list_shows_health(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña T CrB", group_name="obsSN")
    proj_mod.create(mw.db, "variable", "T CrB",
                    {"ra_deg": 239.9, "dec_deg": 25.9}, campaign_id=cid)
    window._refresh_campaigns_tab()
    lst = window.campaigns.lst_campaigns
    texts = [lst.item(i).text() for i in range(lst.count())]
    assert any("Campaña T CrB" in t and "obsSN" in t for t in texts)
    assert any("1 target" in t or "1 objetivo" in t for t in texts)


def test_finished_campaign_is_dimmed(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Vieja")
    camp_mod.finish(mw.db, cid)
    window._refresh_campaigns_tab()
    lst = window.campaigns.lst_campaigns
    item = next(lst.item(i) for i in range(lst.count())
                if lst.item(i).data(Qt.UserRole) == cid)
    assert "finished" in item.text() or "finalizada" in item.text()
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Campaigns | Campañas | Campaigns |
| Campaign detail | Detalle de la campaña | Campaign detail |
| Select a campaign. | Selecciona una campaña. | Select a campaign. |
| Select a campaign to see its detail | Selecciona una campaña para ver su detalle | Select a campaign to see its detail |
| Double-click a row to open its project | Doble-clic en una fila para abrir su proyecto | Double-click a row to open its project |
| Protocol | Protocolo | Protocol |
| Targets | Objetivos | Targets |
| %1 targets · %2 due | %1 objetivos · %2 vencidos | %1 targets · %2 due |
| (finished) | (finalizada) | (finished) |
| active | activa | active |
| finished | finalizada | finished |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaigns_tab.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M). Verifica además con
`grep -n "_goto_tab(1)\|index == 1" nightscribe/gui/main_window.py` que no
quedan literales de pestaña principal.
**Commit**: `Gui: Campaigns tab — skeleton, fifth tab, campaign list with health summary (UX, subplan UA.2)`
**Estado**: Pendiente

---

## UA.3 — Detalle de campaña: protocolo, URLs clicables y tabla de miembros

**Contexto a leer (solo esto)**: tu `main_window.py` de UA.2
(`_campaign_selected`); `nightscribe/gui/theme.py` (`KIND_LABELS`,
`C_TEXT_DIM`, `C_WARN`, `C_GOOD`).

**Precondición**: UA.2.

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_campaigns_tab.py` (ampliar).

**Escribe exactamente esto**:

1. `_campaign_selected`: el método completo pasa a ser (sustituye al de
   UA.2 entero):

```python
    def _campaign_selected(self):
        # Fills the whole campaign detail: header, protocol, URLs and the
        # members table with the per-target cadence health (UX-b).
        from PySide6.QtWidgets import QAbstractItemView
        w = self.campaigns
        cid = self._selected_campaign_id()
        from ..core import campaign as _camp
        rep = _camp.status_report(db, cid) if cid is not None else None
        tbl = w.tbl_members
        if rep is None:
            w.lbl_cname.setText(self.tr("Select a campaign."))
            w.lbl_cmeta.setText("—")
            w.lbl_cgoal.setText("")
            w.lbl_urls.setText("")
            w.lbl_protocol.setText("—")
            tbl.setRowCount(0)
            tbl.setColumnCount(0)
            return
        c = rep["campaign"]
        w.lbl_cname.setText(c["name"])
        status = self.tr("active") if c["status"] == \
            _camp.CAMPAIGN_ACTIVE else self.tr("finished")
        meta = [status]
        if c.get("group_name"):
            meta.append(c["group_name"])
        if c.get("coordinator"):
            meta.append(c["coordinator"])
        w.lbl_cmeta.setText(" · ".join(meta))
        w.lbl_cgoal.setText(c.get("goal") or "")
        # protocol block (plain readable text; the fields are free text)
        prot = c.get("protocol") or {}
        cad = int(prot.get("cadence_nights", 1) or 1)
        lines = [self.tr("One measurement every %1 night(s) per filter"
                         ).replace("%1", str(cad))]
        if prot.get("filters"):
            lines.append(self.tr("Filters: %1").replace(
                "%1", ", ".join(prot["filters"])))
        if prot.get("comp_stars"):
            lines.append(self.tr("Comparison stars: %1").replace(
                "%1", ", ".join(prot["comp_stars"])))
        if prot.get("notes"):
            lines.append(prot["notes"])
        w.lbl_protocol.setText("\n".join(lines))
        # clickable URLs (linkActivated is connected once in _connect)
        links = []
        if c.get("report_url"):
            links.append("<a href='%1'>%2</a>".replace(
                "%1", c["report_url"]).replace("%2", self.tr("Report form")))
        if c.get("data_url"):
            links.append("<a href='%1'>%2</a>".replace(
                "%1", c["data_url"]).replace("%2", self.tr("Data")))
        w.lbl_urls.setText(" · ".join(links))
        # members table: object | kind | last visit | status
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels([
            self.tr("Object"), self.tr("Kind"), self.tr("Last visit"),
            self.tr("Status")])
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        tbl.verticalHeader().setVisible(False)
        tbl.setRowCount(0)
        for m in rep["members"]:
            row = tbl.rowCount()
            tbl.insertRow(row)
            name_item = QTableWidgetItem(m["object_name"])
            name_item.setData(Qt.UserRole, m["id"])
            tbl.setItem(row, 0, name_item)
            tbl.setItem(row, 1, QTableWidgetItem(
                theme.KIND_LABELS.get(m["kind"], m["kind"])))
            last = "—" if m["days_since"] is None else \
                self.tr("%1 d ago").replace("%1", str(m["days_since"]))
            tbl.setItem(row, 2, QTableWidgetItem(last))
            if m["event"]:
                st, col = self.tr("⚡ brightness event"), theme.C_WARN
            elif m["due"] and m["days_since"] is None:
                st, col = self.tr("● never visited"), theme.C_WARN
            elif m["due"]:
                st, col = self.tr("⚠ %1 d overdue").replace(
                    "%1", str(m["overdue_days"])), theme.C_WARN
            else:
                st, col = self.tr("✓ up to date"), theme.C_GOOD
            st_item = QTableWidgetItem(st)
            st_item.setForeground(QColor(col))
            tbl.setItem(row, 3, st_item)
```

2. En `_connect` (junto a la conexión de UA.2 de `lst_campaigns`):
   ```python
       c.lbl_urls.linkActivated.connect(self._open_url)
   ```
   y el handler:
   ```python
       def _open_url(self, url):
           # Opens an http(s) link from a label (campaign report/data URLs).
           from PySide6.QtCore import QUrl
           from PySide6.QtGui import QDesktopServices
           QDesktopServices.openUrl(QUrl(url))
   ```

**Tests a añadir** (al final de `tests/unit/test_campaigns_tab.py`):

```python
def test_campaign_detail_shows_protocol_and_members(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(
        mw.db, "Campaña WeSb 1", group_name="obsSN",
        goal="Catch the fade",
        protocol={"cadence_nights": 1, "filters": ["B", "V"],
                  "comp_stars": ["000-BB0-123"], "notes": "HJD report"},
        report_url="https://example.org/report")
    proj_mod.create(mw.db, "variable", "WeSb 1",
                    {"ra_deg": 15.2, "dec_deg": 55.0}, campaign_id=cid)
    window._refresh_campaigns_tab()
    lst = window.campaigns.lst_campaigns
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == cid:
            lst.setCurrentRow(i)
    w = window.campaigns
    assert w.lbl_cname.text() == "Campaña WeSb 1"
    assert "obsSN" in w.lbl_cmeta.text()
    assert "Catch the fade" in w.lbl_cgoal.text()
    assert "B, V" in w.lbl_protocol.text()
    assert "000-BB0-123" in w.lbl_protocol.text()
    assert "https://example.org/report" in w.lbl_urls.text()
    tbl = w.tbl_members
    assert tbl.rowCount() == 1
    assert tbl.item(0, 0).text() == "WeSb 1"
    assert "never" in tbl.item(0, 3).text() or \
        "visitar" in tbl.item(0, 3).text()


def test_empty_campaign_detail_is_clean(window):
    window.campaigns.lst_campaigns.clearSelection()
    window._campaign_selected()
    assert window.campaigns.tbl_members.rowCount() == 0
    assert window.campaigns.lbl_cname.text() != ""
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| One measurement every %1 night(s) per filter | Una medida cada %1 noche(s) por filtro | One measurement every %1 night(s) per filter |
| Filters: %1 | Filtros: %1 | Filters: %1 |
| Comparison stars: %1 | Estrellas de comparación: %1 | Comparison stars: %1 |
| Report form | Formulario de reporte | Report form |
| Data | Datos | Data |
| Object | Objeto | Object |
| Kind | Tipo | Kind |
| Last visit | Última visita | Last visit |
| Status | Estado | Status |
| ⚡ brightness event | ⚡ evento de brillo | ⚡ brightness event |
| ● never visited | ● sin visitar todavía | ● never visited |
| ⚠ %1 d overdue | ⚠ %1 d de retraso | ⚠ %1 d overdue |
| ✓ up to date | ✓ al día | ✓ up to date |
| %1 d ago | hace %1 d | %1 d ago |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaigns_tab.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: campaign detail — protocol, clickable URLs and members table with cadence health (UX, subplan UA.3)`
**Estado**: Pendiente

---

## UA.4 — Navegación, gestos y acciones `_camp_*` en la pestaña

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:4721-4724`
y `:4751-4754` (los dos bucles de selección en el hub — se refactorizan);
tu `main_window.py` de UA.2/UA.3;
`nightscribe/gui/campaigns_dialog.py:194-368` (los sub-diálogos que se
reutilizan).

**Precondición**: UA.3, U0.3, U0.4 (los handlers recogen el feedback y el
delete/edit-finalizada decididos ahí).

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_campaigns_tab.py` (ampliar).

**Escribe exactamente esto**:

1. Extrae el helper y úsalo en los dos sitios viejos:
   ```python
       def _select_project_row(self, pid):
           # @args: pid - project id
           # @return: True when the hub list holds the project and selects it
           for i in range(self.projects.lst_projects.count()):
               if self.projects.lst_projects.item(i).data(Qt.UserRole) == pid:
                   self.projects.lst_projects.setCurrentRow(i)
                   return True
           return False
   ```
   - En `_create_project` (:4721-4724): el bucle pasa a ser
     `self._select_project_row(p["id"])` (borra el `for` con su `break`).
   - En `_goto_active_project` (:4751-4754): el bucle pasa a ser
     `return self._select_project_row(match["id"])` (tras el
     `_goto_tab(TAB_PROJECTS)`).
2. Los dos saltos nuevos:
   ```python
       def _goto_project_by_id(self, pid):
           # Jumps to the Projects hub with this project selected (UX-d).
           # @return: True when the project was found in the list
           self.on_refresh_projects()
           self._goto_tab(TAB_PROJECTS)
           return self._select_project_row(pid)

       def _goto_campaigns(self, cid=None):
           # Jumps to the Campaigns tab, optionally selecting a campaign
           # (the landing spot of every campaign link, UX-d).
           self._goto_tab(TAB_CAMPAIGNS)
           self._refresh_campaigns_tab()
           if cid is not None:
               lst = self.campaigns.lst_campaigns
               for i in range(lst.count()):
                   if lst.item(i).data(Qt.UserRole) == cid:
                       lst.setCurrentRow(i)
                       break
   ```
3. Las acciones de campaña (los handlers que comparten botones (UA.5) y
   menús contextuales (esta tarjeta); el feedback de U0.3/U0.4 ya viene
   incorporado — nada vuelve a fallar en silencio):

   ```python
       def _camp_after_action(self):
           # Refresh both master-detail tabs after any campaign mutation.
           self._refresh_campaigns_tab()
           self.on_refresh_projects()

       def _camp_new(self):
           from .campaigns_dialog import CampaignEditDialog
           if CampaignEditDialog(self, db_obj=db).exec():
               self._camp_after_action()

       def _camp_edit(self):
           # Finished campaigns are editable too (UX, ex U0.4).
           from .campaigns_dialog import CampaignEditDialog
           from ..core import campaign as _camp
           cid = self._selected_campaign_id()
           if cid is None:
               return
           if CampaignEditDialog(self, camp=_camp.get(db, cid),
                                 db_obj=db).exec():
               self._camp_after_action()

       def _camp_delete(self):
           # Deletes the campaign after confirmation; its projects keep
           # going (campaign_id -> NULL, migration v7).
           from PySide6.QtWidgets import QMessageBox
           from ..core import campaign as _camp
           cid = self._selected_campaign_id()
           if cid is None:
               return
           c = _camp.get(db, cid)
           ans = QMessageBox.question(
               self, self.tr("Delete campaign"),
               self.tr("Delete the campaign “%1”? Its projects are kept, "
                       "only the link is removed.").replace(
                           "%1", c["name"]))
           if ans == QMessageBox.Yes:
               _camp.delete(db, cid)
               self._camp_after_action()

       def _camp_finish(self):
           from ..core import campaign as _camp
           cid = self._selected_campaign_id()
           if cid is not None:
               _camp.finish(db, cid)
               self._camp_after_action()

       def _camp_reopen(self):
           from ..core import campaign as _camp
           cid = self._selected_campaign_id()
           if cid is not None:
               _camp.reopen(db, cid)
               self._camp_after_action()

       def _camp_add_target(self):
           from .campaigns_dialog import AddTargetDialog
           cid = self._selected_campaign_id()
           if cid is None:
               return
           if AddTargetDialog(self, campaign_id=cid, db_obj=db).exec():
               self._camp_after_action()

       def _camp_attach(self):
           # Links an existing active project to the selected campaign.
           # Never silent (UX-e): an empty candidate list says so.
           from PySide6.QtWidgets import QInputDialog, QMessageBox
           from ..core import project
           cid = self._selected_campaign_id()
           if cid is None:
               return
           actives = project.list_projects(db, status="active")
           choices = [p for p in actives if not p.get("campaign_id")]
           if not choices:
               QMessageBox.information(
                   self, self.tr("Attach project"),
                   self.tr("No active project without a campaign."))
               return
           names = [f"[{p['kind']}] {p['object_name']}" for p in choices]
           sel, ok = QInputDialog.getItem(
               self, self.tr("Attach project"), self.tr("Project:"),
               names, 0, False)
           if ok:
               project.set_campaign(db, choices[names.index(sel)]["id"],
                                    cid)
               self._camp_after_action()

       def _camp_detach(self):
           # Unlinks a member of the selected campaign (chosen by name).
           from PySide6.QtWidgets import QInputDialog, QMessageBox
           from ..core import campaign as _camp
           from ..core import project
           cid = self._selected_campaign_id()
           if cid is None:
               return
           members = _camp.projects_of(db, cid, status=None)
           if not members:
               QMessageBox.information(
                   self, self.tr("Detach project"),
                   self.tr("This campaign has no projects yet."))
               return
           names = [p["object_name"] for p in members]
           sel, ok = QInputDialog.getItem(
               self, self.tr("Detach project"), self.tr("Project:"),
               names, 0, False)
           if ok:
               project.set_campaign(db, members[names.index(sel)]["id"],
                                    None)
               self._camp_after_action()

       def _camp_detach_member(self, pid):
           # Detaches one member project straight from the members table.
           from ..core import project
           project.set_campaign(db, pid, None)
           self._camp_after_action()
   ```

4. En `_connect`, tras las conexiones de UA.2/UA.3 de la pestaña:
   ```python
       c.tbl_members.cellDoubleClicked.connect(self._campaign_member_opened)
       c.lst_campaigns.setContextMenuPolicy(Qt.CustomContextMenu)
       c.lst_campaigns.customContextMenuRequested.connect(
           self._campaign_context_menu)
       c.tbl_members.setContextMenuPolicy(Qt.CustomContextMenu)
       c.tbl_members.customContextMenuRequested.connect(
           self._campaign_member_menu)
       c.lst_campaigns.viewport().setCursor(Qt.PointingHandCursor)
       c.tbl_members.viewport().setCursor(Qt.PointingHandCursor)
   ```
5. Los handlers de navegación/gestos:
   ```python
       def _campaign_member_opened(self, row, _col):
           # Double-click on a member row: open its project in the hub.
           item = self.campaigns.tbl_members.item(row, 0)
           if item is not None and item.data(Qt.UserRole) is not None:
               self._goto_project_by_id(item.data(Qt.UserRole))

       def _campaign_context_menu(self, pos):
           # Right-click on the campaign list (UX-c): the row's actions.
           item = self.campaigns.lst_campaigns.itemAt(pos)
           if item is None or item.data(Qt.UserRole) is None:
               return
           self.campaigns.lst_campaigns.setCurrentItem(item)
           from PySide6.QtWidgets import QMenu
           menu = QMenu(self)
           for label, slot in (
                   (self.tr("Edit…"), self._camp_edit),
                   (self.tr("Finish"), self._camp_finish),
                   (self.tr("Reopen"), self._camp_reopen),
                   (self.tr("Delete…"), self._camp_delete),
                   (self.tr("Add target…"), self._camp_add_target),
                   (self.tr("Attach…"), self._camp_attach),
                   (self.tr("Detach…"), self._camp_detach)):
               act = menu.addAction(label)
               act.triggered.connect(slot)
           menu.exec(self.campaigns.lst_campaigns.viewport()
                     .mapToGlobal(pos))

       def _campaign_member_menu(self, pos):
           # Right-click on a member row (UX-c): open its project or detach.
           tbl = self.campaigns.tbl_members
           item = tbl.itemAt(pos)
           if item is None:
               return
           row = item.row()
           pid_item = tbl.item(row, 0)
           if pid_item is None or pid_item.data(Qt.UserRole) is None:
               return
           tbl.selectRow(row)
           from PySide6.QtWidgets import QMenu
           menu = QMenu(self)
           act_open = menu.addAction(self.tr("Open project"))
           act_detach = menu.addAction(self.tr("Detach from campaign"))
           chosen = menu.exec(tbl.viewport().mapToGlobal(pos))
           if chosen is act_open:
               self._goto_project_by_id(pid_item.data(Qt.UserRole))
           elif chosen is act_detach:
               self._camp_detach_member(pid_item.data(Qt.UserRole))
   ```

**Tests a añadir** (al final de `tests/unit/test_campaigns_tab.py`):

```python
def test_member_double_click_jumps_to_project(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    from nightscribe.gui.main_window import TAB_PROJECTS
    cid = camp_mod.create(mw.db, "Campaña salto")
    p = proj_mod.create(mw.db, "variable", "R CrB",
                        {"ra_deg": 1.0, "dec_deg": 2.0}, campaign_id=cid)
    window._refresh_campaigns_tab()
    lst = window.campaigns.lst_campaigns
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == cid:
            lst.setCurrentRow(i)
    window._campaign_member_opened(0, 0)
    from PySide6.QtWidgets import QTabWidget
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.currentIndex() == TAB_PROJECTS
    cur = window.projects.lst_projects.currentItem()
    assert cur is not None and cur.data(Qt.UserRole) == p["id"]


def test_goto_campaigns_selects_the_campaign(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    from nightscribe.gui.main_window import TAB_CAMPAIGNS
    cid = camp_mod.create(mw.db, "Campaña destino")
    window._goto_campaigns(cid)
    from PySide6.QtWidgets import QTabWidget
    tabs = window.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.currentIndex() == TAB_CAMPAIGNS
    cur = window.campaigns.lst_campaigns.currentItem()
    assert cur is not None and cur.data(Qt.UserRole) == cid


def test_camp_detach_member_unlinks(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña quita")
    p = proj_mod.create(mw.db, "variable", "SS Cyg",
                        {"ra_deg": 1.0, "dec_deg": 2.0}, campaign_id=cid)
    window._goto_campaigns(cid)
    window._camp_detach_member(p["id"])
    assert proj_mod.get(mw.db, p["id"])["campaign_id"] is None
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Open project | Abrir proyecto | Open project |
| Detach from campaign | Quitar de la campaña | Detach from campaign |

(Delete…, Delete campaign, las cadenas de los QMessageBox y las de
Attach/Detach ya existen de U0.3/U0.4 — no las dupliques en los `.ts`.)

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaigns_tab.py tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: campaign tab navigation + camp actions — member double-click, context menus, goto helpers (UX, subplan UA.4)`
**Estado**: Pendiente

---

## UA.5 — Botones visibles + jubilación del gestor modal

**Contexto a leer (solo esto)**: `nightscribe/gui/campaigns_dialog.py`
entero (368 líneas); tu `main_window.py` de UA.4;
`nightscribe/gui/main_window.py:469` (botón del hub) y `:4768-4772`
(`_tools_campaigns`).

**Precondición**: UA.4.

**Toca**: `nightscribe/gui/campaigns_dialog.py` (se borra la clase
`CampaignsDialog`; quedan `CampaignEditDialog` y `AddTargetDialog`);
`nightscribe/gui/main_window.py`; `tests/unit/test_campaigns_dialog.py`
(se borran los tests del gestor — ver abajo);
`tests/unit/test_campaigns_tab.py` (ampliar).

**Escribe exactamente esto**:

1. `campaigns_dialog.py`: borra la clase `CampaignsDialog` completa
   (:33-191, incluidos sus `_attach_project`/`_detach_project` — su lógica
   y sus mensajes ya viven en los `_camp_*` de UA.4) y actualiza el
   docstring del módulo (:14-20) a:
   ```python
   """Sub-dialogs of the Campaigns tab (UX-a): the create/edit form and the
   add-target dialog with its VSX/SIMBAD resolution chain. The manager
   itself is the top-level Campaigns tab (supersedes the modal dialog of
   ADR-035 V-j). All persistence goes through core/campaign.py.
   """
   ```
2. `main_window.py`:
   a. `_tools_campaigns` (:4768-4772) pasa a saltar a la pestaña (menú
      Tools y botón del hub ya apuntan aquí):
      ```python
          def _tools_campaigns(self):
              # Campaigns live in their own top-level tab (UX-a; supersedes
              # the modal manager of ADR-035 V-j). Also the hub button.
              self._goto_campaigns()
      ```
   b. En `_connect`, tras las conexiones de UA.4 de la pestaña:
      ```python
          c.btn_new.clicked.connect(self._camp_new)
          c.btn_edit.clicked.connect(self._camp_edit)
          c.btn_delete.clicked.connect(self._camp_delete)
          c.btn_finish.clicked.connect(self._camp_finish)
          c.btn_reopen.clicked.connect(self._camp_reopen)
          c.btn_add_target.clicked.connect(self._camp_add_target)
          c.btn_attach.clicked.connect(self._camp_attach)
          c.btn_detach.clicked.connect(self._camp_detach)
      ```
3. `tests/unit/test_campaigns_dialog.py`: **borra** los tests del gestor
   que ya no existe: `test_dialog_lists_active_and_finished`,
   `test_finish_and_reopen_from_the_buttons`,
   `test_empty_dialog_buttons_disabled`,
   `test_detach_with_no_members_informs`,
   `test_delete_campaign_keeps_projects`,
   `test_finished_campaign_is_editable`. Se quedan los del formulario y del
   alta de objetivo (que ahora viven de las clases supervivientes).
4. Y sus equivalentes de pestaña (al final de `tests/unit/test_campaigns_tab.py`):

```python
def test_tab_lists_active_and_finished(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    camp_mod.create(mw.db, "Activa")
    cid = camp_mod.create(mw.db, "Vieja")
    camp_mod.finish(mw.db, cid)
    window._refresh_campaigns_tab()
    texts = [window.campaigns.lst_campaigns.item(i).text()
             for i in range(window.campaigns.lst_campaigns.count())]
    assert any(t.startswith("Activa") for t in texts)
    assert any("Vieja" in t and ("finalizada" in t or "finished" in t)
               for t in texts)


def test_tab_finish_and_reopen(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "A")
    window._goto_campaigns(cid)
    window._camp_finish()
    assert camp_mod.get(mw.db, cid)["status"] == camp_mod.CAMPAIGN_FINISHED
    window._camp_reopen()
    assert camp_mod.get(mw.db, cid)["status"] == camp_mod.CAMPAIGN_ACTIVE


def test_tab_delete_keeps_projects(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    cid = camp_mod.create(mw.db, "Campaña X")
    proj_mod.create(mw.db, "variable", "T CrB",
                    {"ra_deg": 1.0, "dec_deg": 2.0}, campaign_id=cid)
    window._goto_campaigns(cid)
    window._camp_delete()
    assert camp_mod.list_campaigns(mw.db) == []
    p = proj_mod.list_projects(mw.db)[0]
    assert p["campaign_id"] is None


def test_attach_without_candidates_informs(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    seen = {}
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: seen.setdefault("told", True))
    cid = camp_mod.create(mw.db, "Campaña sola")
    window._goto_campaigns(cid)
    window._camp_attach()
    assert seen.get("told")
```

   Ojo: los tests de este fichero comparten la BD temporal del arnés
   (module scope) — usa nombres de campaña únicos por test (ya vienen así)
   para que los listados no se pisen.

**Cadenas nuevas**: ninguna (todas existen de fases anteriores).

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaigns_tab.py tests/unit/test_campaigns_dialog.py -q`
**Hecho cuando**: verde; suite verde (N→M). Verifica con
`grep -rn "CampaignsDialog" nightscribe/ tests/` que no quedan referencias
en código vivo.
**Commit**: `Gui: campaign actions live in the Campaigns tab — the modal manager retires (UX, subplan UA.5; supersedes ADR-035 V-j)`
**Estado**: Pendiente

---

## UA.6 — Toda mención de campaña es un enlace (badge, chip ⚑, chips de cadencia)

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:192-203`
(`_ClickableFrame` — molde de `_LinkChip`), `:1055-1102`
(`_show_cadence_hints`), `:1202-1208` (`_chip`), `:1314-1330` (zona del
`_make_row` tras el chip de Luna), `:1897-1902` (badge de campaña).

**Precondición**: UA.4 (usa `_goto_campaigns` / `_goto_project_by_id`).

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_campaigns_tab.py` (ampliar);
`tests/unit/test_tonight_kinds.py` (ampliar — solo añadir al final).

**Escribe exactamente esto**:

1. Clase `_LinkChip` (tras `_ClickableFrame`, :203):
   ```python
   class _LinkChip(QLabel):
       # A chip that behaves like a link (UX-c): hand cursor + clicked
       # signal that CONSUMES the event, so a clickable parent row never
       # fires when the chip is the real target.
       clicked = Signal()

       def __init__(self, text, color, tip=""):
           super().__init__(text)
           self.setStyleSheet(theme.chip_style(color))
           if tip:
               self.setToolTip(tip)
           self.setCursor(Qt.PointingHandCursor)

       def mousePressEvent(self, ev):
           ev.accept()
           self.clicked.emit()
   ```
2. Badge de la cabecera del proyecto (:1897-1902): el `span` pasa a enlace
   (`tr()` plano fuera del f-string — error frecuente nº 1 del LEEME):
   ```python
           if p.get("campaign_id"):
               from ..core import campaign as _camp
               c = _camp.get(db, p["campaign_id"])
               if c:
                   lab = self.tr("campaign")
                   header += (" · <a href='campaign://%1' "
                              "style='color:#65cf30; text-decoration:none'>"
                              "⚑ %2: %3</a>").replace(
                                  "%1", str(c["id"])).replace(
                                  "%2", lab).replace("%3", c["name"])
   ```
   y en `_connect` (una sola vez):
   ```python
       # UX-d: the project header campaign badge is a link to the tab
       self.projects.lbl_header.linkActivated.connect(
           self._campaign_link_clicked)
   ```
   handler:
   ```python
       def _campaign_link_clicked(self, url):
           # The project header campaign badge is a link (UX-d).
           if url.startswith("campaign://"):
               self._goto_campaigns(int(url.split("://", 1)[1]))
   ```
3. Chip ⚑ en la tarjeta de Tonight: en `_make_row`, tras el bloque del chip
   de Luna (el `if info and info.get("warning"):` completo), añade:
   ```python
           camp = t.get("campaign") or {}
           if camp.get("name"):
               chip = _LinkChip(
                   "⚑ " + camp["name"], theme.KIND_COLORS["variable"],
                   self.tr("Part of this observing campaign — click to "
                           "open it"))
               cid = camp.get("id")
               if cid is not None:
                   chip.clicked.connect(
                       lambda _c=cid: self._goto_campaigns(_c))
               head.addWidget(chip)
   ```
4. Chips de cadencia clicables y por proyecto: en `_show_cadence_hints`
   (:1055-1102) cambia tres cosas:
   a. La limpieza inicial (:1061-1066) borra TODOS los chips viejos (ahora
      hay varios): el `old = self.tonight.findChild(...)` y su `if` pasan a
      ```python
          for old in self.tonight.findChildren(QLabel, "ns_cadence_chip"):
              parent = old.parentWidget()
              if parent and parent.layout():
                  parent.layout().removeWidget(old)
              old.deleteLater()
      ```
   b. El bucle de `hints` lleva también el id (:1075-1079):
      ```python
          hints = []
          for pid, name in rows:
              days = fu.days_since_last_session(db, pid)
              if days is not None and days >= threshold:
                  hints.append((pid, name, days))
      ```
   c. El tramo final (desde `if not hints:` hasta el final del método) se
      reescribe — un chip por proyecto (máx. 3) que salta a su Follow-up,
      más etiqueta «+N»:
      ```python
          if not hints:
              return
          # insert the chips in the tonight header's layout (the parent of
          # lbl_context is a QWidget; find its containing layout)
          parent = self.tonight.lbl_context.parentWidget()
          header_layout = parent.layout() if parent else None
          if header_layout is None:
              p = parent
              while p is not None:
                  if p.layout() is not None:
                      header_layout = p.layout()
                      break
                  p = p.parentWidget()
          if not (header_layout and hasattr(header_layout, "addWidget")):
              return
          for pid, name, days in hints[:3]:
              chip = _LinkChip(
                  self.tr("SN due: %1 (%2 d)").replace(
                      "%1", name).replace("%2", str(days)),
                  "#e0c060",
                  self.tr("Due for a revisit — click to open its "
                          "Follow-up"))
              chip.setObjectName("ns_cadence_chip")
              chip.clicked.connect(
                  lambda _p=pid: self._goto_project_followup(_p))
              header_layout.addWidget(chip)
          if len(hints) > 3:
              more = QLabel(f"+{len(hints) - 3}")
              more.setObjectName("ns_cadence_chip")
              more.setStyleSheet(theme.chip_style("#e0c060"))
              header_layout.addWidget(more)
      ```
   d. El handler de salto (junto a `_show_cadence_hints`):
      ```python
          def _goto_project_followup(self, pid):
              # Opens the project's Follow-up tab (the cadence chips land
              # here, UX-d). Follow-up is tab index 4 of tabs_steps.
              if not self._goto_project_by_id(pid):
                  return
              tabs = self.projects.tabs_steps
              if tabs.isTabVisible(4):
                  tabs.setCurrentIndex(4)
      ```
      > **Nota de interacción con la fase D** (UD.4 la reescribe): cuando el
      > detalle del proyecto sea una página única, este salto pasa a ser
      > `self._scroll_to_section("followup")` — la tarjeta UD.4 ya trae ese
      > retarget escrito; aquí se queda la versión de pestañas para que cada
      > commit intermedio sea consistente.

**Tests a añadir**:

`tests/unit/test_campaigns_tab.py`:

```python
def test_header_badge_is_a_link(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña enlace")
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 10.1},
                        campaign_id=cid)
    window._render_project_header(proj_mod.get(mw.db, p["id"]))
    text = window.projects.lbl_header.text()
    assert f"campaign://{cid}" in text and "Campaña enlace" in text


def test_cadence_chip_navigates_to_followup(window):
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099zz", {"mag": 15.0})
    fu.create_session(mw.db, p["id"])
    # age the session beyond the cadence threshold
    old = 1_700_000_000
    mw.db.execute("UPDATE project_sessions SET created=? WHERE project_id=?",
                  (old, p["id"]))
    mw.db.commit()
    window._show_cadence_hints()
    chips = window.tonight.findChildren(QLabel, "ns_cadence_chip")
    assert chips, "no cadence chip was created"
    window._goto_project_followup(p["id"])
    cur = window.projects.lst_projects.currentItem()
    assert cur is not None and cur.data(Qt.UserRole) == p["id"]
    assert window.projects.tabs_steps.currentIndex() == 4
```

(`QLabel` y `Qt`: añade los imports arriba si el fichero no los tiene —
única edición permitida fuera de los tests nuevos.)

`tests/unit/test_tonight_kinds.py` (al final):

```python
def test_campaign_chip_opens_campaign(window, monkeypatch):
    # UX-d: the ⚑ chip on a campaign target jumps to the Campaigns tab
    from nightscribe.gui import main_window as mw
    seen = []
    monkeypatch.setattr(mw.MainWindow, "_goto_campaigns",
                        lambda self, cid=None: seen.append(cid))
    window._set_tonight([
        ({"id": "X", "name": "T CrB", "kind": "variable", "mag": 10.0,
          "campaign": {"id": 42, "name": "Campaña T CrB"}}, 50.0, {}, "")])
    from nightscribe.gui.main_window import _LinkChip
    chips = window.tonight.scroll_suggestions.findChildren(_LinkChip)
    assert chips and chips[0].text().endswith("Campaña T CrB")
    chips[0].clicked.emit()
    assert seen == [42]
```

(si el harness de `test_tonight_kinds.py` inyecta objetivos con otro
método que `_set_tonight`, usa el suyo — lee sus primeras 60 líneas; si no
existe nada parecido, **para y reporta**.)

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Part of this observing campaign — click to open it | Parte de esta campaña de observación — clic para abrirla | Part of this observing campaign — click to open it |
| SN due: %1 (%2 d) | SN pendiente: %1 (%2 d) | SN due: %1 (%2 d) |
| Due for a revisit — click to open its Follow-up | Toca revisitarla — clic para abrir su Seguimiento | Due for a revisit — click to open its Follow-up |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaigns_tab.py tests/unit/test_tonight_kinds.py tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M). El test viejo
`test_project_header_shows_campaign_badge` debe seguir verde (el nombre
sigue en el HTML).
**Commit**: `Gui: every campaign mention is a link — header badge, ⚑ card chip, clickable cadence chips (UX, subplan UA.6)`
**Estado**: Pendiente

---

## UA.7 — Hub: marca ⚑ por proyecto + columna «Campaign» en la vista All

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:149-184`
(`TABLE_COLS` / `TABLE_COLS_DEFAULT`), `:1542-1543` (formateador `camp` —
ya genérico), `:1689-1726` (`on_refresh_projects`, construcción del ítem).

**Precondición**: UA.2.

**Toca**: `nightscribe/gui/main_window.py` (dos puntos);
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. Marca ⚑ en los ítems del hub: en `on_refresh_projects`, tras la llamada
   a `project.list_projects` (:1689-1692) añade:
   ```python
       from ..core import campaign as _camp
       camp_names = {c["id"]: c["name"] for c in _camp.list_campaigns(db)}
   ```
   y tras construir el `item` (:1721-1723), antes del `lst.addItem(item)`:
   ```python
           if p.get("campaign_id"):
               item.setText(item.text() + " ⚑")
               item.setToolTip(self.tr("Campaign: %1").replace(
                   "%1", camp_names.get(p["campaign_id"], "?")))
   ```
2. Columna «Campaign» en la vista All: `TABLE_COLS_DEFAULT` (:180-184) gana
   la pareja tras `("Type", "kind")`:
   ```python
   TABLE_COLS_DEFAULT = [("Object", "name"), ("Type", "kind"),
                         ("Campaign", "camp"), ("Score", "score"),
                         ("Mag", "mag"), ("Max alt", "max_alt"),
                         ("Best time (UTC)", "best_time"), ("NEOfixer", "nf"),
                         ("NObs", "nobs"), ("Discovered", "disc"),
                         ("Observed", "obs")]
   ```
   (El formateador `camp` de :1542 ya sirve a cualquier target con
   sub-dict `campaign`; los layouts por kind no cambian.)

**Tests a añadir** (al final de `tests/unit/test_projects_hub.py`):

```python
def test_hub_item_marks_campaign_membership(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña marca")
    proj_mod.create(mw.db, "variable", "EE Cep", {"mag": 11.0},
                    campaign_id=cid)
    proj_mod.create(mw.db, "sn", "SN 2099cc", {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    texts = {lst.item(i).text(): lst.item(i)
             for i in range(lst.count())}
    marked = [t for t in texts if "⚑" in t]
    assert any("EE Cep" in t for t in marked)
    assert not any("SN 2099cc" in t for t in marked)
    ee = next(it for t, it in texts.items() if "EE Cep" in t)
    assert "Campaña marca" in (ee.toolTip() or "")
```

**Cadenas nuevas**: `Campaign` (cabecera de tabla) → ES «Campaña», EN
«Campaign». (`Campaign: %1` ya existe de VC.2.)

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py tests/unit/test_tonight_kinds.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: hub items flag campaign membership + Campaign column in the All table (UX, subplan UA.7)`
**Estado**: Pendiente
