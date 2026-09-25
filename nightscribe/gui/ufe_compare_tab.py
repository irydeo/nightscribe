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
observer only tweaks by clicking stars (the manual controls live folded
under «Manual tweak»). The loaded plate IS the field background, so the
section needs it to carry a WCS (the common «Solve astrometry…» button
fixes that in place). Known VSX variables can never be comparisons; the
table edits names and kinds; the CSV export comes out next to the plate
(the chart PNG goes through the shared "Export PNG…" button in the
dialog's top bar). The object itself wears the dialog's global red mark
(the top bar's toggle), not a marker of this section.
"""

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (QComboBox, QFileDialog, QProgressDialog,
                               QPushButton, QTableWidgetItem, QWidget,
                               QGraphicsEllipseItem, QGraphicsLineItem,
                               QGraphicsRectItem, QGraphicsSimpleTextItem)

from ..core import compstars
from ..core.sources import vizier
from ..viz import palette
from .ufe_sequence_dialog import UfeSequenceDialog
from .ui_loader import adopt_ui

logger = logging.getLogger("nightscribe.gui.ufe_compare_tab")

# the FinderChart's colours, so both pickers read the same (ADR-042)
C_COMP = "#4dd0e1"      # comparison ring
C_CHECK = "#ff7ad9"     # check square
C_VAR = "#ff6378"       # known variable ring
C_RING = "#58d68d"      # catalog label ring

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
    wait.show()
    return wait


def _reap_wait(wait):
    # @args: wait - the busy dialog to close once the worker finished
    wait.close()
    wait.deleteLater()


class UfeCompareTab(QWidget):
    pick_clicks = True   # clicks mark things: the dialog hands us
                           # the pick cursor + snapping reticle on stage
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
        self._cutout_worker = None   # UfeCutoutWorker while DSS2 lands
        self._prefill_sky = None     # (ra, dec) from the host, for DSS2
        self._build_ui()
        state.image_loaded.connect(self._on_image_loaded)
        if view is not None:
            view.scene_clicked.connect(self._on_scene_clicked)
        self._on_image_loaded()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # The structure is the Designer file's (ADR-005); this method
        # aliases the widgets, fills the catalog combo (its items carry
        # userData, which a .ui cannot hold), folds the manual picking
        # controls into their collapsible section and connects the
        # signals.
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

        # the manual tweak: its controls are translatable, so they live
        # in their own Designer file; here they fold into the collapsed
        # section that takes the .ui's placeholder. Everything hand-driven
        # lives inside: picking hints and kind, catalog labels, and the
        # step-by-step actions (field alone, proposal alone, the table)
        from .ui_loader import load_ui, drop_in
        from .widgets.collapsible_section import CollapsibleSection
        manual = load_ui("ufe_compare_manual", self)
        self.sec_manual = CollapsibleSection(self.tr("Manual tweak"))
        self.sec_manual.setContentWidget(manual)
        self.sec_manual.setCollapsed(True)
        drop_in(self.layout(), self._ui.ph_manual, self.sec_manual)
        self.rdo_comp = manual.rdo_comp
        self.rdo_check = manual.rdo_check
        self.rdo_check.toggled.connect(
            lambda on: setattr(self, "_pick_kind",
                               "check" if on else "comp"))
        self.chk_labels = manual.chk_labels
        self.chk_labels.toggled.connect(self._on_catalog_visible)
        self.btn_field = manual.btn_field
        self.btn_field.clicked.connect(self._on_generate)
        self.btn_propose = manual.btn_propose
        self.btn_propose.clicked.connect(self._on_propose)
        self.btn_seq_open = manual.btn_seq_open
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

    def _open_sequence(self):
        # @return: the sequence window rises, non-modal, so picking stars
        # keeps going while it is open
        self._seqdlg.show()
        self._seqdlg.raise_()
        self._seqdlg.activateWindow()

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
        self._field = None
        self._entries = []
        self._stars = []
        self._drop_items()
        if self._state.has_image:
            self.edt_target.setText(Path(self._state.path).stem)
            self.lbl_status.setText(
                "" if self._state.wcs is not None else self.tr(
                    "The plate has no WCS: solve it with «Solve "
                    "astrometry…» to build the comparison field."))
        else:
            self.lbl_status.setText(self.tr(
                "No plate loaded: load a FITS or fetch the field from "
                "the survey."))
        self._reload_table()

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
                self.lbl_status.setText(
                    "⚠ " + err.messages.get(self._lang, ""))
                return
            ra, dec = target["ra"], target["dec"]
            self.edt_target.setText(target["name"])
            self._prefill_sky = (ra, dec)
        from .workers import UfeCutoutWorker
        self.btn_dss.setEnabled(False)
        self.lbl_status.setText(self.tr("Downloading the survey field…"))
        wait = _busy_wait(self, self.tr("Downloading the survey field…"),
                          self.tr("Comparison field"))
        self._cutout_worker = UfeCutoutWorker(ra, dec)
        self._cutout_worker.progress.connect(
            lambda msg: wait.setLabelText(msg.get(self._lang, "")))
        self._cutout_worker.progress.connect(
            lambda msg: self.lbl_status.setText(msg.get(self._lang, "")))

        def survey_landed(result):
            # same rule as the field chain: the modal dialog is always
            # reaped, whatever the landing does
            try:
                self._on_survey_landed(result)
            except Exception as err:
                logger.exception("survey landing failed: %s", err)
                self.lbl_status.setText(str(err))
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
            self.lbl_status.setText(self.tr(
                "The survey download failed (offline?). Try again later."))
            return
        try:
            self._state.load(path)
        except Exception as err:
            logger.warning("survey cutout unreadable: %s", err)
            self.lbl_status.setText(str(err))
            return
        self.lbl_status.setText(self.tr("Field loaded: {0}").format(label))

    def _on_auto(self):
        # The one-click path (ADR-044 rev 2026-09-25): with a field
        # already loaded it only re-proposes; without one it generates
        # the field and the proposal runs the moment the field lands.
        # Both paths sit under the busy dialog: the proposal is local
        # math, but on a big field it still takes its moment, and a
        # bare freeze reads as a hang.
        if self._field is not None:
            wait = _busy_wait(self, self.tr("Proposing the sequence…"),
                              self.tr("Comparison field"))
            wait.setRange(0, 1)
            wait.setValue(0)
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()   # let the dialog paint before
                                           # the synchronous proposal
            try:
                self._on_propose()
            finally:
                wait.setValue(1)
                _reap_wait(wait)
            return
        self._auto_propose = True
        self._on_generate()

    def _on_generate(self):
        # Generate field: VizieR catalog + VSX variables around the plate
        # centre, off the GUI thread.
        if not self._state.has_image:
            self._auto_propose = False
            return
        if self._state.wcs is None:
            self._auto_propose = False
            self.lbl_status.setText(self.tr(
                "The plate has no WCS: solve it with «Solve astrometry…» "
                "to build the comparison field."))
            return
        from .workers import UfeFieldWorker
        ra, dec = self._state.wcs.center()
        w, h = self._state.plate_shape
        fov_arcmin = max(w, h) * self._state.wcs.pixel_scale() / 60.0
        self.btn_field.setEnabled(False)
        self.lbl_status.setText(self.tr("Querying the catalog…"))
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
        self._worker = UfeFieldWorker(self.cmb_catalog.currentData(),
                                      ra, dec, fov_arcmin)

        def _stage(msg):
            # @args: msg - the worker's {"es", "en"} stage text
            wait.setLabelText(msg.get(self._lang, ""))
            self.lbl_status.setText(msg.get(self._lang, ""))
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
                self.lbl_status.setText(self.tr(
                    "The field landed but its handling failed: {0}")
                    .format(err))
            finally:
                wait.setValue(3)
                _reap_wait(wait)
        self._worker.finished.connect(field_landed)
        self._worker.start()

    def _on_field_ready(self, field):
        # @args: field - compstars.load_field result, or {} on failure
        self.btn_field.setEnabled(True)
        self._worker = None
        if not field:
            self._auto_propose = False
            self.lbl_status.setText(self.tr(
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
        wcs_note = ""
        if field.get("vsx_warning"):
            wcs_note = " · " + self.tr("VSX check failed")
        self.lbl_status.setText(
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
            self.lbl_status.setText(self.tr("Proposing the sequence…"))
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
                self.lbl_status.setText(self.tr(
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

    def _on_propose(self):
        # The automatic sequence: isolated, non-variable stars matched to
        # the target's brightness (compstars' criteria).
        if self._field is None:
            # no silent no-op: say what to do first, in both languages
            self.lbl_status.setText(self.tr(
                "Generate the field first: I need the plate's catalog "
                "stars to propose the sequence."))
            return
        self._flush_table()
        seq = compstars.propose_comps(self._stars, self.spn_mag.value())
        self._entries = (seq["comps"]
                         + ([seq["check"]] if seq["check"] else []))
        self._redraw_entries()
        self._reload_table()
        self.lbl_status.setText(
            self.tr("Proposed {0} comparisons (tweak by clicking stars).")
            .format(len(self._entries)))

    # ------------------------------------------------------------- table

    def _reload_table(self):
        # Rebuilds the table from the entries (after chart picks).
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
            mag = QTableWidgetItem(f"{star['band']} {star['mag']:.2f}")
            mag.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(i, 2, mag)
            btn = QPushButton("×")
            btn.setFixedWidth(28)
            btn.setProperty("compact", True)   # the global padding would
                                               # clip the glyph away
            btn.clicked.connect(lambda _c=False, row=i: self._remove(row))
            self.table.setCellWidget(i, 3, btn)
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        # the button wears the live count, so the observer sees growth
        self.btn_seq_open.setText(
            self.tr("Sequence ({0})…").format(len(self._entries)))

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

    def _remove(self, row):
        del self._entries[row]
        self._redraw_entries()
        self._reload_table()

    def _on_clear(self):
        self._entries = []
        self._redraw_entries()
        self._reload_table()

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
        self.lbl_status.setText(self.tr("Written to {0}").format(out))
