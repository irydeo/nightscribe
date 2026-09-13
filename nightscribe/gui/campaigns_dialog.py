############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Campaign manager dialog module (ADR-035)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

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
        self.btn_target = QPushButton(self.tr("Add target…"))
        self.btn_attach = QPushButton(self.tr("Attach project…"))
        self.btn_detach = QPushButton(self.tr("Detach…"))
        self.btn_close = QPushButton(self.tr("Close"))
        for b in (self.btn_new, self.btn_edit, self.btn_finish,
                  self.btn_reopen, self.btn_target, self.btn_attach,
                  self.btn_detach):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.btn_close)
        layout.addLayout(row)
        self.btn_close.clicked.connect(self.accept)
        self.btn_new.clicked.connect(self._new_campaign)
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_finish.clicked.connect(self._finish_selected)
        self.btn_reopen.clicked.connect(self._reopen_selected)
        self.btn_target.clicked.connect(self._add_target)
        self.btn_attach.clicked.connect(self._attach_project)
        self.btn_detach.clicked.connect(self._detach_project)
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
        # @return: None — enables each action only for its own list
        self.btn_finish.setEnabled(self._selected_id(self.lst_active)
                                   is not None)
        self.btn_reopen.setEnabled(self._selected_id(self.lst_finished)
                                   is not None)
        self.btn_edit.setEnabled(self._selected_id(self.lst_active)
                                  is not None)
        self.btn_target.setEnabled(self._selected_id(self.lst_active)
                                   is not None)
        self.btn_attach.setEnabled(self._selected_id(self.lst_active)
                                   is not None)
        self.btn_detach.setEnabled(self._selected_id(self.lst_active)
                                   is not None)

    def _finish_selected(self):
        # @return: None — moves the picked active campaign to finished
        cid = self._selected_id(self.lst_active)
        if cid is not None:
            campaign.finish(self._db, cid)
            self._reload()

    def _reopen_selected(self):
        # @return: None — moves the picked finished campaign back to active
        cid = self._selected_id(self.lst_finished)
        if cid is not None:
            campaign.reopen(self._db, cid)
            self._reload()

    def _new_campaign(self):
        # @return: None — opens the create form and reloads on accept
        if CampaignEditDialog(self, db_obj=self._db).exec():
            self._reload()

    def _edit_selected(self):
        # @return: None — opens the edit form for the active-list selection
        cid = self._selected_id(self.lst_active)
        if cid is None:
            return
        camp = campaign.get(self._db, cid)
        if camp is not None and \
                CampaignEditDialog(self, camp=camp, db_obj=self._db).exec():
            self._reload()

    def _add_target(self):
        # @return: None — opens the target form for the active-list selection
        cid = self._selected_id(self.lst_active)
        if cid is None:
            return
        AddTargetDialog(self, campaign_id=cid, db_obj=self._db).exec()
        self._reload()

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
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, self.tr("Attach project"),
                self.tr("No active project without a campaign."))
            return
        names = [f"[{p['kind']}] {p['object_name']}" for p in choices]
        sel, ok = QInputDialog.getItem(
            self, self.tr("Attach project"), self.tr("Project:"),
            names, 0, False)
        if ok:
            idx = names.index(sel)
            project.set_campaign(self._db, choices[idx]["id"], cid)
            self._reload()

    def _detach_project(self):
        # Unlinks a project of the selected campaign (chosen by name).
        cid = self._selected_id(self.lst_active)
        if cid is None:
            return
        from PySide6.QtWidgets import QInputDialog
        members = campaign.projects_of(self._db, cid, status=None)
        if not members:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, self.tr("Detach project"),
                self.tr("This campaign has no projects yet."))
            return
        names = [p["object_name"] for p in members]
        sel, ok = QInputDialog.getItem(
            self, self.tr("Detach project"), self.tr("Project:"),
            names, 0, False)
        if ok:
            from ..core import project
            project.set_campaign(self._db, members[names.index(sel)]["id"],
                                 None)
            self._reload()


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
        # @args: text - comma-separated field text
        # @return: list of non-empty stripped items
        return [x.strip() for x in text.split(",") if x.strip()]

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
