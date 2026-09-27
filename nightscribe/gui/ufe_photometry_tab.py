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

"""The UFE's Photometry tab: the Comparisons (sequence) and Measure
sections stacked in one vertical splitter, both always visible (ADR-044
rev, 2026-09-25, third revision of the day: the mode toggle is gone).
There are no modes: what a plate click does follows the Comparisons
section's «Manual tweak…» window. While it is closed (the normal state)
the click measures; while it is open it picks stars. Both sections keep
their overlays while the tab is on stage, because the measurement reads
the sequence.

The container plays the tab contract the dialog knows: pick_clicks and
set_active(flag). Deep links may still name the old tabs by widget
(tab_compare / tab_measure) or by "compare" / "measure" and the dialog
routes them here.

ADR-005 restored (2026-09-25): the structure lives in
ui/ufe_photometry_tab.ui; this class loads it and inserts the two
code-built sections into the splitter's placeholders.
"""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

from .ui_loader import adopt_ui


class UfePhotometryTab(QWidget):
    pick_clicks = True   # clicks mark things: the dialog hands us
                         # the pick cursor + snapping reticle on stage

    # @args: state - the shared UfeImageState, lang - "es" | "en",
    #        view - the UfeImageView, parent - the dialog (or None)
    # @return: the Photometry tab; the Measure section owns the clicks
    #          until the observer opens the manual tweak window
    def __init__(self, state, lang="es", view=None, parent=None):
        super().__init__(parent)
        self._state = state
        self._lang = lang
        self._view = view
        self._on_stage = False

        from .ufe_compare_tab import UfeCompareTab
        from .ufe_measure_tab import UfeMeasureTab

        self.tab_compare = UfeCompareTab(state, lang, view=view)
        self.tab_measure = UfeMeasureTab(
            state, lang, view=view, compare_tab=self.tab_compare)

        # the structure is the Designer file's (ADR-005); the section
        # insertion and the window-driven click routing happen here
        self._ui = adopt_ui(self, "ufe_photometry_tab")
                                            # over: no wrapper, no extra
                                            # margins
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

        # the manual window decides what a click does (open: pick stars;
        # closed: measure); re-arm on every visibility change
        self.tab_compare.manual.openStateChanged.connect(
            self._on_manual_toggled)

    # -------------------------------------------------------- activation

    def _on_manual_toggled(self, _visible):
        # Window-driven (ADR-044 rev 2026-09-26): the manual tweak lives
        # in a floating window of its own, so the splitter keeps its
        # fixed share and there is nothing to re-deal; only the click
        # routing flips.
        self._apply()

    def _apply(self):
        # Arms the section the manual window points at; the other keeps
        # its overlays (the measurement reads the sequence, the
        # sequence's rings stay readable under the measurement).
        picking = self.tab_compare.manual_visible()
        self.tab_compare.set_active(picking,
                                    keep_overlays=not picking)
        self.tab_measure.set_active(not picking,
                                    keep_overlays=picking)

    def set_active(self, flag):
        # Stage handoff between the dialog's feature tabs: on stage, the
        # manual window rules the clicks; a full leave drops both
        # sections' overlays and diffs, to be rebuilt on the return.
        # @args: flag - on stage or not
        self._on_stage = bool(flag)
        if flag:
            self._apply()
        else:
            self.tab_compare.set_active(False)
            self.tab_measure.set_active(False)

    # ------------------------------------------------------ state (ADR-047)

    def capture_state(self):
        # Both halves, as two plain JSON blocks (ADR-047): the measuring
        # recipe and the sequence a saved point was built from. Read-only.
        # @return: the {"measure": ..., "sequence": ...} dict the dialog
        #          stores in the plate's meta
        return {
            "measure": self.tab_measure.capture_state(),
            "sequence": self.tab_compare.capture_state(),
        }

    def apply_state(self, st):
        # Restores both blocks (ADR-047). Each half is a no-op when its
        # piece is missing (no recipe saved, no sequence saved), so a
        # half-empty state restores whatever it holds.
        # @args: st - capture_state dict, or None to skip
        if not st:
            return
        self.tab_measure.apply_state(st.get("measure"))
        self.tab_compare.apply_state(st.get("sequence"))
