############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Manual object panel (Interfaz 1.0, ADR-053)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The manual object form: when the name search does not locate an object,
the observer types its data and the project is created just the same. The
common fields are always there; the kind-specific block swaps with the Type
combo. to_target() returns the same planner-target dict core/project.py
already knows how to snapshot, so nothing else changes downstream.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ..ui_loader import adopt_ui

# The combo order in manual_object_panel.ui, mapped to project kinds.
_KIND_IDS = ("sn", "neo", "comet", "pccp", "transit", "variable", "hads")
# kind -> page index in the kind_stack (pccp shares the NEO page)
_KIND_PAGE = {"sn": 0, "comet": 1, "neo": 2, "pccp": 2, "transit": 3,
              "variable": 4, "hads": 5}


class ManualObjectPanel(QWidget):
    created = Signal(dict)     # the target dict to create the project from
    cancelled = Signal()

    # @args: parent - the hosting widget
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ui = adopt_ui(self, "manual_object_panel")
        self._ui.cmb_mf_kind.currentIndexChanged.connect(self._kind_changed)
        self._ui.btn_mf_create.clicked.connect(self._create)
        self._ui.btn_mf_cancel.clicked.connect(self.cancelled.emit)
        self._kind_changed()

    def _kind_changed(self, _index=0):
        kind = _KIND_IDS[self._ui.cmb_mf_kind.currentIndex()]
        self._ui.kind_stack.setCurrentIndex(_KIND_PAGE.get(kind, 0))

    @staticmethod
    def _num(edit):
        # @args: edit - a QLineEdit holding a number or nothing
        # @return: the float, or None when empty / not a number
        text = edit.text().strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _txt(edit):
        # @return: the stripped text, or None when empty
        text = edit.text().strip()
        return text or None

    def to_target(self):
        # @return: the target dict core/project.py snapshots into the
        #          project context (name, kind, coords, mag and the
        #          kind-specific fields the planner/exports understand)
        u = self._ui
        kind = _KIND_IDS[u.cmb_mf_kind.currentIndex()]
        t = {"name": self._txt(u.edt_mf_name), "kind": kind}
        for key, edit in (("ra_deg", u.edt_mf_ra), ("dec_deg", u.edt_mf_dec),
                          ("mag", u.edt_mf_mag)):
            val = self._num(edit)
            if val is not None:
                t[key] = val
        notes = self._txt(u.edt_mf_notes)
        if notes:
            t["notes"] = notes
        if kind == "sn":
            for key, edit in (("disc_date", u.edt_sn_date),
                              ("sn_type", u.edt_sn_type),
                              ("host", u.edt_sn_host)):
                val = self._txt(edit)
                if val:
                    t[key] = val
        elif kind == "comet":
            val = self._txt(u.edt_comet_peri)
            if val:
                t["perihelion_date"] = val
            h = self._num(u.edt_comet_h)
            if h is not None:
                t["h"] = h
        elif kind in ("neo", "pccp"):
            for key, edit in (("rate_arcsec_min", u.edt_neo_rate),
                              ("h", u.edt_neo_h), ("moid", u.edt_neo_moid)):
                val = self._num(edit)
                if val is not None:
                    t[key] = val
        elif kind == "transit":
            tr = {}
            for key, edit in (("period_d", u.edt_tr_period),
                              ("t0", u.edt_tr_t0),
                              ("duration_h", u.edt_tr_dur),
                              ("depth_mmag", u.edt_tr_depth)):
                val = self._num(edit)
                if val is not None:
                    tr[key] = val
            if tr:
                t["transit"] = tr
        elif kind == "variable":
            var = {}
            for key, edit in (("period_d", u.edt_var_period),
                              ("amplitude", u.edt_var_amp),
                              ("epoch", u.edt_var_epoch)):
                val = self._num(edit)
                if val is not None:
                    var[key] = val
            sub = self._txt(u.edt_var_sub)
            if sub:
                var["var_type"] = sub
            if var:
                t["variable"] = var
        elif kind == "hads":
            hd = {}
            for key, edit in (("period_d", u.edt_hads_period),
                              ("amplitude", u.edt_hads_amp),
                              ("epoch", u.edt_hads_epoch)):
                val = self._num(edit)
                if val is not None:
                    hd[key] = val
            if hd:
                t["hads"] = hd
        return t

    def _create(self):
        # Name and coordinates are the honest minimum: without them the
        # planner cannot tell whether the object is up tonight.
        t = self.to_target()
        if not t.get("name"):
            self._ui.lbl_mf_status.setText(
                self.tr("The object needs a name."))
            return
        if t.get("ra_deg") is None or t.get("dec_deg") is None:
            self._ui.lbl_mf_status.setText(
                self.tr("RA and Dec are needed, in degrees."))
            return
        self.created.emit(t)
