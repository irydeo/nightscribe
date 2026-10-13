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
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QListWidgetItem, QPlainTextEdit,
                               QSpinBox, QTableWidget,
                               QVBoxLayout, QWidget)

from . import theme

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


def make_titled(group, hue=None):
    # Give a group a TITLE BAR and leave its content ALWAYS visible (ADR-071
    # rev): the title is a filled strip (a soft tint of the accent) with the
    # title in the accent, so adjacent groups do not read as one continuous
    # list. There is NO fold control and no chip: just the title.
    # @args: group - a QGroupBox, hue - accent (None = the app's)
    # @return: the title QLabel, or None when the group has no layout
    old = group.layout()
    if old is None:
        return None
    content = QWidget(group)
    content.setObjectName(group.objectName() + "_content")
    cbox = QVBoxLayout(content)
    cbox.setContentsMargins(10, 6, 10, 8)
    cbox.setSpacing(6)
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
    bar_style = theme.section_bar_style(hue)
    # The group's native title space is dead now (the bar carries the title):
    # drop the reserved margin/padding and give the group a clear BOTTOM margin
    # so two groups never touch. The border is repeated because an instance
    # stylesheet overrides the app's for this widget.
    group.setStyleSheet(
        f"QGroupBox {{ border: 1px solid {theme.C_LINE};"
        f" border-radius: 6px; margin: 0px 0px 10px 0px; padding: 0px; }}")
    group.setTitle("")
    bar = QWidget(group)
    bar.setObjectName(group.objectName() + "_bar")
    bar.setStyleSheet(f"QWidget#{group.objectName()}_bar {{ {bar_style} }}")
    brow = QHBoxLayout(bar)
    brow.setContentsMargins(10, 5, 10, 5)
    label = QLabel(title)
    label.setObjectName(group.objectName() + "_title")
    label.setStyleSheet(
        f"color: {hue or theme.C_ACCENT}; font-weight: bold;")
    brow.addWidget(label)
    brow.addStretch(1)
    old.setContentsMargins(0, 0, 0, 0)
    old.setSpacing(0)
    old.addWidget(bar)
    old.addWidget(content)
    return label


def title_groups(dlg):
    # Give every group of the Settings dialog a title bar. Nothing folds.
    # @args: dlg - the loaded settings dialog
    # @return: None
    for group in dlg.findChildren(QGroupBox):
        lay = group.layout()
        if lay is None or lay.count() == 0:
            continue
        make_titled(group)


def insert_page_intros(dlg, intros, tr):
    # A one-line intro at the top of each page (ADR-071 rev): the page says
    # what its settings are for, so it reads as a page and not as a list.
    # @args: dlg - the dialog, intros - {page_objectName: text}, tr - self.tr
    # @return: None
    for page_name, text in intros.items():
        page = dlg.findChild(QWidget, page_name)
        if page is None or page.layout() is None:
            continue
        lbl = QLabel(tr(text))
        lbl.setObjectName(page_name + "_intro")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #8a90a6; font-size: 12px;")
        page.layout().insertWidget(0, lbl)


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
        # every group's rows live inside the <group>_content widget created by
        # settings_view.title_groups, not directly in the group's layout
        content = group.findChild(QWidget, group.objectName() + "_content")
        lay = content.layout() if content is not None else group.layout()
        if lay is None:
            continue
        title = group.title()
        if not title:
            # the group's title moved to its title bar, so the search still
            # reads it there
            lbl = group.findChild(QLabel, group.objectName() + "_title")
            if lbl is not None:
                title = lbl.text()
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


def backend_gate(dlg, groups):
    # Keeps only the fields of the observatory backend picked in the combo
    # (ADR-081): the Integrations page must not show the host and port of a
    # program the observer is not using. A unit whose group is another
    # backend's is NEVER eligible, so the search cannot bring it back either.
    # @args: dlg - the dialog, groups - {"ccdciel": "grp_ccdciel", ...}
    # @return: an eligible(unit) callable for wire_search
    def eligible(unit):
        group = unit.get("group")
        for kind, name in groups.items():
            if group == name:
                return dlg.cmb_obs_backend.currentData() == kind
        return True
    return eligible


def wire_search(dlg, no_results, eligible=None):
    # Filters the field rows as the observer types: a row stays when the
    # query appears in its label, its help or its group's title (accent and
    # case insensitive). A group with no match hides; if the shown page has
    # no match but another does, the rail jumps to the first one; if nothing
    # matches anywhere, a quiet line says so.
    # @args: dlg - the dialog, no_results - the quiet line's text (already
    #        translated; it lives in main_window so lupdate sees it in the
    #        MainWindow context), eligible - optional unit -> bool gate (a
    #        row that fails it is hidden whatever the query says; used for
    #        the observatory backend, ADR-081)
    # @return: the apply() callable, so the caller can re-evaluate it when
    #          something the gate reads changes (the backend combo)
    units = _index_units(dlg)
    group_page = {}
    for i in range(dlg.stk_pages.count()):
        page = dlg.stk_pages.widget(i).widget()
        for g in page.findChildren(QGroupBox):
            group_page[g.objectName()] = i

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
            if ok and eligible is not None:
                ok = eligible(unit)
            for name in unit["names"]:
                w = getattr(dlg, name, None)
                if w is not None:
                    w.setVisible(ok)
            group_ok[unit["group"]] = group_ok.get(unit["group"], False) or ok
        for name, ok in group_ok.items():
            g = getattr(dlg, name, None)
            if g is not None:
                g.setVisible(ok)
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
    return apply
