############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the .ui loader (ADR-005)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Every name in every Designer file must resolve to a WIDGET.

The loader registers the .ui's children by name (gui/ui_loader.py), and the
whole app reaches its widgets that way. Under a full test run the fallback
handed back a QWidgetItem (a layout item) for two of them, and the workbench
crashed while being built. This walks all the .ui files and checks the kind
of every name, which is the class of bug that no single feature test can see.
"""

import os
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                   # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget   # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_every_named_widget_of_every_ui_is_a_widget(qapp):
    from nightscribe.gui import ui_loader
    # The workbench's own Designer files: they are the ones the editor
    # builds at every open, which is where the bad resolution appeared.
    # (Walking ALL of them, main window and wizards included, is not a test
    # of the loader: it is a stress test of Qt's object graph, and it took
    # the whole pytest process down with it.)
    files = sorted(list(ui_loader.UI_DIR.glob("ufe_*.ui"))
                   + list(ui_loader.UI_DIR.glob("visit*.ui")))
    assert len(files) >= 15                     # the workbench is walked
    bad = []
    # every loaded .ui hangs from ONE host and goes with it: deleting the
    # roots one by one without an event loop left C++ husks behind and the
    # process died later, inside another test (measured: the same three
    # files pass when the husks share a parent)
    host = QWidget()
    for path in files:
        tree = ET.parse(path).getroot()
        root_node = tree.find("widget")
        root_name = root_node.get("name") if root_node is not None else None
        widget = ui_loader.load_ui(path.stem, host)
        for node in tree.iter("widget"):
            name = node.get("name")
            if not name or name == root_name:
                continue            # the root IS the loaded widget
            got = getattr(widget, name, None)
            if not isinstance(got, QWidget):
                bad.append((path.name, name, type(got).__name__))
    host.deleteLater()
    qapp.processEvents()
    assert not bad, bad


def test_the_loader_registers_the_children_by_hand(qapp):
    # The registration is the loader's own, not a fallback's: the husk and
    # its children behave the same, and a name that belongs to the class is
    # left alone.
    from nightscribe.gui import ui_loader
    from nightscribe.gui.ui_loader import _register_children
    host = QWidget()
    panel = ui_loader.load_ui("ufe_visit_panel", host)
    assert isinstance(panel.ph_series, QWidget)
    assert isinstance(panel.lbl_frame, QWidget)
    assert not hasattr(panel, "load_ui")        # a class attribute survives
    _register_children(panel)                   # idempotent
    assert isinstance(panel.ph_series, QWidget)
    host.deleteLater()
    qapp.processEvents()
