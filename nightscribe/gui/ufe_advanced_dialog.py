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
"""

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QHBoxLayout, QLabel,
                               QVBoxLayout)


class UfeAdvancedDialog(QDialog):
    # @args: parent - the UfeMeasureTab that owns the behaviour
    # @return: the dialog with the recipe controls, one click per knob
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Advanced"))
        self.setMinimumWidth(420)
        self._build()

    def _build(self):
        # @return: the dialog populated with the six recipe controls
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Sky:")))
        self.cmb_sky = QComboBox()
        self.cmb_sky.addItem(self.tr("Median (flat sky)"), "median")
        self.cmb_sky.addItem(self.tr("Plane (galactic cores)"), "plane")
        self.cmb_sky.setToolTip(self.tr(
            "How the annulus estimates the background: a flat median, or "
            "a tilted plane when the host galaxy tilts it"))
        row.addWidget(self.cmb_sky, 1)
        lay.addLayout(row)

        self.chk_sigmaclip = QCheckBox(self.tr("Sigma-clip the sky"))
        self.chk_sigmaclip.setChecked(True)
        self.chk_sigmaclip.setToolTip(self.tr(
            "Two 2.5-sigma rounds on the annulus: extra skin against hot "
            "pixels and crowded cores"))
        lay.addWidget(self.chk_sigmaclip)

        self.chk_seeing = QCheckBox(self.tr("Aperture follows the seeing"))
        self.chk_seeing.setChecked(True)
        self.chk_seeing.setToolTip(self.tr(
            "Measure the FWHM of the comparison stars and size the "
            "aperture as 1.35 times the seeing (H3)"))
        lay.addWidget(self.chk_seeing)

        row = QHBoxLayout()
        self.chk_color = QCheckBox(self.tr("Colour term"))
        self.chk_color.setChecked(True)
        self.chk_color.setToolTip(self.tr(
            "Fit the zero point AND its slope against the comps' B−V "
            "(H1); needs at least 6 comps with colour spread"))
        row.addWidget(self.chk_color)
        row.addWidget(QLabel(self.tr("B−V target:")))
        self.spn_target_bv = QDoubleSpinBox()
        self.spn_target_bv.setRange(-1.0, 3.0)
        self.spn_target_bv.setDecimals(2)
        self.spn_target_bv.setSingleStep(0.05)
        self.spn_target_bv.setValue(0.0)
        self.spn_target_bv.setToolTip(self.tr(
            "The target's B−V when known (variables: VSX). A supernova "
            "near peak is about 0; the panel warns when the colour term "
            "is applied with this assumption"))
        self.spn_target_bv.setKeyboardTracking(False)
        row.addWidget(self.spn_target_bv)
        lay.addLayout(row)

        self.chk_subtract = QCheckBox(self.tr(
            "Subtract host galaxy (PS1 reference)"))
        self.chk_subtract.setToolTip(self.tr(
            "Download the aligned PanSTARRS reference, scale it so the "
            "comparison stars vanish, and measure the target on the "
            "difference image (H2b; needs network once per field)"))
        lay.addWidget(self.chk_subtract)
        lay.addStretch(1)
