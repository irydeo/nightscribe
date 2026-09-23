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

"""The UFE's Compare tab (ADR-044, phase F): the photometric comparison
sequence picker on top of core/compstars (VizieR Gaia/APASS + VSX
cross-match), with the FinderChart's visual language reimplemented as
overlays on the shared plate view (the legacy SeqChartDialog keeps
living untouched).

The loaded plate IS the field background, so the tab needs it to carry a
WCS (the common «Solve astrometry…» button fixes that in place). The
field (catalog stars + known variables) loads around the plate centre
with the plate's field of view, off the GUI thread. Clicks on the plate
toggle stars in and out of the sequence (known VSX variables can never
be comparisons); the table edits names and kinds; the CSV export comes
out next to the plate (the chart PNG goes through the shared
"Export PNG…" button in the dialog's top bar).
"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QProgressDialog,
                               QPushButton, QRadioButton,
                               QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget,
                               QGraphicsEllipseItem, QGraphicsLineItem,
                               QGraphicsRectItem, QGraphicsSimpleTextItem)

from ..core import compstars
from ..core.sources import vizier
from ..viz import palette

logger = logging.getLogger("nightscribe.gui.ufe_compare_tab")

# the FinderChart's colours, so both pickers read the same (ADR-042)
C_COMP = "#4dd0e1"      # comparison ring
C_CHECK = "#ff7ad9"     # check square
C_VAR = "#ff6378"       # known variable ring
C_RING = "#58d68d"      # catalog label ring

_PICK_PX = 11.0         # click/hover radius in SCREEN px at any zoom
_MAX_LABELS = 34        # catalog magnitude labels, brightest first


def _busy_wait(host, label, title):
    # A modal busy dialog without Cancel for the seconds of network work:
    # the legacy comparison-chart flow leaned on it (a status line alone
    # reads as "nothing is happening"), and the UFE rewrite dropped it:
    # restoring it here.
    # @args: host - parent widget, label - first busy message,
    #        title - the window title
    # @return: the ready dialog (zero minimumDuration: it appears at once)
    wait = QProgressDialog(label, "", 0, 0, host)
    wait.setWindowTitle(title)
    wait.setWindowModality(Qt.WindowModal)
    wait.setCancelButton(None)
    wait.setMinimumDuration(0)
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
        self._active = False
        self._field = None           # compstars.load_field result
        self._entries = []           # the sequence: name/kind/star dicts
        self._stars = []             # catalog stars with _sx/_sy cached
        self._items = []             # every overlay this tab owns
        self._pick_kind = "comp"
        self._catalog_visible = True
        self._catalog_items = []     # subset hidden with the checkbox
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
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Target:")))
        self.edt_target = QLineEdit()
        row.addWidget(self.edt_target, 1)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Target mag:")))
        self.spn_mag = QDoubleSpinBox()
        self.spn_mag.setRange(0.0, 25.0)
        self.spn_mag.setDecimals(2)
        self.spn_mag.setValue(12.0)
        self.spn_mag.setToolTip(self.tr(
            "Approximate magnitude of the target: the proposal picks "
            "comparisons brighter than or similar to it"))
        row.addWidget(self.spn_mag)
        self.cmb_catalog = QComboBox()
        for key, spec in vizier.CATALOGS.items():
            self.cmb_catalog.addItem(spec["name"], key)
        row.addWidget(self.cmb_catalog)
        lay.addLayout(row)
        self.btn_field = QPushButton(self.tr("Generate field"))
        self.btn_field.setToolTip(self.tr(
            "Query the catalog (and VSX variables) around the plate "
            "centre"))
        self.btn_field.clicked.connect(self._on_generate)
        lay.addWidget(self.btn_field)
        self.btn_dss = QPushButton(self.tr("Load a survey field (DSS2)…"))
        self.btn_dss.setToolTip(self.tr(
            "No plate of your own? Download the field from the survey "
            "(PS1-g, DSS2-red fallback) as a FITS with WCS and work on "
            "it directly"))
        self.btn_dss.clicked.connect(self._on_load_survey)
        lay.addWidget(self.btn_dss)
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)
        hint = QLabel(self.tr(
            "Click a star to add or remove it. Known variables (red "
            "rings) can never be comparisons."))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("On click, add as:")))
        self.rdo_comp = QRadioButton(self.tr("Comparison"))
        self.rdo_comp.setChecked(True)
        self.rdo_check = QRadioButton(self.tr("Check"))
        self.rdo_check.toggled.connect(
            lambda on: setattr(self, "_pick_kind",
                               "check" if on else "comp"))
        row.addWidget(self.rdo_comp)
        row.addWidget(self.rdo_check)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.chk_labels = QCheckBox(self.tr("Show catalog magnitudes"))
        self.chk_labels.setChecked(True)
        self.chk_labels.toggled.connect(self._on_catalog_visible)
        row.addWidget(self.chk_labels)
        self.btn_propose = QPushButton(self.tr("Propose sequence"))
        self.btn_propose.setToolTip(self.tr(
            "Automatic proposal: isolated, non-variable stars matched to "
            "the target's brightness"))
        self.btn_propose.clicked.connect(self._on_propose)
        row.addWidget(self.btn_propose)
        lay.addLayout(row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [self.tr("Name"), self.tr("Type"), self.tr("Mag"), ""])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.btn_clear = QPushButton(self.tr("Remove all"))
        self.btn_clear.clicked.connect(self._on_clear)
        row.addWidget(self.btn_clear)
        self.btn_csv = QPushButton(self.tr("Export CSV…"))
        self.btn_csv.clicked.connect(self._export_csv)
        row.addWidget(self.btn_csv)
        lay.addLayout(row)

    # ------------------------------------------------------- activation

    def set_active(self, flag, keep_overlays=False):
        # Only the visible tab owns the view's clicks, overlays and the
        # hover probe (the state's pixel/DN/RA probe returns on leave).
        # @args: flag - on stage or not, keep_overlays - leaving for the
        #        Measure tab: the sequence stays visible and its probe
        #        keeps talking (the Measure tab measures WITH it)
        self._active = bool(flag)
        if self._view is None:
            return
        if self._active:
            self._view.set_hover_probe(self._probe)
            self._redraw_overlays()
        else:
            if not keep_overlays:
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
            _reap_wait(wait)
            self._on_survey_landed(result)
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

    def _on_generate(self):
        # Generate field: VizieR catalog + VSX variables around the plate
        # centre, off the GUI thread.
        if not self._state.has_image:
            return
        if self._state.wcs is None:
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
        # legacy flow had (a status line alone reads as "nothing happens")
        wait = _busy_wait(self, self.tr("Querying the catalog…"),
                          self.tr("Comparison field"))
        self._worker = UfeFieldWorker(self.cmb_catalog.currentData(),
                                      ra, dec, fov_arcmin)
        # Pipeline stages (catalog query, VSX crossmatch) reach the
        # dialog label as well as the status line
        self._worker.progress.connect(
            lambda msg: wait.setLabelText(msg.get(self._lang, "")))
        self._worker.progress.connect(
            lambda msg: self.lbl_status.setText(msg.get(self._lang, "")))

        def field_landed(field):
            _reap_wait(wait)
            self._on_field_ready(field)
        self._worker.finished.connect(field_landed)
        self._worker.start()

    def _on_field_ready(self, field):
        # @args: field - compstars.load_field result, or {} on failure
        self.btn_field.setEnabled(True)
        self._worker = None
        if not field:
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
        if self._active:
            self._redraw_overlays()

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
        if not self._active or self._view is None or self._field is None:
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
        # the target (plate centre): amber ring + ticks + name
        cx, cy = w / 2.0, h / 2.0
        r = w * 0.022
        target = QGraphicsEllipseItem(cx - r, cy - r, 2 * r, 2 * r)
        target.setPen(self._pen(palette.ACCENT, 2.2))
        self._items.append(self._view.add_overlay(target))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ln = QGraphicsLineItem(cx + dx * r * 1.15, cy + dy * r * 1.15,
                                   cx + dx * r * 1.7, cy + dy * r * 1.7)
            ln.setPen(self._pen(palette.ACCENT, 2.2))
            self._items.append(self._view.add_overlay(ln))
        name = self.edt_target.text().strip()
        if name:
            self._items.append(self._view.add_overlay(
                self._text(name, cx, cy + r * 2.4, palette.ACCENT,
                           w * 0.018, bold=True, anchor="center")))
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
        if not self._active or self._field is None:
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
            btn.clicked.connect(lambda _c=False, row=i: self._remove(row))
            self.table.setCellWidget(i, 3, btn)
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()

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
