############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Campaign manager dialog module (ADR-035)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The campaign manager (V-j): one modal dialog listing the active and
finished campaigns with their CRUD, reachable from the Tools menu and the
Projects hub. All persistence goes through core/campaign.py; the dialog
never touches the network.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QGroupBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout)

from ..core import campaign
from ..core.db import db

logger = logging.getLogger(__name__)


class CampaignsDialog(QDialog):
    # @args: parent - QWidget, db_obj - Database (tests inject a temp one)
    def __init__(self, parent=None, db_obj=None):
        super().__init__(parent)
        self._db = db_obj or db
        self.setWindowTitle(self.tr("Campaigns"))
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        self.grp_active = QGroupBox(self.tr("Active campaigns"))
        self.grp_active.setLayout(QVBoxLayout())
        self.lst_active = QListWidget()
        self.grp_active.layout().addWidget(self.lst_active)
        layout.addWidget(self.grp_active)
        self.grp_finished = QGroupBox(self.tr("Finished campaigns"))
        self.grp_finished.setLayout(QVBoxLayout())
        self.lst_finished = QListWidget()
        self.grp_finished.layout().addWidget(self.lst_finished)
        layout.addWidget(self.grp_finished)
        row = QHBoxLayout()
        self.btn_new = QPushButton(self.tr("New campaign…"))
        self.btn_edit = QPushButton(self.tr("Edit…"))
        self.btn_finish = QPushButton(self.tr("Finish"))
        self.btn_reopen = QPushButton(self.tr("Reopen"))
        self.btn_close = QPushButton(self.tr("Close"))
        for b in (self.btn_new, self.btn_edit, self.btn_finish,
                  self.btn_reopen):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.btn_close)
        layout.addLayout(row)
        self.btn_close.clicked.connect(self.accept)
        self.btn_finish.clicked.connect(self._finish_selected)
        self.btn_reopen.clicked.connect(self._reopen_selected)
        self.lst_active.itemSelectionChanged.connect(self._sync_buttons)
        self.lst_finished.itemSelectionChanged.connect(self._sync_buttons)
        self._reload()
        self._sync_buttons()

    # ---------------- data ----------------

    def _reload(self):
        # @return: None — refills both lists from the db
        for lst, status in ((self.lst_active, campaign.CAMPAIGN_ACTIVE),
                            (self.lst_finished, campaign.CAMPAIGN_FINISHED)):
            lst.clear()
            for c in campaign.list_campaigns(self._db, status):
                label = c["name"]
                if c.get("group_name"):
                    label += f"  ({c['group_name']})"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, c["id"])
                lst.addItem(item)

    def _selected_id(self, lst):
        # @return: campaign id of the list selection, or None
        item = lst.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    # ---------------- actions ----------------

    def _sync_buttons(self):
        # @return: None — enables each action only for its own list
        self.btn_finish.setEnabled(self._selected_id(self.lst_active)
                                   is not None)
        self.btn_reopen.setEnabled(self._selected_id(self.lst_finished)
                                   is not None)
        self.btn_edit.setEnabled(self._selected_id(self.lst_active)
                                 is not None)

    def _finish_selected(self):
        # @return: None — moves the picked active campaign to finished
        cid = self._selected_id(self.lst_active)
        if cid is not None:
            campaign.finish(self._db, cid)
            self._reload()

    def _reopen_selected(self):
        # @return: None — moves the picked finished campaign back to active
        cid = self._selected_id(self.lst_finished)
        if cid is not None:
            campaign.reopen(self._db, cid)
            self._reload()
