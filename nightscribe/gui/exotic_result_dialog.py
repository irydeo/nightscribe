############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - EXOTIC result window (ADR-052 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The reduction's result in one window: its numbers, its light curve and
every file it wrote.

The reduction runs from the editor's left panel, so the result comes back
there; this window is what the observer opens (and what opens itself when
the run lands) instead of going to dig in the project's work folder. It
follows the period-and-phase window's pattern: non-modal, the figure in a
label, the text read-only, and every file one double click away.

Nothing is invented: a parameter the reduction did not write is not shown,
a file that is not there is not listed, and when the parameters cannot be
read the window says so instead of showing zeros.

ADR-005: the structure lives in ui/exotic_result_dialog.ui; this class
fills it and wires the buttons.
"""

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QDialog, QListWidgetItem

from ..core import exotic_import
from .ui_loader import adopt_ui, drop_in
from .widgets.ufe_project_badge import UfeProjectBadge

logger = logging.getLogger(__name__)

# The groups the file list shows, in order.
_GROUPS = ("curve", "field", "data")


class ExoticResultDialog(QDialog):
    # @args: out_dir - EXOTIC's "Directory to Save Plots" (our work folder),
    #        params - exotic_import.load_params output (may be empty),
    #        badge - the project's badge payload
    #        (MainWindow._ufe_project_badge_payload) or None: the window's
    #        title is the project's own identity, in the list's colours,
    #        title - the object's name (the window bar), when - a datetime or
    #        a short string for the run, save_fn - callable() that registers
    #        the products as resources of the visit (None: the button is
    #        hidden), parent - the window that opened it
    def __init__(self, out_dir, params=None, badge=None, title="", when=None,
                 save_fn=None, parent=None):
        super().__init__(parent)
        self._out_dir = Path(out_dir)
        self._params = params or {}
        self._save_fn = save_fn
        self._chart_pixmap = None       # the figure, before fitting
        self._ui = adopt_ui(self, "exotic_result_dialog")
        self.setWindowTitle(
            self.tr("EXOTIC reduction of {0}").format(title) if title
            else self.tr("EXOTIC reduction"))
        # the project's identity, exactly as the workbench shows it (same
        # widget, same payload builder, same colours): the window's title is
        # WHO this is about. No next action here: this window is showing a
        # finished reduction, so "what is next" belongs to the workbench
        self.badge = UfeProjectBadge(self)
        drop_in(self._ui.row_badge, self._ui.ph_badge, self.badge)
        self.badge.set_badge(badge, show_next=False)
        self._ui.lbl_subtitle.setText(self._subtitle(when))
        self._ui.txt_params.setPlainText(self._params_text())
        self._ui.lst_files.itemDoubleClicked.connect(self._on_open_file)
        self._ui.btn_folder.clicked.connect(self._on_folder)
        self._ui.btn_save.setVisible(self._save_fn is not None)
        self._ui.btn_save.clicked.connect(self._on_save)
        self._ui.btn_close.clicked.connect(self.accept)
        self._fill_files()
        self._show_figure()
        self.setMinimumSize(720, 700)
        self.resize(1020, 940)

    # ------------------------------------------------------------- filling

    def resizeEvent(self, event):
        # The chart follows the window: fitted once at load and again here,
        # so it always fits its label (see _fit_chart).
        # @args: event - the resize event
        # @return: None
        super().resizeEvent(event)
        self._fit_chart()

    def _role(self, role):
        # What a file of a given role IS, and which group it belongs to.
        # Each label is a literal self.tr() so lupdate sees it: a label built
        # from a variable would never be translated.
        # @args: role - the role exotic_import.find_products gave the file
        # @return: (group, label)
        table = {
            "figure": ("curve", self.tr(
                "Light curve (the publishable figure)")),
            "curve": ("curve", self.tr("Light curve (data)")),
            "normalized": ("curve", self.tr("Normalized flux")),
            "field": ("field", self.tr(
                "Field with apertures and comparison stars")),
            "stats": ("field", self.tr(
                "Observing statistics per comparison star")),
            "centroid": ("field", self.tr("Centroid positions and distances")),
            "compflux": ("field", self.tr("Raw comparison-star flux")),
            "params": ("data", self.tr("Fitted parameters (JSON)")),
            "plate": ("data", self.tr("Plate status")),
            "aavso": ("data", self.tr("AAVSO report (ready to send)")),
            "inits": ("data", self.tr("The handoff file")),
            "log": ("data", self.tr("The run log")),
        }
        return table.get(role, ("data", self.tr("File")))

    def _group_title(self, group):
        # @args: group - "curve" | "field" | "data"
        # @return: the heading the list shows for it
        return {"curve": self.tr("Light curve"),
                "field": self.tr("Field and diagnostics"),
                "data": self.tr("Data and report")}.get(group, group)

    def _subtitle(self, when):
        # @return: what this window is, when it ran and where the files are
        stamp = when.isoformat(sep=" ", timespec="minutes") if when else None
        if stamp:
            return self.tr(
                "EXOTIC reduction · run of {0} · files in {1}").format(
                    stamp, str(self._out_dir))
        return self.tr("EXOTIC reduction · files in {0}").format(
            str(self._out_dir))

    def _params_text(self):
        # @return: the fitted numbers, one per line; nothing when there are
        #          none (a run that failed leaves no parameters, and showing
        #          zeros would be a lie)
        p = self._params
        if not p or p.get("tmid") is None:
            return self.tr(
                "The reduction did not leave a fitted result: check its log "
                "(the file list below has it).")
        lines = [self.tr("Mid-transit time: {0} BJD_TDB").format(
            self._pair(p.get("tmid"), p.get("tmid_err"), 5))]
        if p.get("rprs") is not None:
            lines.append(self.tr("Rp/Rs: {0}").format(
                self._pair(p.get("rprs"), p.get("rprs_err"), 4)))
        if p.get("depth") is not None:
            lines.append(self.tr("Transit depth: {0} %").format(
                self._pair(p.get("depth") * 100.0,
                           (p.get("depth_err") or 0) * 100.0, 2)))
        if p.get("inc") is not None:
            lines.append(self.tr("Orbital inclination: {0} deg").format(
                self._pair(p.get("inc"), p.get("inc_err"), 2)))
        if p.get("duration_d") is not None:
            lines.append(self.tr("Transit duration: {0} d").format(
                self._pair(p.get("duration_d"), p.get("duration_err"), 4)))
        if p.get("scatter_pct") is not None:
            lines.append(self.tr("Scatter of the residuals: {0} %").format(
                self._num(p.get("scatter_pct"), 2)))
        chosen = []
        # EXOTIC writes the string "None" when it kept no comparison star
        # (it happened on the reference run): that is not a name, so it is
        # not shown as one
        comp = (p.get("best_comp") or "").strip()
        if comp and comp.lower() != "none":
            chosen.append(self.tr("comparison star {0}").format(comp))
        if p.get("aperture") is not None:
            chosen.append(self.tr("aperture {0}").format(
                self._num(p.get("aperture"), 2)))
        if p.get("annulus") is not None:
            chosen.append(self.tr("annulus {0}").format(
                self._num(p.get("annulus"), 2)))
        if chosen:
            lines.append(self.tr("The search settled on: {0}").format(
                ", ".join(chosen)))
        return "\n".join(lines)

    @staticmethod
    def _num(value, digits):
        # @return: the number, or "?" when it is not usable
        try:
            return f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return "?"

    def _pair(self, value, err, digits):
        # @return: "value +/- err" (or just the value when there is no error)
        text = self._num(value, digits)
        if err is None:
            return text
        return self.tr("{0} ± {1}").format(text, self._num(err, digits))

    def _fill_files(self):
        # The files, grouped by what they are: one double click away, with
        # the full path in the tooltip (the window never copies anything).
        products = exotic_import.find_products(self._out_dir)
        if not products:
            self._ui.lbl_files.setText(self.tr(
                "This folder has no files from a reduction yet."))
            return
        grouped = {}
        for role, path in products:
            group, label = self._role(role)
            grouped.setdefault(group, []).append((label, path))
        for group in _GROUPS:
            if group not in grouped:
                continue
            head = QListWidgetItem(self._group_title(group).upper())
            head.setFlags(Qt.NoItemFlags)      # a title, not a row to click
            self._ui.lst_files.addItem(head)
            for label, path in grouped[group]:
                item = QListWidgetItem(
                    self.tr("{0}: {1}").format(label, Path(path).name))
                item.setData(Qt.UserRole, path)
                item.setToolTip(path)
                self._ui.lst_files.addItem(item)

    def _show_figure(self):
        # The publishable light curve, fitted to the label; the other figures
        # are one double click away (they are not all PNGs and some are A4
        # PDFs: a stack of them in here would be unusable).
        figures = [p for role, p in
                   exotic_import.find_products(self._out_dir)
                   if role == "figure" and p.lower().endswith(".png")]
        if not figures:
            self._ui.lbl_chart.setText(self.tr(
                "No figure: the reduction did not get to write its light "
                "curve (check the log below)."))
            return
        pix = QPixmap(figures[0])
        if pix.width() > 1:
            self._chart_pixmap = pix
            self._fit_chart()
        else:
            self._ui.lbl_chart.setText(Path(figures[0]).name)

    def _fit_chart(self):
        # The figure fits the label, never the other way round, and it is
        # never blown up (a small one stays as it is). Scaling to a fixed
        # width instead clipped it: measured, a 609x429 figure in a 960x412
        # label lost its bottom 17 px.
        # @return: None
        if self._chart_pixmap is None:
            return
        box = self._ui.lbl_chart.size()
        target = QSize(
            min(self._chart_pixmap.width(), max(1, box.width())),
            min(self._chart_pixmap.height(), max(1, box.height())))
        self._ui.lbl_chart.setPixmap(self._chart_pixmap.scaled(
            target, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ------------------------------------------------------------- actions

    def _on_open_file(self, item):
        path = item.data(Qt.UserRole)
        if not path:
            return                      # a group title
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._out_dir)))

    def _on_save(self):
        if self._save_fn is None:
            return
        try:
            n = self._save_fn()
        except Exception as err:        # never a dead window
            logger.warning("could not save the EXOTIC products: %s", err)
            self._ui.lbl_files.setText(self.tr(
                "The products could not be saved in the visit: {0}"
            ).format(err))
            return
        self._ui.lbl_files.setText(self.tr(
            "{0} products saved in the visit: they are in its window, "
            "under Resources.").format(n))


def open_exotic_result(parent, out_dir, params=None, badge=None, title="",
                       when=None, save_fn=None):
    # Opens the window non-modally (the observer keeps working while it is
    # open) and returns it.
    # @args: as ExoticResultDialog; parent - the window that opens it
    # @return: the ExoticResultDialog
    dlg = ExoticResultDialog(out_dir, params=params, badge=badge, title=title,
                             when=when, save_fn=save_fn, parent=parent)
    dlg.setAttribute(Qt.WA_DeleteOnClose, True)
    dlg.show()
    return dlg
