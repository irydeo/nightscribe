############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Visits panel: the core of the Analysis tab (ADR-045)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The visits manager (ADR-045): every day you work the object is a visit,
and every resource (FITS plates, imported photometry, ephemeris, MPC
reports, charts) hangs from one.

The split that keeps the tab light and the work roomy (2026-09-24 review):
the Analysis tab carries the OVERVIEW (the rich-rows list, the count, the
single primary "New visit" button); the visit's own work (resources,
measurements, notes) lives in the VisitWindow, a non-modal dialog opened
by the primary action and by double-clicking a row.

Rules of the redesign, honoured here:

* One primary entry point: "New visit". No duplicated buttons.
* Nothing attaches without a visit: the attach action lives inside the
  visit's window.
* The file on disk is never touched: removing a resource only unlinks it.

All CRUD goes through core/followup.py (visits, points) and
core/project.py (the file registry). The host wires two callbacks:
open_in_editor(path, session_id) for FITS rows and on_change() to refresh
the tab's reactive blocks (curve, cadence, summary) after data changes.
"""

import datetime
import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QTextEdit, QVBoxLayout, QWidget)

from .passive_wheel import PassiveDoubleSpinBox, PassiveList

logger = logging.getLogger("nightscribe.gui.visits_panel")

# Kinds whose visits keep photometry points (the light-curve kinds);
# everyone gets resources and notes. NEO/PCCP visits carry the night's
# astrometry: the MPC paste/validate/save block (ADR-045 form A: the
# measurements are the visit's product, so the block lives in the
# visit's window and nowhere else).
CURVE_KINDS = ("sn", "hads", "variable")
MPC_KINDS = ("neo", "pccp")

_FILTERS = ["Clear", "V", "R", "B", "I", "NIR"]

# extension -> registry kind for a generic attachment
_KIND_BY_SUFFIX = {
    ".fits": "fits", ".fit": "fits", ".fts": "fits", ".fz": "fits",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".mp4": "image",
    ".csv": "report", ".eff": "report", ".txt": "report",
    ".json": "ephemeris", ".eph": "ephemeris",
}


def _kind_for(path):
    # @args: path - file path
    # @return: the registry kind guessed from the extension
    return _KIND_BY_SUFFIX.get(Path(path).suffix.lower(), "file")


class VisitsPanel(QWidget):
    # The in-tab visits overview: the list, the count and the two entry
    # points (New visit / Open visit…). The per-visit work lives in the
    # VisitWindow (opened, never crammed inline).
    #
    # @args: db - the Database, lang - "es" | "en",
    #        open_in_editor - callable(path, session_id) opening a FITS in
    #        the UFE (None hides the window's editor action),
    #        on_change - callable() after any data change (the host
    #        refreshes the curve/cadence/summary),
    #        curve_kind - True keeps the measurement block in the window

    def __init__(self, db, lang="es", open_in_editor=None, on_change=None,
                 curve_kind=True, kind=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._lang = lang
        self._open_in_editor = open_in_editor
        self._on_change = on_change
        # the project's kind drives what a visit carries: light-curve
        # kinds get the measurements block, MPC kinds the astrometry one
        self._kind = kind if kind is not None else (
            "sn" if curve_kind else "neo")
        self._pid = None              # current project id
        self._win = None              # the open VisitWindow (or None)
        self._build_ui()

    # ------------------------------------------------------------ build

    def _build_ui(self):
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.btn_new = QPushButton(self.tr("New visit"))
        self.btn_new.setToolTip(self.tr(
            "Every day you work the object is a visit: it opens in its "
            "own window, ready for its images, reports and measurements"))
        self.btn_new.clicked.connect(self._on_new_visit)
        top.addWidget(self.btn_new)
        self.btn_open = QPushButton(self.tr("Open visit…"))
        self.btn_open.setObjectName("vp_btn_open_visit")
        self.btn_open.setToolTip(self.tr(
            "Open the selected visit's window (double-click works too)"))
        self.btn_open.clicked.connect(self._on_open_selected)
        top.addWidget(self.btn_open)
        self.lbl_count = QLabel("")
        top.addWidget(self.lbl_count)
        top.addStretch(1)
        lay.addLayout(top)

        self.lbl_empty = QLabel(self.tr(
            "No visits yet. Each night you work the object starts one: "
            "plates, reports and measurements attach to it."))
        self.lbl_empty.setWordWrap(True)
        lay.addWidget(self.lbl_empty)

        self.lst = PassiveList()
        self.lst.setToolTip(self.tr(
            "The project's visits, newest first; double-click opens one"))
        self.lst.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.lst.itemSelectionChanged.connect(self._on_select)
        lay.addWidget(self.lst, 1)
        self._show_empty(True)

    # ------------------------------------------------------------ state

    def set_project(self, project_id, keep_selection=True):
        # @args: project_id - the project to manage, keep_selection - try
        #        to keep the selected visit across a refresh
        prev = self.current_session_id() if keep_selection else None
        if self._pid != project_id:
            self.close_visit_window()      # the window belongs to a visit
        self._pid = project_id
        self.refresh()
        if prev is not None:
            for row in range(self.lst.count()):
                if self.lst.item(row).data(Qt.UserRole) == prev:
                    self.lst.setCurrentRow(row)
                    return

    def current_session_id(self):
        # @return: the selected visit id, or None (the host attaches
        #          reports to it when set)
        items = self.lst.selectedItems()
        return items[0].data(Qt.UserRole) if items else None

    def refresh(self):
        # Refills the visits list from the database (newest first).
        from ...core import followup as fu
        sel = self.current_session_id()
        self.lst.clear()
        sessions = fu.list_sessions(self._db, self._pid) \
            if self._pid is not None else []
        for s in sessions:
            n_img = len(fu.list_images(self._db, s["id"]))
            pts = fu.list_points(self._db, self._pid)
            n_pts = sum(1 for p in pts if p.get("session_id") == s["id"])
            chips = []
            if n_img:
                chips.append(self.tr("{0} img").format(n_img))
            if n_pts:
                chips.append(self.tr("{0} mag").format(n_pts))
            tag = ("  ·  " + " · ".join(chips)) if chips else ""
            notes = f"  ·  {s['notes'][:24]}…" if s["notes"] else ""
            pin = "📌 " if s.get("pinned") else ""
            item = QListWidgetItem(f"{pin}{s['obs_date']}{tag}{notes}")
            item.setData(Qt.UserRole, s["id"])
            self.lst.addItem(item)
        n = len(sessions)
        self.lbl_count.setText(self.tr("{0} visits").format(n) if n else "")
        self._show_empty(n == 0)
        if n and sel is not None:
            for row in range(self.lst.count()):
                if self.lst.item(row).data(Qt.UserRole) == sel:
                    self.lst.setCurrentRow(row)
                    break
        self.btn_open.setEnabled(self.current_session_id() is not None)

    def _show_empty(self, flag):
        # @args: flag - no visits exist
        self.lbl_empty.setVisible(flag)
        self.lst.setVisible(not flag)
        self.btn_open.setVisible(not flag)

    def _on_select(self):
        self.btn_open.setEnabled(self.current_session_id() is not None)

    # ------------------------------------------------- the visit window

    def _on_new_visit(self):
        # The single entry point: create today's visit and open its window
        # right away (the whole point of the visit is what hangs from it).
        from ...core import followup as fu
        if self._pid is None:
            return
        sid = fu.create_session(self._db, self._pid)
        self.refresh()
        self.lst.setCurrentRow(0)   # newest first
        self.open_visit(sid)

    def _on_open_selected(self):
        sid = self.current_session_id()
        if sid is not None:
            self.open_visit(sid)

    def _on_row_double_clicked(self, item):
        self.open_visit(item.data(Qt.UserRole))

    def open_visit(self, session_id):
        # The visit's work window: one at a time, non-modal, so the page
        # never blocks and the headless suite can drive it.
        # @args: session_id - the visit to open
        # @return: the VisitWindow
        self.close_visit_window()
        self._win = VisitWindow(self._db, self._pid, session_id,
                                lang=self._lang,
                                kind=self._kind,
                                open_in_editor=self._open_in_editor,
                                data_changed=self._from_window_changed,
                                parent=self)
        # WA_DeleteOnClose: the C++ object dies when the user closes the
        # window, so the wrapper must be dropped on the spot — keeping it
        # makes the next open_visit call close() on a deleted object
        # (the shiboken RuntimeError trap)
        self._win.destroyed.connect(self._on_window_gone)
        self._win.show()
        return self._win

    def _on_window_gone(self):
        # The visit window died (the user closed it): forget it at once.
        self._win = None

    def close_visit_window(self):
        # Closes the open visit window, if any (project switch, delete).
        # The RuntimeError guard covers the in-between state where the
        # deletion is queued but not yet delivered.
        if self._win is not None:
            try:
                self._win.close()
            except RuntimeError:
                pass            # already deleted (WA_DeleteOnClose)
            self._win = None

    def _from_window_changed(self):
        # The window edited its visit: the list's counts and the host's
        # reactive blocks follow.
        self.refresh()
        self._emit_change()

    def _emit_change(self):
        # Tells the host the data changed (curve, cadence, summary).
        if self._on_change is not None:
            self._on_change()


class VisitWindow(QDialog):
    # The visit's own window (non-modal, shown with show()): its
    # resources, its measurements (light-curve kinds) and its notes.
    # Nothing here is modal and nothing blocks the main window.
    #
    # @args: db - the Database, pid - project id, sid - the visit's id,
    #        lang - "es" | "en", curve_kind - keep the measurements block,
    #        open_in_editor - callable(path, session_id) for FITS rows,
    #        data_changed - callable() after any edit (the panel refreshes
    #        and notifies the host), parent - the panel

    def __init__(self, db, pid, sid, lang="es", curve_kind=None,
                 kind=None, open_in_editor=None, data_changed=None,
                 parent=None):
        super().__init__(parent)
        self._db = db
        self._pid = pid
        self._sid = sid
        self._lang = lang
        self._kind = kind if kind is not None else (
            "sn" if (curve_kind or curve_kind is None) else "neo")
        self._curve_kind = self._kind in CURVE_KINDS
        self._mpc_kind = self._kind in MPC_KINDS
        self._open_in_editor = open_in_editor
        self._data_changed = data_changed
        self.setWindowTitle(self.tr("Visit"))
        self.resize(640, 520)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._build_ui()

    # ------------------------------------------------------------ build

    def _build_ui(self):
        from ...core import followup as fu
        s = fu.get_session(self._db, self._sid)
        if s is None:
            self.close()
            return
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        # the visit's date is its name in the list — editable in place
        # (ADR-045 review: «pin or edit a visit's name»)
        self._date_ed = QLineEdit(s["obs_date"] or "")
        self._date_ed.setObjectName("vp_visit_date")
        self._date_ed.setPlaceholderText("YYYY-MM-DD")
        self._date_ed.setToolTip(self.tr(
            "The visit's date (its name in the list). Points already "
            "saved to it keep their own MJD"))
        self._date_ed.setMaximumWidth(150)
        f = self._date_ed.font()
        f.setBold(True)
        self._date_ed.setFont(f)
        self._date_ed.editingFinished.connect(self._on_date_edited)
        head.addWidget(self._date_ed, 1)
        # an explicit save gesture: an invisible save-on-focus-out alone
        # leaves the observer guessing whether the edit took
        self.btn_save_date = QPushButton(self.tr("Save date"))
        self.btn_save_date.setObjectName("vp_btn_save_date")
        self.btn_save_date.setToolTip(self.tr(
            "Save the visit's date (the date is its name in the list)"))
        self.btn_save_date.setEnabled(False)   # arms on a dirty field
        self.btn_save_date.clicked.connect(self._on_save_date_clicked)
        self._date_ed.textChanged.connect(self._on_date_dirty)
        head.addWidget(self.btn_save_date)
        self.btn_pin = QPushButton("📌")
        self.btn_pin.setObjectName("vp_btn_pin")
        self.btn_pin.setCheckable(True)
        self.btn_pin.setChecked(bool(s.get("pinned")))
        self.btn_pin.setToolTip(self.tr(
            "Pin the visit: it floats to the top of the list"))
        self.btn_pin.toggled.connect(self._on_pin_toggled)
        head.addWidget(self.btn_pin)
        btn_del = QPushButton(self.tr("Delete visit…"))
        btn_del.setObjectName("vp_btn_delete")
        btn_del.clicked.connect(self._on_delete_visit)
        head.addWidget(btn_del)
        lay.addLayout(head)

        # ---- resources
        grp_res = QGroupBox(self.tr("Resources"))
        grp_res.setLayout(QVBoxLayout())
        res_row = QHBoxLayout()
        btn_add = QPushButton(self.tr("Attach files…"))
        btn_add.setObjectName("vp_btn_attach")
        btn_add.setToolTip(self.tr(
            "FITS plates, imported photometry, ephemeris, reports… "
            "registered to this visit (the file on disk is linked, "
            "never copied or moved)"))
        btn_add.clicked.connect(self._on_attach)
        res_row.addWidget(btn_add)
        btn_open = QPushButton(self.tr("Open"))
        btn_open.setObjectName("vp_btn_open")
        btn_open.setToolTip(self.tr(
            "Plates open in the FITS editor; everything else opens with "
            "the system"))
        btn_open.clicked.connect(self._on_open_resource)
        res_row.addWidget(btn_open)
        btn_rm = QPushButton(self.tr("Remove from visit"))
        btn_rm.setObjectName("vp_btn_remove")
        btn_rm.setToolTip(self.tr(
            "Unlink the selected resource (the file on disk is never "
            "touched)"))
        btn_rm.clicked.connect(self._on_remove_resource)
        res_row.addWidget(btn_rm)
        res_row.addStretch(1)
        grp_res.layout().addLayout(res_row)
        self.lst_res = PassiveList()
        self.lst_res.setObjectName("vp_resources")
        self.lst_res.itemDoubleClicked.connect(
            lambda _it: self._on_open_resource())
        grp_res.layout().addWidget(self.lst_res)
        lay.addWidget(grp_res, 1)
        self._populate_resources()

        # ---- measurements (light-curve kinds)
        if self._curve_kind:
            self._build_measurements_block(lay, s)

        # ---- the night's astrometry (NEO/PCCP; ADR-045 form A)
        if self._mpc_kind:
            self._build_mpc_block(lay)

        # ---- notes
        snotes = QTextEdit()
        snotes.setObjectName("vp_notes")
        snotes.setPlaceholderText(self.tr("Night notes (seeing, clouds…)"))
        snotes.setText(s["notes"])
        snotes.textChanged.connect(self._on_notes_changed)
        lay.addWidget(snotes)
        self._notes = snotes

    # ---------------------------------------------------------- visit

    def _stored_date(self):
        # @return: the visit's date as persisted (or "")
        from ...core import followup as fu
        s = fu.get_session(self._db, self._sid)
        return (s or {}).get("obs_date") or ""

    def _on_date_dirty(self, _text):
        # The save gesture arms exactly while the field differs from the
        # stored date.
        self.btn_save_date.setEnabled(
            self._date_ed.text().strip() != self._stored_date())

    def _on_save_date_clicked(self):
        # The explicit save gesture shares the validation path.
        self._save_date()

    def _on_date_edited(self):
        # Enter/focus-out saves too — the visible button is the same path.
        self._save_date()

    def _save_date(self):
        # The visit's date is its name in the list: validate, save, and
        # let the panel re-sort. An invalid date reverts to the stored
        # one with the text selected for a retry (never a modal).
        from ...core import followup as fu
        txt = self._date_ed.text().strip()
        ok = False
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y/%m/%d"):
            try:
                datetime.datetime.strptime(txt, fmt)
                ok = True
                break
            except ValueError:
                pass
        if not ok or not txt:
            self._date_ed.blockSignals(True)
            self._date_ed.setText(self._stored_date())
            self._date_ed.selectAll()
            self._date_ed.blockSignals(False)
            self.btn_save_date.setEnabled(False)
            return
        fu.update_session_date(self._db, self._sid, txt)
        self.btn_save_date.setEnabled(False)   # clean again
        self._emit_change()

    def _on_pin_toggled(self, checked):
        # Pin/unpin: the visit floats to the top of the panel's list.
        from ...core import followup as fu
        fu.set_session_pinned(self._db, self._sid, checked)
        self._emit_change()

    def _on_delete_visit(self):
        # Confirmation first; points and files keep living in the project,
        # unlinked (the DB's ON DELETE SET NULL), and the dialog says so.
        from ...core import followup as fu
        ans = QMessageBox.question(
            self, self.tr("Delete visit"),
            self.tr("Delete this visit? Its measurements and files are "
                    "kept, unlinked from it."))
        if ans != QMessageBox.Yes:
            return
        fu.delete_session(self._db, self._sid)
        self._emit_change()
        self.close()

    # ------------------------------------------------------- resources

    def _populate_resources(self):
        # Refills the visit's resource list from the registry.
        from ...core import project as proj_mod
        self.lst_res.clear()
        for f in proj_mod.files_for_session(self._db, self._sid):
            meta = f.get("meta") or {}
            bits = [f"[{f['kind']}]", Path(f["path"]).name]
            if meta.get("filter"):
                bits.append(f"({meta['filter']})")
            if meta.get("date_obs"):
                bits.append(f"({meta['date_obs']})")
            item = QListWidgetItem(" ".join(bits))
            item.setToolTip(f["path"])
            item.setData(Qt.UserRole, f["id"])
            self.lst_res.addItem(item)

    def _on_attach(self):
        # File picker (multi) -> per-FITS editable metadata confirmation
        # -> registered to THIS visit. The rule of the redesign: nothing
        # attaches without a visit, and this action only exists inside
        # one.
        from ...core import fits_meta, project as proj_mod
        paths, _sel = QFileDialog.getOpenFileNames(
            self, self.tr("Attach files to the visit"), "",
            self.tr("All files (*)"))
        if not paths:
            return
        for path in paths:
            kind = _kind_for(path)
            meta = {}
            if kind == "fits":
                meta = self._ask_fits_meta(path)
                if meta is None:
                    continue        # the observer cancelled this one
            proj_mod.add_file(self._db, self._pid, path, kind,
                              session_id=self._sid, meta=meta)
        self._populate_resources()
        self._emit_change()

    def _ask_fits_meta(self, path):
        # The FITS confirmation dialog, pre-filled from the header (a
        # misnamed filter breaks the light-curve split, so it stays
        # editable). @return: the meta dict, or None when cancelled
        try:
            meta = fits_meta.read_meta(path)
        except Exception:
            meta = {}
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("FITS details"))
        dlg.setLayout(QFormLayout())
        lbl = QLabel(Path(path).name)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dlg.layout().addRow(self.tr("File:"), lbl)
        cmb_f = QComboBox()
        cmb_f.setObjectName("vp_img_filter")
        cmb_f.setEditable(True)
        cmb_f.addItems(_FILTERS)
        cmb_f.setCurrentText((meta.get("filter") or "Clear").strip()
                             or "Clear")
        dlg.layout().addRow(self.tr("Filter:"), cmb_f)
        edt_date = QLineEdit(str(meta.get("date_obs") or ""))
        edt_date.setObjectName("vp_img_date")
        dlg.layout().addRow(self.tr("Date:"), edt_date)
        edt_exp = QLineEdit("" if meta.get("exptime_s") in (None, "")
                            else str(meta["exptime_s"]))
        edt_exp.setObjectName("vp_img_exptime")
        dlg.layout().addRow(self.tr("Exptime:"), edt_exp)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        dlg.layout().addWidget(box)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.Accepted:
            return None
        exp = edt_exp.text().strip()
        try:
            exp = float(exp) if exp else None
        except ValueError:
            exp = None
        return {"filter": cmb_f.currentText().strip() or "Clear",
                "date_obs": edt_date.text().strip() or None,
                "exptime_s": exp}

    def _selected_resource(self):
        # @return: the selected registry row dict, or None
        from ...core import project as proj_mod
        items = self.lst_res.selectedItems()
        if not items:
            return None
        fid = items[0].data(Qt.UserRole)
        row = next((f for f in proj_mod.list_files(self._db, self._pid)
                    if f["id"] == fid), None)
        return row

    def _on_open_resource(self):
        # Plates go to the FITS editor (the host's callback carries the
        # visit so what is saved there lands back here); the rest open
        # with the system.
        f = self._selected_resource()
        if f is None:
            return
        if f["kind"] == "fits" and self._open_in_editor is not None:
            self._open_in_editor(f["path"], self._sid)
            return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(f["path"]))

    def _on_remove_resource(self):
        # Unlink only; the file on disk is never touched.
        from ...core import project as proj_mod
        f = self._selected_resource()
        if f is None:
            return
        proj_mod.delete_file(self._db, f["id"])
        self._populate_resources()
        self._emit_change()

    # ----------------------------------------------------- measurements

    def _build_measurements_block(self, lay, s):
        # Quick magnitude entry + the visit's points with a remove
        # action. The point's MJD comes from the visit's date.
        grp = QGroupBox(self.tr("Measurements"))
        grp.setLayout(QVBoxLayout())
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Mag:")))
        self.spn_mag = PassiveDoubleSpinBox()
        self.spn_mag.setRange(-5.0, 30.0)
        self.spn_mag.setDecimals(3)
        self.spn_mag.setValue(16.0)
        row.addWidget(self.spn_mag)
        row.addWidget(QLabel(self.tr("Err:")))
        self.spn_err = PassiveDoubleSpinBox()
        self.spn_err.setRange(0.0, 9.0)
        self.spn_err.setDecimals(3)
        self.spn_err.setValue(0.0)
        self.spn_err.setSpecialValueText("—")
        row.addWidget(self.spn_err)
        row.addWidget(QLabel(self.tr("Filter:")))
        self.cmb_filt = QComboBox()
        self.cmb_filt.setEditable(True)
        self.cmb_filt.addItems(_FILTERS)
        row.addWidget(self.cmb_filt)
        btn_add = QPushButton(self.tr("Add"))
        btn_add.setObjectName("vp_btn_add_meas")
        btn_add.clicked.connect(self._on_add_measurement)
        row.addWidget(btn_add)
        btn_del = QPushButton(self.tr("Delete point"))
        btn_del.setObjectName("vp_btn_del_meas")
        btn_del.clicked.connect(self._on_delete_measurement)
        row.addWidget(btn_del)
        row.addStretch(1)
        grp.layout().addLayout(row)
        self.lst_meas = PassiveList()
        self.lst_meas.setObjectName("vp_measurements")
        grp.layout().addWidget(self.lst_meas)
        lay.addWidget(grp, 1)
        self._populate_measurements()

    def _populate_measurements(self):
        from ...core import followup as fu
        self.lst_meas.clear()
        for pt in fu.list_points(self._db, self._pid):
            if pt.get("session_id") != self._sid:
                continue
            err = f" ±{pt['err']}" if pt["err"] is not None else ""
            item = QListWidgetItem(
                f"[{pt['filter']}] mag {pt['mag']}{err}  ({pt['source']})")
            item.setData(Qt.UserRole, pt["id"])
            self.lst_meas.addItem(item)

    def _session_mjd(self, s):
        # The visit's MJD: its observing date when parseable, else its
        # creation epoch; never 0 (a zero MJD corrupts the curve order).
        from ...core.coords import jd_from_datetime
        date_str = (s.get("obs_date") or "").strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y/%m/%d"):
            if date_str:
                try:
                    dt = datetime.datetime.strptime(date_str, fmt) \
                        .replace(tzinfo=datetime.timezone.utc)
                    return jd_from_datetime(dt) - 2400000.5
                except ValueError:
                    pass
        created = s.get("created")
        dt = (datetime.datetime.fromtimestamp(created,
                      tz=datetime.timezone.utc) if created
              else datetime.datetime.now(datetime.timezone.utc))
        return jd_from_datetime(dt) - 2400000.5

    def _on_add_measurement(self):
        from ...core import followup as fu
        mag = self.spn_mag.value()
        err = self.spn_err.value() if self.spn_err.value() > 0 else None
        filt = self.cmb_filt.currentText().strip() or "Clear"
        s = fu.get_session(self._db, self._sid)
        fu.add_point(self._db, self._pid, self._session_mjd(s), filt,
                     mag, err=err, source="manual", session_id=self._sid)
        self._populate_measurements()
        self._emit_change()

    def _on_delete_measurement(self):
        from ...core import followup as fu
        items = self.lst_meas.selectedItems()
        if not items:
            return
        fu.delete_point(self._db, items[0].data(Qt.UserRole))
        self._populate_measurements()
        self._emit_change()

    # --------------------------------------------------- MPC astrometry

    def _project(self):
        # @return: the project dict (or None)
        from ...core import project as proj_mod
        return proj_mod.get(self._db, self._pid)

    def _build_mpc_block(self, lay):
        # The night's astrometry (NEO/PCCP): paste the MPC 80-col or ADES
        # lines, validate them, save the report. The report registers to
        # THIS visit — the measurements are the visit's product, so the
        # block lives here and nowhere else (ADR-045, form A).
        grp = QGroupBox(self.tr("Astrometry (MPC report)"))
        grp.setLayout(QVBoxLayout())
        grp.layout().addWidget(QLabel(self.tr(
            "Paste the night's astrometric measurements (MPC 80-col or "
            "ADES PSV)")))
        self.txt_mpc = QTextEdit()
        self.txt_mpc.setMaximumHeight(120)
        self.txt_mpc.setAcceptRichText(False)
        self.txt_mpc.setPlaceholderText(self.tr(
            "Paste MPC 80-column or ADES PSV lines here…"))
        font = self.txt_mpc.font()
        font.setFamily("Monospace")
        self.txt_mpc.setFont(font)
        grp.layout().addWidget(self.txt_mpc)
        row = QHBoxLayout()
        btn_val = QPushButton(self.tr("Validate"))
        btn_val.setObjectName("vp_mpc_validate")
        btn_val.clicked.connect(self._on_mpc_validate)
        row.addWidget(btn_val)
        btn_save = QPushButton(self.tr("Save report…"))
        btn_save.setObjectName("vp_mpc_save")
        btn_save.clicked.connect(self._on_mpc_save)
        row.addWidget(btn_save)
        row.addStretch(1)
        grp.layout().addLayout(row)
        self.lbl_mpc_status = QLabel("—")
        self.lbl_mpc_status.setObjectName("vp_mpc_status")
        self.lbl_mpc_status.setWordWrap(True)
        grp.layout().addWidget(self.lbl_mpc_status)
        lay.addWidget(grp)

    def _on_mpc_validate(self):
        from ...core import mpc_report
        from ...config import config
        text = self.txt_mpc.toPlainText()
        if not text.strip():
            self.lbl_mpc_status.setText(
                self.tr("Paste your measurements first."))
            return
        p = self._project()
        result = mpc_report.validate(
            text, obs_code=config.get("mpc_code", ""),
            expected_obj=(p or {}).get("object_name"))
        if result["valid"]:
            status = (self.tr("Valid: %1 lines, %2")
                      .replace("%1", str(result["n_lines"]))
                      .replace("%2", result["format"]))
            if result["warnings"]:
                status += " ⚠ " + "; ".join(result["warnings"])
            self.lbl_mpc_status.setText(status)
        else:
            self.lbl_mpc_status.setText(
                self.tr("Invalid: ") + "; ".join(result["errors"][:4])
                + ("…" if len(result["errors"]) > 4 else ""))

    def _on_mpc_save(self):
        # Package and register the report to THIS visit; when the
        # report's own first measurement disagrees with the visit's date,
        # say so (a report hung on the wrong night is a silent database
        # sin), without blocking.
        from ...core import followup as fu, mpc_report
        from ...core import project as proj_mod
        from ...config import config
        text = self.txt_mpc.toPlainText()
        if not text.strip():
            self.lbl_mpc_status.setText(
                self.tr("Paste your measurements first."))
            return
        p = self._project()
        obj = (p or {}).get("object_name", "")
        outdir = proj_mod.storage_dir(p) if p else Path.home()
        default = outdir / f"{obj}_mpc_report.txt"
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save MPC report"), str(default),
            "Text files (*.txt);;All files (*)")
        if not out:
            return
        path, result = mpc_report.package(
            text, out, obs_code=config.get("mpc_code", ""),
            expected_obj=obj)
        if not path:
            self.lbl_mpc_status.setText(
                self.tr("Invalid: ") + "; ".join(result["errors"][:4])
                + ("…" if len(result["errors"]) > 4 else ""))
            return
        proj_mod.add_file(self._db, self._pid, path, "report",
                          session_id=self._sid)
        note = ""
        rep_date = mpc_report.first_obs_date(text)
        s = fu.get_session(self._db, self._sid)
        if rep_date and s and s["obs_date"] and rep_date != s["obs_date"]:
            note = " " + self.tr(
                "⚠ the report's first measurement is from %1, not this "
                "visit's date").replace("%1", rep_date)
        self.lbl_mpc_status.setText(
            self.tr("Saved: %1 (%2 lines)")
            .replace("%1", path).replace("%2", str(result["n_lines"]))
            + note)
        self._populate_resources()
        self._emit_change()

    # ------------------------------------------------------------ notes

    def _on_notes_changed(self):
        from ...core import followup as fu
        fu.update_session_notes(self._db, self._sid,
                                self._notes.toPlainText())

    # ------------------------------------------------------------ misc

    def _emit_change(self):
        # Tells the panel (and through it the host) that data changed.
        if self._data_changed is not None:
            self._data_changed()
