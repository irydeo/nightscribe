############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: MPC report dialog (ADR-080)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The MPC report in its own non-modal window (ADR-080).

The report is a full submission (header + one line/row per observation), so
it does not fit the Astrometry tab's narrow column: it lives here, opened by
the tab's "Report…" button, with the format selector and the three actions
(Copy, Save, Send). The tab owns the behaviour (it builds the text, fills the
widgets and runs the submission); the window stays a dumb container, like the
published-observations and manual windows (ADR-077, ADR-065).

ADR-005: the structure lives in ui/ufe_report_dialog.ui; this class only
dresses the window (title, non-modal, size) and exposes the widgets.
"""

from PySide6.QtWidgets import QDialog

from .ui_loader import adopt_ui


class UfeReportDialog(QDialog):
    # @args: parent - the UfeTrackStackTab that owns the behaviour
    # @return: the dialog with the format combo, the report and the actions

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("MPC report"))
        self.setModal(False)
        self._ui = adopt_ui(self, "ufe_report_dialog")
        self.cmb_format = self._ui.cmb_format
        # the format combo carries its own data (the generator's key), so the
        # tab reads currentData() and never parses the label
        self.cmb_format.addItem(self.tr("ADES XML (preferred)"), "xml")
        self.cmb_format.addItem(self.tr("ADES PSV"), "ades")
        self.cmb_format.addItem(self.tr("MPC 1992 (80 columns)"), "mpc80")
        self.txt_report = self._ui.txt_report
        self.lbl_report_hint = self._ui.lbl_report_hint
        self.btn_copy = self._ui.btn_copy
        self.btn_save = self._ui.btn_save
        self.btn_send = self._ui.btn_send
        self.btn_close = self._ui.btn_close
        self.resize(760, 560)
