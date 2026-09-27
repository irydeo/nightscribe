############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: Manual tweak window (ADR-044 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The UFE Compare tab's manual controls in one small window (ADR-044,
rev 2026-09-26): the hand-driven path, picked star by star (comparison
or check), the catalog-labels toggle and the step-by-step actions that
the one-click flow bundles (field alone, proposal alone, the sequence
table). The «Manual tweak…» toggle, right of the DSS2 button, raises it
; closed (the normal state) the plate clicks measure.

The Compare tab owns the behaviour: it aliases the window's widgets as
its own (rdo_comp, rdo_check, chk_labels, btn_field, btn_propose,
btn_seq_open) so the old call sites and the pinned tests keep working,
and it routes the plate clicks by this window's visibility. The state
lives on the widgets, so closing and reopening the window keeps the
picking kind, the labels choice and whatever was already queued.

ADR-005: the structure and its translatable texts live in
ui/ufe_manual_dialog.ui; this class loads it through adopt_ui and
exposes the widgets.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog

from .ui_loader import adopt_ui


class UfeManualDialog(QDialog):
    # Qt's own QDialog.visibilityChanged signal is not bound in this
    # PySide6 build, so the window reports its state with its own
    # signal: True when it rises, False when it is hidden (the tab's
    # hide() or the window's X button) and the host can unsync its
    # toggle from that
    openStateChanged = Signal(bool)

    # @args: parent - the UFE Compare tab (owns the behaviour; the
    #        window is transient and dies with it)
    # @return: the manual tweak window, ready to be raised and routed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manual tweak"))
        # the sizing lives here, not in the .ui: adopt_ui's hidden shell
        # is what would receive the root's size properties there, so
        # this file deliberately carries none.
        # 500x185 keeps the buttons' row from ever squishing (measured
        # it needs 428, a wide font eats about 15% more) and 540x200
        # gives the spacers a little air to spend
        self.setMinimumSize(500, 185)
        self.resize(540, 200)
        # the structure is the Designer file's (ADR-005); this class
        # only dresses the window and exposes the widgets the tab
        # aliases
        self._ui = adopt_ui(self, "ufe_manual_dialog")
        self.lbl_hint = self._ui.lbl_hint
        self.lbl_pick = self._ui.lbl_pick
        self.rdo_comp = self._ui.rdo_comp
        self.rdo_check = self._ui.rdo_check
        self.chk_labels = self._ui.chk_labels
        self.btn_seq_open = self._ui.btn_seq_open
        self.btn_field = self._ui.btn_field
        self.btn_propose = self._ui.btn_propose

    def showEvent(self, ev):
        # @args: ev - the show event, passed on
        super().showEvent(ev)
        self.openStateChanged.emit(True)

    def hideEvent(self, ev):
        # the X button hides (a non-modal QDialog dies with host or X),
        # so this is the one hook that sees every close
        # @args: ev - the hide event, passed on
        super().hideEvent(ev)
        self.openStateChanged.emit(False)
