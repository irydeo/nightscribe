# Track UX — Fase 0: arreglos y feedback (U0.1–U0.6)

> Subplanes U0.1–U0.6 del plan maestro
> [../ux-variables-campaigns.md](../ux-variables-campaigns.md). Un subplan =
> un commit. Anclas verificadas a HEAD `4df771b`; si una no coincide:
> **parar y reportar**. Lee antes `LEEME.md` (y el de
> `../variables/LEEME.md`, que sigue vigente).
> Precondición: ninguna (es la fase de entrada).

---

## U0.1 — Micro-fixes: tooltip de Tonight, `_STEP_TABS`, cadena ES→EN, registro doble del post

**Contexto a leer (solo esto)**: `nightscribe/gui/ui/tonight_tab.ui:78-84`;
`nightscribe/gui/main_window.py:69` (constante muerta), `:2118-2124`
(cadena ES) y `:3328-3335` (la gemela EN correcta), `:4999-5029`
(`_dialog_post_done`, doble registro).

**Toca**: `nightscribe/gui/ui/tonight_tab.ui`;
`nightscribe/gui/main_window.py` (tres puntos);
`tests/unit/test_projects_hub.py` (ampliar — solo añadir al final).

**Escribe exactamente esto**:

1. `ui/tonight_tab.ui:82` — el tooltip pasa a describir el comportamiento
   real (fase E: el doble-clic abre Explore):
   ```xml
   <property name="toolTip"><string>Double-click a row to explore the object</string></property>
   ```
2. `main_window.py:69` — borra la línea `_STEP_TABS = {0: "tab_plan", 1:
   "tab_process", 2: "tab_publish"}` (muerta: grep confirma una sola
   ocurrencia).
3. `main_window.py:2122` — la fuente en español
   ```python
                       f" · {self.tr('guía, no SNR — prueba antes de saturar')}"
   ```
   pasa a usar la fuente inglesa ya existente en :3332 (misma cadena →
   `lupdate` las fusiona; si quedara una entrada huérfana con la fuente
   antigua en los `.ts`, bórrala a mano tras el pipeline):
   ```python
                       f" · {self.tr('guide, not SNR — confirm with a test shot')}"
   ```
4. `main_window.py:5002-5008` — borra el primer bloque de registro (el que
   empieza con el comentario `# A4: register every written file (posts +
   tweet) in the project` y su `if self._current_project ...` con el bucle
   de `("es", "en", "tweet")`). Se queda el segundo bloque completo
   (:5014-5026, que además registra charts/resources y refresca la lista).
   El doble registro desaparece.

**Tests a añadir** (al final de `tests/unit/test_projects_hub.py`; usa el
arnés `window` del fichero):

```python
def test_post_files_registered_exactly_once(window, tmp_path, monkeypatch):
    # U0.1: _dialog_post_done registered es/en/tweet twice (two A4 blocks).
    from types import SimpleNamespace
    from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit, \
        QPushButton
    from nightscribe.core import project as proj_mod
    from nightscribe.core import post as post_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099zz", {"mag": 15.0})
    window._current_project = proj_mod.get(mw.db, p["id"])
    post_w = SimpleNamespace(
        btn_generate=QPushButton(), lbl_files=QLabel(),
        edt_folder=QLineEdit(str(tmp_path)),
        txt_es=QPlainTextEdit(), txt_en=QPlainTextEdit(),
        txt_tweet=QPlainTextEdit())
    written = {"es": tmp_path / "x_ES.md", "en": tmp_path / "x_EN.md",
               "tweet": tmp_path / "x_tweet.txt"}
    for f in written.values():
        f.write_text("x")
    monkeypatch.setattr(post_mod, "save_outputs",
                        lambda *a, **k: written)
    monkeypatch.setattr(window, "_render_object_charts",
                        lambda *a, **k: {})
    window._dialog_post_done(post_w, "SN 2099zz",
                             {"name": "SN 2099zz"}, {"es": "a", "en": "b"})
    files = [f for f in proj_mod.list_files(mw.db, p["id"])
             if f["kind"] == "post"]
    assert len(files) == 3
    window._current_project = None
```

(si `proj_mod.list_files` devuelve dicts sin clave `"kind"`, mira
`core/project.py` y usa la clave real — para y reporta si difiere.)

