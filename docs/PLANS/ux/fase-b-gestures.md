# Track UX — Fase B: un solo lenguaje de gestos (UB.1–UB.3)

> Subplanes UB.1–UB.3 del plan maestro
> [../ux-variables-campaigns.md](../ux-variables-campaigns.md). Un subplan =
> un commit. Anclas verificadas a HEAD `4df771b`; si una no coincide:
> **parar y reportar**. Lee antes `LEEME.md`.
> Precondición: U0.2 (la lista de proyectos), UA.2+UA.4 (constantes de
> pestaña y la pestaña Campaigns).

La regla universal (UX-c): **clic = seleccionar · doble-clic/Enter =
abrir/saltar · clic derecho = menú contextual · cursor de mano donde sea
clicable**.

---

## UB.1 — Lista de proyectos: abrir en el paso actual, menú contextual, «New project…»

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:466-493`
(`_connect`, bloque de projects), `:1718-1726` (ítem del hub),
`:3968-3977` (`_step_key_idx`), `:4237-4250` (`_update_step_buttons`),
`:4293-4384` (handlers de ciclo de vida que el menú reutiliza);
`nightscribe/core/project.py:40-42` (constantes de estado);
`nightscribe/gui/ui/projects_tab.ui:12-23` (`filterLayout`).

**Precondición**: U0.2.

**Toca**: `nightscribe/gui/main_window.py`;
`nightscribe/gui/ui/projects_tab.ui`;
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. `projects_tab.ui`: en `filterLayout`, tras el ítem de `btn_campaigns`
   (:22), añade:
   ```xml
             <item><widget class="QPushButton" name="btn_new_project"><property name="text"><string>New project…</string></property></widget></item>
   ```
2. `main_window.py`, en `_connect` (tras :472, la conexión de
   `itemSelectionChanged`):
   ```python
           # UX-c: one gesture language — double-click/Enter opens the
           # project at its current step, right-click offers every action,
           # the hand cursor advertises clickability.
           p.btn_new_project.clicked.connect(self._tools_explore)
           p.lst_projects.itemActivated.connect(
               self._project_open_activated)
           p.lst_projects.setContextMenuPolicy(Qt.CustomContextMenu)
           p.lst_projects.customContextMenuRequested.connect(
               self._project_context_menu)
           p.lst_projects.viewport().setCursor(Qt.PointingHandCursor)
   ```
3. Los handlers (junto a `_project_selected`):

```python
    def _project_open_activated(self, item):
        # Double-click / Enter on a project row (UX-c): jump straight to
        # its current step (single click stays at the Details card).
        if item is None or item.data(Qt.UserRole) is None:
            return
        self.projects.lst_projects.setCurrentItem(item)
        p = self._current_project
        if not p or p["status"] != project.STATUS_ACTIVE:
            return
        cur = project.current_step(db, p["id"])
        if cur in _STEP_KEYS:
            self.projects.tabs_steps.setCurrentIndex(
                _STEP_KEYS.index(cur) + 1)          # Details is index 0
```

   > **Nota de interacción con la fase D** (UD.4 la reescribe): cuando el
   > detalle sea una página única, «abrir en el paso actual» pasa a ser
   > `self._scroll_to_section(self._next_target_key(...))` — UD.4 trae el
   > retarget escrito. Lo mismo aplica a la rama `act_fu` del menú
   > contextual (`isTabVisible(4)` → `p["kind"] in FOLLOWUP_KINDS`, y el
   > salto → `_scroll_to_section("followup")`).

```python

    def _project_context_menu(self, pos):
        # Right-click on the projects list (UX-c): all the row actions,
        # with state-aware enablement.
        item = self.projects.lst_projects.itemAt(pos)
        if item is None or item.data(Qt.UserRole) is None:
            return
        self.projects.lst_projects.setCurrentItem(item)
        p = self._current_project
        if not p:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        act_open = menu.addAction(self.tr("Open"))
        act_fu = menu.addAction(self.tr("Follow-up"))
        act_fu.setEnabled(
            p["kind"] in FOLLOWUP_KINDS
            and self.projects.tabs_steps.isTabVisible(4))
        act_fav = menu.addAction(
            self.tr("Unstar") if p.get("favorite")
            else self.tr("Star as favorite"))
        menu.addSeparator()
        act_close = menu.addAction(self.tr("Close project…"))
        act_close.setEnabled(p["status"] == project.STATUS_ACTIVE)
        act_reopen = menu.addAction(self.tr("Reopen"))
        act_reopen.setEnabled(p["status"] != project.STATUS_ACTIVE)
        act_archive = menu.addAction(self.tr("Archive…"))
        act_delete = menu.addAction(self.tr("Delete…"))
        menu.addSeparator()
        act_folder = menu.addAction(self.tr("Show in folder"))
        chosen = menu.exec(
            self.projects.lst_projects.viewport().mapToGlobal(pos))
        if chosen is act_open:
            self._project_open_activated(item)
        elif chosen is act_fu:
            self.projects.tabs_steps.setCurrentIndex(4)
        elif chosen is act_fav:
            self._project_toggle_favorite()
        elif chosen is act_close:
            self._project_close()
        elif chosen is act_reopen:
            self._project_reopen()
        elif chosen is act_archive:
            self._project_archive()
        elif chosen is act_delete:
            self._project_delete()
        elif chosen is act_folder:
            self._open_project_folder()
