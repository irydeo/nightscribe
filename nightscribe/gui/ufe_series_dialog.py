############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - The series' chart window module (U6)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The series' chart and quality controls, in their own window (U6).

The left panel of the workbench had thirty controls stacked in a 300 px
column, seventeen of them about how the curve is DRAWN: the scale, the
error bars, the binning, the outliers. Those are not what an observer
touches while measuring; they are what an observer touches while LOOKING,
and looking happens in the centre of the window, at the curve.

So they live here now, non-modal, in the same spirit as "Advanced recipe…"
and "Sequence (N)…": open it, leave it open, move the window where it does
not cover the curve. The panel keeps the action and this dialog keeps the
knobs, and the knobs are the same widgets (same names, same wiring), so
nothing had to be learned again.
"""

import logging

from PySide6.QtWidgets import QDialog

from .ui_loader import adopt_ui

logger = logging.getLogger(__name__)


class UfeSeriesDialog(QDialog):
    # The chart and quality controls of the photometric series. It owns no
    # logic: the Measure tab wires every control to the chart it measures
    # into (that is where the data is), and this window only gives them a
    # place where they can be read.
    #
    # @args: parent - the owning window

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ui = adopt_ui(self, "ufe_series_dialog")
        self.setWindowTitle(self.tr("Chart and quality"))
        # the window sizes itself to its content: it arrived with the
        # Designer's default and the third block was cut off (reported).
        # A minimum keeps it sane if a style reports odd metrics.
        self.setMinimumWidth(470)
        self.adjustSize()
        hint = self.sizeHint()
        self.resize(max(470, hint.width() + 20),
                    max(360, hint.height() + 20))
        # the controls, by name: the Measure tab reads them from here and
        # wires them exactly as it did (see UfeMeasureTab.__init__)
        self.cmb_series_scale = self._ui.cmb_series_scale
        self.btn_series_robust = self._ui.btn_series_robust
        self.btn_series_fixaxis = self._ui.btn_series_fixaxis
        self.spn_series_maglo = self._ui.spn_series_maglo
        self.spn_series_maghi = self._ui.spn_series_maghi
        self.btn_series_zoomfit = self._ui.btn_series_zoomfit
        self.btn_series_errors = self._ui.btn_series_errors
        self.btn_series_hideflags = self._ui.btn_series_hideflags
        self.btn_series_quality = self._ui.btn_series_quality
        self.cmb_series_bin = self._ui.cmb_series_bin
        self.spn_series_binn = self._ui.spn_series_binn
        self.chk_series_mean = self._ui.chk_series_mean
        self.spn_series_meanwin = self._ui.spn_series_meanwin
        self.chk_series_outliers = self._ui.chk_series_outliers
        self.spn_series_outsigma = self._ui.spn_series_outsigma
        self.btn_series_exclout = self._ui.btn_series_exclout
        self.btn_series_exclsel = self._ui.btn_series_exclsel
        self.btn_series_restore = self._ui.btn_series_restore
        self.lbl_series_selection = self._ui.lbl_series_selection

    def show_nonmodal(self):
        # The window rises without blocking the workbench: the point of
        # having it is to keep looking at the curve while changing how it
        # is drawn.
        # @return: None
        self.show()
        self.raise_()
        self.activateWindow()
