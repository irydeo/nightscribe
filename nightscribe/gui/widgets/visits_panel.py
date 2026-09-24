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
reports, charts) hangs from one. Master-detail inline in the Analysis tab,
for EVERY project kind; the photometry measurement block shows for the
kinds that keep light curves.

Rules of the redesign, honoured here:

* One primary entry point: "New visit". No duplicated buttons.
* Nothing attaches without a visit: the add-resource action lives inside
  the selected visit; with no visit the empty state offers to create one.
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
                               QFileDialog, QFormLayout, QFrame,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QScrollArea, QTextEdit, QVBoxLayout, QWidget)

from .passive_wheel import PassiveDoubleSpinBox, PassiveList

logger = logging.getLogger("nightscribe.gui.visits_panel")

# Kinds whose visits keep photometry points (the light-curve kinds);
# everyone gets resources and notes.
CURVE_KINDS = ("sn", "hads", "variable")

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
    # The visits master-detail manager. One instance per built Analysis
    # tab; set_project() refills it (the page caches it until the project
    # changes).
    #
    # @args: db - the Database, lang - "es" | "en",
    #        open_in_editor - callable(path, session_id) opening a FITS in
    #        the UFE (None hides the per-row editor action),
    #        on_change - callable() after any data change (curve/cadence
    #        refresh lives outside),
    #        curve_kind - True keeps the measurement block (light-curve
    #        kinds); everyone gets resources and notes

    def __init__(self, db, lang="es", open_in_editor=None, on_change=None,
                 curve_kind=True, parent=None):
        super().__init__(parent)
        self._db = db
        self._lang = lang
        self._open_in_editor = open_in_editor
        self._on_change = on_change
        self._curve_kind = bool(curve_kind)
        self._pid = None              # current project id
        self._sid = None              # selected visit id (or None)
        self._build_ui()

    # ------------------------------------------------------------ build

    def _build_ui(self):
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.btn_new = QPushButton(self.tr("New visit"))
        self.btn_new.setToolTip(self.tr(
            "Every day you work the object is a visit: images, reports "
            "and measurements hang from it"))
        self.btn_new.clicked.connect(self._on_new_visit)
        top.addWidget(self.btn_new)
        self.lbl_count = QLabel("")
        top.addWidget(self.lbl_count)
        top.addStretch(1)
        lay.addLayout(top)

        self.lbl_empty = QLabel(self.tr(
            "No visits yet. Each night you work the object starts one: "
            "plates, reports and measurements attach to it."))
        self.lbl_empty.setWordWrap(True)
        lay.addWidget(self.lbl_empty)

        self.split = QHBoxLayout()
        self.lst = PassiveList()
        self.lst.setMaximumWidth(340)
        self.lst.itemSelectionChanged.connect(self._on_select)
        self.split.addWidget(self.lst, 2)
        self.detail = QFrame()
        self.detail.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_layout = QVBoxLayout(self.detail)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.detail)
        self.split.addWidget(scroll, 5)
        lay.addLayout(self.split, 1)
        self._show_empty(True)

    # ------------------------------------------------------------ state

    def set_project(self, project_id, keep_selection=True):
        # @args: project_id - the project to manage, keep_selection - try
        #        to keep the selected visit across a refresh
        prev = self._sid if keep_selection else None
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
        return self._sid

    def refresh(self):
        # Refills the visits list from the database (newest first).
        from ...core import followup as fu
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
            item = QListWidgetItem(f"{s['obs_date']}{tag}{notes}")
            item.setData(Qt.UserRole, s["id"])
            self.lst.addItem(item)
        n = len(sessions)
        self.lbl_count.setText(self.tr("{0} visits").format(n) if n else "")
        self._show_empty(n == 0)
        if n:
            if self.lst.currentRow() < 0:
                self.lst.setCurrentRow(0)
        else:
            self._sid = None

    def _show_empty(self, flag):
        # @args: flag - no visits exist
        self.lbl_empty.setVisible(flag)
        self.lst.setVisible(not flag)
        self.detail.setVisible(not flag)

    # ---------------------------------------------------------- visits

    def _on_new_visit(self):
        # The single entry point: create today's visit and land on it.
        from ...core import followup as fu
        if self._pid is None:
            return
        fu.create_session(self._db, self._pid)
        self.refresh()
        self.lst.setCurrentRow(0)   # newest first
        self._emit_change()

    def _on_select(self):
        items = self.lst.selectedItems()
        if not items:
            return
        self._sid = items[0].data(Qt.UserRole)
        self._rebuild_detail()

    def _on_delete_visit(self):
        # Confirmation first; points and files keep living in the project,
        # unlinked (the DB's ON DELETE SET NULL), and the panel says so.
        from ...core import followup as fu
        if self._sid is None:
            return
        ans = QMessageBox.question(
            self, self.tr("Delete visit"),
            self.tr("Delete this visit? Its measurements and files are "
                    "kept, unlinked from it."))
        if ans != QMessageBox.Yes:
            return
        fu.delete_session(self._db, self._sid)
        self._sid = None
        self.refresh()
        self._emit_change()

    # ---------------------------------------------------------- detail

    def _wipe(self):
        # Drops every widget in the detail pane (same discipline as the
        # main window's _wipe_layout).
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                sub = item.layout()
                while sub.count():
                    sub_item = sub.takeAt(0)
                    sw = sub_item.widget()
                    if sw is not None:
                        sw.setParent(None)
                        sw.deleteLater()

    def _rebuild_detail(self):
        # The selected visit's full card: resources, measurements (curve
        # kinds) and notes.
        from ...core import followup as fu
        self._wipe()
        s = fu.get_session(self._db, self._sid)
        if s is None:
            return
        lay = self.detail_layout
        head = QHBoxLayout()
        title = QLabel(f"<b>{s['obs_date'] or '?'}</b>")
        head.addWidget(title, 1)
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
        lay.addWidget(grp_res)
        self._populate_resources()

        # ---- measurements (light-curve kinds)
        if self._curve_kind:
            self._build_measurements_block(lay, s)

        # ---- notes
        snotes = QTextEdit()
        snotes.setObjectName("vp_notes")
        snotes.setPlaceholderText(self.tr("Night notes (seeing, clouds…)"))
        snotes.setText(s["notes"])
        snotes.textChanged.connect(self._on_notes_changed)
        lay.addWidget(snotes)
        self._notes = snotes

    # ------------------------------------------------------- resources

    def _populate_resources(self):
        # Refills the selected visit's resource list from the registry.
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
        self.refresh()
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
        self.refresh()
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
        lay.addWidget(grp)
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
        if self._sid is None:
            return
        mag = self.spn_mag.value()
        err = self.spn_err.value() if self.spn_err.value() > 0 else None
        filt = self.cmb_filt.currentText().strip() or "Clear"
        s = fu.get_session(self._db, self._sid)
        fu.add_point(self._db, self._pid, self._session_mjd(s), filt,
                     mag, err=err, source="manual", session_id=self._sid)
        self._populate_measurements()
        self.refresh()
        self._emit_change()

    def _on_delete_measurement(self):
        from ...core import followup as fu
        items = self.lst_meas.selectedItems()
        if not items:
            return
        fu.delete_point(self._db, items[0].data(Qt.UserRole))
        self._populate_measurements()
        self.refresh()
        self._emit_change()

    # ------------------------------------------------------------ notes

    def _on_notes_changed(self):
        from ...core import followup as fu
        if self._sid is not None:
            fu.update_session_notes(self._db, self._sid,
                                    self._notes.toPlainText())

    # ------------------------------------------------------------ misc

    def _emit_change(self):
        # Tells the host the data changed (curve, cadence, summary).
        if self._on_change is not None:
            self._on_change()