**Cadenas nuevas**: `Double-click a row to explore the object` → ES
«Doble-clic en una fila para explorar el objeto», EN igual a la fuente.

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q`
+ pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: micro-fixes — tonight tooltip, dead constant, ES source string, post files registered once (UX, subplan U0.1)`
**Estado**: Hecho (1096→1097)

---

## U0.2 — CTA Explore: no cerrar en fallo + detalle stale + re-clic reintenta

**Contexto a leer (solo esto)**:
`nightscribe/gui/main_window.py:1735-1761` (`_project_selected`),
`:1875-1880` (`_reset_proj_panel`), `:1979-1992` (`_clear_step_tabs`),
`:4695-4727` (`_create_project` — devuelve `None` en fallo),
`:4817-4832` (`_on_create` / `_on_continue`).

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. `_on_create` (:4817-4822) y `_on_continue` (:4824-4832) pasan a cerrar
   el diálogo solo cuando la acción tuvo éxito:
   ```python
           def _on_create(nm, fb):
               # the CTA said "create a fresh project on this object". `fb`
               # is the planner target (Tonight) or None for an ad-hoc
               # Tools-menu name. PySide6 passes only the declared args.
               # Only close the dialog when the project was really created
               # (UX, U0.2): otherwise the status-bar error would be lost.
               if self._create_project(_target(nm, fb)) is not None:
                   dlg.accept()

           def _on_continue(nm, fb):
               # the CTA said "resume the active project". When nothing
               # matches the ad-hoc name (Tools menu), create it — same
               # intent as the card's green "Continue" button. Only close
               # on success (UX, U0.2).
               fb = fb if isinstance(fb, dict) else None
               name_or_id = nm or (fb.get("id") if fb else None)
               ok = self._goto_active_project(name_or_id, fb)
               if not ok:
                   ok = self._create_project(_target(nm, fb)) is not None
               if ok:
                   dlg.accept()
   ```
2. Nuevo método junto a `_reset_proj_panel` (:1875):
   ```python
       def _clear_project_detail(self):
           # Empties the whole detail side when the selection goes away
           # (closed under the Active filter, filtered out, deleted): header,
           # context, step tabs and the panel worker. Before U0.2 the header
           # and tabs kept showing the vanished project (stale detail).
           self._current_project = None
           self._reset_proj_panel()
           self._clear_step_tabs()
           self.projects.lbl_header.setText(
               self.tr("Select a project or create one from Tonight."))
           self.projects.lbl_context.setText("—")
           self.projects.lbl_step_status.setText("")
           self.projects.lbl_advisor.setVisible(False)
   ```
3. `_project_selected` (:1735-1744): las dos ramas vacías usan el nuevo
   método:
   ```python
       def _project_selected(self):
           items = self.projects.lst_projects.selectedItems()
           if not items:
               self._clear_project_detail()
               return
           pid = items[0].data(Qt.UserRole)
           p = project.get(db, pid)
           if not p:
               self._clear_project_detail()
               return
           self._current_project = p
           ...  (resto sin cambios)
   ```
4. Re-clic = reintento: en `_connect`, tras :472
   (`p.lst_projects.itemSelectionChanged...`), añade:
   ```python
           # U0.2: itemSelectionChanged is not re-emitted for the row that
           # is already selected, so a click on it used to be a no-op. It
           # now retries the detail load (e.g. after a failed enrich).
           p.lst_projects.itemClicked.connect(self._project_reclicked)
   ```
   y el handler junto a `_project_selected`:
   ```python
       def _project_reclicked(self, item):
           # @args: item - the QListWidgetItem just clicked
           # @return: None — reloads the detail when the clicked row is the
           #          already-selected project
           if item is not None and item.data(Qt.UserRole) == \
                   (self._current_project or {}).get("id"):
               self._project_selected()
   ```

**Tests a añadir** (al final de `tests/unit/test_projects_hub.py`):

```python
def test_detail_cleared_when_selection_vanishes(window):
    # U0.2: closing a project under the Active filter must clear the detail
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099aa", {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == p["id"]:
            lst.setCurrentRow(i)
            break
    assert window._current_project is not None
    lst.clearSelection()
    window._project_selected()
    assert window._current_project is None
    assert "SN 2099aa" not in window.projects.lbl_header.text()


def test_reclick_selected_project_retries_load(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099ab", {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    item = next(lst.item(i) for i in range(lst.count())
                if lst.item(i).data(Qt.UserRole) == p["id"])
    lst.setCurrentItem(item)
    calls = []
    orig = window._render_project_header
    window._render_project_header = lambda p: calls.append(p["id"]) or orig(p)
    window._project_reclicked(item)          # same row: must reload
    assert calls == [p["id"]]
    window._render_project_header = orig
```

