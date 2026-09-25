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
