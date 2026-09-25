############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: advanced recipe dialog (ADR-044 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The UFE Measure section's recipe knobs in one small window
(ADR-044 rev, 2026-09-24). The daily flow on the tab is band,
apertures, Suggest; the rest (sky model, sigma-clip, seeing-sized
apertures, colour term, host-galaxy subtraction) lives here, non-modal,
so the observer can keep measuring while it stays open.

The Measure tab owns the behaviour: it reads the widgets through the
public attributes it aliases and wires every signal itself (the dialog
stays a dumb container, which keeps the pinned tests in place).

ADR-005 restored (2026-09-25): the structure lives in
ui/ufe_advanced_dialog.ui; this class loads it and fills the sky
combo (its items carry userData, which a Designer file cannot hold).
"""

from PySide6.QtWidgets import QDialog

from .ui_loader import load_ui


class UfeAdvancedDialog(QDialog):
    # @args: parent - the UfeMeasureTab that owns the behaviour
    # @return: the dialog with the recipe controls, one click per knob
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Advanced"))
        self.setMinimumWidth(420)
        self._ui = load_ui("ufe_advanced_dialog", self)
        self.setLayout(self._ui.layout())   # the .ui's own layout takes
                                            # over: no wrapper, no extra
                                            # margins
        self.cmb_sky = self._ui.cmb_sky
        self.cmb_sky.addItem(self.tr("Median (flat sky)"), "median")
        self.cmb_sky.addItem(self.tr("Plane (galactic cores)"), "plane")
        self.chk_sigmaclip = self._ui.chk_sigmaclip
        self.chk_seeing = self._ui.chk_seeing
        self.chk_color = self._ui.chk_color
        self.spn_target_bv = self._ui.spn_target_bv
        self.chk_subtract = self._ui.chk_subtract