(`Qt` ya está importado en el fichero de tests; si no, añade
`from PySide6.QtCore import Qt` arriba — única edición permitida fuera de
los tests nuevos.)

**Cadenas nuevas**: ninguna (la cadena «Select a project or create one from
Tonight.» ya existe en `projects_tab.ui`).

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: Explore CTA stays open on failure, stale project detail cleared, re-click retries (UX, subplan U0.2)`
**Estado**: Hecho (1097→1099)

---

## U0.3 — Feedback en diálogos de campaña (fin de los silencios)

**Contexto a leer (solo esto)**:
`nightscribe/gui/campaigns_dialog.py:244-270` (`CampaignEditDialog._save`),
`:154-191` (`_attach_project` / `_detach_project`), `:346-368`
(`AddTargetDialog._save`). Patrón de tests con `QMessageBox`:
`LEEME.md` §2.

**Toca**: `nightscribe/gui/campaigns_dialog.py`;
`tests/unit/test_campaigns_dialog.py` (los tres tests que fijaban el
silencio se **reescriben** — es la única tarjeta que lo permite:
`test_save_without_name_is_refused`,
`test_add_target_without_coordinates_is_refused`,
`test_detach_with_no_members_is_a_noop`).

**Escribe exactamente esto**:

1. `CampaignEditDialog._save` (:244): el `return` silencioso pasa a:
   ```python
       def _save(self):
           # Validates the name and persists (create or update). Never
           # silent (UX-e): an empty name tells the user why nothing
           # happened.
           name = self.edt_name.text().strip()
           if not name:
               from PySide6.QtWidgets import QMessageBox
               QMessageBox.warning(
                   self, self.windowTitle(),
                   self.tr("The campaign needs a name."))
               return
           ...  (resto sin cambios)
   ```
2. `AddTargetDialog._save` (:346): los dos `return` silenciosos pasan a:
   ```python
           name = self.edt_name.text().strip()
           if not name or self._campaign_id is None:
               from PySide6.QtWidgets import QMessageBox
               QMessageBox.warning(
                   self, self.windowTitle(),
                   self.tr("The target needs a name."))
               return
           from ..core import project
           try:
               ra = float(self.edt_ra.text())
               dec = float(self.edt_dec.text())
           except ValueError:
               from PySide6.QtWidgets import QMessageBox
               QMessageBox.warning(
                   self, self.windowTitle(),
                   self.tr("RA and Dec must be numbers, in degrees."))
               return
   ```
3. `CampaignsDialog._attach_project` (:154): el `if not choices: return`
   pasa a:
   ```python
           if not choices:
               from PySide6.QtWidgets import QMessageBox
               QMessageBox.information(
                   self, self.tr("Attach project"),
                   self.tr("No active project without a campaign."))
               return
   ```
4. `CampaignsDialog._detach_project` (:174): el `if not members: return`
   pasa a:
   ```python
           if not members:
               from PySide6.QtWidgets import QMessageBox
               QMessageBox.information(
                   self, self.tr("Detach project"),
                   self.tr("This campaign has no projects yet."))
               return
   ```

**Tests a añadir / reescribir** (en `tests/unit/test_campaigns_dialog.py`):

```python
def test_save_without_name_warns(qapp, db, monkeypatch):
    # UX-e: the silent refusal becomes a warning (replaces
    # test_save_without_name_is_refused)
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.gui.campaigns_dialog import CampaignEditDialog
    seen = {}
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: seen.setdefault("warned", True))
    dlg = CampaignEditDialog(db_obj=db)
    dlg._save()
    assert seen.get("warned")
    assert campaign.list_campaigns(db) == []


def test_add_target_without_coordinates_warns(qapp, db, monkeypatch):
    # UX-e: replaces test_add_target_without_coordinates_is_refused
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import AddTargetDialog
    seen = {}
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: seen.setdefault("warned", True))
    cid = campaign.create(db, "C")
    dlg = AddTargetDialog(campaign_id=cid, db_obj=db)
    dlg.edt_name.setText("X")
    dlg._save()
    assert seen.get("warned")
    assert proj_mod.list_projects(db) == []


