############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: published observations dialog (ADR-077)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The published observations the Find_Orb check compares us with, in their
own non-modal window (ADR-077).

The check block is a narrow column (about 380 px): the whole listing, with
the instant, the station, the direction and the two residuals of every
published observation, does not fit there without pushing the rest of the
panel out. It lives in this window instead, opened by the block's button,
and it can stay open beside the work while the observer reads it.

The Astrometry tab owns the behaviour: it fills the table, keeps the window
as its own attribute and shows it. The dialog stays a dumb container, like
the manual-centre and manual-stack ones (ADR-044 rev, ADR-065).

ADR-005: the structure lives in ui/ufe_published_obs_dialog.ui; this class
only dresses the window (title, non-modal, size) and exposes the widgets.
"""

from PySide6.QtWidgets import QDialog

from .ui_loader import adopt_ui


class UfePublishedObsDialog(QDialog):
    # @args: parent - the UfeTrackStackTab that owns the behaviour
    # @return: the dialog with the hint and the published observations' table

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Published observations"))
        self.setModal(False)
        self._ui = adopt_ui(self, "ufe_published_obs_dialog")
        self.lbl_residuals_hint = self._ui.lbl_residuals_hint
        self.tbl_residuals = self._ui.tbl_residuals
        # a listing of seven columns needs room: the tab it opens from is a
        # 380 px panel, so the window starts wide and tall enough to read a
        # night's worth of observations without scrolling sideways
        self.setMinimumWidth(560)
        self.resize(720, 460)
