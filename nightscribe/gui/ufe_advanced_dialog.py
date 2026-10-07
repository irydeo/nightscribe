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

from .ui_loader import adopt_ui


class UfeAdvancedDialog(QDialog):
    # @args: parent - the UfeMeasureTab that owns the behaviour
    # @return: the dialog with the recipe controls, one click per knob
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Advanced"))
        self.setMinimumWidth(420)
        self._ui = adopt_ui(self, "ufe_advanced_dialog")
                                            # over: no wrapper, no extra
                                            # margins
        self.cmb_sky = self._ui.cmb_sky
        self.cmb_sky.addItem(self.tr("Median (flat sky)"), "median")
        self.cmb_sky.addItem(self.tr("Plane (galactic cores)"), "plane")
        self.chk_sigmaclip = self._ui.chk_sigmaclip
        self.chk_seeing = self._ui.chk_seeing
        # P3 de la campana de SNR: medir con el filtro adaptado (el objetivo
        # Y las comparsas), para que el cero punto salga del mismo metodo
        self.chk_matched = self._ui.chk_matched
        self.chk_color = self._ui.chk_color
        self.spn_target_bv = self._ui.spn_target_bv
        self.chk_subtract = self._ui.chk_subtract
        # series knobs (series plan, phase 5): group_n, detrend policy,
        # per-night aperture sweep and the saturation ceiling
        self.spn_group_n = self._ui.spn_group_n
        self.cmb_align = self._ui.cmb_align
        # Auto is the honest default: a visit's frames rarely sit on the
        # same pixels, and measuring them as if they did is how a series
        # is lost (see the V0526 Per case in docs/PLANS/series-quality.md)
        self.cmb_align.addItem(self.tr("Auto (recommended)"), "auto")
        self.cmb_align.addItem(self.tr("Off (frames already aligned)"),
                               "off")
        self.cmb_align.addItem(self.tr("Translation only"), "translation")
        self.cmb_align.addItem(self.tr("Rotation and translation"),
                               "similarity")
        self.cmb_detrend = self._ui.cmb_detrend
        self.cmb_detrend.addItem(self.tr("Off (raw curve)"), "off")
        self.cmb_detrend.addItem(self.tr("Airmass (minimum)"), "airmass")
        self.cmb_detrend.addItem(self.tr("Auto (FWHM, sky, x-y)"), "auto")
        self.chk_auto_aperture = self._ui.chk_auto_aperture
        self.spn_saturate = self._ui.spn_saturate
        # the line that says what "0 = auto" resolves to (header card,
        # Ajustes or the camera profile's linearity)
        self.lbl_saturate_auto = self._ui.lbl_saturate_auto
        self.btn_restore = self._ui.btn_restore