def test_detach_with_no_members_informs(qapp, db, monkeypatch):
    # UX-e: replaces test_detach_with_no_members_is_a_noop
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    seen = {}
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: seen.setdefault("told", True))
    campaign.create(db, "C")
    dlg = CampaignsDialog(db_obj=db)
    dlg.lst_active.setCurrentRow(0)
    dlg._detach_project()
    assert seen.get("told")
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| The campaign needs a name. | La campaña necesita un nombre. | The campaign needs a name. |
| The target needs a name. | El objetivo necesita un nombre. | The target needs a name. |
| RA and Dec must be numbers, in degrees. | AR y Dec deben ser números, en grados. | RA and Dec must be numbers, in degrees. |
| No active project without a campaign. | No hay ningún proyecto activo sin campaña. | No active project without a campaign. |
| This campaign has no projects yet. | Esta campaña aún no tiene proyectos. | This campaign has no projects yet. |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaigns_dialog.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: campaign dialogs never fail silently — validation warnings + empty-list info (UX, subplan U0.3)`
**Estado**: Pendiente

---

## U0.4 — Campañas: Delete con confirmación + editar finalizadas + selección única

**Contexto a leer (solo esto)**: `nightscribe/gui/campaigns_dialog.py:33-152`
(`CampaignsDialog` completo); `nightscribe/core/campaign.py:141-146`
(`delete`).

**Toca**: `nightscribe/gui/campaigns_dialog.py`;
`tests/unit/test_campaigns_dialog.py` (ampliar).

**Escribe exactamente esto**:

1. `CampaignsDialog.__init__`: añade el botón tras `self.btn_reopen`
   (creado en la misma fila):
   ```python
           self.btn_delete = QPushButton(self.tr("Delete…"))
   ```
   insértalo en `row` tras `btn_reopen`, conéctalo:
   ```python
           self.btn_delete.clicked.connect(self._delete_selected)
   ```
2. Selección única entre las dos listas (mata la ambigüedad de doble
   selección): en `__init__`, tras las conexiones de `_sync_buttons`:
   ```python
           self.lst_active.itemSelectionChanged.connect(
               lambda: self.lst_finished.clearSelection())
           self.lst_finished.itemSelectionChanged.connect(
               lambda: self.lst_active.clearSelection())
   ```
   (Ojo: esto dispara `_sync_buttons` dos veces; es inocuo.)
3. `_sync_buttons`: Edit y Delete valen con selección en **cualquiera** de
   las dos listas:
   ```python
       def _sync_buttons(self):
           act = self._selected_id(self.lst_active) is not None
           fin = self._selected_id(self.lst_finished) is not None
           self.btn_finish.setEnabled(act)
           self.btn_reopen.setEnabled(fin)
           self.btn_edit.setEnabled(act or fin)
           self.btn_delete.setEnabled(act or fin)
           self.btn_target.setEnabled(act)
           self.btn_attach.setEnabled(act)
           self.btn_detach.setEnabled(act)
   ```
   (los tres últimos ya existen con `act`; déjalos.)
4. `_edit_selected` lee de la lista que tenga la selección (así una
   finalizada también se edita — ya no hace falta Reabrir→Editar→Finalizar):
   ```python
       def _edit_selected(self):
           cid = self._selected_id(self.lst_active) or \
               self._selected_id(self.lst_finished)
           if cid is None:
               return
           camp = campaign.get(self._db, cid)
           if CampaignEditDialog(self, camp=camp, db_obj=self._db).exec():
               self._reload()
   ```
5. Nuevo handler:
   ```python
       def _delete_selected(self):
           # Deletes the campaign after a confirmation; its projects keep
           # going (campaign_id -> NULL, migration v7).
           cid = self._selected_id(self.lst_active) or \
               self._selected_id(self.lst_finished)
           if cid is None:
               return
           from PySide6.QtWidgets import QMessageBox
           camp = campaign.get(self._db, cid)
           ans = QMessageBox.question(
               self, self.tr("Delete campaign"),
               self.tr("Delete the campaign “%1”? Its projects are kept, "
                       "only the link is removed.").replace(
                           "%1", camp["name"]))
           if ans == QMessageBox.Yes:
               campaign.delete(self._db, cid)
               self._reload()
   ```

**Tests a añadir** (al final de `tests/unit/test_campaigns_dialog.py`):

```python
def test_delete_campaign_keeps_projects(qapp, db, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.Yes)
    cid = campaign.create(db, "Campaña X")
    proj_mod.create(db, "variable", "T CrB", {"ra_deg": 1.0, "dec_deg": 2.0},
                    campaign_id=cid)
    dlg = CampaignsDialog(db_obj=db)
    dlg.lst_active.setCurrentRow(0)
    dlg.btn_delete.click()
    assert campaign.list_campaigns(db) == []
    p = proj_mod.list_projects(db)[0]
    assert p["campaign_id"] is None            # ON DELETE SET NULL


