############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Campaign sub-dialogs module (UX-a)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Sub-dialogs of the Campaigns tab (UX-a): the create/edit form and the
new-project dialog with its VSX/SIMBAD resolution chain. A campaign member
is a *project* — "target" is reserved for tonight's candidates (see
docs/CAMPAIGNS). The manager itself is the top-level Campaigns tab
(supersedes the modal dialog of ADR-035 V-j). All persistence goes through
core/campaign.py.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QLabel, QPushButton, QVBoxLayout)

from ..core import campaign
from ..core.db import db

logger = logging.getLogger(__name__)


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
        layout.addWidget(QLabel(self.tr(
            "A campaign groups the projects of one shared observation "
            "effort — several nights, several observatories, one goal. "
            "Name it after the goal, e.g. “T CrB 2026 eruption” or "
            "“WeSb 1 light curve”.")))
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


class NewProjectDialog(QDialog):
    # Creates a `variable` project for one object and links it to the
    # selected campaign (the member IS the project — the early draft's
    # "Add target…" wording was the source of the confusion, so the copy
    # now says "project" everywhere). Resolution chain (V-c): VSX
    # (cached) -> SIMBAD (coords anchor) -> fully manual. The lookups are
    # one tiny cached GET each and run synchronously; the form tells the
    # user while it resolves.
    # @args: parent, campaign_id - int, db_obj - Database
    def __init__(self, parent=None, campaign_id=None, db_obj=None):
        super().__init__(parent)
        from PySide6.QtWidgets import (QDialogButtonBox, QFormLayout,
                                       QLineEdit)
        self._db = db_obj or db
        self._campaign_id = campaign_id
        self._resolved = {}
        self._resolve_worker = None
        self.setWindowTitle(self.tr("New project"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr(
            "Creates a new project for this object and links it to the "
            "selected campaign. If the project already exists, use "
            "“Attach project…” in the campaigns tab instead.")))
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
        # Kicks the VSX->SIMBAD chain off the GUI thread (UX-f); the form
        # stays editable while it resolves.
        name = self.edt_name.text().strip()
        if not name or self._resolve_worker is not None:
            return
        from .workers import ResolveWorker
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

    def _save(self):
        # Creates the variable project linked to the campaign.
        name = self.edt_name.text().strip()
        if not name or self._campaign_id is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, self.windowTitle(),
                self.tr("The object needs a name."))
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
