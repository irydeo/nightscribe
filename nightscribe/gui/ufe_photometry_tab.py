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

import logging

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from . import theme
from .ui_loader import adopt_ui, drop_in
from .ufe_host import host_of
from .widgets.kind_glyph import kind_glyph_pixmap

logger = logging.getLogger("nightscribe.gui.ufe_photometry_tab")


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
        # ONE scroll area for the whole column (ADR-038 rev): with every
        # group folded the content is short, and the old splitter kept
        # handing each half a share of the height, so the air collected in
        # the middle (the reported vertical gaps). The two sections are
        # stacked inside it, with a trailing stretch that keeps everything at
        # the top. Each half is still the object every other piece of code
        # reaches for; only its container changed.
        # ('scroll' would collide with QWidget.scroll, a method: the loader
        # skips names that belong to the class)
        self.area_column = self._ui.area_column
        self._contents = self._ui.scrollAreaWidgetContents
        drop_in(self._contents.layout(), self._ui.ph_compare, self.tab_compare)
        drop_in(self._contents.layout(), self._ui.ph_measure, self.tab_measure)
        # the sections size to their content (no share to defend)
        self.tab_compare.setMinimumSize(0, 0)
        self.tab_measure.setMinimumSize(0, 0)

        # the manual window decides what a click does (open: pick stars;
        # closed: measure); re-arm on every visibility change
        self.tab_compare.manual.openStateChanged.connect(
            self._on_manual_toggled)
        # a manual band/mag edit in the sequence must be selectable in the
        # Measure band combo without waiting for a first measurement
        self.tab_compare.sequence_changed.connect(
            self.tab_measure.refresh_bands)
        # THE action of the panel (ADR-038 rev): one hero button, in the
        # object's hue, that does what the flow needs next: today, always
        # the comparison sequence, which is what a photometry session starts
        # with. It DELEGATES to the section's own button, which stays hidden
        # while the hero offers it: one action, one visible place.
        self.btn_primary = self._ui.btn_primary
        # the same fit as the Astrometry panel's hero (asked for 2026-10-06:
        # "Construir la secuencia (comparsas)…" asks for 329 px and the
        # column can be 262)
        from .widgets.hero_fit import install_hero_fit
        install_hero_fit(self.btn_primary)
        self.lbl_primary_sub = self._ui.lbl_primary_sub
        # the guide of the tab, right under the action: what to do with the
        # panel (it used to live inside the Measure half, where the observer
        # had to find it)
        self.lbl_hint = self._ui.lbl_hint
        self.btn_primary.clicked.connect(self.tab_compare.btn_auto.click)
        self.tab_compare.btn_auto.setVisible(False)
        self.tab_compare.sequence_changed.connect(self._sync_primary)
        self._hue = theme.C_ACCENT
        self._accent = None
        self.refresh_accent()

    # ------------------------------------------------------ the one action

    def refresh_accent(self):
        # @return: None. The panel speaks in the object's hue (the same
        #          grammar the masthead's active tab uses): the hero button
        #          and the block spines of both sections. Without a project
        #          the app's own accent is used, with no kind glyph.
        ask = getattr(host_of(self), "project_accent", None)
        accent = None
        if callable(ask):
            try:
                accent = ask()
            except Exception as err:
                logger.warning("the project accent could not be read: %s", err)
        self._accent = accent
        self._hue = (accent or {}).get("hue") or theme.C_ACCENT
        self.btn_primary.setStyleSheet(theme.hero_button_style(self._hue))
        kind = (accent or {}).get("kind")
        if kind:
            self.btn_primary.setIcon(QIcon(kind_glyph_pixmap(
                kind, 22, color=theme.chip_text_for(self._hue))))
            self.btn_primary.setIconSize(QSize(22, 22))
        else:
            self.btn_primary.setIcon(QIcon())
        for half in (self.tab_compare, self.tab_measure):
            refresh = getattr(half, "refresh_accent", None)
            if callable(refresh):
                refresh()
        self._sync_primary()

    def _sync_primary(self):
        # @return: None. The button follows the section's own state (it can
        #          be busy, or there may be no plate to work on) and the
        #          line under it says what pressing it will do, or what is
        #          missing. A dead button with no explanation is the fastest
        #          way to lose the observer (ADR-038).
        target = self.tab_compare.btn_auto
        self.btn_primary.setEnabled(target.isEnabled())
        self.btn_primary.setToolTip(target.toolTip())
        self._set_sub(self.tab_compare.primary_subtitle())

    def _set_sub(self, text):
        # @args: text - the line under the hero button
        # @return: None
        self.lbl_primary_sub.setText(text or "")
        self.lbl_primary_sub.setVisible(bool(text))

    # -------------------------------------------------------- activation

    def _on_manual_toggled(self, _visible):
        # Window-driven (ADR-044 rev 2026-09-26): the manual tweak lives
        # in a floating window of its own, so the column keeps its
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
            # the object's hue may have arrived after this tab was armed
            self.refresh_accent()
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
