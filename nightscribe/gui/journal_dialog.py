############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Observing journal dialog (ADR-036, J2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The observing journal dialog (ADR-036, J2): the derived journal of
core/journal.py, grouped by observing night, with a kind filter and a
search box. Read-only; double-clicking an entry jumps to its project (or
explores the object) through the caller's callback. The structure is
ui/journal_dialog.ui (ADR-005, restored 2026-09-25).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QListWidgetItem

from ..core import journal
from .ui_loader import load_ui

_DAYS = 90        # the journal shows the last ~three months


class JournalDialog(QDialog):
    # @args: db_obj - Database, lang - "es" | "en", on_open_object -
    #        callable(name, project_id|None) for the double-click jump,
    #        parent - parent widget

    def __init__(self, db_obj, lang="es", on_open_object=None,
                 parent=None):
        super().__init__(parent)
        self._db = db_obj
        self._lang = lang
        self._on_open = on_open_object
        self.setWindowTitle(self.tr("Observing journal"))
        # the structure is the Designer file's (ADR-005); the kind
        # combo's items carry userData and are filled here
        self._ui = load_ui("journal_dialog", self)
        self.setLayout(self._ui.layout())   # no wrapper, no extra margins
        self.cmb_kind = self._ui.cmb_kind
        self.cmb_kind.addItem(self.tr("All kinds"), None)
        for k in (journal.K_PROJECT, journal.K_SESSION, journal.K_FILE,
                  journal.K_PHOTOMETRY, journal.K_CAMPAIGN,
                  journal.K_OBSERVATION):
            self.cmb_kind.addItem(journal.kind_label(k, lang), k)
        self.edt_search = self._ui.edt_search
        self.lst = self._ui.lst
        self.lst.viewport().setCursor(Qt.PointingHandCursor)
        self._ui.buttonBox.rejected.connect(self.reject)
        self.resize(720, 520)
        self.cmb_kind.currentIndexChanged.connect(self._render)
        self.edt_search.textChanged.connect(self._render)
        self.lst.itemActivated.connect(self._entry_activated)
        self._nights = []
        self.refresh()

    def refresh(self):
        # Rebuilds from the database and re-renders (keeps the filter).
        self._nights = journal.build_journal(self._db, days=_DAYS)
        self._render()

    def _render(self):
        # Paints nights as non-selectable header rows (the projects hub
        # pattern), events as "HH:MM · object — text" rows.
        want_kind = self.cmb_kind.currentData()
        search = self.edt_search.text().strip().lower()
        idx = 0 if self._lang == "es" else 1
        self.lst.clear()
        for n in self._nights:
            events = [e for e in n["events"]
                      if (want_kind is None or e["kind"] == want_kind)
                      and (not search or search in e["object"].lower())]
            if not events:
                continue
            header = QListWidgetItem(f"— {n['night']} —")
            header.setFlags(Qt.NoItemFlags)
            from PySide6.QtGui import QColor
            from . import theme
            header.setForeground(QColor(theme.C_TEXT_DIM))
            self.lst.addItem(header)
            for e in events:
                item = QListWidgetItem(
                    f"{journal.hm_local(e['ts'])} · {e['object']} — "
                    f"{e['text'][idx]}")
                item.setData(Qt.UserRole, e["project_id"])
                item.setData(Qt.UserRole + 1, e["object"])
                self.lst.addItem(item)
        if self.lst.count() == 0:
            empty = QListWidgetItem(self.tr("No activity recorded yet"))
            empty.setFlags(Qt.NoItemFlags)
            self.lst.addItem(empty)

    def _entry_activated(self, item):
        # Double-click/Enter on an entry: hand the jump to the owner.
        # Header and empty-state rows carry no data: no-ops.
        if item is None or item.data(Qt.UserRole + 1) is None:
            return
        if self._on_open is not None:
            self._on_open(item.data(Qt.UserRole + 1),
                          item.data(Qt.UserRole))
