############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Explore object entry dialog module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Explore object entry dialog (2026-10-08): a small form that collects
the object's name and says, in one line, what Explore is for. It replaces
the bare QInputDialog that asked for the name with no context at all.

The lookup is untouched. The dialog only returns a name, and MainWindow
hands it to the same `_open_explore_dialog` (core/enrich, ExploreWorker and
ObjectPanel are not involved here): the always-visible top-bar search is the
quick door for whoever already knows what to type, and this dialog is the
door that explains itself, opened from Tools > Explore object.

ADR-005: the structure lives in ui/explore_dialog.ui; this class only
dresses the window and exposes the widgets.
"""

from PySide6.QtWidgets import QDialog

from . import theme
from .ui_loader import adopt_ui


class ExploreDialog(QDialog):
    # @args: parent - the owning window
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Explore object"))
        self._ui = adopt_ui(self, "explore_dialog")
        self.edt_name = self._ui.edt_name
        self.btn_explore = self._ui.btn_explore
        self.btn_cancel = self._ui.btn_cancel
        # Enter in the field and the button are the same gesture; an empty
        # name is not accepted (nothing to look up), so the dialog stays put
        self.edt_name.returnPressed.connect(self._accept)
        self.btn_explore.clicked.connect(self._accept)
        self.btn_cancel.clicked.connect(self.reject)
        # the one action of the form wears the accent, the way the panel
        # CTAs do; it is small on purpose (this is a form, not a landing)
        self.btn_explore.setStyleSheet(
            f"QPushButton {{ background: {theme.C_SEL}; color: #ffffff;"
            f" border: 1px solid {theme.C_ACCENT}; border-radius: 4px;"
            f" padding: 6px 18px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {theme.C_ACCENT};"
            f" color: #0b0d12; }}")
        self.setMinimumWidth(440)
        self.adjustSize()
        self.edt_name.setFocus()

    def name(self):
        # @return: the trimmed name the observer typed ("" when empty)
        return self.edt_name.text().strip()

    def _accept(self):
        # An empty name has nothing to look up: keep the dialog open so the
        # observer can type or cancel, instead of closing on a no-op.
        if not self.name():
            return
        self.accept()
