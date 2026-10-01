############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Welcome view: first-run / update setup (ADR-053)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Welcome view (Interfaz 1.0): the old modal QWizard lives here as an
inline stepper (Observatory -> Targets -> Data). The heavy lifting is the
SAME code as before: the helpers in gui/wizard.py (_detect, _resolve_site,
_setup_kinds, _setup_data, _apply_site, _apply_kinds, _mark_done) are
reused verbatim against the loaded widget, so the two never drift.

The host (MainWindow) decides when Welcome is shown (first run, a pending
update, or no projects) and gates navigation on the Data step while an
update is unacknowledged.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..ui_loader import load_ui


class WelcomeSetup(QWidget):
    # create_project: the CTA asks the host to open the new-project view.
    # finished: the Data step was acknowledged (the host seals app_version).
    create_project = Signal()
    finished = Signal()

    # @args: snapshot - the pre-migration backup dict (core/backup.backup)
    #        or None when there is no database yet; parent - the host
    def __init__(self, snapshot=None, parent=None):
        super().__init__(parent)
        self._snapshot = snapshot
        # the .ui is loaded as a child and its named widgets are reached
        # through self.ui (ADR-005); the wizard helpers take the husk
        self.ui = load_ui("welcome_tab", self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.ui)
        self._boxes = {}
        self._wire()
        self._fill_from_config()
        self.show_step("obs")

    def _wire(self):
        from .. import wizard as wz
        u = self.ui
        u.btn_detect.clicked.connect(lambda: wz._detect(u))
        u.btn_resolve.clicked.connect(lambda: wz._resolve_site(u))
        u.btn_step_obs.clicked.connect(lambda: self.show_step("obs"))
        u.btn_step_kinds.clicked.connect(lambda: self.show_step("kinds"))
        u.btn_step_data.clicked.connect(lambda: self.show_step("data"))
        u.btn_obs_next.clicked.connect(self._obs_next)
        u.btn_kinds_next.clicked.connect(self._kinds_next)
        u.btn_data_ack.clicked.connect(self.finished.emit)
        u.btn_create.clicked.connect(self._create)
        # the kinds list and the migration report are data (ADR-005)
        self._boxes = wz._setup_kinds(u)
        wz._setup_data(u, self._snapshot)
        for w in (u.spn_site_lat, u.spn_site_lon, u.edt_site_mpc,
                  u.edt_site_name):
            if hasattr(w, "valueChanged"):
                w.valueChanged.connect(lambda _v: self._refresh_create())
            else:
                w.textChanged.connect(lambda _t: self._refresh_create())

    def _fill_from_config(self):
        # Seeds the form from the current settings so a re-visit shows what
        # is already saved (a first run shows zeros / empty).
        from ...config import config
        u = self.ui
        u.spn_site_lat.setValue(float(config.get("lat") or 0.0))
        u.spn_site_lon.setValue(float(config.get("lon") or 0.0))
        u.spn_site_height.setValue(int(config.get("height") or 0))
        u.edt_site_name.setText(config.get("observatory_name") or "")
        u.edt_site_mpc.setText(config.get("mpc_code") or "")
        self._refresh_create()

    def _site_ok(self):
        # @return: True when the form has a usable site (coords or MPC code)
        u = self.ui
        return (u.spn_site_lat.value() != 0.0
                or u.spn_site_lon.value() != 0.0
                or bool(u.edt_site_mpc.text().strip()))

    def _refresh_create(self):
        # The CTA only works once there is somewhere to observe from.
        self.ui.btn_create.setEnabled(self._site_ok())

    def show_step(self, key):
        # @args: key - "obs" | "kinds" | "data"
        idx = {"obs": 0, "kinds": 1, "data": 2}.get(key, 0)
        self.ui.setup_stack.setCurrentIndex(idx)
        for btn, k in ((self.ui.btn_step_obs, "obs"),
                       (self.ui.btn_step_kinds, "kinds"),
                       (self.ui.btn_step_data, "data")):
            btn.setChecked(k == key)

    def _obs_next(self):
        from .. import wizard as wz
        if not self._site_ok():
            self.ui.lbl_site_status.setText(
                self.tr("Type the coordinates, use the MPC code or detect "
                        "your location."))
            return
        wz._apply_site(self.ui)
        self._refresh_create()
        self.show_step("kinds")

    def _kinds_next(self):
        from .. import wizard as wz
        wz._apply_kinds(self._boxes)
        self.show_step("data")

    def _create(self):
        # The CTA: persist whatever is set and ask the host to open the
        # new-project view.
        from .. import wizard as wz
        if self._site_ok():
            wz._apply_site(self.ui)
        wz._apply_kinds(self._boxes)
        self.create_project.emit()

    def ack_data(self):
        # The host calls this when the Data step is the acknowledged gate.
        from .. import wizard as wz
        wz._mark_done()