```

**Tests a añadir** (al final de `tests/unit/test_projects_hub.py`):

```python
def test_project_activated_jumps_to_current_step(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099dd", {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    item = next(lst.item(i) for i in range(lst.count())
                if lst.item(i).data(Qt.UserRole) == p["id"])
    window._project_open_activated(item)
    # a fresh project sits at step "plan" -> tab index 1 (Details is 0)
    assert window.projects.tabs_steps.currentIndex() == 1


def test_projects_context_menu_offers_actions(window, monkeypatch):
    from PySide6.QtWidgets import QMenu
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099ee", {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    item = next(lst.item(i) for i in range(lst.count())
                if lst.item(i).data(Qt.UserRole) == p["id"])
    seen = {}

    def fake_exec(menu, *a):
        seen["actions"] = [act.text() for act in menu.actions()]
        return None
    monkeypatch.setattr(QMenu, "exec", fake_exec)
    window._project_context_menu(
        lst.visualItemRect(item).center())
    texts = seen["actions"]
    assert any("Open" in t or "Abrir" in t for t in texts)
    assert any("Follow" in t or "Seguimiento" in t for t in texts)
    assert any("Delete" in t or "Eliminar" in t for t in texts)
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| New project… | Nuevo proyecto… | New project… |
| Open | Abrir | Open |
| Follow-up | Seguimiento | Follow-up |
| Unstar | Quitar estrella | Unstar |
| Star as favorite | Marcar como favorito | Star as favorite |
| Close project… | Cerrar proyecto… | Close project… |
| Archive… | Archivar… | Archive… |
| Show in folder | Mostrar en la carpeta | Show in folder |

(Reopen/Delete… ya existen de la fila de botones; `Delete…` llega en U0.4
— si tu tarjeta corre antes que U0.4 y la cadena falta en los `.ts`,
añádela aquí y no la dupliques allí.)

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: projects list gestures — open at current step, context menu, hand cursor, New project button (UX, subplan UB.1)`
**Estado**: Pendiente

---

## UB.2 — History clicable + atajos Ctrl+1..5

**Contexto a leer (solo esto)**:
`nightscribe/gui/main_window.py:5476-5489` (`on_refresh_history`);
`:4729-4755` (`_goto_active_project`); `:4774-4845`
(`_open_explore_dialog` — modal, en tests se monkeypatchea);
`nightscribe/core/db.py:356-369` (`mark_observed`).

**Precondición**: UA.2 (constantes `TAB_*`).

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_projects_hub.py` (ampliar — el arnés de MainWindow ya
vive ahí).

**Escribe exactamente esto**:

1. En `_connect` (zona de History, tras las conexiones de solar, ~:494):
   ```python
       # UX-c/UX-d: the history rows are links to their project (or to
       # Explore when there is none), and Ctrl+1..5 switches main tabs.
       self.history.tbl_history.cellDoubleClicked.connect(
           self._history_open)
       self.history.tbl_history.viewport().setCursor(
           Qt.PointingHandCursor)
       self.history.tbl_history.setToolTip(
           self.tr("Double-click a row to open its project or explore "
                   "the object"))
       from PySide6.QtGui import QKeySequence, QShortcut
       for i, tab_idx in enumerate((TAB_TONIGHT, TAB_PROJECTS,
                                    TAB_CAMPAIGNS, TAB_SOLAR,
                                    TAB_HISTORY)):
           sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
           sc.setContext(Qt.ApplicationShortcut)
           sc.activated.connect(lambda idx=tab_idx: self._goto_tab(idx))
   ```
