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

from PySide6.QtWidgets import QDialog

from ..core import campaign
from ..core.db import db
from .ui_loader import load_ui

logger = logging.getLogger(__name__)


class CampaignEditDialog(QDialog):
    # The create/edit form of one campaign. Protocol fields: cadence in
    # nights (default 1, V-l), filters and comparison stars as
    # comma-separated text (parsed on save). The form's structure is
    # ui/campaign_edit_dialog.ui (ADR-005); the prefill is data.
    # @args: parent - QWidget, camp - campaign dict to edit or None (new),
    #        db_obj - Database
    def __init__(self, parent=None, camp=None, db_obj=None):
        super().__init__(parent)
        self._db = db_obj or db
        self._camp = camp
        self.setWindowTitle(self.tr("Edit campaign") if camp
                            else self.tr("New campaign"))
        self._ui = load_ui("campaign_edit_dialog", self)
        self.setLayout(self._ui.layout())   # no wrapper, no extra margins
        self.edt_name = self._ui.edt_name
        self.edt_group = self._ui.edt_group
        self.edt_coord = self._ui.edt_coord
        self.edt_goal = self._ui.edt_goal
        self.spn_cadence = self._ui.spn_cadence
        self.edt_filters = self._ui.edt_filters
        self.edt_comps = self._ui.edt_comps
        self.edt_report = self._ui.edt_report
        self.edt_data = self._ui.edt_data
        self.edt_notes = self._ui.edt_notes
        prot = (camp or {}).get("protocol") or {}
        self.edt_name.setText((camp or {}).get("name", ""))
        self.edt_group.setText((camp or {}).get("group_name", ""))
        self.edt_coord.setText((camp or {}).get("coordinator", ""))
        self.edt_goal.setText((camp or {}).get("goal", ""))
        self.spn_cadence.setValue(int(prot.get("cadence_nights", 1)))
        self.edt_filters.setText(", ".join(prot.get("filters", [])))
        self.edt_comps.setText(", ".join(prot.get("comp_stars", [])))
        self.edt_report.setText((camp or {}).get("report_url", ""))
        self.edt_data.setText((camp or {}).get("data_url", ""))
        self.edt_notes.setPlainText(prot.get("notes", ""))
        self._ui.buttonBox.accepted.connect(self._save)
        self._ui.buttonBox.rejected.connect(self.reject)

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
        self._db = db_obj or db
        self._campaign_id = campaign_id
        self._resolved = {}
        self._resolve_worker = None
        self.setWindowTitle(self.tr("New project"))
        # the form's structure is ui/new_project_dialog.ui (ADR-005);
        # the resolution chain fills its fields in code
        self._ui = load_ui("new_project_dialog", self)
        self.setLayout(self._ui.layout())   # no wrapper, no extra margins
        self.edt_name = self._ui.edt_name
        self.btn_resolve = self._ui.btn_resolve
        self.lbl_resolved = self._ui.lbl_resolved
        self.edt_ra = self._ui.edt_ra
        self.edt_dec = self._ui.edt_dec
        self.edt_mag = self._ui.edt_mag
        self.btn_resolve.clicked.connect(self._resolve)
        self._ui.buttonBox.accepted.connect(self._save)
        self._ui.buttonBox.rejected.connect(self.reject)

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
