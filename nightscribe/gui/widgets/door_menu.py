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

from PySide6.QtWidgets import QLayout, QMenu, QToolButton


def _out_of_layout(widget):
    # A layout does NOT drop its item when the widget is reparented: Qt keeps
    # a QWidgetItem pointing at it and goes on setting geometry on a widget
    # that now belongs elsewhere. Measured: the workbench's bar still held 22
    # items after its eighteen buttons had been moved out of it, and with the
    # old panel design the same widgets were laid out by two layouts at once.
    # @args: widget - the widget about to be reparented
    # @return: None
    parent = widget.parentWidget()
    if parent is None:
        return
    for lay in [parent.layout()] + parent.findChildren(QLayout):
        if lay is not None and lay.indexOf(widget) != -1:
            lay.removeWidget(widget)
            return


def build_door(tool, buttons):
    # @args: tool - the QToolButton the menu hangs from, buttons - the
    #        widgets (buttons) the door opens onto, in order; None entries
    #        are skipped
    # @return: the QMenu. Its items carry the button's objectName in data(),
    #          so a test (or a probe) can say which button each item drives
    menu = QMenu(tool)
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
        # Out of the layout that held it and out of sight, but alive: the
        # button keeps its slot and the .ui's own row does not keep a gap.
        # Leaving it hidden in place would work on screen too, but the bar
        # would still be carrying eighteen items, and "the bar is not a
        # cockpit" is measured by counting them.
        _out_of_layout(btn)
        btn.setParent(tool.window())
        btn.setVisible(False)
        items.append((act, btn))
    # the plate decides whether the export and the resets are available, and
    # that changes after the door is built: reading the buttons again on
    # every opening is what keeps the door from lying
    menu.aboutToShow.connect(lambda: sync_door(items))
    tool.setMenu(menu)
    tool.setPopupMode(QToolButton.InstantPopup)
    return menu


def sync_door(items):
    # @args: items - [(QAction, button), ...] as build_door left them
    # @return: None
    for act, btn in items:
        act.setEnabled(btn.isEnabled())
        act.setText(btn.text())
        act.setToolTip(btn.toolTip())
        if btn.isCheckable():
            act.setChecked(btn.isChecked())