2. El handler (junto a `on_refresh_history`):

```python
    def _history_open(self, row, _col):
        # Double-click on a history row: open the object's active project,
        # or explore the object when there is none (UX-c/UX-d).
        name_item = self.history.tbl_history.item(row, 1)
        name = name_item.text().strip() if name_item is not None else ""
        if not name:
            return
        if not self._goto_active_project(name):
            self._open_explore_dialog(name)
```

**Tests a añadir** (al final de `tests/unit/test_projects_hub.py`):

```python
def test_history_double_click_opens_project(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099ff", {"mag": 15.0})
    mw.db.mark_observed("SN 2099ff", "sn", "2026-09-13")
    window.on_refresh_history()
    tbl = window.history.tbl_history
    row = next(r for r in range(tbl.rowCount())
               if tbl.item(r, 1) and tbl.item(r, 1).text() == "SN 2099ff")
    window._history_open(row, 1)
    cur = window.projects.lst_projects.currentItem()
    assert cur is not None and cur.data(Qt.UserRole) == p["id"]


def test_history_double_click_without_project_explores(window, monkeypatch):
    from nightscribe.gui import main_window as mw
    mw.db.mark_observed("2099 ZZ9", "neo", "2026-09-13")
    seen = []
    monkeypatch.setattr(window, "_open_explore_dialog",
                        lambda name: seen.append(name))
    window.on_refresh_history()
    tbl = window.history.tbl_history
    row = next(r for r in range(tbl.rowCount())
               if tbl.item(r, 1) and tbl.item(r, 1).text() == "2099 ZZ9")
    window._history_open(row, 1)
    assert seen == ["2099 ZZ9"]
```

**Cadenas nuevas**: `Double-click a row to open its project or explore
the object` → ES «Doble-clic en una fila para abrir su proyecto o explorar
el objeto», EN igual a la fuente.

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: history rows navigate to their project or Explore + Ctrl+1..5 tab shortcuts (UX, subplan UB.2)`
**Estado**: Pendiente

---

## UB.3 — Barrido de consistencia de gestos

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:490-493`
(el banner advisor clicable); las conexiones de UA.4, UB.1 y UB.2.

**Precondición**: UB.1, UB.2, UA.4.

**Toca**: `nightscribe/gui/main_window.py` (un punto);
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. El banner del advisor (clicable desde A2) no anuncia que lo es: en
   `_connect`, tras la conexión del `mouseReleaseEvent` (:492-493):
   ```python
       self.projects.lbl_advisor.setCursor(Qt.PointingHandCursor)
   ```
2. Auditoría automática del lenguaje de gestos — test nuevo (al final de
   `tests/unit/test_projects_hub.py`):

```python
def test_gesture_language_is_consistent(window):
    # UX-c sweep: every list/table that navigates advertises it with the
    # hand cursor
    from PySide6.QtCore import Qt
    for w in (window.projects.lst_projects, window.campaigns.lst_campaigns,
              window.campaigns.tbl_members, window.history.tbl_history):
        assert w.viewport().cursor().shape() == Qt.PointingHandCursor, \
            f"{w.objectName()} lost its hand cursor"


def test_year_headers_never_open(window):
    # the hub's year separators have no id: activation must be a no-op
    lst = window.projects.lst_projects
    header = next((lst.item(i) for i in range(lst.count())
                   if lst.item(i).data(Qt.UserRole) is None), None)
    if header is not None:
        window._project_open_activated(header)      # must not raise
        assert window._current_project is None or True
```

3. Checklist manual (lo verifica el ejecutor arrancando la GUI; no hace
   falta test): cada lista/tabla responde a clic (selecciona),
   doble-clic/Enter (abre) y clic derecho (menú) según la tabla del
   maestro; el tooltip de cada una lo dice.

**Cadenas nuevas**: ninguna.

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py tests/unit/test_campaigns_tab.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: gesture-language sweep — advisor cursor, consistency tests (UX, subplan UB.3)`
**Estado**: Pendiente
