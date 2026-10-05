############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Dropdown doors built from the buttons behind them
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""A dropdown that IS the buttons behind it.

The workbench's occasional actions (the view switches, the zoom presets, the
export and reset pairs, the series' own) live behind a small "…" tool
button: they are not what you press every night, and a row of them would eat
the panel.

They used to be moved, one by one, into a QWidget that a QWidgetAction
handed to the menu. That crashed Windows with an access violation while the
dialog was being built: the fault landed on `menu.addAction`, it wandered
between the dialog's doors and the measure tab's, it happened on both Qt
platforms and it killed a test worker mid-suite (measured 2026-10-01). A
standard QMenu has no widget to reparent and no ownership to get wrong.

So a door is a plain QMenu with one item per button: the item shows the
button's icon and label, and TRIGGERS it. The button stays where the
Designer file put it (ADR-005), hidden, and keeps its text, its tooltip, its
checkable state and its slot: the door is a way in, not a second copy.
"""

from PySide6.QtWidgets import QMenu, QToolButton, QVBoxLayout, QWidget

from ..ui_loader import out_of_layout as _out_of_layout


def build_door(tool, buttons):
    # @args: tool - the QToolButton the menu hangs from, buttons - the
    #        widgets (buttons) the door opens onto, in order; None entries
    #        are skipped
    # @return: the QMenu. Its items carry the button's objectName in data(),
    #          so a test (or a probe) can say which button each item drives
    menu = QMenu(tool)
    # Where the buttons go: OUT of the row that held them (the door is where
    # they live now, and the row is emptied) and into a HIDDEN holder, never
    # into the window. The product switches their visibility by itself
    # (setVisible(True) when a project is behind the editor), and a button
    # with no layout and a visible parent came out floating over the window
    # while the door's own item made it look duplicated (reported
    # 2026-10-01). Inside a hidden holder it can never show, and its text,
    # tooltip, state and slot are untouched.
    holder = QWidget(tool)
    holder.setObjectName("door_holder")
    hold_box = QVBoxLayout(holder)
    hold_box.setContentsMargins(0, 0, 0, 0)
    holder.hide()
    items = []
    for btn in buttons:
        if btn is None:
            continue
        act = menu.addAction(btn.icon(), btn.text())
        act.setToolTip(btn.toolTip())
        act.setCheckable(btn.isCheckable())
        act.setChecked(btn.isChecked())
        act.setData(btn.objectName())
        # the button keeps the behaviour and the state: the item drives it
        # and follows it (a checkable button's own toggle is the truth)
        act.triggered.connect(btn.click)
        if btn.isCheckable():
            btn.toggled.connect(act.setChecked)
        # the icon-only skin must leave these ones their label: the item
        # shows it, and a riddle icon is not a menu entry
        btn.setProperty("in_panel", True)
        _out_of_layout(btn)
        btn.setParent(holder)
        hold_box.addWidget(btn)
        btn.setVisible(False)
        items.append((act, btn))
    # the plate decides whether the export and the resets are available, and
    # that changes after the door is built: reading the buttons again on
    # every opening is what keeps the door from lying
    menu.aboutToShow.connect(lambda: sync_door(items))
    # the items are kept on the menu so the product can refresh the door the
    # moment it changes what the buttons can do (a door that lies is worse
    # than no door): refresh_door(tool) is that call
    menu._door_items = items
    tool.setMenu(menu)
    tool.setPopupMode(QToolButton.InstantPopup)
    return menu


def refresh_door(tool):
    # Re-reads the buttons a door was built from, without waiting for it to
    # open. For a change the observer must see at once (the plate's resets
    # appearing, the export going live).
    # @args: tool - the QToolButton the door hangs from
    # @return: None
    menu = tool.menu() if tool is not None else None
    if menu is not None:
        sync_door(getattr(menu, "_door_items", []))


def sync_door(items):
    # @args: items - [(QAction, button), ...] as build_door left them
    # @return: None
    for act, btn in items:
        act.setEnabled(btn.isEnabled())
        act.setText(btn.text())
        act.setToolTip(btn.toolTip())
        if btn.isCheckable():
            act.setChecked(btn.isChecked())
