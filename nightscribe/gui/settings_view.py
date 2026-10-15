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
does the four things that are behaviour and not layout:

* fills the rail from `settings_spec.CATEGORIES` and ties it to the stack;
* gives every group its title bar (`title_groups`), so two groups never
  read as one continuous list;
* folds each page's expert groups behind ONE "Advanced" door
  (`make_advanced_doors`, ADR-092): nothing is removed, the common path
  just stays short;
* indexes every field row (its label + its help) and filters the pages as
  the observer types in `edt_search`, opening the door when the match
  lives behind it.

Everything is offscreen and testable: no network, no MainWindow.
"""

import unicodedata

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QListWidgetItem, QPlainTextEdit,
                               QSpinBox, QTableWidget, QToolButton,
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
    # Fills the left rail with one row per category, ICON + NAME (ADR-092),
    # and ties it to the stacked pages, so the observer picks a task and the
    # page follows. ADR-071's rail was icon-only: six glyphs you had to
    # hover to learn. The name is visible now (the app's own FITS editor
    # bar shows text by default for the same reason); the tooltip and the
    # accessible name repeat it, and a missing icon still leaves the text,
    # so the rail never goes mute.
    # @args: dlg - the dialog, categories - [(page, label, svg stem)],
    #        tr - self.tr
    # @return: None
    from . import theme
    rail = dlg.lst_categories
    rail.clear()
    rail.setViewMode(QListView.ListMode)
    rail.setMovement(QListView.Static)
    rail.setResizeMode(QListView.Adjust)
    rail.setUniformItemSizes(True)
    rail.setSpacing(2)
    rail.setIconSize(QSize(20, 20))
    rail.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    for _page, label, stem in categories:
        name = tr(label)
        item = QListWidgetItem()
        icon = _rail_icon(theme, stem)
        if not icon.isNull():
            item.setIcon(icon)
        item.setText(name)
        item.setToolTip(name)
        item.setData(Qt.AccessibleTextRole, name)
        item.setSizeHint(QSize(140, 34))
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


class _AdvancedDoor(QWidget):
    # The ONE collapsible section at the bottom of a Settings page
    # (ADR-092): the page's expert groups live inside, closed by default,
    # so the common path reads short and finished. Not a QGroupBox on
    # purpose: the search index walks the groups, and a door that were one
    # would index (and hide) itself. The chevron speaks the app's idiom
    # (the same ▸/▾ as the Tonight "Filters" toggle).
    def __init__(self, page, count, tr):
        # @args: page - the page widget the door belongs to, count - how
        #        many groups live behind it, tr - self.tr
        super().__init__(page)
        self.setObjectName(f"door_{page.objectName()}")
        # what the observer last chose; the search opens the door on a hit
        # WITHOUT touching this, so clearing the box hands the door back
        # to the state its owner left it in
        self.user_open = False
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 10)
        box.setSpacing(0)
        self.bar = QToolButton(self)
        self.bar.setObjectName(self.objectName() + "_bar")
        self.bar.setCursor(Qt.PointingHandCursor)
        self.bar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        # the same filled strip a group title wears, rounded on all four
        # corners: a door, not just another group start
        self.bar.setStyleSheet(
            f"QToolButton {{ {theme.section_bar_style()}"
            f" border-bottom-left-radius: 6px;"
            f" border-bottom-right-radius: 6px; border: none;"
            f" color: {theme.C_ACCENT}; font-weight: bold;"
            f" text-align: left; padding: 6px 10px; }}")
        self.bar.clicked.connect(
            lambda: self.set_open(not self.is_open(), by_user=True))
        box.addWidget(self.bar)
        self.content = QWidget(self)
        self.content.setObjectName(self.objectName() + "_content")
        cbox = QVBoxLayout(self.content)
        cbox.setContentsMargins(0, 0, 0, 0)
        cbox.setSpacing(0)
        box.addWidget(self.content)
        self._count = count
        self._title = tr("Advanced")
        self.bar.setAccessibleName(self._title)
        self.set_open(False)

    def is_open(self):
        # @return: True when the expert groups are on screen
        return not self.content.isHidden()

    def set_open(self, open_, by_user=False):
        # @args: open_ - show the groups, by_user - remember it as the
        #        observer's own choice (the search passes False)
        # @return: None
        if by_user:
            self.user_open = open_
        self.content.setVisible(open_)
        chevron = "▾" if open_ else "▸"
        self.bar.setText(f"{chevron}  {self._title} ({self._count})")


def make_advanced_doors(dlg, groups, tr):
    # Moves each page's ADVANCED groups (settings_spec.ADVANCED_GROUPS)
    # behind the page's door, keeping their relative order. Run AFTER
    # title_groups, so a moved group already wears its bar.
    # @args: dlg - the dialog, groups - set of group objectNames,
    #        tr - self.tr
    # @return: {group objectName: door}, for wire_search
    doors = {}
    for i in range(dlg.stk_pages.count()):
        page = dlg.stk_pages.widget(i).widget()
        lay = page.layout()
        if lay is None:
            continue
        advanced = []
        for j in range(lay.count()):
            w = lay.itemAt(j).widget()
            if isinstance(w, QGroupBox) and w.objectName() in groups:
                advanced.append(w)
        if not advanced:
            continue
        door = _AdvancedDoor(page, len(advanced), tr)
        for group in advanced:
            lay.removeWidget(group)          # keeps the widget alive
            door.content.layout().addWidget(group)
        lay.addWidget(door)
        for group in advanced:
            doors[group.objectName()] = door
    return doors


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


def wire_search(dlg, no_results, eligible=None, doors=None):
    # Filters the field rows as the observer types: a row stays when the
    # query appears in its label, its help or its group's title (accent and
    # case insensitive). A group with no match hides; if the shown page has
    # no match but another does, the rail jumps to the first one; if nothing
    # matches anywhere, a quiet line says so. A match behind an "Advanced"
    # door OPENS it (ADR-092): a search hit must be visible, not folded
    # away; clearing the box hands every door back to its owner.
    # @args: dlg - the dialog, no_results - the quiet line's text (already
    #        translated; it lives in main_window so lupdate sees it in the
    #        MainWindow context), eligible - optional unit -> bool gate (a
    #        row that fails it is hidden whatever the query says; used for
    #        the observatory backend, ADR-081), doors - {group objectName:
    #        _AdvancedDoor} from make_advanced_doors
    # @return: the apply() callable, so the caller can re-evaluate it when
    #          something the gate reads changes (the backend combo)
    units = _index_units(dlg)
    doors = doors or {}
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
        # a door opens for a hit behind it; with no query it goes back to
        # the state the observer chose (user_open)
        door_hit = {}
        for name, ok in group_ok.items():
            door = doors.get(name)
            if door is not None:
                door_hit[door] = door_hit.get(door, False) or ok
        for door in set(doors.values()):
            door.set_open(door.user_open
                          or (bool(query) and door_hit.get(door, False)))
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
