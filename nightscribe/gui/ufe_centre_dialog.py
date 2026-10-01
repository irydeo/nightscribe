############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: manual centre dialog (ADR-044 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The UFE Measure section's manual-centre control in one small non-modal
window (ADR-044 rev). The tab keeps only the "Manual centre" checkbox:
checking it shows this dialog, unchecking closes it.

The Measure tab owns the behaviour: it reads the widgets through the
public attributes it aliases and wires every signal itself (the dialog
stays a dumb container, like the Advanced one). The arrows move the
measurement centre by hand in 0.1 px steps and, while this mode is on, the
measurement uses exactly that point: no centroid search, which is what a
very faint SN or a galaxy core needs.

ADR-005: the structure lives in ui/ufe_centre_dialog.ui; this class only
dresses the window (title, non-modal, size) and exposes the widgets.
"""

from PySide6.QtWidgets import QDialog

from .ui_loader import adopt_ui


class UfeCentreDialog(QDialog):
    # @args: parent - the UfeMeasureTab that owns the behaviour
    # @return: the dialog with the arrows, the readout and the reset
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manual centre"))
        self.setModal(False)
        self._ui = adopt_ui(self, "ufe_centre_dialog")
        self.btn_up = self._ui.btn_up
        self.btn_left = self._ui.btn_left
        self.btn_right = self._ui.btn_right
        self.btn_down = self._ui.btn_down
        self.btn_nudge_reset = self._ui.btn_nudge_reset
        self.lbl_nudge = self._ui.lbl_nudge
        self.lbl_nudge.setText("(0.0, 0.0)")         # data, not text
        # compact: the two lines of hint and the pad, nothing else
        self.setMinimumWidth(260)
        self.adjustSize()
