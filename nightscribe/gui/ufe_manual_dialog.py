############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: Manual tweak window (ADR-044 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The UFE Compare tab's manual controls in one small window (ADR-044,
rev 2026-09-26): the hand-driven path, picked star by star (comparison
or check), the catalog-labels toggle and the step-by-step actions that
the one-click flow bundles (field alone, proposal alone, the sequence
table). The «Manual tweak…» toggle, right of the DSS2 button, raises it
; closed (the normal state) the plate clicks measure.

The Compare tab owns the behaviour: it aliases the window's widgets as
its own (rdo_comp, rdo_check, chk_labels, btn_field, btn_propose,
btn_seq_open) so the old call sites and the pinned tests keep working,
and it routes the plate clicks by this window's visibility. The state
lives on the widgets, so closing and reopening the window keeps the
picking kind, the labels choice and whatever was already queued.

ADR-005: the structure and its translatable texts live in
ui/ufe_manual_dialog.ui; this class loads it through adopt_ui and
exposes the widgets.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog

from .ui_loader import adopt_ui


class UfeManualDialog(QDialog):
    # Qt's own QDialog.visibilityChanged signal is not bound in this
    # PySide6 build, so the window reports its state with its own
    # signal: True when it rises, False when it is hidden (the tab's
    # hide() or the window's X button) and the host can unsync its
    # toggle from that
    openStateChanged = Signal(bool)

    # @args: parent - the UFE Compare tab (owns the behaviour; the
    #        window is transient and dies with it)
    # @return: the manual tweak window, ready to be raised and routed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manual tweak"))
        # the structure is the Designer file's (ADR-005); this class
        # only dresses the window and exposes the widgets the tab
        # aliases
        self._ui = adopt_ui(self, "ufe_manual_dialog")
        self.lbl_hint = self._ui.lbl_hint
        self.lbl_pick = self._ui.lbl_pick
        self.rdo_comp = self._ui.rdo_comp
        self.rdo_check = self._ui.rdo_check
        self.chk_labels = self._ui.chk_labels
        self.btn_seq_open = self._ui.btn_seq_open
        self.btn_field = self._ui.btn_field
        self.btn_propose = self._ui.btn_propose
        # THE SIZE, once the layout exists. It used to open at a fixed
        # 820x400 while the content ends around 330: a dead strip under the
        # last row, because the stretch below it is not part of any size
        # hint (reported: "ajusta también el diálogo Manual Tweak").
        #
        # The WIDTH keeps its floor: the actions row (field plus proposal
        # buttons) measures 292 locally but 691 with the wide Windows CI
        # font, so 760 clears that and test_manual_window_cannot_squish_its_
        # buttons pins it. The HEIGHT now follows the content.
        self.setMinimumWidth(760)
        self._fitted = False
        self._fit_to_content()

    def showEvent(self, event):
        # The metrics are the APPLIED font's, not the one the dialog was
        # built with: on Windows the layout needs 8 px more than the floor
        # computed in __init__, so the window could squish its own buttons
        # (measured in CI, 2026-10-01: minimumHeight 147 against a hint of
        # 155). The first show re-fits, once, so it does not fight a size the
        # observer chose.
        # @args: event - the show event
        # @return: None
        super().showEvent(event)
        if not self._fitted:
            self._fitted = True
            self._fit_to_content()

    def _fit_to_content(self):
        # The window takes the height its CONTENT really needs, at the width
        # it opens with: no dead strip and nothing cut.
        #
        # The size hints lie here, which is why this measures the rows
        # themselves: measured on the real window, it opened at 400 px with
        # the content ending at 278 (a dead strip of 111 under the last row)
        # while `sizeHint` said 177 and the layout's `heightForWidth` said
        # 161. The extra space is spread over the rows, so only the laid-out
        # geometry tells the truth.
        #
        # The sequence button is measured DRESSED with its live count (the
        # longest form it may show): its bare label is shorter, and with a
        # wider font the window came out 8 px under what the dressed row
        # needs, so it could squish its own buttons (measured in CI,
        # 2026-10-01: minimumHeight 147 against a hint of 155).
        # @return: None
        width = max(820, self.minimumWidth())
        layout = self.layout()
        if layout is None:
            return
        bare = self.btn_seq_open.text()
        self.btn_seq_open.setText(self.tr("Sequence (99)…"))
        try:
            self.resize(width, 600)         # room to lay the content out
            layout.activate()
            bottom = 0
            for i in range(layout.count()):
                item = layout.itemAt(i)
                widget = item.widget() if item is not None else None
                if widget is None or not widget.isVisible():
                    continue
                bottom = max(bottom, widget.geometry().bottom() + 1)
            margin = layout.contentsMargins().bottom()
            if bottom <= 0:
                bottom = self.sizeHint().height()
            self.setMinimumHeight(int(self.minimumSizeHint().height()))
            # the content plus a little air: flush against the frame looks
            # broken, and the strip this replaces was 111 px of nothing
            self.resize(width,
                        max(int(bottom) + margin + 12, self.minimumHeight()))
        finally:
            self.btn_seq_open.setText(bare)

    def resizeEvent(self, ev):
        # A word-wrapped hint label does not always ask for the height its
        # text needs (the sizeHint is computed for a width that changes
        # later): refit it at the REAL width, the same fix the series
        # block's header carries.
        # @args: ev - the resize event, passed on
        super().resizeEvent(ev)
        lbl = getattr(self, "lbl_hint", None)
        if lbl is not None and lbl.width() >= 50:
            need = lbl.heightForWidth(lbl.width())
            if need > 0:
                lbl.setMinimumHeight(int(need))

    def showEvent(self, ev):
        # @args: ev - the show event, passed on
        super().showEvent(ev)
        self.openStateChanged.emit(True)

    def hideEvent(self, ev):
        # the X button hides (a non-modal QDialog dies with host or X),
        # so this is the one hook that sees every close
        # @args: ev - the hide event, passed on
        super().hideEvent(ev)
        self.openStateChanged.emit(False)
