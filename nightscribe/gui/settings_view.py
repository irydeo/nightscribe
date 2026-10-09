############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Settings: the rail, the search and the disclosures (ADR-071)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The moving parts of the reorganized Settings dialog.

The `.ui` carries the structure: a rail (`lst_categories`), a stack of
scrollable pages (`stk_pages`) and the groups inside their page. This module
does the three things that are behaviour and not layout:

* fills the rail from `settings_spec.CATEGORIES` and ties it to the stack;
* turns a group into a disclosure (advanced groups open collapsed), so the
  common path stays short;
* indexes every field row (its label + its help) and filters the pages as
  the observer types in `edt_search`.

Everything is offscreen and testable: no network, no MainWindow.
"""

import unicodedata

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QGroupBox, QLabel, QLineEdit, QListView,
                               QListWidgetItem, QPlainTextEdit, QSpinBox,
                               QTableWidget, QToolButton, QVBoxLayout, QWidget)

_FIELD_TYPES = (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
                QPlainTextEdit, QTableWidget)


def style_help_labels(dlg):
    # Every lblH_* is the help that sits BELOW its field: 11 px, dim,
    # word-wrapped. It used to be styled by on_open_settings; it lives here
    # with the rest of the dialog's behaviour (ADR-028 kept, ADR-071).
    # @args: dlg - the loaded settings dialog
    # @return: None
    for w in dlg.findChildren(QLabel):
        if w.objectName().startswith("lblH_"):
            w.setStyleSheet("font-size: 11px; color: #8a90a6;")
            w.setWordWrap(True)


def _rail_icon(theme, stem):
    # @args: theme - the theme module, stem - the asset stem
    # @return: a QIcon whose Normal mode is the dim icon and whose Selected
    #          mode is the accent one, so Qt paints the bright variant on
    #          the active row by itself (the pair the UFE already uses).
    #          Null when the idle asset is missing (the caller falls back
    #          to the text).
    from PySide6.QtGui import QIcon
    idle = theme.asset(stem + ".svg")
    if not idle.exists():
        return QIcon()
    icon = QIcon()
    icon.addFile(idle.as_posix(), QSize(24, 24), QIcon.Normal)
    active = theme.asset(stem + "_on.svg")
    if active.exists():
        icon.addFile(active.as_posix(), QSize(24, 24), QIcon.Selected)
    return icon


def build_rail(dlg, categories, tr):
    # Fills the left rail with one ICON per category (ADR-071) and ties it
    # to the stacked pages, so the observer picks a task and the page
    # follows. The name survives as the tooltip and the accessible name:
    # an icon-only rail must say what it is on hover. A missing asset falls
    # back to the text, so the rail never goes mute.
    # @args: dlg - the dialog, categories - [(page, label, svg stem)],
    #        tr - self.tr
    # @return: None
    from . import theme
    rail = dlg.lst_categories
    rail.clear()
    rail.setViewMode(QListView.IconMode)
    rail.setFlow(QListView.TopToBottom)
    rail.setMovement(QListView.Static)
    rail.setResizeMode(QListView.Adjust)
    rail.setUniformItemSizes(True)
    rail.setSpacing(4)
    rail.setIconSize(QSize(24, 24))
    rail.setWordWrap(False)
    rail.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    for _page, label, stem in categories:
        name = tr(label)
        item = QListWidgetItem()
        icon = _rail_icon(theme, stem)
        if icon.isNull():
            item.setText(name)
        else:
            item.setIcon(icon)
        item.setToolTip(name)
        item.setData(Qt.AccessibleTextRole, name)
        item.setSizeHint(QSize(52, 52))
        item.setTextAlignment(Qt.AlignCenter)
        rail.addItem(item)
    rail.setCurrentRow(0)
    rail.currentRowChanged.connect(
        lambda row: dlg.stk_pages.setCurrentIndex(max(0, row)))
    dlg.stk_pages.setCurrentIndex(0)


def make_collapsible(group, collapsed=True):
    # Wraps a group's content behind a clickable header. The group's title
    # becomes the header's text and the native title is cleared, so the box
    # reads as one line until it is opened: the rare knobs are one click
    # away instead of on the common path.
    # @args: group - a QGroupBox, collapsed - start closed?
    # @return: the header button (its checked state is "open")
    old = group.layout()
    if old is None:
        return None
    content = QWidget(group)
    content.setObjectName(group.objectName() + "_content")
    cbox = QVBoxLayout(content)
    cbox.setContentsMargins(0, 0, 0, 0)
    while old.count():
        item = old.takeAt(0)
        w = item.widget()
        if w is not None:
            cbox.addWidget(w)
        else:
            lay = item.layout()
            if lay is not None:
                cbox.addLayout(lay)
    title = group.title()
    header = QToolButton(group)
    header.setObjectName(group.objectName() + "_header")
    header.setCheckable(True)
    header.setChecked(not collapsed)
    header.setStyleSheet(
        "QToolButton { border: none; font-weight: bold; text-align: left; }")
    header.setToolButtonStyle(Qt.ToolButtonTextOnly)

    def refresh():
        header.setText(("\u25be " if header.isChecked() else "\u25b8 ") + title)
        content.setVisible(header.isChecked())

    header.toggled.connect(lambda _on: refresh())
    group.setTitle("")
    old.addWidget(header)
    old.addWidget(content)
    refresh()
    return header


def _norm(text):
    # @args: text - any string
    # @return: lowercase without accents, so "acimut" finds "Acimut" and
    #          "atmosfera" finds "atmósfera" (the observer should not have
    #          to type the accent to find a field)
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _index_units(dlg):
    # @args: dlg - the dialog
    # @return: one unit per field row: the objectNames to hide/show and the
    #          text the search reads (the group title + the row's labels +
    #          the help that follows it)
    units = []
    for group in dlg.findChildren(QGroupBox):
        # an advanced group is already a disclosure: its rows live inside
        # the <group>_content widget, not directly in the group's layout
        content = group.findChild(QWidget, group.objectName() + "_content")
        lay = content.layout() if content is not None else group.layout()
        if lay is None:
            continue
        title = group.title()
        if not title:
            # a collapsed group's title moved to its header button, so the
            # search still reads it there (strip the disclosure arrow)
            header = group.findChild(QToolButton,
                                     group.objectName() + "_header")
            if header is not None:
                title = header.text().lstrip("\u25be\u25b8 ").strip()
        current = None
        for i in range(lay.count()):
            item = lay.itemAt(i)
            w = item.widget()
            if isinstance(w, QLabel) and w.objectName().startswith("lblH_"):
                if current is not None:
                    current["text"] += " " + w.text()
                    current["names"].append(w.objectName())
                continue
            names = []
            labels = []

            def walk(it):
                ww = it.widget()
                if ww is not None:
                    names.append(ww.objectName())
                    if isinstance(ww, QLabel):
                        labels.append(ww.text())
                    return
                sub = it.layout()
                if sub is not None:
                    for j in range(sub.count()):
                        walk(sub.itemAt(j))

            walk(item)
            if not names:
                continue
            current = {"text": title + " " + " ".join(labels),
                       "names": names, "group": group.objectName()}
            units.append(current)
    return units


def wire_search(dlg, no_results):
    # Filters the field rows as the observer types: a row stays when the
    # query appears in its label, its help or its group's title (accent and
    # case insensitive). A group with no match hides; if the shown page has
    # no match but another does, the rail jumps to the first one; if nothing
    # matches anywhere, a quiet line says so.
    # @args: dlg - the dialog, no_results - the quiet line's text (already
    #        translated; it lives in main_window so lupdate sees it in the
    #        MainWindow context)
    # @return: the index, in case a test wants it
    units = _index_units(dlg)
    group_page = {}
    for i in range(dlg.stk_pages.count()):
        page = dlg.stk_pages.widget(i).widget()
        for g in page.findChildren(QGroupBox):
            group_page[g.objectName()] = i
    headers = {h.objectName()[:-len("_header")]: h
               for h in dlg.findChildren(QToolButton)
               if h.objectName().endswith("_header")}
    default_open = {name: h.isChecked() for name, h in headers.items()}

    note = QLabel(no_results, dlg)
    note.setObjectName("lbl_no_results")
    note.setAlignment(Qt.AlignCenter)
    note.setVisible(False)
    # under the search box, above the rail + pages
    dlg.layout().insertWidget(1, note)

    def apply():
        query = _norm(dlg.edt_search.text().strip())
        group_ok = {}
        for unit in units:
            ok = (not query) or (query in _norm(unit["text"]))
            for name in unit["names"]:
                w = getattr(dlg, name, None)
                if w is not None:
                    w.setVisible(ok)
            group_ok[unit["group"]] = group_ok.get(unit["group"], False) or ok
        for name, ok in group_ok.items():
            g = getattr(dlg, name, None)
            if g is not None:
                g.setVisible(ok)
            header = headers.get(name)
            if header is not None:
                # a matching advanced group opens itself while searching,
                # and goes back to its default when the box is cleared
                header.setChecked(True if (query and ok)
                                  else default_open.get(name, True))
        page_ok = {}
        for name, ok in group_ok.items():
            page = group_page.get(name)
            if page is not None:
                page_ok[page] = page_ok.get(page, False) or ok
        if query and not page_ok.get(dlg.stk_pages.currentIndex(), False):
            for i in range(dlg.stk_pages.count()):
                if page_ok.get(i):
                    dlg.stk_pages.setCurrentIndex(i)
                    dlg.lst_categories.setCurrentRow(i)
                    break
        note.setVisible(bool(query) and not any(page_ok.values()))

    dlg.edt_search.textChanged.connect(lambda _t: apply())
    return units
