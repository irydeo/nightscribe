############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Shared .ui loader module (ADR-005)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The single home of the Designer-file loader (ADR-005, restored
2026-09-25): every dialog/tab defines its interface in a .ui under
gui/ui/ and loads it at runtime through here. Custom widgets never
appear in a .ui: a placeholder QWidget marks the slot and the code
inserts the real widget there (the pattern main_window.ui has always
used for its tab pages).
"""

import logging
from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QWidget

logger = logging.getLogger("nightscribe.gui.ui_loader")

UI_DIR = Path(__file__).parent / "ui"


def load_ui(name, parent=None):
    # Loads a Designer file by basename. The .ui root is a plain
    # QWidget/QDialog that the caller embeds; its <class> tag matches the
    # owning Python class so the i18n context (and its translations)
    # carry over unchanged.
    # @args: name - the file's basename without ".ui", parent - the
    #        widget the loaded root is parented to
    # @return: the loaded widget; children are reachable as attributes
    #          through their objectName (registered here, see
    #          _register_children)
    path = UI_DIR / f"{name}.ui"
    names = _named_widgets(path)
    for attempt in (0, 1):
        file = QFile(str(path))
        file.open(QFile.ReadOnly)
        widget = QUiLoader().load(file, parent)
        file.close()
        _register_children(widget)
        wrong = [n for n in names
                 if not isinstance(getattr(widget, n, None), QWidget)]
        if not wrong:
            return widget
        # A LOAD THAT CAME BACK WRONG IS NOT A LOAD. Seen under a full test
        # run: three names of one panel resolved to their widgets and a
        # fourth to a QWidgetItem (a layout item), which crashed the
        # workbench while it was being built with a message about 'clicked'
        # that said nothing about the real problem. It is rare (one load in
        # a few thousand) and it is per-load, so it is retried once; if the
        # retry is wrong too, the failure is said out loud here instead of
        # surfacing as a mystery inside a feature.
        logger.warning("the %s load came back wrong for %s (attempt %d)",
                       name, wrong, attempt + 1)
        # The wrong widget is UNPARENTED before it is deleted (2026-10-01):
        # deleteLater only runs on the next event-loop pass, and until then
        # it sat at (0, 0) of the host with its default 100x30 size, covering
        # the first row. In a full test run that was the editor's top bar:
        # "Load FITS" stopped answering because a stray widget was on top of
        # it. Unparenting is immediate, so nothing can be covered in between.
        widget.setParent(None)
        widget.deleteLater()
    raise RuntimeError(
        f"{name}.ui did not load cleanly: {wrong} did not resolve to widgets")


def _named_widgets(path):
    # @args: path - a Designer file
    # @return: the objectNames of every widget it declares, except the root
    #          (the root IS the loaded widget)
    import xml.etree.ElementTree as ET
    tree = ET.parse(path).getroot()
    root = tree.find("widget")
    if root is None:
        return []
    own = root.get("name")
    return [node.get("name") for node in tree.iter("widget")
            if node.get("name") and node.get("name") != own]


def _register_children(root):
    # Every named child of a loaded .ui becomes an attribute of the loaded
    # widget. This is done HERE, by hand, instead of trusting QUiLoader's
    # own name fallback: that fallback resolves a name to whatever object
    # carries it, and under a full test run it has handed back a
    # QWidgetItem (a LAYOUT ITEM, not a widget) for
    # `visit_panel.ph_series` and `visit_panel.btn_solve_visit` (that second
    # one lives in the top bar since 2026-09-30, next to "Solve
    # astrometry…"), which
    # crashed the dialog while it was being built ("'QWidgetItem' object has
    # no attribute 'clicked'") and fed `drop_in` the wrong kind of argument
    # (intermittent: not reproducible in 120 builds in a row, nor in
    # isolation). Setting them here is deterministic and costs a walk over
    # the tree once per load.
    # @args: root - the widget QUiLoader returned
    # @return: None
    from PySide6.QtCore import QObject
    for child in root.findChildren(QObject):
        name = child.objectName()
        # a name that belongs to the class (a method, a property) is left
        # alone: only the .ui's own objects are registered
        if not name or hasattr(type(root), name):
            continue
        setattr(root, name, child)


def adopt_ui(host, name):
    # The standard adoption idiom for a class that owns a .ui (ADR-005):
    # load, let the .ui's root layout take over the host (no wrapper, no
    # double margins), and HIDE the husk: the .ui's root widget stays as
    # a child at (0, 0) with a default 100x30 size, and left visible it
    # paints over the host's first row and eats its clicks.
    # @args: host - the owning widget/dialog, name - the .ui basename
    # @return: the loaded widget (the husks of the widgets stay
    #          attribute-reachable through it)
    ui = load_ui(name, host)
    host.setLayout(ui.layout())
    ui.hide()
    return ui


def drop_in(layout, placeholder, widget):
    # Swaps a .ui placeholder for the real (custom) widget. Unlike
    # QSplitter.replaceWidget, QLayout.replaceWidget does NOT hide the
    # old widget: left visible it floats at (0, 0), covering and
    # starving the first row of clicks, so hide it here (ADR-005).
    # @args: layout - the placeholder's QLayout, placeholder - the .ui
    #        marker widget, widget - the real widget taking its slot
    layout.replaceWidget(placeholder, widget)
    placeholder.hide()
