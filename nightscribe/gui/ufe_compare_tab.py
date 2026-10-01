############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: Compare tab (ADR-044, phase F)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The UFE's Comparisons section (ADR-044, phase F; rev 2026-09-25): the
photometric comparison sequence on top of core/compstars (VizieR
Gaia/APASS + VSX cross-match), with the FinderChart's visual language
reimplemented as overlays on the shared plate view (the legacy
SeqChartDialog keeps living untouched).

The normal path is ONE click: «Build the sequence…» generates the
catalog field around the plate centre and proposes the comparisons; the
observer only tweaks by clicking stars, and the «Manual tweak…» toggle
(right of the DSS2 button) raises the small window that holds the
hand-driven controls. The loaded plate IS the field background, so the
section needs it to carry a WCS (the common «Solve astrometry…» button
fixes that in place). Known VSX variables can never be comparisons; the
table edits names and kinds; the CSV export comes out next to the plate
(the chart PNG goes through the shared "Export PNG…" button in the
dialog's top bar). The object itself wears the dialog's global red mark
(the top bar's toggle), not a marker of this section.
"""

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog,
                               QProgressDialog, QPushButton, QTableWidgetItem,
                               QWidget, QGraphicsEllipseItem,
                               QGraphicsLineItem, QGraphicsRectItem,
                               QGraphicsSimpleTextItem)

from ..core import compstars, photometry
from ..core.sources import vizier
from ..viz import palette
from .ufe_manual_dialog import UfeManualDialog
from .ufe_sequence_dialog import UfeSequenceDialog
from .ui_loader import adopt_ui

logger = logging.getLogger("nightscribe.gui.ufe_compare_tab")

# the FinderChart's colours, so both pickers read the same (ADR-042)
C_COMP = "#4dd0e1"      # comparison ring
C_CHECK = "#ff7ad9"     # check square
C_VAR = "#ff6378"       # known variable ring
C_RING = "#58d68d"      # catalog label ring

# a busy dialog is shown only if the work takes this long: a flash of a
# window is worse than no window at all
_BUSY_SHOW_MS = 250

# Above this many catalog stars on the plate, the proposal goes to its own
# thread. The plate check costs ~2 ms per candidate (measured after H1):
# below the threshold the whole thing is a tenth of a second and a thread
# would be a lifecycle liability (a worker alive at close aborts the app);
# above it the window must stay alive while the plate is asked.
_PROPOSE_THREAD_MIN = 300

_PICK_PX = 11.0         # click/hover radius in SCREEN px at any zoom
_MAX_LABELS = 34        # catalog magnitude labels, brightest first


class _CenterOnWindow(QObject):
    # Keeps the busy dialog centred over the editor window. The stage
    # labels change its size (long bilingual texts), and the window
    # manager's placement is not ours to trust: re-centre on every
    # Show/Resize instead of a single move() that ages with the first
    # label change.
    # @args: dialog - the QProgressDialog, host - the widget whose
    #        top-level window is the reference

    def __init__(self, dialog, host):
        super().__init__(dialog)
        self._dialog = dialog
        self._host = host

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.Resize):
            win = self._host.window()
            self._dialog.move(win.geometry().center()
                              - self._dialog.rect().center())
        return False


def _busy_wait(host, label, title):
    # A modal busy dialog without Cancel for the seconds of network work:
    # the legacy comparison-chart flow leaned on it (a status line alone
    # reads as "nothing is happening"), and the UFE rewrite dropped it:
    # restoring it here.
    # @args: host - parent widget, label - first busy message,
    #        title - the window title
    # @return: the shown dialog, centred over the UFE window (an
    #          indeterminate QProgressDialog never gets a setValue, which
    #          is the only call that auto-shows it: without an explicit
    #          show() it simply never appears)
    wait = QProgressDialog(label, "", 0, 0, host)
    wait.setWindowTitle(title)
    wait.setWindowModality(Qt.WindowModal)
    wait.setCancelButton(None)
    wait.setMinimumDuration(0)
    # only _reap_wait closes it: no auto-close/reset when the bar hits
    # its maximum (the caller's last setValue is not the end signal)
    wait.setAutoClose(False)
    wait.setAutoReset(False)
    wait.installEventFilter(_CenterOnWindow(wait, host))
    # A dialog that appears for twenty milliseconds is noise, and it reads
    # as "something failed" (reported: "a dialog appears and disappears at
    # once and the sequence is not built"). It is shown only when the work
    # really takes a moment; if it finishes first, the observer never sees
    # it. _reap_wait cancels the pending show.
    wait._show_timer = QTimer(wait)
    wait._show_timer.setSingleShot(True)
    wait._show_timer.timeout.connect(wait.show)
    wait._show_timer.start(_BUSY_SHOW_MS)
    return wait


def _reap_wait(wait):
    # @args: wait - the busy dialog to close once the worker finished
    timer = getattr(wait, "_show_timer", None)
    if timer is not None:
        timer.stop()
    wait.close()
    wait.deleteLater()


class UfeCompareTab(QWidget):
    pick_clicks = True   # clicks mark things: the dialog hands us
                           # the pick cursor + snapping reticle on stage

    sequence_changed = Signal()   # the entries grew/shrank (the UFE's
                                  # EXOTIC block enables itself from this)
    # @args: state - the shared UfeImageState, lang - "es" | "en",
    #        view - the UfeImageView the field overlays and picks live on

    def __init__(self, state, lang="es", view=None, parent=None):
        super().__init__(parent)
        self._state = state
        self._lang = lang
        self._view = view
        self._active = False         # owns the view's clicks right now
        self._on_stage = False       # the Photometry tab is on stage and
                                     # this section is visible (armed or
                                     # not): its overlays may be drawn
        self._field = None           # compstars.load_field result
        self._entries = []           # the sequence: name/kind/star dicts
        self._stars = []             # catalog stars with _sx/_sy cached
        self._items = []             # every overlay this tab owns
        self._pick_kind = "comp"
        self._catalog_visible = True
        self._catalog_items = []     # subset hidden with the checkbox
        self._auto_propose = False   # the field worker landed from the
                                     # one-click path: propose on arrival
        self._worker = None
        self._propose_worker = None  # the proposal's own thread (H2)
        self._names_before_build = None   # was the proposal any different?
        # what the observer had before a rebuild started: taken BEFORE the
        # catalogue query goes out (the field's arrival empties the table on
        # purpose), and what a failed or empty rebuild restores
        self._build_backup = []
        self._cutout_worker = None   # UfeCutoutWorker while DSS2 lands
        self._prefill_sky = None     # (ra, dec) from the host, for DSS2
        self._build_ui()
        state.image_loaded.connect(self._on_image_loaded)
        # a solve can land on the open plate: the stale "no WCS" line must
        # go without touching the (untouched) field
        state.wcs_changed.connect(self._on_wcs_changed)
        if view is not None:
            view.scene_clicked.connect(self._on_scene_clicked)
        self._on_image_loaded()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # The structure is the Designer file's (ADR-005); this method
        # aliases the widgets, fills the catalog combo (its items carry
        # userData, which a .ui cannot hold), raises the manual tweak
        # window from its toggle button and connects the signals.
        self._ui = adopt_ui(self, "ufe_compare_tab")
                                            # over: no wrapper, no extra
                                            # margins, and layout-walking
                                            # code sees the rows directly
        self.edt_target = self._ui.edt_target
        self.spn_mag = self._ui.spn_mag
        self.cmb_catalog = self._ui.cmb_catalog
        for key, spec in vizier.CATALOGS.items():
            self.cmb_catalog.addItem(spec["name"], key)
        # the one-click path: field + proposal in a single action
        self.btn_auto = self._ui.btn_auto
        self.btn_auto.clicked.connect(self._on_auto)
        self.btn_dss = self._ui.btn_dss
        self.btn_dss.clicked.connect(self._on_load_survey)
        self.lbl_status = self._ui.lbl_status
        self._status_hook = None     # the window's single status line (U4)

        # the manual tweak: its controls are translatable, so they live
        # in their own window (ui/ufe_manual_dialog.ui). The toggle
        # button, right of the DSS2 one, raises it; while it is open the
        # plate clicks pick stars, while it is closed they measure. Its
        # widgets are aliased here, so the old call sites keep finding
        # them, and their state (picking kind, labels) lives on the
        # widgets and survives close/reopen
        self._manual = UfeManualDialog(self)
        self.manual = self._manual
        self.manual.openStateChanged.connect(self._on_manual_visibility)
        self.btn_manual = self._ui.btn_manual
        self.btn_manual.toggled.connect(self._on_manual_toggled)
        self.rdo_comp = self._manual.rdo_comp
        self.rdo_check = self._manual.rdo_check
        self.rdo_check.toggled.connect(
            lambda on: setattr(self, "_pick_kind",
                               "check" if on else "comp"))
        self.chk_labels = self._manual.chk_labels
        self.chk_labels.toggled.connect(self._on_catalog_visible)
        self.btn_field = self._manual.btn_field
        self.btn_field.clicked.connect(self._on_generate)
        self.btn_propose = self._manual.btn_propose
        self.btn_propose.clicked.connect(self._on_propose)
        self.btn_seq_open = self._manual.btn_seq_open
        self.btn_seq_open.clicked.connect(self._open_sequence)

        # The table lives in its own small non-modal window (ADR-044 rev):
        # the tab stays compact, the window stays open for reading;
        # _reload_table rebuilds it through self.table and refreshes the
        # count behind the button. The window also carries the two
        # actions that used to sit on the tab ("Remove all", "Export
        # CSV…"), and we alias them here so old code keeps finding them.
        self._seqdlg = UfeSequenceDialog(self, on_clear=self._on_clear,
                                         on_export=self._export_csv)
        self.table = self._seqdlg.table
        self.btn_clear = self._seqdlg.btn_clear
        self.btn_csv = self._seqdlg.btn_export

    def set_status_hook(self, fn):
        # The window takes the messages (U4): its bottom line is where a
        # reader looks. The tab's own label stays as a record (hidden), so
        # everything that reads it keeps working.
        # @args: fn - callable(text, level) or None
        # @return: None
        self._status_hook = fn

    def _say(self, text, level=None):
        # Says one thing: to this tab's record AND to the window.
        # @args: text - the message, level - "info" | "warn" | "error"
        #        (None: inferred from the ⚠ the message already carries)
        # @return: None
        text = str(text)
        if level is None:
            level = "warn" if text.startswith("⚠") else "info"
        self.lbl_status.setText(text)      # the tab's own record (hidden)
        if self._status_hook is not None:
            self._status_hook(text, level)

    def _open_sequence(self):
        # @return: the sequence window rises, non-modal, so picking stars
        # keeps going while it is open
        self._seqdlg.show()
        self._seqdlg.raise_()
        self._seqdlg.activateWindow()

    def _on_manual_toggled(self, on):
        # The button is the switch of the manual tweak window: check it
        # and the window rises, uncheck it and it goes away (the plate
        # clicks go back to measuring).
        # @args: on - toggle checked (show) or unchecked (hide)
        if on:
            self._manual.show()
            self._manual.raise_()
            self._manual.activateWindow()
        else:
            self._manual.hide()

    def _on_manual_visibility(self, visible):
        # The window can also be closed through its X (or die with the
        # host): keep the toggle honest in that case.
        # @args: visible - the dialog's new visibility state
        if not visible and self.btn_manual.isChecked():
            self.btn_manual.blockSignals(True)
            self.btn_manual.setChecked(False)
            self.btn_manual.blockSignals(False)

    def manual_visible(self):
        # @return: the manual tweak window is up: the plate clicks then
        #          pick stars, and closed state they measure
        return self._manual.isVisible()

    # ------------------------------------------------------- activation

    def set_active(self, flag, keep_overlays=False):
        # Stage handoff, two distinct concepts (ADR-044 rev): the CLICKS
        # follow the armed section (self._active), the OVERLAYS follow
        # the Photometry tab's stage (self._on_stage): both sections are
        # visible at once, so a disarmed section keeps its rings and its
        # probe, and its buttons (Generate field, Propose) must paint.
        # @args: flag - owns the clicks or not, keep_overlays - leaving
        #        the stage for the sister section: the sequence stays
        #        visible and its probe keeps talking (the Measure
        #        section measures WITH it); a full leave drops all
        self._active = bool(flag)
        if self._view is None:
            return
        if self._active:
            self._on_stage = True
            self._view.set_hover_probe(self._probe)
            self._redraw_overlays()
        elif keep_overlays:
            # disarmed but on stage: the overlays follow the TAB, so the
            # stage flag must be set even when this section was never
            # armed (the visit deep link lands straight on Measure)
            self._on_stage = True
        else:
            self._on_stage = False
            self._view.set_hover_probe(self._state.probe_text)
            self._drop_items()

    # ------------------------------------------------------------- state

    def _on_image_loaded(self):
        # A new plate stalemates the field; the target name defaults to
        # the plate's stem. The tab never disables: without a plate the
        # survey button is the way in (ADR-044 rev).
        self.reset_state()
        if self._state.has_image:
            self.edt_target.setText(Path(self._state.path).stem)
            if self._state.wcs is None:
                self._say(self._no_wcs_hint())

    def _no_wcs_hint(self):
        # @return: the "solve it first" line, shared by the load and the
        #          stale-message clear (same source, same translation)
        return self.tr(
            "The plate has no WCS: solve it with «Solve astrometry…» to "
            "build the comparison field.")

    def _on_wcs_changed(self):
        # A solve landed on the open plate: the "no WCS" line is stale.
        # Re-state the neutral field line (the solve never touched the
        # sequence, so the field is not reset here).
        if not (self._state.has_image and self._state.wcs is not None):
            return
        if self._field is None and self.lbl_status.text() == self._no_wcs_hint():
            self._say(self.tr(
                "The sequence field is empty: build it with «Generate "
                "field…», or restore the one saved with the plate."))

    def shutdown(self):
        # Stops the propose thread before the tab goes: a QThread destroyed
        # while it runs aborts the whole application (the shiboken trap the
        # Blink tab already documents).
        # @return: None
        worker = getattr(self, "_propose_worker", None)
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(3000)
        self._propose_worker = None
        self._reap_propose_wait()

    def clear_session(self):
        # A different PROJECT is a different session (issue report: opening
        # the workbench on another project kept the previous one's plate,
        # sequence and target). The dialog asks for this on every change of
        # project, and nothing here is a deletion of the observer's work:
        # the sequence lives in its project and comes back with it.
        # @return: None
        self.reset_state()
        self.edt_target.clear()
        self._prefill_sky = None
        self._auto_propose = False
        if self._worker is not None:
            self._worker = None
        if self._cutout_worker is not None:
            self._cutout_worker = None

    def reset_state(self):
        # ADR-047: the sequence field's zero point: no catalog, no
        # entries, empty table, a neutral status. The state reset in the
        # Measure tab goes through here (the new-plate stalemate above
        # reuses it too).
        # @args: none
        # @return: None
        self._field = None
        self._entries = []
        self._stars = []
        self._drop_items()
        if self._state.has_image:
            self._say(self.tr(
                "The sequence field is empty: build it with «Generate "
                "field…», or restore the one saved with the plate."))
        else:
            self._say(self.tr(
                "No plate loaded: load a FITS or fetch the field from "
                "the survey."))
        self._reload_table()

    # ----------------------------------------------------- state (ADR-047)

    def capture_state(self):
        # The sequence (and the field that produced it), as plain JSON
        # (ADR-047): the catalog, the sky centre and width, the target
        # magnitude and every chosen star with the photometry the
        # calibration needs (band + bands). Only stars inside entries are
        # kept: the rest is re-derivable from the catalog.
        #
        # THE SEQUENCE IS THE OBSERVER'S WORK AND DOES NOT NEED A LIVE
        # FIELD: it survives a frame with no WCS and a field that has not
        # been rebuilt yet (the visit's navigator captures and re-applies
        # this state on every frame). The catalog key comes from the combo;
        # the centre and the width only exist when there is a field.
        # @return: None when there is neither a sequence nor a field
        if self._field is None and not self._entries:
            return None
        field = self._field or {}
        catalog = field.get("catalog") or self.cmb_catalog.currentData()
        if not catalog:
            return None
        return {
            "catalog": catalog,
            "catalog_name": field.get("catalog_name")
            or self.cmb_catalog.currentText(),
            "center": list(field.get("center") or ()),
            "fov_arcmin": float(field.get("fov_arcmin") or 0.0),
            "target_mag": float(self.spn_mag.value()),
            "entries": [
                {
                    "name": e["name"],
                    "kind": e["kind"],
                    "star": {
                        "id": e["star"].get("id"),
                        "ra": e["star"].get("ra"),
                        "dec": e["star"].get("dec"),
                        "band": e["star"].get("band"),
                        "mag": e["star"].get("mag"),
                        "bv": e["star"].get("bv"),
                        "color_origin": e["star"].get("color_origin"),
                        "catalog": e["star"].get("catalog"),
                        "bands": [
                            {"label": b.get("label"),
                             "value": b.get("value"),
                             "err": b.get("err"),
                             "derived": bool(b.get("derived", False))}
                            for b in (e["star"].get("bands") or [])
                            if isinstance(b, dict)],
                    },
                }
                for e in self._entries
            ],
        }

    def apply_state(self, st):
        # Restores a plate's saved field and sequence (ADR-047): the
        # saved stars are re-placed by their sky coordinates into THIS
        # plate (no WCS or out of the plate means the star is dropped,
        # it stays only in the table via _stars when placed), the
        # catalog combo points back at the saved key and the target
        # magnitude returns. No proposal: that is the observer's beat.
        # @args: st - capture_state dict (None/empty is a no-op)
        if not st or not st.get("catalog"):
            return
        catalog = st["catalog"]
        # NO FIELD IS FABRICATED HERE. A field is a live answer from the
        # catalogue (with its stars placed on THIS plate), not a saved
        # artifact: the state keeps the sequence, the catalog key and the
        # target magnitude, and that is what comes back. This used to build
        # a field with "stars": [] and leave it in place, and the visit's
        # frame navigator re-applies this state on every frame, so on the
        # new plate _field was set but empty: "Build the sequence" believed
        # the field was there and proposed over nothing ("The proposal found
        # no usable comparison star", reported), while the manual
        # "Generate field" filled the stars again and everything worked.
        if self._field is not None and not self._stars:
            # a field that has no stars on this plate is not a field either
            self._field = None
        placed = []      # stars that landed on this plate (overlays)
        pairs = []       # (star, saved entry): EVERY entry is kept, the
                         # sequence is RA/Dec and survives a frame with no
                         # WCS (only its overlays need one)
        for raw in (st.get("entries") or []):
            rs = raw.get("star") or {}
            star = {
                "id": rs.get("id"),
                "name": None,
                "ra": rs.get("ra"),
                "dec": rs.get("dec"),
                "band": rs.get("band"),
                "mag": rs.get("mag"),
                "bv": rs.get("bv"),
                "color_origin": rs.get("color_origin"),
                "catalog": rs.get("catalog"),
                "bands": [b for b in (rs.get("bands") or [])
                          if isinstance(b, dict)],
                "vsx": None,
            }
            if star.get("mag") is None:
                continue     # the table formats the magnitude
            pos = self._sky_to_scene(star["ra"], star["dec"])
            if pos is not None:
                star["_sx"], star["_sy"] = pos
                placed.append(star)
            pairs.append((star, raw))
        self._stars = placed
        self._entries = []
        for star, raw in pairs:
            kind = raw.get("kind") or "comp"
            self._entries.append({
                "name": str(raw.get("name") or self._next_name(kind)),
                "kind": kind,
                "star": star,
                "why": {"es": "devuelta de la placa",
                        "en": "restored from the plate"}})
        # the combo lists the shipped catalogs; a saved one from an
        # older build gets added so the export keeps its label
        if self.cmb_catalog.findData(catalog) < 0:
            self.cmb_catalog.addItem(
                self._field["catalog_name"], catalog)
        self.cmb_catalog.setCurrentIndex(
            self.cmb_catalog.findData(catalog))
        if st.get("target_mag") is not None:
            self.spn_mag.setValue(float(st["target_mag"]))
        self._auto_propose = False   # the restored field must not be
                                     # re-proposed under the observer's feet
        self._reload_table()
        self._redraw_overlays()     # no-ops off stage (it checks itself)
        # the catalog NAME comes from the state (the field is not restored
        # any more: it is a live answer, see above)
        self._say(self.tr(
            "{0}: {1} in the sequence ({2} placed on this frame)")
            .format(st.get("catalog_name") or catalog, len(self._entries),
                    len(self._stars)))

    # ------------------------------------------------------------- field

    def _on_load_survey(self):
        # Load a survey field (DSS2/PS1): the plate centre when there is
        # one, the host's coordinates when we were opened from a project,
        # else an object name resolved by the usual sources. Network off
        # the GUI thread; the cutout loads as a normal plate.
        ra = dec = None
        if self._state.has_image and self._state.wcs is not None:
            ra, dec = self._state.wcs.center()
        elif self._prefill_sky is not None:
            ra, dec = self._prefill_sky
        else:
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(
                self, self.tr("Survey field"),
                self.tr("Object or field name (SIMBAD):"))
            if not ok or not name.strip():
                return
            from ..core import blink as _blink
            try:
                target = _blink.resolve_sn(name.strip())
            except _blink.BlinkError as err:
                self._say(
                    "⚠ " + err.messages.get(self._lang, ""))
                return
            ra, dec = target["ra"], target["dec"]
            self.edt_target.setText(target["name"])
            self._prefill_sky = (ra, dec)
        from .workers import UfeCutoutWorker
        self.btn_dss.setEnabled(False)
        self._say(self.tr("Downloading the survey field…"))
        wait = _busy_wait(self, self.tr("Downloading the survey field…"),
                          self.tr("Comparison field"))
        self._cutout_worker = UfeCutoutWorker(ra, dec)
        self._cutout_worker.progress.connect(
            lambda msg: wait.setLabelText(msg.get(self._lang, "")))
        self._cutout_worker.progress.connect(
            lambda msg: self._say(msg.get(self._lang, "")))

        def survey_landed(result):
            # same rule as the field chain: the modal dialog is always
            # reaped, whatever the landing does
            try:
                self._on_survey_landed(result)
            except Exception as err:
                logger.exception("survey landing failed: %s", err)
                self._say(str(err))
            finally:
                _reap_wait(wait)
        self._cutout_worker.finished.connect(survey_landed)
        self._cutout_worker.start()

    def _on_survey_landed(self, result):
        # @args: result - (local FITS path, survey label) or (None, None)
        self.btn_dss.setEnabled(True)
        self._cutout_worker = None
        path, label = result
        if not path:
            self._say(self.tr(
                "The survey download failed (offline?). Try again later."))
            return
        try:
            self._state.load(path)
        except Exception as err:
            logger.warning("survey cutout unreadable: %s", err)
            self._say(str(err))
            return
        self._say(self.tr("Field loaded: {0}").format(label))

    def _on_auto(self):
        # The one-click path (ADR-044 rev 2026-09-25): with a field
        # already loaded it only re-proposes; without one it generates
        # the field and the proposal runs the moment the field lands.
        # Both paths sit under the busy dialog: the proposal is local
        # math, but on a big field it still takes its moment, and a
        # bare freeze reads as a hang.
        if self._field is not None and self._stars:
            # THE WAIT BELONGS TO WHOEVER DOES THE WORK, and that is either
            # an inline proposal (a tenth of a second on a normal field, and
            # it needs no dialog at all) or the proposal's own thread (which
            # shows its own bar until it lands).
            #
            # This branch used to wrap the call in a wait of its own, from
            # when the proposal was synchronous: with the thread it opened
            # and closed in the same instant (measured: 0.00 s open), which
            # the observer read as "a dialog appears and disappears and
            # nothing happens" (reported).
            self._on_propose()
            return
        # A plate with no solved position used to be an exception when the
        # project ALREADY had its sequence loaded (the normal case in a
        # visit): the click stopped and explained that the rings needed a
        # solved plate, so no solve, no field and no proposal. That was
        # written when a blind solve took 66 s (the dialog came and went and
        # nothing was built, reported) and it left the observer with no
        # field at all: "Build the sequence needs the field generated first,
        # otherwise it finds nothing" (reported). The solve is a tenth of a
        # second now (ADR-051: the project's field points it), so the
        # pipeline is the same whatever the plate carries, solve then field
        # then proposal. What the observer already has is kept while the
        # catalogue answers: a query that fails, that returns nothing ON THIS
        # PLATE, or a solve that does not land, must not leave them with an
        # empty sequence (reported as "it builds nothing" when what it did
        # was erase what was there).
        self._build_backup = list(self._entries)
        self._auto_propose = True
        self._on_generate()

    def _explain_no_wcs(self):
        # The automatic solve did not land: the field cannot be built and
        # the observer reads why (the manual button is still there).
        self._auto_propose = False
        self._say(self.tr(
            "The plate has no WCS and it could not be solved: use «Solve "
            "astrometry…» or check the solver in Settings."), "warn")

    def _on_generate(self):
        # Generate field: VizieR catalog + VSX variables around the plate
        # centre, off the GUI thread.
        if not self._state.has_image:
            # never a silent no-op: without a plate there is no centre to
            # query around and nothing to propose
            self._auto_propose = False
            self._say(self.tr(
                "Load a plate first (or fetch the field from the survey "
                "with «DSS2…»): the catalogue is queried around its "
                "centre."))
            return
        if self._state.wcs is None:
            # ADR-051: solving is automatic now, never a hand-off
            self._say(self.tr(
                "The plate has no WCS: solving it to build the comparison "
                "field…"))
            dlg = self.window()
            req = getattr(dlg, "request_wcs", None)
            if callable(req):
                req(lambda: self._on_generate(),
                    on_fail=self._explain_no_wcs)
                return
            self._auto_propose = False
            self._explain_no_wcs()
            return
        from .workers import UfeFieldWorker
        ra, dec = self._state.wcs.center()
        w, h = self._state.plate_shape
        fov_arcmin = max(w, h) * self._state.wcs.pixel_scale() / 60.0
        self.btn_field.setEnabled(False)
        self._say(self.tr("Querying the catalog…"))
        # The queries take seconds: cover them with the busy dialog the
        # legacy flow had (a status line alone reads as "nothing
        # happens"). The bar walks the real stages (catalog → VSX →
        # proposal): an indeterminate bar that never moves reads as
        # stuck.
        wait = _busy_wait(self, self.tr("Querying the catalog…"),
                          self.tr("Comparison field"))
        wait.setRange(0, 3)
        wait.setValue(0)
        stage = {"n": 0}
        # the field is the sensor's real rectangle (w x h pixels) shrunk by
        # a safety ring, not a square: quality plan, C2
        from ..core import compstars
        margin = compstars.COMP_MARGIN_ARCSEC
        self._worker = UfeFieldWorker(self.cmb_catalog.currentData(),
                                      ra, dec, fov_arcmin,
                                      naxis=(w, h), margin_arcsec=margin)

        def _stage(msg):
            # @args: msg - the worker's {"es", "en"} stage text
            wait.setLabelText(msg.get(self._lang, ""))
            self._say(msg.get(self._lang, ""))
            stage["n"] = min(stage["n"] + 1, 1)
            wait.setValue(stage["n"])
        self._worker.progress.connect(_stage)

        def field_landed(field):
            # the one-click chain stays covered end to end: the proposal
            # runs under the dialog, and the dialog is ALWAYS reaped (a
            # modal dialog surviving an exception reads as a hang)
            try:
                if self._auto_propose:
                    wait.setLabelText(self.tr("Proposing the sequence…"))
                    wait.setValue(2)
                self._on_field_ready(field)
            except Exception as err:
                logger.exception("field handling failed: %s", err)
                self._auto_propose = False
                self._say(self.tr(
                    "The field landed but its handling failed: {0}")
                    .format(err))
            finally:
                wait.setValue(3)
                _reap_wait(wait)
        self._worker.finished.connect(field_landed)
        self._worker.start()

    def _restore_sequence(self, message):
        # Says why the build could not deliver, and puts back what the
        # observer had. Nothing is deleted: a rebuild that cannot deliver
        # keeps the sequence it was going to replace.
        #
        # The reason is said ALWAYS (even with nothing to restore: a failure
        # the observer cannot read is a failure nobody can fix); the "it is
        # kept" half is added when there was a sequence to keep. The text
        # arrives already through self.tr, like every other visible string
        # of this widget.
        # @args: message - the reason, translated
        # @return: True when something was restored
        backup = list(getattr(self, "_build_backup", None) or [])
        self._build_backup = []
        text = message
        if not backup:
            # a WARNING, not a note: "the build did not deliver" is news the
            # observer has to see (the line is styled, see set_status)
            self._say(text, "warn")
            return False
        self._entries = backup
        self._redraw_entries()
        self._reload_table()
        self._commit()
        self._say(self.tr(
            "{0} Your sequence of {1} stars is kept; nothing was lost."
        ).format(text, len(backup)), "warn")
        return True

    def _on_field_ready(self, field):
        # @args: field - compstars.load_field result, or {} on failure
        self.btn_field.setEnabled(True)
        self._worker = None
        if not field:
            self._auto_propose = False
            self._restore_sequence(self.tr(
                "The catalog query failed (offline?). Try again later."))
            return
        self._field = field
        self._entries = []
        self._stars = []
        for star in field.get("stars", []):
            pos = self._sky_to_scene(star["ra"], star["dec"])
            if pos is None:
                continue
            star["_sx"], star["_sy"] = pos
            self._stars.append(star)
        if not self._stars:
            # the catalogue answered but NOTHING lands on this plate: the
            # pointing is wrong, the field is too small, or the plate is a
            # crop. Either way there is nothing to propose, and the
            # observer's own sequence is worth more than an empty table.
            self._auto_propose = False
            self._restore_sequence(self.tr(
                "The catalogue returned no stars inside this plate (is the "
                "pointing right?)."))
            return
        wcs_note = ""
        if field.get("vsx_warning"):
            wcs_note = " · " + self.tr("VSX check failed")
        self._say(
            self.tr("{0} · field {1}′ · {2} catalog stars on the plate · "
                    "{3} known variables").format(
                        field.get("catalog_name", ""),
                        f"{field.get('fov_arcmin', 0):g}",
                        len(self._stars),
                        len(field.get("variables", []))) + wcs_note)
        self._reload_table()
        # paint follows the stage, not the clicks: the field can land
        # while the Measure section is armed (opened from a visit) and
        # the Comparisons half is still on view
        if self._on_stage:
            self._redraw_overlays()
        # the one-click path: the proposal rides the landing (local math,
        # but it gets its own beat in the status line so the chain reads)
        if self._auto_propose:
            self._auto_propose = False
            self._say(self.tr("Proposing the sequence…"))
            self._on_propose()

    def _sky_to_scene(self, ra, dec):
        # @return: (x, y) scene coords for a sky position through the
        #          plate's WCS, or None when it lands off the plate
        if self._state.wcs is None:
            return None
        try:
            col, row = self._state.wcs.sky_to_pixel(ra, dec)
        except Exception:
            return None
        w, h = self._state.plate_shape
        if not (0 <= col < w and 0 <= row < h):
            return None
        return self._state.data_to_scene(col, row)

    # ----------------------------------------------------------- overlays

    def _pen(self, hex_color, width=1.6):
        pen = QPen(QColor(hex_color))
        pen.setWidthF(width)
        pen.setCosmetic(True)
        return pen

    def _text(self, text, x, y, hex_color, size, bold=False, anchor="left"):
        # @return: a label item; size in PLATE px like the FinderChart's
        it = QGraphicsSimpleTextItem(text)
        it.setBrush(QBrush(QColor(hex_color)))
        f = QFont("monospace")
        f.setPixelSize(max(6, int(size)))
        f.setBold(bold)
        it.setFont(f)
        br = it.boundingRect()
        if anchor == "right":
            it.setPos(x - br.width(), y - br.height() / 2.0)
        elif anchor == "center":
            it.setPos(x - br.width() / 2.0, y - br.height() / 2.0)
        else:
            it.setPos(x, y - br.height() / 2.0)
        it.setZValue(55)
        return it

    def _drop_items(self):
        if self._view is not None:
            for it in self._items:
                try:
                    self._view.scene().removeItem(it)
                    if it in self._view._items_registered:
                        self._view._items_registered.remove(it)
                except RuntimeError:
                    pass
        self._items = []
        self._catalog_items = []
        self._entry_items = []

    def _redraw_overlays(self):
        # Repaints the whole compare layer: catalog labels (brightest
        # first, collision-free), known-variable rings, the target and
        # the sequence entries.
        self._drop_items()
        if not self._on_stage or self._view is None or self._field is None:
            return
        w, h = self._state.plate_shape
        # catalog: only the brightest stars get ring + magnitude label
        # (the FinderChart's rule; the rest is click target only)
        labelled = sorted(self._stars, key=lambda s: s["mag"])[
            :_MAX_LABELS]
        in_seq = {id(e["star"]) for e in self._entries}
        r_cat = w * 0.0065
        self._catalog_items = []         # [(item, star_id)]
        for star in labelled:
            if id(star) in in_seq:
                continue                # the entry carries its own label
            x, y = star["_sx"], star["_sy"]
            ring = QGraphicsEllipseItem(x - r_cat, y - r_cat,
                                        2 * r_cat, 2 * r_cat)
            ring.setPen(self._pen(C_RING, 1.4))
            ring.setVisible(self._catalog_visible)
            self._items.append(self._view.add_overlay(ring))
            self._catalog_items.append((ring, id(star)))
            right = x > w * 0.82
            txt = self._text(f"{star['mag']:.2f}",
                             x - r_cat * 1.7 if right
                             else x + r_cat * 1.7,
                             y - r_cat * 1.2, palette.FG, w * 0.011,
                             anchor="right" if right else "left")
            txt.setVisible(self._catalog_visible)
            self._items.append(self._view.add_overlay(txt))
            self._catalog_items.append((txt, id(star)))
        # known variables: red rings, never pickable
        for var in self._field.get("variables", []):
            pos = var.get("star") or var
            p = self._sky_to_scene(pos["ra"], pos["dec"])
            if p is None:
                continue
            x, y = p
            mag = (var.get("star") or {}).get("mag")
            radius = (8 + (14 - mag) * 1.15) if mag is not None else 10.0
            radius = max(7.0, min(20.0 * w / 1000.0, radius))
            ring = QGraphicsEllipseItem(x - radius, y - radius,
                                        2 * radius, 2 * radius)
            ring.setPen(self._pen(C_VAR, 1.6))
            self._items.append(self._view.add_overlay(ring))
        self._redraw_entries()

    def _redraw_entries(self):
        # Sequence rings (comp cyan circles, check pink squares) plus
        # names; stars in the sequence lose their catalog label.
        self.sequence_changed.emit()
        if self._view is None:
            return
        for it in getattr(self, "_entry_items", []):
            try:
                self._view.scene().removeItem(it)
                if it in self._view._items_registered:
                    self._view._items_registered.remove(it)
                if it in self._items:
                    self._items.remove(it)
            except RuntimeError:
                pass
        self._entry_items = []
        if not self._on_stage or self._field is None:
            return
        w, _h = self._state.plate_shape
        in_seq = {id(e["star"]) for e in self._entries}
        for it, star_id in self._catalog_items:
            it.setVisible(self._catalog_visible and star_id not in in_seq)
        r = w * 0.012
        for e in self._entries:
            star = e["star"]
            if star.get("_sx") is None:
                continue        # not placeable on this (unsolved) frame
            x, y = star["_sx"], star["_sy"]
            if e["kind"] == "check":
                item = QGraphicsRectItem(x - r, y - r, 2 * r, 2 * r)
                item.setPen(self._pen(C_CHECK, 1.8))
                colour = C_CHECK
            else:
                item = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
                item.setPen(self._pen(C_COMP, 1.8))
                colour = C_COMP
            self._entry_items.append(self._view.add_overlay(item))
            self._items.append(item)
            right = x > w * 0.78
            txt = self._text(e["name"], x - 1.6 * r if right
                             else x + 1.6 * r, y - 1.3 * r, colour,
                             w * 0.016, bold=True,
                             anchor="right" if right else "left")
            self._entry_items.append(self._view.add_overlay(txt))
            self._items.append(txt)

    def _on_catalog_visible(self, flag):
        self._catalog_visible = bool(flag)
        in_seq = {id(e["star"]) for e in self._entries}
        for it, star_id in self._catalog_items:
            it.setVisible(flag and star_id not in in_seq)

    # ------------------------------------------------------------ picking

    def _nearest_star(self, sx, sy):
        # @return: the catalog star within a constant SCREEN radius (~11
        #          px) of the scene point, or None
        if self._view is None:
            return None
        radius = _PICK_PX / max(self._view.current_factor(), 1e-3)
        best, best_d = None, radius * radius
        for s in self._stars:
            dx, dy = s["_sx"] - sx, s["_sy"] - sy
            d = dx * dx + dy * dy
            if d < best_d:
                best, best_d = s, d
        return best

    def nearest_field_star(self, ra, dec, tol_arcsec=8.0):
        # The Measure tab's cross-match: the loaded field star nearest to
        # a sky position (the measured centroid), within tolerance.
        # @args: ra, dec - degrees, tol_arcsec - maximum separation
        # @return: (star, separation in arcsec), or (None, None)
        best, best_sep = None, float(tol_arcsec)
        for s in self._stars:
            sep = compstars.separation_arcsec({"ra": ra, "dec": dec}, s)
            if sep < best_sep:
                best, best_sep = s, sep
        if best is None:
            return None, None
        return best, best_sep

    def _next_name(self, kind):
        # Comp1, Comp2… / Check, Check2… (SecFot's convention)
        make = (lambda n: "Check" if n == 1 else f"Check{n}") \
            if kind == "check" else (lambda n: f"Comp{n}")
        k = 1
        while any(e["name"] == make(k) for e in self._entries):
            k += 1
        return make(k)

    def _on_scene_clicked(self, scene_pt):
        # A click toggles the nearest star in/out of the sequence; known
        # variables refuse with a reason.
        if not self._active or self._field is None:
            return
        star = self._nearest_star(scene_pt.x(), scene_pt.y())
        if star is None:
            return
        existing = next((i for i, e in enumerate(self._entries)
                         if e["star"] is star), -1)
        if existing >= 0:
            del self._entries[existing]
        else:
            if star.get("vsx"):
                self._say(self.tr(
                    "{0} is a known variable: it can never be a "
                    "comparison.").format(star["vsx"].get("name", "?")))
                return
            kind = self._pick_kind
            self._entries.append({
                "name": self._next_name(kind), "kind": kind,
                "star": star,
                "why": {"es": "elegida a mano", "en": "picked by hand"}})
        self._redraw_entries()
        self._reload_table()
        self._commit()

    def _probe(self, sx, sy):
        # Hover probe while on stage: the star under the cursor, else the
        # state's pixel/DN/RA probe.
        # @return: (hit, lines)
        star = self._nearest_star(sx, sy)
        if star is None:
            return self._state.probe_text(sx, sy)
        lines = [f"{star['catalog']} {star['id']}",
                 f"{star['band']} {star['mag']:.2f}"]
        if star.get("bv") is not None:
            approx = "" if star.get("color_origin") == "direct" else " ≈"
            lines.append(f"B−V {star['bv']:.2f}{approx}")
        if star.get("vsx"):
            var = star["vsx"]
            extra = f" ({var['type']})" if var.get("type") else ""
            lines.append(self.tr("VSX variable") + f": {var['name']}{extra}")
            lines.append(self.tr("variables cannot be comparisons"))
        else:
            lines.append(self.tr("click: add/remove from the sequence"))
        return True, [ln for ln in lines if ln]

    # ---------------------------------------------------------- proposal

    def _comp_validator(self):
        # The observer's own plate is the only thing that can say whether a
        # catalogue star is usable (quality plan, C1): the saturated core,
        # the linearity limit, the sensor's edge and the real SNR all live
        # here. Returns None when there is no plate to check against, and
        # then the proposal is the catalogue's alone (as it always was).
        # @return: a callable(star, role) -> None | {"key","es","en"}
        state = self._state
        if state is None or state.data is None or state.wcs is None:
            return None
        from ..config import config
        from ..core import compstars, photometry
        sat = photometry.saturation_ceiling(
            state.header, {"ccd_saturate": config.get("ccd_saturate")})
        lin = photometry.linearity_ceiling(config)
        gain = config.get("ccd_gain")
        ron = config.get("ccd_read_noise")
        # the Compare tab owns no aperture spins (the Measure tab does), so
        # the check uses the recipe's own default radii: saturation,
        # linearity, the sensor's edge and the SNR do not depend on the
        # exact radius
        radii = None
        scale = state.wcs.pixel_scale() or 1.0
        margin_px = compstars.COMP_MARGIN_ARCSEC / scale
        shape = state.data.shape

        def validator(star, _role="comp"):
            return compstars.validate_on_plate(
                star, state.data, state.wcs, radii=radii, sat_adu=sat,
                linear_adu=lin, gain=gain, ron=ron, shape=shape,
                margin_px=margin_px)
        return validator

    def _on_propose(self):
        # The automatic sequence: isolated, non-variable stars matched to
        # the target's brightness (compstars' criteria), VALIDATED on the
        # open plate (quality plan, C1): saturated, non-linear, off-sensor
        # or too faint candidates are dropped with their reason said.
        #
        # ONE DECISION, SAID OUT LOUD. The plate check is the expensive
        # half (measuring a candidate asks the plate, and there can be
        # hundreds): it runs off the GUI thread when there is a plate to ask
        # and the status line narrates it. With no plate there is nothing
        # expensive to do: the catalogue's own criteria are arithmetic over
        # a list, and a dialog for that would be noise.
        if self._field is None or not self._stars:
            # THE STEP THAT IS MISSING, DONE HERE: the field (and the solve
            # behind it when the plate has none), then the proposal. Asking
            # the observer to press another button for a step this one needs
            # was a riddle, and it is the same report the one-click button
            # answers: "Build the sequence needs the field generated first,
            # otherwise it finds nothing".
            self._build_backup = list(self._entries)
            self._auto_propose = True
            self._on_generate()
            return
        self._flush_table()
        # The backup is what the observer had BEFORE this rebuild started.
        # The field's arrival empties the table on purpose (a new field is a
        # new sequence), so taking a fresh copy here would back up an empty
        # sequence and lose theirs: the one the rebuild must be able to
        # restore was taken before the query went out.
        if not self._build_backup:
            self._build_backup = list(self._entries)
        # and "was it any different?" compares against that same truth: with
        # the table already empty (the rebuild path) the reference is the
        # sequence the rebuild is about to replace.
        self._names_before_build = [e.get("name") for e in
                                    (self._entries or self._build_backup)]
        validator = self._comp_validator()
        if validator is None:
            self._say(self.tr(
                "Proposing the sequence from the {0} catalog stars on the "
                "plate (no plate to check them against yet).").format(
                    len(self._stars)))
            self._propose_inline(validator)
            return
        if len(self._stars) < _PROPOSE_THREAD_MIN:
            # a field this size is a tenth of a second of arithmetic: the
            # status line says what is happening and the window never
            # notices
            self._say(self.tr(
                "Proposing the sequence: checking the {0} catalog stars on "
                "your plate…").format(len(self._stars)))
            self._propose_inline(validator)
            return
        self._start_propose_worker(validator)

    def _propose_inline(self, validator):
        # The plain path: no plate to ask, so nothing to wait for.
        # @args: validator - None
        # @return: None
        try:
            seq = compstars.propose_comps(
                self._stars, self.spn_mag.value(), validator=validator,
                margin_arcsec=compstars.COMP_MARGIN_ARCSEC)
        except Exception as err:
            logger.exception("sequence proposal failed: %s", err)
            self._say(self.tr("Could not build the sequence: {0}").format(
                err), "error")
            return
        self._apply_proposal(seq)

    def _start_propose_worker(self, validator):
        # The plate has to be asked once per candidate: that is seconds on a
        # crowded field, so it goes to a thread and the window stays alive.
        # The wait is the shared one (shown only if the work really takes a
        # moment, with a real Cancel).
        # @args: validator - the plate's verdict callable
        # @return: None
        from .workers import UfeProposeWorker
        self._propose_worker = UfeProposeWorker(
            self._stars, self.spn_mag.value(), validator,
            margin_arcsec=compstars.COMP_MARGIN_ARCSEC)
        self._propose_worker.progress.connect(self._on_propose_stage)
        self._propose_worker.finished.connect(self._on_proposed)
        self._propose_worker.cancelled.connect(self._on_propose_cancelled)
        self._say(self.tr(
            "Proposing the sequence: checking the {0} catalog stars on your "
            "plate…").format(len(self._stars)))
        self._propose_wait = _busy_wait(
            self, self.tr("Checking the candidates on your plate…"),
            self.tr("Comparisons"))
        self._propose_wait.canceled.connect(self._propose_worker.cancel)
        self._propose_worker.start()

    def _on_propose_stage(self, stage):
        # @args: stage - {"es", "en"} from the worker
        if stage:
            self._say(stage.get(self._lang, stage.get("en", "")))

    def _on_proposed(self, seq):
        # @args: seq - the compstars result, or None on a data failure
        self._reap_propose_wait()
        self._propose_worker = None
        if seq is None:
            self._say(self.tr(
                "Could not build the sequence: the plate check failed."),
                "error")
            return
        self._apply_proposal(seq)

    def _on_propose_cancelled(self):
        self._reap_propose_wait()
        self._propose_worker = None
        self._say(self.tr(
            "Sequence proposal cancelled: nothing was changed. Your "
            "sequence is as it was."))

    def _reap_propose_wait(self):
        wait = getattr(self, "_propose_wait", None)
        if wait is not None:
            self._propose_wait = None
            _reap_wait(wait)

    def _apply_proposal(self, seq):
        # The proposal's outcome, said in the observer's words: what was
        # proposed, what the PLATE refused (with its reasons), and whether
        # anything changed at all.
        # @args: seq - the compstars result
        # @return: None
        self._entries = (seq["comps"]
                         + ([seq["check"]] if seq["check"] else []))
        self._redraw_entries()
        self._reload_table()
        text = self.tr("Proposed {0} comparisons (tweak by clicking "
                       "stars).").format(len(self._entries))
        rejected = seq.get("rejected") or []
        if rejected:
            counts = {}
            for r in rejected:
                counts[r.get("key") or "other"] = counts.get(
                    r.get("key") or "other", 0) + 1
            text += " " + self.tr("Left out {0} on your own plate: {1}").format(
                len(rejected),
                ", ".join(f"{k} × {v}" for k, v in sorted(counts.items())))
        if not self._entries:
            # THE REASON, NOT JUST THE VERDICT. This message used to be the
            # bare "no usable comparison star" and the reasons built above
            # were thrown away with it, so a report like "it finds nothing"
            # could not be answered from what the observer sees.
            if not self._stars:
                why = self.tr("The field has no stars on this plate: rebuild "
                              "it with «Generate field…».")
            elif not rejected:
                why = self.tr("No catalog star survived the field's own "
                              "rules: all of them are known variables or sit "
                              "too close to a neighbour.")
            else:
                why = self.tr("The proposal found no usable comparison "
                              "star.")
            if self._restore_sequence(why):
                return
        self._build_backup = []
        if self._last_proposal_was_same():
            text += " " + self.tr("The sequence is the same as before.")
        self._say(text)
        self._commit()

    def _last_proposal_was_same(self):
        # @return: True when the proposal did not change the sequence
        before = getattr(self, "_names_before_build", None)
        now = [e.get("name") for e in self._entries]
        return before is not None and before == now

    # ------------------------------------------------------------- table

    def _reload_table(self):
        # Rebuilds the table from the entries (after chart picks). Band and
        # magnitude are editable: the observer can override what the
        # catalog gave (a comp with a bad catalogue value, a band the
        # catalog lacks); the manual value feeds the calibration.
        self._table_building = True
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._entries))
        for i, e in enumerate(self._entries):
            self.table.setItem(i, 0, QTableWidgetItem(e["name"]))
            combo = QComboBox()
            combo.addItem("Comp", "comp")
            combo.addItem("Check", "check")
            combo.setCurrentIndex(1 if e["kind"] == "check" else 0)
            combo.currentIndexChanged.connect(
                lambda _ix, row=i: self._type_changed(row))
            self.table.setCellWidget(i, 1, combo)
            star = e["star"]
            # band: the star's own bands first, then the usual labels; it
            # is editable so an odd label can be typed
            band = QComboBox()
            band.setEditable(True)
            labels = [b.get("label") for b in (star.get("bands") or [])
                      if b.get("label")]
            for lab in (star.get("band"), *labels, "V", "B", "R", "I", "G"):
                if lab and band.findText(str(lab)) < 0:
                    band.addItem(str(lab))
            band.setCurrentText(str(star.get("band") or
                                    (labels[0] if labels else "V")))
            band.currentTextChanged.connect(
                lambda text, row=i: self._band_edited(row, text))
            self.table.setCellWidget(i, 2, band)
            mag = QDoubleSpinBox()
            mag.setDecimals(3)
            mag.setRange(-5.0, 30.0)
            mag.setSingleStep(0.01)
            mag.setValue(float(star.get("mag") or 0.0))
            mag.valueChanged.connect(
                lambda value, row=i: self._mag_edited(row, value))
            self.table.setCellWidget(i, 3, mag)
            btn = QPushButton("×")
            btn.setFixedWidth(28)
            btn.setProperty("compact", True)   # the global padding would
                                               # clip the glyph away
            btn.clicked.connect(lambda _c=False, row=i: self._remove(row))
            self.table.setCellWidget(i, 4, btn)
        self.table.blockSignals(False)
        self._table_building = False
        self.table.resizeColumnsToContents()
        # the button wears the live count, so the observer sees growth
        self.btn_seq_open.setText(
            self.tr("Sequence ({0})…").format(len(self._entries)))

    def _upsert_band(self, star, label, value):
        # The star's magnitude in one band, edited by hand: it replaces the
        # catalog value for that band (derived=False, solid) so band_of()
        # and the calibration pick it up.
        # @args: star - the sequence star dict, label - band, value - mag
        for item in star.setdefault("bands", []):
            if item.get("label") == label:
                item["value"] = float(value)
                item["derived"] = False
                item["origin"] = "manual"
                return
        star["bands"].append({"label": label, "value": float(value),
                              "err": None, "derived": False,
                              "origin": "manual"})

    def _band_edited(self, row, label):
        if getattr(self, "_table_building", False) or not label:
            return
        star = self._entries[row]["star"]
        star["band"] = label
        value, _derived = photometry.band_of(star, label)
        if value is not None:
            star["mag"] = float(value)
            spin = self.table.cellWidget(row, 3)
            if spin is not None:
                spin.blockSignals(True)
                spin.setValue(float(value))
                spin.blockSignals(False)
        self._commit()

    def _mag_edited(self, row, value):
        if getattr(self, "_table_building", False):
            return
        star = self._entries[row]["star"]
        band = star.get("band") or "V"
        self._upsert_band(star, band, value)
        star["mag"] = float(value)
        self._commit()

    def _flush_table(self):
        # Names edited in the table land in the entries (and the overlay).
        for i, e in enumerate(self._entries):
            item = self.table.item(i, 0)
            if item is not None and item.text().strip():
                e["name"] = item.text().strip()
        self._redraw_entries()

    def _type_changed(self, row):
        combo = self.table.cellWidget(row, 1)
        if combo is None:
            return
        self._entries[row]["kind"] = combo.currentData()
        self._redraw_entries()
        self._commit()

    def _remove(self, row):
        del self._entries[row]
        self._redraw_entries()
        self._reload_table()
        self._commit()

    def _on_clear(self):
        self._entries = []
        self._redraw_entries()
        self._reload_table()
        self._commit(force=True)

    def entries(self):
        # The sequence, for the Measure tab (phase G2; the only public
        # accessor other tabs may use).
        # @return: a copy of the current [{"name","kind","star"}] entries
        return list(self._entries)

    # ------------------------------------------------- host integration

    def prefill(self, target=None, mag=None, ra=None, dec=None):
        # The host app (a project) lands the chart with the target known:
        # name and magnitude set, and the sky position remembered so the
        # survey-field button can download DSS2/PS1 when the observer has
        # no plate of the field.
        # @args: target - object name, mag - its approx magnitude,
        #        ra/dec - J2000 degrees or None
        if target is not None:
            self.edt_target.setText(target)
        if mag is not None:
            self.spn_mag.setValue(float(mag))
        if ra is not None and dec is not None:
            self._prefill_sky = (float(ra), float(dec))

    def _notify_saved(self, paths, payload=None):
        # Files written while a host watches (a project) get registered
        # there; with no host this is a no-op.
        dlg = self.window()
        notify = getattr(dlg, "notify_saved", None)
        if callable(notify):
            notify(paths, "sequence", payload or {})

    def _sequence_payload(self):
        # The sequence in the shape the host stores (project context): the
        # field dict when there is one, else a minimal one so a hand-picked
        # sequence is not lost.
        # @return: {"catalog", "catalog_name", "fov_arcmin", "target_mag",
        #          "entries"}
        st = self.capture_state()
        if st is None:
            st = {"catalog": "manual", "catalog_name": "Manual",
                  "fov_arcmin": 0.0,
                  "target_mag": float(self.spn_mag.value())}
        if not st.get("entries"):
            st = dict(st)
            st["entries"] = [
                {"name": e["name"], "kind": e["kind"],
                 "star": {k: e["star"].get(k) for k in
                          ("id", "ra", "dec", "band", "mag", "bv",
                           "color_origin", "catalog", "bands")}}
                for e in self._entries]
        return st

    def _commit(self, force=False):
        # The sequence changed by the observer (not by a restore): tell
        # the host, so the project keeps it and reopening does not mean
        # rebuilding the comparison stars every time.
        # @args: force - persist even when empty (an explicit clear)
        dlg = self.window()
        notify = getattr(dlg, "notify_sequence", None)
        if callable(notify):
            notify(self._sequence_payload(), force)

    # ------------------------------------------------------------- export

    def _export_csv(self):
        # The sequence table as CSV next to the plate (compstars' format).
        if not self._entries:
            return
        src = Path(self._state.path)
        default = src.with_name(f"{src.stem}_secuencia.csv")
        out, _sel = QFileDialog.getSaveFileName(
            self, self.tr("Export sequence CSV"), str(default),
            "CSV (*.csv)")
        if not out:
            return
        self._flush_table()
        compstars.export_sequence_csv(
            self._entries, out, target_name=self.edt_target.text().strip(),
            catalog_label=self._field.get("catalog_name", "")
            if self._field else "")
        logger.info("sequence CSV exported to %s", out)
        self._notify_saved([out], {"which": "csv",
                                   "entries": self.entries(),
                                   "catalog": (self._field or {}).get(
                                       "catalog"),
                                   "catalog_name": (self._field or {}).get(
                                       "catalog_name", ""),
                                   "fov_arcmin": (self._field or {}).get(
                                       "fov_arcmin"),
                                   "target_mag": self.spn_mag.value()})
        self._say(self.tr("Written to {0}").format(out))