def test_finished_campaign_is_editable(qapp, db):
    from nightscribe.gui.campaigns_dialog import CampaignsDialog
    cid = campaign.create(db, "Vieja")
    campaign.finish(db, cid)
    dlg = CampaignsDialog(db_obj=db)
    dlg.lst_finished.setCurrentRow(0)
    assert dlg.btn_edit.isEnabled()
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Delete… | Eliminar… | Delete… |
| Delete campaign | Eliminar campaña | Delete campaign |
| Delete the campaign “%1”? Its projects are kept, only the link is removed. | ¿Eliminar la campaña «%1»? Sus proyectos se conservan, solo se quita el enlace. | Delete the campaign “%1”? Its projects are kept, only the link is removed. |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_campaigns_dialog.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: campaign delete + edit finished campaigns + single selection across both lists (UX, subplan U0.4)`
**Estado**: Pendiente

---

## U0.5 — Workers de red: `ResolveWorker` + `SurveyWorker`

**Contexto a leer (solo esto)**: `nightscribe/gui/workers.py:24-80`
(patrón `TonightWorker`/`ExploreWorker`);
`nightscribe/gui/campaigns_dialog.py:273-368` (`AddTargetDialog`, con la
resolución síncrona en `_resolve`); `nightscribe/gui/main_window.py:
4183-4213` (`_fu_download_survey`, síncrono).

**Toca**: `nightscribe/gui/workers.py` (dos clases nuevas);
`nightscribe/gui/campaigns_dialog.py` (`_resolve`);
`nightscribe/gui/main_window.py` (`_fu_download_survey`);
`tests/unit/test_workers.py` (**nuevo**);
`tests/unit/test_campaigns_dialog.py` (**dos tests se reescriben** — la
resolución ya no es síncrona; ver abajo).

**Escribe exactamente esto**:

1. Al final de `nightscribe/gui/workers.py`:

```python
class ResolveWorker(QThread):
    # Resolves a target name against VSX, then SIMBAD (ADR-035, V-c), off
    # the GUI thread (UX-f) — the campaign Add-target dialog used to freeze
    # on these two network calls.
    finished = Signal(dict)     # {"vsx": dict|None, "simbad": dict|None}

    def __init__(self, name):
        super().__init__()
        self._name = name

    def run(self):
        from ..core.sources import simbad, vsx
        out = {"vsx": None, "simbad": None}
        try:
            out["vsx"] = vsx.lookup(self._name)
            if not out["vsx"]:
                out["simbad"] = simbad.query_id(self._name)
        except Exception as err:      # never crash the dialog on network
            logger.warning("resolve worker failed: %s", err)
        self.finished.emit(out)


class SurveyWorker(QThread):
    # Downloads the ALeRCE/ZTF context points for one position, off the GUI
    # thread (UX-f) — the Follow-up survey button used to freeze on it.
    finished = Signal(list)     # photometry point dicts ([] on failure)

    def __init__(self, ra_deg, dec_deg):
        super().__init__()
        self._ra, self._dec = ra_deg, dec_deg

    def run(self):
        from ..core.sources import surveys
        try:
            self.finished.emit(surveys.fetch_points(self._ra, self._dec)
                               or [])
        except Exception as err:
            logger.warning("survey worker failed: %s", err)
            self.finished.emit([])
