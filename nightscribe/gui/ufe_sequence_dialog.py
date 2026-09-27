############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: sequence dialog (ADR-044 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The UFE Compare section's sequence table in one small window
(ADR-044 rev, 2026-09-24). The tab stays compact: name, target
magnitude, the field/DSS2 buttons, the click mode and the
Sequence (N) button that raises this window.

The Compare tab owns the behaviour: it rebuilds the table through
_reload_table (which runs against this dialog's QTableWidget) and
aliases it as its own public .table so the pinned tests keep working.
Since 2026-09-25 the "Remove all" and "Export CSV…" actions live
here, under the table they act on (the tab keeps btn_clear / btn_csv
aliases pointing at these buttons).

ADR-005 restored (2026-09-25): the structure lives in
ui/ufe_sequence_dialog.ui; this class loads it, hides the action
buttons nobody wired, and connects the rest.
"""

from PySide6.QtWidgets import QDialog

from .ui_loader import adopt_ui


class UfeSequenceDialog(QDialog):
    # @args: parent - the UFE Compare tab that owns the behaviour,
    #        on_clear - the tab's "Remove all" action, shown as a
    #        button under the table, on_export - its "Export CSV…"
    #        action (either may be None to hide the button)
    # @return: the dialog with the sequence table, ready to rebuild
    def __init__(self, parent=None, on_clear=None, on_export=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Sequence"))
        self.setMinimumSize(420, 240)
        # the structure is the Designer file's (ADR-005); the code keeps
        # the window dressing and the callback wiring
        self._ui = adopt_ui(self, "ufe_sequence_dialog")
                                            # over: no wrapper, no extra
                                            # margins, tests see the
                                            # structure directly
        self.table = self._ui.table
        self.btn_clear = self._ui.btn_clear
        self.btn_export = self._ui.btn_export
        for btn, cb in ((self.btn_clear, on_clear),
                        (self.btn_export, on_export)):
            if cb is None:
                btn.setVisible(False)
            else:
                btn.clicked.connect(cb)
