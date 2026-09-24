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
"""

from PySide6.QtWidgets import QDialog, QTableWidget, QVBoxLayout


class UfeSequenceDialog(QDialog):
    # @args: parent - the UfeCompareTab that owns the behaviour
    # @return: the dialog with the sequence table, ready to rebuild
    def __init__(self, parent=None):
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
