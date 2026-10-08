############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - The workbench's tool windows (ADR-044 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The feature panels that used to be tabs, in windows of their own.

Blink, Calibration and Annotate spent the first life of the workbench as
tabs of the right column. They are not what an observer does all the time:
blinking a pair, calibrating or writing an annotation is an errand, and the
tab bar paid for them with a permanent 380 px column and a title each. Asked
for: a button with its icon and its text in the top bar, and the panel in a
non-modal window that opens over the plate, sized to what it holds.

What this class is NOT: a second home for the panels. Each panel keeps its
own Designer file and its own class (`ufe_blink_tab.py` and friends), and the
window only gives it a frame. There is no structure of its own to design,
which is why there is no `.ui` here: the window is one content area, and the
content's structure lives where it always did (ADR-005).

Two things the window takes care of, because getting them wrong is how a
floating panel becomes furniture:

* **The size.** The panels were laid out for a 380 px column. In a window
  they can breathe, but only as much as they need: the height is measured on
  the laid-out rows (the same trick `UfeManualDialog` documents: the size
  hints lie about a form's real height) and the width has a floor per tool.
* **Closing.** The window reports its state with its own signal, because
  Qt's `visibilityChanged` is not bound in this PySide6 build. The dialog
  above uses it to give the stage back to the panel that had it.
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout

logger = logging.getLogger("nightscribe.gui.ufe_tool_dialog")


class UfeToolDialog(QDialog):
    """A non-modal window holding one feature panel."""

    # True when the window rises, False when it is hidden (its own hide() or
    # the X button), so the workbench can hand the stage back. Qt's own
    # QDialog.visibilityChanged is not bound in this PySide6 build (the same
    # reason UfeManualDialog declares its own).
    openStateChanged = Signal(bool)

    # @args: title - the window's title (already translated), panel - the
    #        feature widget it hosts, icon - the QIcon of the tool button
    #        (the window wears the same one), min_width - the width below
    #        which the panel's rows start to squish, parent - the workbench

    def __init__(self, title, panel, icon=None, min_width=420, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        # a tool, not a task: it floats over the plate and never blocks it,
        # so the observer can keep clicking the image (that is the whole
        # point of Blink and Annotate) and keep the other panels working
        self.setModal(False)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        if icon is not None and not icon.isNull():
            self.setWindowIcon(icon)
        self.panel = panel
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(panel)
        self.setMinimumWidth(int(min_width))
        self._fitted = False

    # ------------------------------------------------------------- the size

    def showEvent(self, event):
        # The size is measured on the FIRST show, with the real style and
        # font already applied (measuring in __init__ measures a window that
        # is not dressed yet, and the panels came out short).
        super().showEvent(event)
        if not self._fitted:
            self._fitted = True
            self._fit_to_content()
        self.openStateChanged.emit(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.openStateChanged.emit(False)

    def _fit_to_content(self):
        # @return: None. The height the CONTENT really needs, at the width
        #          the window opens with: no dead strip under the last row
        #          and nothing cut.
        # The hints lie here (a form's rows are stretched to fill whatever
        # height the window has), so what is measured is the laid-out
        # geometry, the same way UfeManualDialog does it.
        width = max(self.minimumWidth(), self.sizeHint().width())
        self.resize(width, 200)
        lay = self.layout()
        if lay is None:
            return
        lay.activate()
        content = lay.sizeHint().height()
        # the window's own chrome (title bar) is not in the layout's hint
        chrome = self.frameGeometry().height() - self.geometry().height()
        self.resize(width, max(160, content + chrome + 4))

    # ------------------------------------------------------------ the door

    def open_panel(self):
        # @return: None. Raises the window where it was left (the observer
        #          who moved it to a corner means it).
        self.show()
        self.raise_()
        self.activateWindow()

    def close_panel(self):
        # @return: None. Hides it without destroying it: the panel keeps its
        #          state (the blink pair, the annotation in progress), like
        #          the plate does.
        self.hide()