```

2. `campaigns_dialog.py` — `AddTargetDialog`: en `__init__` añade
   `self._resolve_worker = None`; el cuerpo de `_resolve` (:309-344) cambia a
   lanzar el worker (la resolución VSX→SIMBAD pasa a `_resolve_done`):

```python
    def _resolve(self):
        # Kicks the VSX->SIMBAD chain off the GUI thread (UX-f); the form
        # stays editable while it resolves.
        name = self.edt_name.text().strip()
        if not name or self._resolve_worker is not None:
            return
        from ..gui.workers import ResolveWorker
        self.btn_resolve.setEnabled(False)
        self.lbl_resolved.setText(self.tr("Resolving…"))
        self._resolve_worker = ResolveWorker(name)
        self._resolve_worker.finished.connect(self._resolve_done)
        self._resolve_worker.finished.connect(
            self._resolve_worker.deleteLater)
        self._resolve_worker.start()

    def _resolve_done(self, result):
        # Fills the form from the worker payload; leaves it editable always.
        from ..core import coords
        self._resolve_worker = None
        self.btn_resolve.setEnabled(True)
        v = result.get("vsx")
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
        ident = result.get("simbad")
        if ident:
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
```

   (`from ..core.sources import simbad, vsx` deja de importarse en
   `_resolve`; el import viejo se borra con el cuerpo antiguo.)

3. `main_window.py:_fu_download_survey` (:4183-4213): la llamada síncrona
   `pts = surveys.fetch_points(ra, dec)` (:4196) y todo lo que sigue pasa a
   worker + callback:

```python
    def _fu_download_survey(self, pid):
        # Pulls the survey context points (V-f) into photometry_points as
        # source="survey:ztf". The download runs in a SurveyWorker (UX-f):
        # the GUI never blocks on the network. Idempotent: a point with the
        # same mjd+filter+source is not duplicated.
        from ..core import followup as fu
        p = project.get(db, pid)
        ctx = p.get("context") or {}
        ra, dec = ctx.get("ra_deg"), ctx.get("dec_deg")
        if ra is None or dec is None:
            self.statusBar().showMessage(
                self.tr("The project has no coordinates"), 6000)
            return
        from .workers import SurveyWorker
        btn = self._project_widgets.get("fu_survey")
        if btn is not None:
            btn.setEnabled(False)
        w = SurveyWorker(ra, dec)
        w.finished.connect(lambda pts: self._fu_survey_done(pid, pts))
        self._keep(w)

    def _fu_survey_done(self, pid, pts):
        # Merges the worker's survey points and rebuilds the tab in place.
        from ..core import followup as fu
        btn = self._project_widgets.get("fu_survey")
        if btn is not None:
            btn.setEnabled(True)
        if not pts:
            self.statusBar().showMessage(
                self.tr("No survey data for this position"), 6000)
            return
        existing = {(q["mjd"], q["filter"]) for q in fu.list_points(db, pid)
                    if (q.get("source") or "").startswith("survey:")}
        n = 0
        for pt in pts:
            if (pt["mjd"], pt["filter"]) in existing:
                continue
            fu.add_point(db, pid, pt["mjd"], pt["filter"], pt["mag"],
                         err=pt.get("err"), source=pt["source"])
            n += 1
        self.statusBar().showMessage(
            self.tr("Added %1 survey points").replace("%1", str(n)), 8000)
        self._build_step_tabs(project.get(db, pid))
```

   Ojo: para que el botón se pueda (des)habilitar hay que registrarlo al
   crearlo: en `_build_followup_tab` (:3515-3522, donde se crea el botón
   «Download survey photometry…»), tras crear el botón añade
   `self._project_widgets["fu_survey"] = btn` (usa el nombre real de la
   variable local; verifica con grep cómo se llama — si no existe
   `_project_widgets`, mira cómo se registran otros widgets del follow-up,
   p. ej. `fu_notes`, y sigue ese patrón).

**Tests a añadir** — `tests/unit/test_workers.py` (**nuevo**; cabecera GPL;
«Unit tests: background workers (UX, U0.5)»; patrón QSignalSpy del
`LEEME.md` §2):

```python
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                     # noqa: E402
from PySide6.QtCore import QSignalSpy             # noqa: E402
from PySide6.QtWidgets import QApplication        # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_resolve_worker_vsx_hit(qapp, monkeypatch):
    from nightscribe.core.sources import vsx
    from nightscribe.gui.workers import ResolveWorker
    monkeypatch.setattr(vsx, "lookup",
                        lambda name: {"name": "T CrB", "period_d": 227.55})
    w = ResolveWorker("T CrB")
    spy = QSignalSpy(w.finished)
    w.run()                                       # same thread: synchronous
    assert spy.count() == 1
    assert spy.at(0)[0]["vsx"]["period_d"] == 227.55


def test_resolve_worker_falls_back_to_simbad(qapp, monkeypatch):
    from nightscribe.core.sources import simbad, vsx
    from nightscribe.gui.workers import ResolveWorker
    monkeypatch.setattr(vsx, "lookup", lambda name: None)
    monkeypatch.setattr(simbad, "query_id",
                        lambda name: {"ra": "01h02m03s", "otype": "Star"})
    w = ResolveWorker("WeSb 1")
    spy = QSignalSpy(w.finished)
    w.run()
    assert spy.at(0)[0]["vsx"] is None
    assert spy.at(0)[0]["simbad"]["otype"] == "Star"


