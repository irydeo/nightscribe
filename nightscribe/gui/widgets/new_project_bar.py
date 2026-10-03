############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - New-project search bar (Interfaz 1.0, ADR-053)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The new-project bar that sits at the top of the Tonight view: search an
object by name (VSX -> SIMBAD, the old Tools > Explore lookup) and, when it
is not located, create it by hand with ManualObjectPanel. The bar only
builds the target dict and emits it; the host (MainWindow) owns the actual
project creation and navigation.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from .manual_object_panel import ManualObjectPanel


class NewProjectBar(QWidget):
    # create_target: a target dict ready for core/project.py (name, kind,
    #                coords, mag and the kind-specific fields).
    create_target = Signal(dict)

    # @args: parent - the hosting widget
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._resolved = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(6)
        row = QHBoxLayout()
        self.edt_search = QLineEdit()
        self.edt_search.setPlaceholderText(
            self.tr("Find an object by name (VSX / SIMBAD)…"))
        self.edt_search.returnPressed.connect(self._resolve)
        row.addWidget(self.edt_search, 1)
        self.btn_resolve = QPushButton(self.tr("Resolve"))
        self.btn_resolve.clicked.connect(self._resolve)
        row.addWidget(self.btn_resolve)
        self.btn_manual = QPushButton(self.tr("Create by hand…"))
        self.btn_manual.clicked.connect(self._toggle_manual)
        row.addWidget(self.btn_manual)
        lay.addLayout(row)
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: #8a90a6; font-size: 11px;")
        lay.addWidget(self.lbl_status)
        self.manual = ManualObjectPanel()
        self.manual.setVisible(False)
        self.manual.created.connect(self.create_target.emit)
        self.manual.cancelled.connect(lambda: self.manual.setVisible(False))
        lay.addWidget(self.manual)

    def _toggle_manual(self):
        show = not self.manual.isVisible()
        self.manual.setVisible(show)
        if show and self.edt_search.text().strip():
            self.manual._ui.edt_mf_name.setText(
                self.edt_search.text().strip())

    def _resolve(self):
        name = self.edt_search.text().strip()
        if not name or self._worker is not None:
            return
        from ..workers import ResolveWorker
        self.btn_resolve.setEnabled(False)
        self.lbl_status.setText(self.tr("Resolving…"))
        self._worker = ResolveWorker(name)
        self._worker.finished.connect(self._resolve_done)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _resolve_done(self, result):
        from ...core import coords
        name = self.edt_search.text().strip()
        self._worker = None
        self.btn_resolve.setEnabled(True)
        v = result.get("vsx")
        if v:
            self._resolved = {"name": name, "type": "variable",
                              "ra_deg": v.get("ra_deg"),
                              "dec_deg": v.get("dec_deg")}
            if v.get("max") is not None:
                self._resolved["mag"] = v["max"]
            self.lbl_status.setText(self.tr(
                "Found in VSX: %1. Creating the project…").replace(
                    "%1", v.get("var_type") or "?"))
            self.create_target.emit(dict(self._resolved))
            return
        ident = result.get("simbad")
        if ident:
            try:
                ra = round(coords.ra_hms_to_deg(ident["ra"]), 5)
                dec = round(coords.dec_dms_to_deg(ident["dec"]), 5)
            except (ValueError, TypeError, KeyError):
                ra = dec = None
            self._resolved = {"name": name, "type": "small_body",
                              "ra_deg": ra, "dec_deg": dec}
            if ident.get("vmag") is not None:
                self._resolved["mag"] = ident["vmag"]
            self.lbl_status.setText(self.tr(
                "Found in SIMBAD: %1. Creating the project…").replace(
                    "%1", ident.get("otype") or "?"))
            self.create_target.emit(dict(self._resolved))
            return
        # not located: open the manual form with the name already typed
        self.lbl_status.setText(self.tr(
            "Not found. Fill in its data to create it by hand."))
        self.manual.setVisible(True)
        self.manual._ui.edt_mf_name.setText(name)

    def reset(self):
        # Clears the search after a project was created from here.
        self.edt_search.clear()
        self.lbl_status.setText("")
        self.manual.setVisible(False)
