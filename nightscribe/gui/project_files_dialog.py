############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Project files module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The project files window: the current project's registered files,
in their own dialog off the Projects masthead's "Files (n)" button.
One table (kind, name, date, size) with a per-row menu; FITS plates
(the "fits" and "image" kinds) open in the Unified FITS Editor with
the project's object attached, anything else opens with the OS.
The old collapsed "Project files" section in the Details tab is
retired: this window is the single entry (ADR-019, UX v3).
"""

import math
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QApplication,
                               QDialog, QHeaderView,
                               QLabel, QMenu, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout)

# Kinds the editor can load directly: a plate, or an annotated copy of one.
FITS_KINDS = ("fits", "image")


class ProjectFilesDialog(QDialog):
    # A row asked to be opened. MainWindow owns both routes and wires
    # the project's object (name, sky position, mag, B-V) onto the
    # editor on the "ufe" one (ADR-044).
    sig_open_ufe = Signal(str)
    sig_open_os = Signal(str)

    # @args: parent - widget (the main window, so it stays with the app)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._rows = []          # one file dict per table row
        self.setWindowTitle(self.tr("Project files"))
        self._build_ui()
        self.resize(760, 440)

    # ------------------------------------------------------------- layout

    def _build_ui(self):
        # One table (kind, name, date, size, per-row menu) + the
        # empty-state line.
        lay = QVBoxLayout(self)
        self.lbl_status = QLabel("")
        self.lbl_status.setVisible(False)
        lay.addWidget(self.lbl_status)
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(
            [self.tr("Kind"), self.tr("Name"), self.tr("Date"),
             self.tr("Size"), ""])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.itemDoubleClicked.connect(self._on_row_activated)
        self.tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._on_context)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        lay.addWidget(self.tbl, 1)

    # ------------------------------------------------------------- data

    @property
    def project_id(self):
        # @return: the attached project id, or None with no project
        return self._project["id"] if self._project else None

    def set_project(self, project):
        # @args: project - the project dict (id, object_name) or None
        # @return: None. The dialog title carries the object name.
        self._project = project
        if project and project.get("object_name"):
            self.setWindowTitle(
                "{} · {}".format(self.tr("Project files"),
                                 project["object_name"]))
        else:
            self.setWindowTitle(self.tr("Project files"))

    def set_files(self, files):
        # @args: files - list of core/project.py file dicts
        #        (id, path, kind, created); order as registered
        # @return: None. Redraws the table and the empty state.
        rows = list(files or [])
        self._rows = rows
        self.tbl.setRowCount(0)
        if not rows:
            self.lbl_status.setText(
                self.tr("No files registered for this project yet."))
            self.lbl_status.setVisible(True)
            return
        self.lbl_status.setVisible(False)
        for f in rows:
            self._add_row(f)

    def _row_file(self, row):
        # @args: row - table row index
        # @return: the file dict, or None out of range
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def _add_row(self, f):
        # One file dict -> one table row (kind, name, date, size, menu).
        idx = self.tbl.rowCount()
        self.tbl.insertRow(idx)
        dt = datetime.fromtimestamp(f["created"])
        for col, text in enumerate(
                [f["kind"], Path(f["path"]).name,
                 dt.strftime("%Y-%m-%d"), self._size(str(f["path"]))]):
            item = QTableWidgetItem(text)
            if col == 1:
                item.setData(Qt.UserRole, str(f["path"]))
            self.tbl.setItem(idx, col, item)
        btn = QToolButton()
        btn.setText("⋯")
        btn.setToolTip(self.tr("Open this file, or other options…"))
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setMenu(self._row_menu(f, parent=btn))
        self.tbl.setCellWidget(idx, 4, btn)

    def _size(self, path):
        # @args: path - file path string
        # @return: a short human size, or "" when the file is gone
        try:
            n = float(Path(path).stat().st_size)
        except OSError:
            return ""
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024 or unit == "TB":
                whole = math.floor(n)
                if n >= 1000 or whole == int(n):
                    return f"{whole} {unit}"
                return f"{n:.1f} {unit}"
            n /= 1024
        return ""

    # ------------------------------------------------------------- actions

    def is_fits(self, f):
        # @args: f - one file dict (or None)
        # @return: True when the editor can load it as a plate
        return bool(f) and f.get("kind") in FITS_KINDS

    def _row_menu(self, f, parent=None):
        # @args: f - the file dict, parent - widget (the row button,
        #        or None for the transient right-click menu)
        # @return: the row's QMenu: plates get the editor first,
        #          everyone gets system / folder / copy path
        menu = QMenu(parent)
        if self.is_fits(f):
            a = menu.addAction(self.tr("Open in the FITS editor"))
            a.triggered.connect(lambda: self.sig_open_ufe.emit(f["path"]))
            menu.addSeparator()
        a = menu.addAction(self.tr("Open with the system"))
        a.triggered.connect(lambda: self.sig_open_os.emit(f["path"]))
        a = menu.addAction(self.tr("Show in folder"))
        a.triggered.connect(lambda: self.show_in_folder(f["path"]))
        a = menu.addAction(self.tr("Copy path"))
        a.triggered.connect(lambda: self.copy_path(f["path"]))
        return menu

    def _on_row_activated(self, item):
        # Double-click a row: plates go to the editor, the rest to the OS.
        f = self._row_file(self.tbl.row(item))
        if not f:
            return
        if self.is_fits(f):
            self.sig_open_ufe.emit(f["path"])
        else:
            self.sig_open_os.emit(f["path"])

    def _on_context(self, pos):
        # Right-click a row: the same menu as the ⋯ button, at the cursor.
        row = self.tbl.rowAt(pos.y())
        f = self._row_file(row)
        if not f:
            return
        menu = self._row_menu(f)
        menu.exec(self.tbl.viewport().mapToGlobal(pos))

    def show_in_folder(self, path):
        # "Show in folder": the file's parent in the OS file manager.
        # @args: path - file path string
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def copy_path(self, path):
        # "Copy path": the full path to the clipboard.
        # @args: path - file path string
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(str(path))