def test_resolve_worker_never_raises(qapp, monkeypatch):
    from nightscribe.core.sources import vsx
    from nightscribe.gui.workers import ResolveWorker

    def boom(_name):
        raise OSError("network down")
    monkeypatch.setattr(vsx, "lookup", boom)
    w = ResolveWorker("X")
    spy = QSignalSpy(w.finished)
    w.run()
    assert spy.at(0)[0] == {"vsx": None, "simbad": None}


def test_survey_worker_payload(qapp, monkeypatch):
    from nightscribe.core.sources import surveys
    from nightscribe.gui.workers import SurveyWorker
    pts = [{"mjd": 60100.0, "filter": "g", "mag": 15.1, "err": 0.02,
            "source": "survey:ztf"}]
    monkeypatch.setattr(surveys, "fetch_points", lambda ra, dec: pts)
    w = SurveyWorker(15.2, 55.0)
    spy = QSignalSpy(w.finished)
    w.run()
    assert spy.at(0)[0][0]["source"] == "survey:ztf"


def test_survey_worker_failure_is_empty(qapp, monkeypatch):
    from nightscribe.core.sources import surveys
    from nightscribe.gui.workers import SurveyWorker

    def boom(_ra, _dec):
        raise OSError("network down")
    monkeypatch.setattr(surveys, "fetch_points", boom)
    w = SurveyWorker(0.0, 0.0)
    spy = QSignalSpy(w.finished)
    w.run()
    assert spy.at(0)[0] == []
```

**Cadenas nuevas**: `Resolving…` → ES «Resolviendo…», EN «Resolving…».

**Tests que se reescriben** (en `tests/unit/test_campaigns_dialog.py`;
mismo nombre, misma cobertura — la resolución ya no es síncrona, así que
los tests alimentan el payload directamente a `_resolve_done`; el worker
tiene sus propios tests arriba):

```python
def test_add_target_resolves_vsx_and_creates_project(qapp, db):
    # U0.5: resolution runs in a ResolveWorker; tests feed the payload
    # straight into _resolve_done
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import AddTargetDialog
    cid = campaign.create(db, "Campaña T CrB")
    dlg = AddTargetDialog(campaign_id=cid, db_obj=db)
    dlg.edt_name.setText("T CrB")
    dlg._resolve_done({"vsx": {
        "name": "T CrB", "auid": "000-BBW-825", "ra_deg": 239.87567,
        "dec_deg": 25.92017, "var_type": "NR+ELL", "period_d": 227.5528,
        "epoch_mjd": 55828.4, "max": 2.0, "min": 10.8, "max_band": "V",
        "min_band": "V", "spectral": "M3III+WD", "constellation": "CrB"},
        "simbad": None})
    assert dlg.edt_ra.text().startswith("239.875")
    dlg._save()
    p = proj_mod.list_projects(db, campaign_id=cid)[0]
    assert p["kind"] == "variable" and p["object_name"] == "T CrB"
    assert p["context"]["variable"]["period_d"] == 227.5528


def test_add_target_manual_when_nothing_knows_it(qapp, db):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui.campaigns_dialog import AddTargetDialog
    cid = campaign.create(db, "Campaña WeSb 1")
    dlg = AddTargetDialog(campaign_id=cid, db_obj=db)
    dlg.edt_name.setText("WeSb 1")
    dlg._resolve_done({"vsx": None, "simbad": None})
    assert "Not found" in dlg.lbl_resolved.text()
    dlg.edt_ra.setText("15.2254")
    dlg.edt_dec.setText("55.0667")
    dlg.edt_mag.setText("15.0")
    dlg._save()
    p = proj_mod.list_projects(db, campaign_id=cid)[0]
    assert p["context"]["ra_deg"] == 15.2254
    assert p["context"]["mag"] == 15.0
```

(borran las versiones viejas con `monkeypatch` sobre `vsx.lookup` /
`simbad.query_id` — ya no aplican a un método síncrono que no existe.)

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_workers.py tests/unit/test_campaigns_dialog.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: ResolveWorker + SurveyWorker — no network on the GUI thread (UX, subplan U0.5)`
**Estado**: Pendiente

---

## U0.6 — Settings: `event_mag_threshold` + persistir el filtro de campaña del hub

