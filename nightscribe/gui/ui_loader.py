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

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader

UI_DIR = Path(__file__).parent / "ui"


def load_ui(name, parent=None):
    # Loads a Designer file by basename. The .ui root is a plain
    # QWidget/QDialog that the caller embeds; its <class> tag matches the
    # owning Python class so the i18n context (and its translations)
    # carry over unchanged.
    # @args: name - the file's basename without ".ui", parent - the
    #        widget the loaded root is parented to
    # @return: the loaded widget; children are reachable as attributes
    #          through their objectName (PySide6's fallback)
    file = QFile(str(UI_DIR / f"{name}.ui"))
    file.open(QFile.ReadOnly)
    widget = QUiLoader().load(file, parent)
    file.close()
    return widget


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
