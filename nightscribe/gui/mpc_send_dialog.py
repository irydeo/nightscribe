############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - MPC submission dialog (ADR-080)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The MPC submission dialog (ADR-080).

Sending a report to the MPC is never silent: this window asks for the
acknowledgement email (AC2), the acknowledgement text, the target keyword and
the mode (Normal or Test), shows the server's own answer in its log, and
refuses to send when the report cannot be built (no email, no header). The
Astrometry tab owns the behaviour (it builds the report, runs the submission
worker and appends to the log); the window stays a dumb container.

ADR-005: the structure lives in ui/mpc_send_dialog.ui; this class only dresses
the window (title, non-modal, size), fills the target list and exposes the
widgets.
"""

from PySide6.QtWidgets import QDialog

from .ui_loader import adopt_ui


class MpcSendDialog(QDialog):
    # @args: parent - the UfeTrackStackTab that owns the behaviour
    # @return: the dialog with the log, the fields and the Send button

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Send report to the Minor Planet Center"))
        self.setModal(False)
        self._ui = adopt_ui(self, "ufe_mpc_send_dialog")
        self.lbl_intro = self._ui.lbl_intro
        self.txt_log = self._ui.txt_log
        self.edt_ack_email = self._ui.edt_ack_email
        self.edt_ack = self._ui.edt_ack
        self.cmb_target = self._ui.cmb_target
        self.cmb_mode = self._ui.cmb_mode
        self.lbl_missing = self._ui.lbl_missing
        self.btn_send = self._ui.btn_send
        self.btn_close = self._ui.btn_close
        self.cmb_mode.addItem(self.tr("Normal"), False)
        self.cmb_mode.addItem(self.tr("Test"), True)
        self.resize(640, 420)

    def set_targets(self, targets):
        # @args: targets - the target keyword list (from mpc_submit.TARGETS)
        # @return: None. Filled here so the dialog does not import the source
        #          and the list lives in one place.
        self.cmb_target.clear()
        for name in targets:
            self.cmb_target.addItem(name, name)

    def log(self, text):
        # @args: text - one line for the submission log
        # @return: None
        self.txt_log.appendPlainText(str(text))
