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
"""

from PySide6.QtWidgets import (QDialog, QHBoxLayout, QPushButton,
                               QTableWidget, QVBoxLayout)


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
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [self.tr("Name"), self.tr("Type"), self.tr("Mag"), ""])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        # ADR-044 rev (2026-09-25): the actions live with the table,
        # not on the tab; the Compare tab exposes them as btn_clear
        # and btn_csv so old code and the pinned tests still find them
        row = QHBoxLayout()
        if on_clear is not None:
            self.btn_clear = QPushButton(self.tr("Remove all"))
            self.btn_clear.clicked.connect(on_clear)
            row.addWidget(self.btn_clear)
        if on_export is not None:
            self.btn_export = QPushButton(self.tr("Export CSV…"))
            self.btn_export.clicked.connect(on_export)
            row.addWidget(self.btn_export)
        row.addStretch(1)
        lay.addLayout(row)