**Contexto a leer (solo esto)**:
`nightscribe/gui/ui/settings_dialog.ui:313-340` (`grp_session`: la fila
`row_sncadence` y su `lblH_sncadence` — el molde de fila+ayuda);
`nightscribe/gui/main_window.py:566` (carga `spn_sn_cadence`) y `:631`
(guarda); `:1653-1666` (`_rebuild_campaign_filter`) y `:1680, 1686-1688`
(uso y persistencia de filtros del hub); `nightscribe/config.py:60-69`
(DEFAULTS; ya existe `"event_mag_threshold": 0.5`).

**Toca**: `nightscribe/gui/ui/settings_dialog.ui`;
`nightscribe/gui/main_window.py` (tres puntos);
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. `settings_dialog.ui`: en `grp_session` (tras el `lblH_sncadence`,
   :333-335), añade la fila y su ayuda (molde exacto de las de arriba):

```xml
          <item>
           <layout class="QHBoxLayout" name="row_eventmag">
            <item><widget class="QLabel" name="lbl_event_mag"><property name="text"><string>Event threshold (mag):</string></property><property name="minimumSize"><size><width>150</width><height>0</height></size></property></widget></item>
            <item><widget class="QDoubleSpinBox" name="spn_event_mag"><property name="decimals"><number>1</number></property><property name="minimum"><double>0.2</double></property><property name="maximum"><double>2.0</double></property><property name="singleStep"><double>0.1</double></property></widget></item>
            <item><spacer name="hsp_eventmag"><property name="orientation"><enum>Qt::Horizontal</enum></property><property name="sizeHint" stdset="0"><size><width>40</width><height>20</height></size></property></spacer></item>
           </layout>
          </item>
          <item><widget class="QLabel" name="lblH_eventmag"><property name="text"><string>Brightness jump (in magnitudes) from which a variable/SN project raises the event advisor</string></property><property name="wordWrap"><bool>true</bool></property><property name="alignment"><set>Qt::AlignLeft|Qt::AlignTop</set></property></widget></item>
```

2. `main_window.py`:
   a. Carga (:566, tras la línea de `spn_sn_cadence`):
      ```python
              dlg.spn_event_mag.setValue(
                  float(config.get("event_mag_threshold", 0.5)))
      ```
   b. Guarda (:631, tras el `config.set("sn_cadence_days", ...)`):
      ```python
              config.set("event_mag_threshold", dlg.spn_event_mag.value())
      ```
   c. Persiste el filtro de campaña: en `on_refresh_projects` (:1686-1688),
      tras los tres `config.set` existentes:
      ```python
          config.set("projects_filter_campaign", camp_id or "")
      ```
      y en `_rebuild_campaign_filter` (:1653-1666) restaura una sola vez por
      sesión (el combo se repuebla en cada refresh — LEEME §3.3):
      ```python
          idx = cmb.findData(current)
          if idx < 0 and not getattr(self, "_campaign_filter_restored", False):
              # restore the persisted campaign filter once per session (U0.6)
              self._campaign_filter_restored = True
              saved = config.get("projects_filter_campaign", "")
              if saved != "":
                  idx = cmb.findData(saved)
          cmb.setCurrentIndex(idx if idx >= 0 else 0)
      ```
      (sustituye a las dos líneas `idx = cmb.findData(current)` /
      `cmb.setCurrentIndex(...)` existentes).

**Tests a añadir** (al final de `tests/unit/test_projects_hub.py`):

```python
def test_campaign_filter_persists_in_config(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    from nightscribe.config import config
    cid = camp_mod.create(mw.db, "Campaña persist")
    window.on_refresh_projects()
    cmb = window.projects.cmb_campaign
    idx = cmb.findData(cid)
    assert idx >= 0
    cmb.setCurrentIndex(idx)                 # fires on_refresh_projects
    assert config.get("projects_filter_campaign") == cid
    cmb.setCurrentIndex(0)
    assert config.get("projects_filter_campaign") == ""
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Event threshold (mag): | Umbral de evento (mag): | Event threshold (mag): |
| Brightness jump (in magnitudes) from which a variable/SN project raises the event advisor | Salto de brillo (en magnitudes) a partir del cual un proyecto de variable/SN activa el asesor de eventos | Brightness jump (in magnitudes) from which a variable/SN project raises the event advisor |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py tests/unit/test_config.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui/Config: event_mag_threshold in Settings + persisted campaign filter (UX, subplan U0.6)`
**Estado**: Pendiente
