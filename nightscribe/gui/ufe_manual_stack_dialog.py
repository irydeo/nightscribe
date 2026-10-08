############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: manual stack dialog (ADR-065)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Astrometry tab's manual mode for a faint object, in one small
non-modal window (ADR-065).

When the detection gate does not fire, the object is still there for a human
eye and a human mark: this window shows the whole-sequence stack, arms the
mark on it, and measures from that mark. The Astrometry tab keeps only the
checkbox and owns the behaviour (it writes the base stack, converts the
click, snaps it to the centroid and wires the arrows); the dialog stays a
dumb container, like the manual-centre one (ADR-044 rev).

ADR-005: the structure lives in ui/ufe_manual_stack_dialog.ui; this class
only dresses the window (title, non-modal, size) and exposes the widgets.
"""

from PySide6.QtWidgets import QDialog

from .ui_loader import adopt_ui


class UfeManualStackDialog(QDialog):
    # @args: parent - the UfeTrackStackTab that owns the behaviour
    # @return: the dialog with the hint, the Show button, the arrows, the
    #          readouts and the Measure button

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manual mode (faint object)"))
        self.setModal(False)
        self._ui = adopt_ui(self, "ufe_manual_stack_dialog")
        self.lbl_manual_hint = self._ui.lbl_manual_hint
        self.btn_manual_show = self._ui.btn_manual_show
        self.btn_up = self._ui.btn_up
        self.btn_left = self._ui.btn_left
        self.btn_right = self._ui.btn_right
        self.btn_down = self._ui.btn_down
        self.btn_nudge_reset = self._ui.btn_nudge_reset
        self.lbl_nudge = self._ui.lbl_nudge
        self.lbl_nudge.setText("(0.0, 0.0)")         # data, not text
        self.lbl_manual_mark = self._ui.lbl_manual_mark
        self.chk_show_cross = self._ui.chk_show_cross
        self.btn_manual_measure = self._ui.btn_manual_measure
        self.setMinimumWidth(340)
        self.adjustSize()
