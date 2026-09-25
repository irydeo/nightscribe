############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: Photometry tab container (ADR-044)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The UFE's Photometry tab: the Compare (sequence) and Measure sections
live together in one vertical panel (ADR-044 rev, 2026-09-24). A small
exclusive toggle up top picks the section that owns the stage; the two
sections stack in a vertical splitter so both stay visible. The Measure
section is the Sequence section's consumer (it calibrates against the
sequence), so switching sections keeps the other section's overlays on
the chart, and only leaving the Photometry tab for real drops them.

The container plays the tab contract the dialog knows: pick_clicks,
set_active(flag), and a mode it restores on re-entry. Deep links may
still name the old tabs by widget (tab_compare / tab_measure) or by
"compare" / "measure" and the dialog routes them here.

ADR-005 restored (2026-09-25): the structure lives in
ui/ufe_photometry_tab.ui; this class loads it and inserts the two
code-built sections into the splitter's placeholders.
"""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QButtonGroup, QWidget

from .ui_loader import adopt_ui


class UfePhotometryTab(QWidget):
    pick_clicks = True   # clicks mark things: the dialog hands us
                         # the pick cursor + snapping reticle on stage

    # @args: state - the shared UfeImageState, lang - "es" | "en",
    #        view - the UfeImageView, parent - the dialog (or None)
    # @return: the Photometry tab, defaulting to the Sequence section
    #          (or the Measure section when a sequence already exists)
    def __init__(self, state, lang="es", view=None, parent=None):
        super().__init__(parent)
        self._state = state
        self._lang = lang
        self._view = view
        self._mode = None
        self._syncing = False

        from .ufe_compare_tab import UfeCompareTab
        from .ufe_measure_tab import UfeMeasureTab

        self.tab_compare = UfeCompareTab(state, lang, view=view)
        self.tab_measure = UfeMeasureTab(
            state, lang, view=view, compare_tab=self.tab_compare,
            go_compare=lambda: self.set_mode("sequence"))

        # the structure is the Designer file's (ADR-005); the mode
        # wiring and the section insertion happen here
        self._ui = adopt_ui(self, "ufe_photometry_tab")
                                            # over: no wrapper, no extra
                                            # margins
        self.btn_seq = self._ui.btn_seq
        self.btn_meas = self._ui.btn_meas
        grp = QButtonGroup(self)
        grp.addButton(self.btn_seq)
        grp.addButton(self.btn_meas)
        self.btn_seq.toggled.connect(
            lambda _on: self._on_mode_button("sequence"))
        self.btn_meas.toggled.connect(
            lambda _on: self._on_mode_button("measure"))

        self.splitter = self._ui.splitter
        self.splitter.replaceWidget(0, self.tab_compare)
        self.splitter.replaceWidget(1, self.tab_measure)
        # setMinimumSize (not the 6.3 "hint" variant: this Qt build's
        # bindings lack it) keeps the top half from collapsing; the
        # compare half is compact now (its table lives in its own
        # window), so it gets the smaller share
        self.tab_compare.setMinimumSize(QSize(0, 200))
        self.tab_measure.setMinimumSize(QSize(0, 260))
        self.splitter.setSizes([320, 540])

        # opening section: the Measure one when a sequence already waits,
        # otherwise the Sequence one (where one is built)
        self._sync_mode("measure" if self.tab_compare.entries()
                        else "sequence", apply=False)

    # ------------------------------------------------------------- mode

    def set_mode(self, mode):
        # Puts a section on stage; the other stays visible with the
        # clicks disarmed and its overlays kept on the chart.
        # @args: mode - "sequence" (compare) or "measure"
        if mode not in ("sequence", "measure") or mode == self._mode:
            return
        self._sync_mode(mode, apply=True)

    def _on_mode_button(self, mode):
        if self._syncing or mode == self._mode:
            return
        self.set_mode(mode)

    def _sync_mode(self, mode, apply=False):
        self._mode = mode
        self._syncing = True
        self.btn_seq.setChecked(mode == "sequence")
        self.btn_meas.setChecked(mode == "measure")
        self._syncing = False
        if apply:
            self._apply()

    def _apply(self):
        # The section on stage takes the clicks and the reticle; the
        # other keeps its overlays (the measurement reads the sequence,
        # the sequence's rings stay readable under the measurement).
        if self._mode == "sequence":
            self.tab_compare.set_active(True)
            self.tab_measure.set_active(False, keep_overlays=True)
        else:
            self.tab_compare.set_active(False, keep_overlays=True)
            self.tab_measure.set_active(True)

    # -------------------------------------------------------- activation

    def set_active(self, flag):
        # Stage handoff between the dialog's feature tabs: re-entering
        # restores whichever section was picked; a full leave drops both
        # sections' overlays and diffs, to be rebuilt on the return.
        # @args: flag - on stage or not
        if flag:
            self._apply()
        else:
            self.tab_compare.set_active(False)
            self.tab_measure.set_active(False)
