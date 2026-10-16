############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Visits panel: the core of the Analysis tab (ADR-045)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The visits manager (ADR-045): every day you work the object is a visit,
and every resource (FITS plates, imported photometry, ephemeris, MPC
reports, charts) hangs from one.

The split that keeps the tab light and the work roomy (2026-09-24 review):
the Analysis tab carries the OVERVIEW (the rich-rows list, the count, the
single primary "New visit" button); the visit's own work (resources,
measurements, notes) lives in the VisitWindow, a non-modal dialog opened
by the primary action and by double-clicking a row.

Rules of the redesign, honoured here:

* One primary entry point: "New visit". No duplicated buttons.
* Nothing attaches without a visit: the attach action lives inside the
  visit's window.
* The file on disk is never touched: removing a resource only unlinks it.

All CRUD goes through core/followup.py (visits, points) and
core/project.py (the file registry). The host wires two callbacks:
open_in_editor(path, session_id) for FITS rows and on_change() to refresh
the tab's reactive blocks (curve, cadence, summary) after data changes.
"""

import datetime
import logging
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QListWidgetItem,
                               QMenu, QMessageBox, QWidget)

from ..ui_loader import adopt_ui, drop_in, load_ui
from .passive_wheel import PassiveDoubleSpinBox, PassiveList

# The visits list: how tall it may grow before it scrolls itself.
_LIST_MAX_H = 168

# What a visit carries, split in two (ADR-045 rev, 2026-10-16): what it
# PRODUCED (Results) and the RAW material (the folded "files of the night").
# The rule is by KIND: a plate, a generic attachment and an ephemeris are
# inputs; a report, a chart, a stack, an animation, an EXOTIC product or a
# measured point is something the night produced.
_RAW_KINDS = ("fits", "file", "ephemeris")

# The glyph each row wears in the two lists: one per family, never a colour
# code (the colour is the object's kind, and mixing the two reads as noise).
_ROW_GLYPHS = {
    "run": "⚑", "point": "◆", "fits": "▦", "stack": "▦", "image": "▧",
    "chart": "▧", "report": "▤", "sequence": "≡", "animation": "▶",
    "ephemeris": "✦",
}


def _epoch_of(value):
    # @args: value - epoch seconds (float or string) or None
    # @return: the epoch as a float, 0.0 when unknown. Used to sort the two
    #          lists together: a run, a file and a point must interleave by
    #          when they happened, and they come from three different clocks.
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class _ContentList(PassiveList):
    """A list that asks for the height of what it holds.

    A QListWidget answers sizeHint() with a fixed 256x192 whatever its
    content, so a project with one visit kept 180 px of empty box. This one
    asks for the rows it has (capped), which is what lets the Analysis tab
    fit without a page scrollbar.
    """

    def sizeHint(self):
        # @return: the width the base wants, the height the content needs
        base = super().sizeHint()
        rows = max(1, min(self.count(), 8))
        row = self.sizeHintForRow(0) if self.count() else 22
        height = rows * max(row, 22) + 2 * self.frameWidth() + 6
        return QSize(base.width(), min(height, _LIST_MAX_H))


logger = logging.getLogger("nightscribe.gui.visits_panel")

# Kinds whose visits keep photometry points (the light-curve kinds);
# everyone gets resources and notes. NEO/PCCP visits carry the night's
# astrometry: the MPC paste/validate/save block (ADR-045 form A: the
# measurements are the visit's product, so the block lives in the
# visit's window and nowhere else).
CURVE_KINDS = ("sn", "hads", "variable")
MPC_KINDS = ("neo", "pccp")

_FILTERS = ["Clear", "V", "R", "B", "I", "NIR"]

# extension -> registry kind for a generic attachment
_KIND_BY_SUFFIX = {
    ".fits": "fits", ".fit": "fits", ".fts": "fits", ".fz": "fits",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".mp4": "image",
    ".csv": "report", ".eff": "report", ".txt": "report",
    ".json": "ephemeris", ".eph": "ephemeris",
}


def _kind_for(path):
    # @args: path - file path
    # @return: the registry kind guessed from the extension
    return _KIND_BY_SUFFIX.get(Path(path).suffix.lower(), "file")


class VisitsPanel(QWidget):
    # The in-tab visits overview: the list, the count and the two entry
    # points (New visit / Open visit…). The per-visit work lives in the
    # VisitWindow (opened, never crammed inline).
    #
    # @args: db - the Database, lang - "es" | "en",
    #        open_in_editor - callable(path, session_id) opening a FITS in
    #        the UFE (None hides the window's editor action),
    #        on_measure_click - callable(point_id) ADR-047: the window's
    #        measurements list, when wired, opens the point's plate in
    #        the editor (None keeps the list plain),
    #        on_change - callable() after any data change (the host
    #        refreshes the curve/cadence/summary),
    #        curve_kind - True keeps the measurement block in the window

    def __init__(self, db, lang="es", open_in_editor=None, on_change=None,
                 curve_kind=True, kind=None, on_measure_click=None,
                 measure_series=None, astrometry=None,
                 on_visit_selected=None, runs_for_session=None, open_run=None,
                 mpc_build=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._lang = lang
        self._open_in_editor = open_in_editor
        self._on_change = on_change
        self._on_measure_click = on_measure_click
        self._measure_series = measure_series
        self._astrometry = astrometry
        self._runs_for_session = runs_for_session
        self._open_run = open_run
        # The visit's MPC block opens the same report window as the editor's
        # Astrometry tab. The host rebuilds the text from the visit's own run
        # (it owns the astrometry data); without the hook the block says so.
        self._mpc_build = mpc_build
        # the host is told which visit is selected: the Analysis curve is
        # the one of the visit you are looking at, not the project's pile
        self._on_visit_selected = on_visit_selected
        # the project's kind drives what a visit carries: light-curve
        # kinds get the measurements block, MPC kinds the astrometry one
        self._kind = kind if kind is not None else (
            "sn" if curve_kind else "neo")
        self._pid = None              # current project id
        self._win = None              # the open VisitWindow (or None)
        self._build_ui()

    # ------------------------------------------------------------ build

    def _build_ui(self):
        # The structure is the Designer file's (ADR-005); the visits
        # list is the wheel-guarded PassiveList, inserted into its
        # placeholder (the wheel guard is behaviour, not structure).
        self._ui = adopt_ui(self, "visits_panel")
        self.btn_new = self._ui.btn_new
        self.btn_new.clicked.connect(self._on_new_visit)
        self.btn_open = self._ui.vp_btn_open_visit
        self.btn_open.clicked.connect(self._on_open_selected)
        self.lbl_count = self._ui.lbl_count
        self.lbl_empty = self._ui.lbl_empty
        self.lst = _ContentList()
        # Interfaz 1.7: the list grows with its content instead of
        # reserving a fixed box (a project with ONE visit kept ~180 px of
        # empty list, which is what pushed the Analysis tab past the fold).
        # The cap keeps twenty visits from taking the whole page: past it,
        # the list scrolls itself.
        self.lst.setMaximumHeight(_LIST_MAX_H)
        self.lst.setToolTip(self.tr(
            "The project's visits, newest first; double-click opens one"))
        self.lst.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.lst.itemSelectionChanged.connect(self._on_select)
        drop_in(self.layout(), self._ui.ph_list, self.lst)
        # Interfaz 1.7: the panel shares its row with the light curve, so it
        # is taller than its own content. Without this the label, the list
        # and the buttons drift apart down the column.
        self.layout().addStretch(1)
        self._show_empty(True)

    # ------------------------------------------------------------ state

    def set_project(self, project_id, keep_selection=True):
        # @args: project_id - the project to manage, keep_selection - try
        #        to keep the selected visit across a refresh
        prev = self.current_session_id() if keep_selection else None
        if self._pid != project_id:
            self.close_visit_window()      # the window belongs to a visit
        self._pid = project_id
        self.refresh()
        if prev is not None:
            for row in range(self.lst.count()):
                if self.lst.item(row).data(Qt.UserRole) == prev:
                    self.lst.setCurrentRow(row)
                    return

    def current_session_id(self):
        # @return: the selected visit id, or None (the host attaches
        #          reports to it when set)
        items = self.lst.selectedItems()
        return items[0].data(Qt.UserRole) if items else None

    def refresh(self):
        # Refills the visits list from the database (newest first).
        from ...core import followup as fu
        sel = self.current_session_id()
        self.lst.clear()
        sessions = fu.list_sessions(self._db, self._pid) \
            if self._pid is not None else []
        # the project's curve ONCE, not once per visit: the chip count is
        # the same query, and asking it inside the loop costed one full
        # curve per visit on every refresh (a 20-visit project, 20 queries
        # for a list that shows five words)
        pts = fu.list_points(self._db, self._pid) if self._pid else []
        for s in sessions:
            n_img = len(fu.list_images(self._db, s["id"]))
            n_pts = sum(1 for p in pts if p.get("session_id") == s["id"])
            chips = []
            if n_img:
                chips.append(self.tr("{0} img").format(n_img))
            if n_pts:
                chips.append(self.tr("{0} mag").format(n_pts))
            tag = ("  ·  " + " · ".join(chips)) if chips else ""
            notes = f"  ·  {s['notes'][:24]}…" if s["notes"] else ""
            pin = "📌 " if s.get("pinned") else ""
            # ADR-045 rev: the name leads when there is one; the date stays
            # the sort key and the folder, so it never disappears
            name = (s.get("label") or "").strip()
            head = f"{name}  ·  {s['obs_date']}" if name else s["obs_date"]
            item = QListWidgetItem(f"{pin}{head}{tag}{notes}")
            item.setData(Qt.UserRole, s["id"])
            self.lst.addItem(item)
        n = len(sessions)
        if not n:
            self.lbl_count.setText("")
        elif n == 1:
            self.lbl_count.setText(self.tr("1 visit"))
        else:
            self.lbl_count.setText(self.tr("{0} visits").format(n))
        self._show_empty(n == 0)
        if n and sel is not None:
            for row in range(self.lst.count()):
                if self.lst.item(row).data(Qt.UserRole) == sel:
                    self.lst.setCurrentRow(row)
                    break
        elif n:
            # A fresh open selects the newest visit (the list is newest
            # first): "the visit you are looking at" has to be a real one,
            # and the Analysis curve, the Open button and the report all
            # hang from it. Measured: without it the panel opened with
            # nothing selected and the curve had no night to show.
            self.lst.setCurrentRow(0)
        self.btn_open.setEnabled(self.current_session_id() is not None)
        self._tell_selection()

    def _show_empty(self, flag):
        # @args: flag - no visits exist
        self.lbl_empty.setVisible(flag)
        self.lst.setVisible(not flag)
        self.btn_open.setVisible(not flag)

    def _on_select(self):
        self.btn_open.setEnabled(self.current_session_id() is not None)
        self._tell_selection()

    def _tell_selection(self):
        # The host follows the selection (the Analysis curve is the visit's).
        # A callback that throws must never break the list.
        # @return: None
        if self._on_visit_selected is None:
            return
        try:
            self._on_visit_selected(self.current_session_id())
        except Exception as err:                # never kills the panel
            import logging
            logging.getLogger(__name__).warning(
                "visit-selection callback failed: %s", err)

    # ------------------------------------------------- the visit window

    def _on_new_visit(self):
        # The single entry point: create today's visit and open its window
        # right away (the whole point of the visit is what hangs from it).
        from ...core import followup as fu
        if self._pid is None:
            return
        sid = fu.create_session(self._db, self._pid)
        self.refresh()
        self.lst.setCurrentRow(0)   # newest first
        self.open_visit(sid)

    def _on_open_selected(self):
        sid = self.current_session_id()
        if sid is not None:
            self.open_visit(sid)

    def _on_row_double_clicked(self, item):
        self.open_visit(item.data(Qt.UserRole))

    def open_visit(self, session_id):
        # The visit's work window: one at a time, non-modal, so the page
        # never blocks and the headless suite can drive it.
        # @args: session_id - the visit to open
        # @return: the VisitWindow
        self.close_visit_window()
        self._win = VisitWindow(self._db, self._pid, session_id,
                                lang=self._lang,
                                kind=self._kind,
                                open_in_editor=self._open_in_editor,
                                on_measure_click=self._on_measure_click,
                                measure_series=self._measure_series,
                                astrometry=self._astrometry,
                                runs_for_session=self._runs_for_session,
                                open_run=self._open_run,
                                mpc_build=self._mpc_build,
                                data_changed=self._from_window_changed,
                                parent=self)
        # WA_DeleteOnClose: the C++ object dies when the user closes the
        # window, so the wrapper must be dropped on the spot — keeping it
        # makes the next open_visit call close() on a deleted object
        # (the shiboken RuntimeError trap)
        self._win.destroyed.connect(self._on_window_gone)
        self._win.show()
        return self._win

    def _on_window_gone(self):
        # The visit window died (the user closed it): forget it at once.
        self._win = None

    def close_visit_window(self):
        # Closes the open visit window, if any (project switch, delete).
        # The RuntimeError guard covers the in-between state where the
        # deletion is queued but not yet delivered.
        if self._win is not None:
            try:
                self._win.close()
            except RuntimeError:
                pass            # already deleted (WA_DeleteOnClose)
            self._win = None

    def _from_window_changed(self):
        # The window edited its visit: the list's counts and the host's
        # reactive blocks follow.
        self.refresh()
        self._emit_change()

    def _emit_change(self):
        # Tells the host the data changed (curve, cadence, summary).
        if self._on_change is not None:
            self._on_change()


class VisitWindow(QDialog):
    # The visit's own window (non-modal, shown with show()): its
    # resources, its measurements (light-curve kinds) and its notes.
    # Nothing here is modal and nothing blocks the main window.
    #
    # @args: db - the Database, pid - project id, sid - the visit's id,
    #        lang - "es" | "en", curve_kind - keep the measurements block,
    #        open_in_editor - callable(path, session_id) for FITS rows,
    #        on_measure_click - callable(point_id) ADR-047: click a
    #        measured point and its plate opens in the editor (None keeps
    #        the list plain),
    #        data_changed - callable() after any edit (the panel refreshes
    #        and notifies the host), parent - the panel

    def __init__(self, db, pid, sid, lang="es", curve_kind=None,
                 kind=None, open_in_editor=None, data_changed=None,
                 on_measure_click=None, measure_series=None, astrometry=None,
                 runs_for_session=None, open_run=None, mpc_build=None,
                 parent=None):
        super().__init__(parent)
        self._db = db
        self._pid = pid
        self._sid = sid
        self._lang = lang
        self._kind = kind if kind is not None else (
            "sn" if (curve_kind or curve_kind is None) else "neo")
        self._curve_kind = self._kind in CURVE_KINDS
        self._mpc_kind = self._kind in MPC_KINDS
        self._open_in_editor = open_in_editor
        self._data_changed = data_changed
        self._on_measure_click = on_measure_click
        self._measure_series = measure_series
        self._astrometry = astrometry
        self._runs_for_session = runs_for_session
        self._open_run = open_run
        self._mpc_build = mpc_build
        self.setWindowTitle(self.tr("Visit"))
        self.resize(640, 520)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._build_ui()

    # ------------------------------------------------------------ build

    def _paint_confirmation(self):
        # @return: None. The rename notice in the visit's own header: the
        #          project's context already carries it (the ficha looked it
        #          up), so this reads and paints and never hits the network.
        #          Whether OUR observations are in the circular is said only
        #          when it is known (ADR-077 rev): otherwise it links to the
        #          object at the MPC and claims no participation.
        lbl = getattr(self._ui, "vp_lbl_confirm", None)
        if lbl is None:
            return
        try:
            from ...core import project as project_mod
            p = project_mod.get(self._db, self._pid)
        except Exception:
            p = None
        conf = ((p or {}).get("context") or {}).get("confirmed") or {}
        desig = conf.get("designation")
        if not desig:
            lbl.setVisible(False)
            return
        mpec = conf.get("mpec") or ""
        url = conf.get("mpec_url") or ""
        if mpec and url:
            tail = self.tr('published in <a href="%1">%2</a>').replace(
                "%1", url).replace("%2", mpec)
        elif mpec:
            tail = self.tr("published in %1").replace("%1", mpec)
        else:
            tail = ""
        text = "★ " + self.tr("Confirmed as <b>%1</b>").replace("%1", desig)
        if tail:
            text += " · " + tail
        if conf.get("ours_published"):
            text += ". " + self.tr(
                "your observations are among them: your data is in that MPEC")
        else:
            obj_url = ("https://www.minorplanetcenter.net/db_search/"
                       "show_object?utf8=True&object_id="
                       + desig.replace(" ", "+"))
            text += ". " + self.tr(
                '<a href="%1">see the object at the MPC</a>').replace(
                    "%1", obj_url)
        lbl.setText(text)
        lbl.setVisible(True)

    def _build_ui(self):
        from ...core import followup as fu
        s = fu.get_session(self._db, self._sid)
        if s is None:
            self.close()
            return
        # The structure is the Designer file's (ADR-005); the per-kind blocks
        # are fragments loaded on demand (absent means absent), and the
        # Passive widgets land in their placeholders.
        self._ui = adopt_ui(self, "visit_window")
        self._paint_confirmation()

        # ---- the head: the date READS and the name is edited in place.
        # The date is the visit's folder and its order in the list, so it is
        # changed from the "..." menu (a calendar), never by typing over it;
        # the name is free text and saves on commit. The "Saved" line is what
        # replaced the old Save button: the button existed so the observer
        # would know the edit took, and a line says it without a permanent
        # disabled control.
        self._date_lbl = self._ui.vp_visit_date
        self._date_lbl.setText(s["obs_date"] or "")
        self._label_ed = self._ui.vp_visit_label
        self._label_ed.setText(s.get("label") or "")
        self._label_ed.textChanged.connect(self._on_label_dirty)
        self._label_ed.editingFinished.connect(self._save_head)
        self._saved_lbl = self._ui.vp_lbl_saved
        self.btn_pin = self._ui.vp_btn_pin
        self.btn_pin.setChecked(bool(s.get("pinned")))
        self.btn_pin.toggled.connect(self._on_pin_toggled)
        self._build_more_menu()

        # ---- ONE analysis action, chosen by the kind (ADR-045 review): the
        # observer does not pick between the series and the track & stack.
        from ...core import kinds
        self.btn_analyze = self._ui.vp_btn_analyze
        self._analysis_action = kinds.analysis_of(self._kind)
        if self._analysis_action == "astrometry":
            self.btn_analyze.setText(self.tr("Measure the position…"))
            self.btn_analyze.setToolTip(self.tr(
                "Stack this visit's frames along the object's motion and "
                "measure its position, checked against the other observers "
                "(track & stack)"))
        elif self._analysis_action == "photometry":
            self.btn_analyze.setText(self.tr("Measure the series…"))
            self.btn_analyze.setToolTip(self.tr(
                "Open the editor on this visit's frames to measure the whole "
                "series (per-frame zero point, quality flags, undo by run)"))
        else:
            self.btn_analyze.setVisible(False)
        self.btn_analyze.clicked.connect(self._on_analyze)
        # ADR-038's grammar: the panel's ONE action wears the object's own
        # hue, the same hero button the Ficha and the series panel use. It is
        # what says "this is the normal path" without a word.
        if self._analysis_action is not None:
            from .. import theme
            hue = theme.KIND_COLORS.get(self._kind) or theme.C_ACCENT
            self.btn_analyze.setStyleSheet(theme.hero_button_style(hue))
        self._ui.vp_btn_attach.clicked.connect(self._on_attach)

        # ---- the visit's content, in ONE pass: Results (what it produced)
        # and the folded frames (the raw material). Both lists read the same
        # three sources, so they are filled together: three queries, not six.
        self.lst_results = PassiveList()
        self.lst_results.setObjectName("vp_results")
        self.lst_results.itemDoubleClicked.connect(self._on_row_open)
        self.lst_results.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lst_results.customContextMenuRequested.connect(
            lambda pos: self._on_row_menu(self.lst_results, pos))
        drop_in(self._ui.grp_results.layout(), self._ui.ph_results,
                self.lst_results)
        self.lst_files = PassiveList()
        self.lst_files.setObjectName("vp_files")
        self.lst_files.itemDoubleClicked.connect(self._on_row_open)
        self.lst_files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lst_files.customContextMenuRequested.connect(
            lambda pos: self._on_row_menu(self.lst_files, pos))
        drop_in(self._ui.grp_files.layout(), self._ui.ph_files, self.lst_files)
        self._ui.vp_btn_files.toggled.connect(self._on_files_fold)
        self._populate_content()

        # ---- the per-kind blocks, right under the actions: the night's own
        # astrometry (NEO/PCCP) or the quick hand measurement (curve kinds)
        if self._curve_kind:
            self._build_measurements_block(s)
        if self._mpc_kind:
            self._build_mpc_block()

        # ---- notes and the closing gesture (everything else auto-saves)
        self._notes = self._ui.vp_notes
        self._notes.setText(s["notes"])
        self._notes.textChanged.connect(self._on_notes_changed)
        self.btn_close = self._ui.vp_btn_close
        self.btn_close.clicked.connect(self._on_close)

    def _build_more_menu(self):
        # The two things that are NOT the daily work: the date (the visit's
        # folder and its order) and deleting the visit. They live behind the
        # "..." so the head keeps ONE job: saying which night this is.
        menu = QMenu(self)
        menu.addAction(self.tr("Change the date…"), self._on_change_date)
        menu.addSeparator()
        menu.addAction(self.tr("Delete the visit…"), self._on_delete_visit)
        self._ui.vp_btn_more.setMenu(menu)

    # ---------------------------------------------------------- the head

    def _stored_date(self):
        # @return: the visit's date as persisted (or "")
        from ...core import followup as fu
        s = fu.get_session(self._db, self._sid)
        return (s or {}).get("obs_date") or ""

    def _stored_head(self):
        # @return: (date, name) as persisted: the two things the head owns
        from ...core import followup as fu
        s = fu.get_session(self._db, self._sid) or {}
        return (s.get("obs_date") or "", s.get("label") or "")

    def _on_label_dirty(self, _text=None):
        # Any edit puts the "Saved" line away; it comes back on the commit.
        self._saved_lbl.setVisible(False)

    def _save_head(self):
        # Enter, or leaving the name field, saves it. Nothing to validate:
        # the date (the only field with a shape) has its own dialog.
        from ...core import followup as fu
        text = self._label_ed.text().strip()
        if text != self._stored_head()[1]:
            fu.update_session_label(self._db, self._sid, text)
            self._emit_change()
        self._flash_saved()

    def _flash_saved(self):
        # @return: None. The one line that says the edit took (the reason the
        #          old Save button existed).
        self._saved_lbl.setText(self.tr("Saved"))
        self._saved_lbl.setVisible(True)

    def _on_change_date(self):
        # A calendar, not a text field: the date is a folder name and a sort
        # key, and a typo there renames a night.
        from ...core import followup as fu
        ui = load_ui("visit_date_dialog", self)
        try:
            current = datetime.date.fromisoformat(self._stored_date()[:10])
        except ValueError:
            current = datetime.date.today()
        ui.dt_date.setDate(QDate(current.year, current.month, current.day))
        if ui.exec() != QDialog.DialogCode.Accepted:
            return
        new = ui.dt_date.date().toString("yyyy-MM-dd")
        fu.update_session_date(self._db, self._sid, new)
        self._date_lbl.setText(new)
        self._flash_saved()
        self._emit_change()

    def _on_pin_toggled(self, checked):
        # Pin/unpin: the visit floats to the top of the panel's list.
        from ...core import followup as fu
        fu.set_session_pinned(self._db, self._sid, checked)
        self._emit_change()

    def _on_close(self):
        # The closing gesture: a pending name edit flushes first (nothing else
        # is pending: everything saved itself as it was typed).
        self._save_head()
        self.close()

    def _on_delete_visit(self):
        # Confirmation first; points and files keep living in the project,
        # unlinked (the DB's ON DELETE SET NULL), and the dialog says so.
        from ...core import followup as fu
        ans = QMessageBox.question(
            self, self.tr("Delete visit"),
            self.tr("Delete this visit? Its measurements and files are "
                    "kept, unlinked from it."))
        if ans != QMessageBox.Yes:
            return
        fu.delete_session(self._db, self._sid)
        self._emit_change()
        self.close()

    # ------------------------------------------------------- the content

    def _kind_label(self, kind):
        # How a row's kind reads. The registry keeps a stable English key, and
        # showing it raw ("[exotic_figure]") made the list unreadable exactly
        # where a visit carries the reduction's own products. Each label is a
        # literal self.tr() so lupdate sees it; an unknown kind still shows its
        # key, never nothing.
        # @args: kind - the registry kind of the file
        # @return: the label
        labels = {
            "fits": self.tr("plate"),
            "image": self.tr("image"),
            "chart": self.tr("chart"),
            "report": self.tr("report"),
            "sequence": self.tr("sequence"),
            "animation": self.tr("animation"),
            "ephemeris": self.tr("ephemeris"),
            "stack": self.tr("stack"),
            "motion_gif": self.tr("motion (GIF)"),
            "motion_mp4": self.tr("motion (MP4)"),
            "evo_gif": self.tr("evolution (GIF)"),
            "evo_mp4": self.tr("evolution (MP4)"),
            "exotic_inits": self.tr("EXOTIC handoff"),
            "exotic_figure": self.tr("EXOTIC figure"),
            "exotic_aavso": self.tr("AAVSO report"),
            "exotic_params": self.tr("EXOTIC parameters"),
        }
        return labels.get(kind, kind)

    def _when(self, raw):
        # @args: raw - epoch seconds (float or string)
        # @return: "HH:MM" (local), or "" when the moment is unknown. The two
        #          lists are chronological, so the hour leads the row: a plain
        #          list cannot right-align a second column, and a log reads
        #          top-down anyway.
        try:
            return datetime.datetime.fromtimestamp(
                float(raw)).strftime("%H:%M")
        except (TypeError, ValueError):
            return ""

    def _freeable(self, run_id):
        # @args: run_id - the execution
        # @return: how many of its originals could still move to prcd/ (0 when
        #          the run is unknown or the module cannot say)
        from ...core import free_space
        try:
            return int(free_space.freeable(self._db, run_id)["n"])
        except Exception:
            return 0

    def _run_row(self, run):
        # @args: run - an astrometry run dict
        # @return: the row dict the two lists are built from
        undone = (run.get("status") or "") == "undone"
        n = run.get("n_obs") or run.get("points") or 0
        state = self.tr("undone") if undone else \
            self.tr("%1 obs · complete").replace("%1", str(n))
        tip = self.tr("The visit's astrometry run: open it in the editor")
        free = self._freeable(run.get("id"))
        if free:
            tip += "\n" + self.tr(
                "%1 original frames can be moved to prcd/.").replace(
                    "%1", str(free))
        return {"where": "results", "epoch": _epoch_of(run.get("created")),
                "glyph": _ROW_GLYPHS["run"], "text": self.tr("Astrometry run"),
                "kind": state, "when": self._when(run.get("created")),
                "tip": tip, "data": {"type": "run", "id": run.get("id")}}

    def _file_row(self, f):
        # @args: f - a project_files row
        # @return: the row dict; a raw kind goes to the folded block, the rest
        #          to Results
        meta = f.get("meta") or {}
        kind = f.get("kind") or "file"
        bits = [self._kind_label(kind)]
        if meta.get("filter"):
            bits.append(str(meta["filter"]))
        if meta.get("exptime_s"):
            bits.append(f"{float(meta['exptime_s']):g} s")
        return {"where": "files" if kind in _RAW_KINDS else "results",
                "epoch": _epoch_of(f.get("created")),
                "glyph": _ROW_GLYPHS.get(kind, "▪"),
                "text": Path(f["path"]).name, "kind": " · ".join(bits),
                "when": self._when(f.get("created")), "tip": f["path"],
                "data": {"type": "file", "id": f["id"], "path": f["path"],
                         "kind": kind}}

    def _point_row(self, p):
        # @args: p - a photometry point dict
        # @return: the row dict; the hour comes from the point's MJD (its own
        #          moment, which the visit's date edit never rewrites)
        err = f" ±{p['err']}" if p.get("err") is not None else ""
        mjd = p.get("mjd") or 0.0
        epoch = (float(mjd) + 2400000.5 - 2440587.5) * 86400.0
        return {"where": "results", "epoch": epoch, "glyph": _ROW_GLYPHS["point"],
                "text": f"{p.get('mag')}{err} ({p.get('filter')})",
                "kind": self.tr("measured") if p.get("source") != "manual"
                else self.tr("by hand"),
                "when": self._when(epoch),
                "tip": self.tr("A measurement of this visit"),
                "data": {"type": "point", "id": p.get("id")}}

    def _populate_content(self):
        # @return: None. Fills both lists from the visit's three sources
        #          (runs, files, points), each sorted by when it happened.
        from ...core import followup as fu, project as proj_mod
        files = proj_mod.files_for_session(self._db, self._sid)
        points = [p for p in fu.list_points(self._db, self._pid)
                  if p.get("session_id") == self._sid]
        runs = []
        if callable(self._runs_for_session):
            try:
                runs = self._runs_for_session(self._sid) or []
            except Exception:
                runs = []
        rows = ([self._run_row(r) for r in runs]
                + [self._file_row(f) for f in files]
                + [self._point_row(p) for p in points])
        results = sorted((r for r in rows if r["where"] == "results"),
                         key=lambda r: r["epoch"])
        raw = sorted((r for r in rows if r["where"] == "files"),
                     key=lambda r: r["epoch"])
        self._fill_list(self.lst_results, results)
        self._fill_list(self.lst_files, raw)
        empty = not results
        self._ui.vp_lbl_results.setText(self.tr(
            "Nothing yet: attach the night's frames or measure."))
        self._ui.vp_lbl_results.setVisible(empty)
        self._ui.vp_btn_files.setText(self.tr(
            "Files of the night (%1)").replace("%1", str(len(raw))))

    def _fill_list(self, lst, rows):
        # @args: lst - the PassiveList to fill, rows - the row dicts
        # @return: None
        lst.clear()
        for row in rows:
            text = row["text"]
            if row["kind"]:
                text += "   ·   " + row["kind"]
            when = (row["when"] + "   ") if row["when"] else ""
            item = QListWidgetItem(f"{row['glyph']}   {when}{text}")
            item.setData(Qt.UserRole, row["data"])
            item.setToolTip(row["tip"])
            lst.addItem(item)

    def _on_files_fold(self, open_):
        # The folded block: the arrow follows the state, and the list is only
        # built when it is open (the rows are cheap, but a hidden list that is
        # still laid out is what pushed the window past the fold).
        self._ui.ph_files.setVisible(open_)
        self._ui.vp_btn_files.setArrowType(
            Qt.DownArrow if open_ else Qt.RightArrow)

    # --------------------------------------------------- the row gestures

    def _row_data(self, lst, pos):
        # @args: lst - the list, pos - the click position
        # @return: (item, data) for the row under the cursor, or (None, {})
        item = lst.itemAt(pos)
        if item is None:
            return None, {}
        return item, (item.data(Qt.UserRole) or {})

    def _on_row_open(self, item):
        # Double click: the row's own default (a run opens in the editor, a
        # plate too, a measurement opens its plate).
        data = item.data(Qt.UserRole) or {}
        kind = data.get("type")
        if kind == "run":
            self._row_open_run(data.get("id"))
        elif kind == "point":
            self._row_open_point(data.get("id"))
        else:
            self._row_open_file(data)

    def _on_row_menu(self, lst, pos):
        # The per-row menu: everything a row can do, so the window needs no
        # button row (Open / Remove / Free space all lived in one before).
        item, data = self._row_data(lst, pos)
        if item is None:
            return
        kind = data.get("type")
        menu = QMenu(self)
        if kind == "run":
            menu.addAction(self.tr("Open in the editor"),
                           lambda: self._row_open_run(data.get("id")))
            free = self._freeable(data.get("id"))
            act = menu.addAction(
                self.tr("Free space (%1 frames)…").replace("%1", str(free))
                if free else self.tr("Free space…"),
                lambda: self._free_runs([data.get("id")]))
            act.setEnabled(bool(free))
            menu.addAction(self.tr("Bring back the frames…"),
                           lambda: self._restore_runs([data.get("id")]))
        elif kind == "point":
            menu.addAction(self.tr("Open its plate"),
                           lambda: self._row_open_point(data.get("id")))
            menu.addSeparator()
            menu.addAction(self.tr("Remove the measurement"),
                           lambda: self._row_remove_point(data.get("id")))
        else:
            menu.addAction(self.tr("Open"),
                           lambda: self._row_open_file(data))
            menu.addSeparator()
            menu.addAction(self.tr("Remove from the visit"),
                           lambda: self._row_remove_file(data.get("id")))
        menu.exec(lst.mapToGlobal(pos))

    def _row_open_run(self, run_id):
        # @return: None. The host owns the navigation (it opens the editor on
        #          the run); without it the gesture is a no-op.
        if callable(self._open_run) and run_id is not None:
            self._open_run(run_id)

    def _row_open_point(self, point_id):
        # ADR-047: the host resolves the plate the point came from and opens
        # it in the editor; without the callback the row stays plain.
        if callable(self._on_measure_click) and point_id is not None:
            self._on_measure_click(point_id)

    def _row_open_file(self, data):
        # FITS plates open in the editor (the host); everything else opens
        # with the system, which is what the observer expects of a PDF or a
        # chart.
        path = data.get("path")
        if not path:
            return
        if data.get("kind") == "fits" and callable(self._open_in_editor):
            self._open_in_editor(path, self._sid)
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _row_remove_file(self, file_id):
        # Unlink only; the file on disk is never touched.
        from ...core import project as proj_mod
        if file_id is None:
            return
        proj_mod.delete_file(self._db, file_id)
        self._populate_content()
        self._emit_change()

    def _row_remove_point(self, point_id):
        # The point is the visit's measurement: deleting it is a data change
        # (the curve follows), so it asks first.
        from ...core import followup as fu
        if point_id is None:
            return
        if QMessageBox.question(
                self, self.tr("Remove the measurement"),
                self.tr("Remove this measurement from the visit? The file it "
                        "came from is not touched."),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        fu.delete_point(self._db, point_id)
        self._populate_content()
        self._emit_change()

    # ------------------------------------------------------ free space

    def _free_runs(self, run_ids):
        # @args: run_ids - the executions whose originals move to prcd/
        # @return: None. ADR-062 phase 9: nothing is deleted, and Bring back
        #          undoes it. The confirmation says the count, the size and
        #          where they land, so the gesture is never blind.
        from ...core import free_space, project as project_mod
        ids = [r for r in (run_ids or []) if r is not None]
        if not ids:
            return
        p = project_mod.get(self._db, self._pid)
        if p is None:
            return
        storage = project_mod.storage_dir(p)
        n, nbytes = 0, 0
        for rid in ids:
            f = free_space.freeable(self._db, rid)
            n += f["n"]
            nbytes += f["bytes"]
        if n == 0:
            QMessageBox.information(
                self, self.tr("Free space"),
                self.tr("Nothing to free: the frames are already in prcd/."))
            return
        dest = str(Path(storage) / free_space.PROCESSED_DIR)
        mb = nbytes / (1024 * 1024)
        if QMessageBox.question(
                self, self.tr("Free space"),
                self.tr("Move %1 original frames (%2 MB) to %3?\n\n"
                        "Nothing is deleted: Bring back undoes it.")
                .replace("%1", str(n)).replace("%2", f"{mb:.0f}")
                .replace("%3", dest),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.WaitCursor)
        moved, errors = 0, 0
        try:
            for rid in ids:
                rep = free_space.move_to_processed(self._db, rid, storage)
                moved += rep.moved
                errors += len(rep.errors)
        finally:
            QApplication.restoreOverrideCursor()
        if errors:
            QMessageBox.warning(
                self, self.tr("Free space"),
                self.tr("%1 frames moved, %2 could not be moved.").replace(
                    "%1", str(moved)).replace("%2", str(errors)))
        self._populate_content()

    def _restore_runs(self, run_ids):
        # @args: run_ids - the executions whose originals come back
        # @return: None. A name already taken is not overwritten: the frame
        #          lands next to it (the registry follows).
        from ...core import free_space
        ids = [r for r in (run_ids or []) if r is not None]
        if not ids:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.WaitCursor)
        moved, renamed, errors = 0, 0, 0
        try:
            for rid in ids:
                rep = free_space.restore(self._db, rid)
                moved += rep.moved
                renamed += len(rep.renamed)
                errors += len(rep.errors)
        finally:
            QApplication.restoreOverrideCursor()
        if moved == 0 and errors == 0:
            QMessageBox.information(
                self, self.tr("Bring back"),
                self.tr("Nothing to bring back."))
            return
        msg = self.tr("%1 frames brought back.").replace("%1", str(moved))
        if renamed:
            msg += " " + self.tr(
                "%1 landed next to a file with the same name.").replace(
                    "%1", str(renamed))
        if errors:
            msg += " " + self.tr("%1 could not be moved.").replace(
                "%1", str(errors))
        QMessageBox.information(self, self.tr("Bring back"), msg)
        self._populate_content()

    def _on_analyze(self):
        # The kind's own analysis (ADR-045 review): the host opens the
        # editor on the right tab for this visit, and the observer does not
        # choose between the series and the track & stack. The blink and the
        # rest of the reduction live in the editor.
        if self._analysis_action == "astrometry" \
                and callable(self._astrometry):
            self._astrometry(self._sid)
        elif self._analysis_action == "photometry" \
                and callable(self._measure_series):
            self._measure_series(self._sid)

    def _on_attach(self):
        # File picker (multi) -> ONE metadata confirmation for the whole
        # batch (consensus from the headers; exceptions listed), never one
        # dialog per file. The rule of the redesign: nothing attaches
        # without a visit, and this action only exists inside one.
        from ...core import fits_meta, project as proj_mod
        paths, _sel = QFileDialog.getOpenFileNames(
            self, self.tr("Attach files to the visit"), "",
            self.tr("All files (*)"))
        if not paths:
            return
        fits = [p for p in paths if _kind_for(p) == "fits"]
        metas = {}
        if fits:
            metas = self._ask_batch_meta(fits)
            if metas is None:
                return        # the observer cancelled the whole batch
        for path in paths:
            kind = _kind_for(path)
            meta = metas.get(path, {}) if kind == "fits" else {}
            proj_mod.add_file(self._db, self._pid, path, kind,
                              session_id=self._sid, meta=meta)
        self._populate_content()
        self._emit_change()

    def _ask_batch_meta(self, paths):
        # One confirmation for a whole batch of FITS: the form carries the
        # batch consensus (most common filter/date/exptime) and a list of
        # the files whose header differs, each editable alone (double-click).
        # @args: paths - the FITS paths just picked
        # @return: {path: meta} or None when cancelled
        from collections import Counter
        from ...core import fits_meta
        raw = []
        for p in paths:
            try:
                meta = fits_meta.read_meta(p)
            except Exception:
                meta = {}
            raw.append((p, meta))
        keys = [((m.get("filter") or "Clear").strip() or "Clear",
                 str(m.get("date_obs") or ""), m.get("exptime_s"))
                for _p, m in raw]
        consensus = Counter(keys).most_common(1)[0][0] if keys \
            else ("Clear", "", None)
        cfilter, cdate, cexp = consensus
        excepts = [p for (p, _m), k in zip(raw, keys) if k != consensus]
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("FITS details"))
        ui = adopt_ui(dlg, "visit_files_meta")
        ui.lbl_count.setText(self.tr("FITS files: {0}").format(len(paths)))
        ui.vp_img_filter.addItems(_FILTERS)
        ui.vp_img_filter.setCurrentText(cfilter)
        ui.vp_img_date.setText(cdate)
        ui.vp_img_exptime.setText("" if cexp in (None, "") else str(cexp))
        ui.lbl_except_hint.setVisible(bool(excepts))
        overrides = {}
        meta_by_path = {p: m for p, m in raw}
        for p in excepts:
            m = meta_by_path[p]
            item = QListWidgetItem(self.tr("{0}  ·  {1} · {2} · {3}s")
                                   .format(Path(p).name,
                                           m.get("filter") or "?",
                                           m.get("date_obs") or "?",
                                           m.get("exptime_s") or "?"))
            item.setData(Qt.UserRole, p)
            ui.lst_except.addItem(item)
        ui.buttonBox.accepted.connect(dlg.accept)
        ui.buttonBox.rejected.connect(dlg.reject)
        ui.lst_except.itemDoubleClicked.connect(
            lambda it: self._edit_batch_exception(dlg, ui, it, overrides))
        if dlg.exec() != QDialog.Accepted:
            return None
        exp_txt = ui.vp_img_exptime.text().strip()
        try:
            exp = float(exp_txt) if exp_txt else None
        except ValueError:
            exp = None
        cons = {"filter": ui.vp_img_filter.currentText().strip() or "Clear",
                "date_obs": ui.vp_img_date.text().strip() or None,
                "exptime_s": exp}
        return {p: overrides.get(p, cons) for p in paths}

    def _edit_batch_exception(self, dlg, ui, item, overrides):
        # Edit one exception's meta alone (the batch consensus stands for
        # the rest); the row's text then shows the new values.
        path = item.data(Qt.UserRole)
        meta = self._ask_fits_meta(path)
        if meta is None:
            return
        overrides[path] = meta
        item.setText(self.tr("{0}  ·  {1} · {2} · {3}s").format(
            Path(path).name, meta.get("filter") or "?",
            meta.get("date_obs") or "?", meta.get("exptime_s") or "?"))

    def _ask_fits_meta(self, path):
        # The FITS confirmation dialog, pre-filled from the header (a
        # misnamed filter breaks the light-curve split, so it stays
        # editable). The form is ui/visit_file_meta.ui (ADR-005).
        # @return: the meta dict, or None when cancelled
        from ...core import fits_meta
        try:
            meta = fits_meta.read_meta(path)
        except Exception:
            meta = {}
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("FITS details"))
        ui = adopt_ui(dlg, "visit_file_meta")
        ui.lbl_file_name.setText(Path(path).name)
        ui.vp_img_filter.addItems(_FILTERS)
        ui.vp_img_filter.setCurrentText((meta.get("filter") or "Clear")
                                        .strip() or "Clear")
        ui.vp_img_date.setText(str(meta.get("date_obs") or ""))
        ui.vp_img_exptime.setText(
            "" if meta.get("exptime_s") in (None, "")
            else str(meta["exptime_s"]))
        ui.buttonBox.accepted.connect(dlg.accept)
        ui.buttonBox.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.Accepted:
            return None
        exp = ui.vp_img_exptime.text().strip()
        try:
            exp = float(exp) if exp else None
        except ValueError:
            exp = None
        return {"filter": ui.vp_img_filter.currentText().strip()
                or "Clear",
                "date_obs": ui.vp_img_date.text().strip() or None,
                "exptime_s": exp}

    # ----------------------------------------------------- measurements

    def _build_measurements_block(self, s):
        # The quick entry for a hand measurement, FOLDED behind its own
        # button: the visit's points are rows in Results now (they used to be
        # listed here as well, twice), so this block only has to say "add
        # one". The structure is the fragment ui/visit_measurements.ui,
        # loaded only for the light-curve kinds: absent means absent (the
        # pinned tests find no widget at all on the other kinds).
        ui = load_ui("visit_measurements", self)
        self._ui_meas = ui
        self.layout().insertWidget(4, ui)      # under the actions, above Results
        self.spn_mag = PassiveDoubleSpinBox()
        self.spn_mag.setRange(-5.0, 30.0)
        self.spn_mag.setDecimals(3)
        self.spn_mag.setValue(16.0)
        drop_in(ui.w_meas.layout(), ui.ph_mag, self.spn_mag)
        self.spn_err = PassiveDoubleSpinBox()
        self.spn_err.setRange(0.0, 9.0)
        self.spn_err.setDecimals(3)
        self.spn_err.setValue(0.0)
        self.spn_err.setSpecialValueText("—")
        drop_in(ui.w_meas.layout(), ui.ph_err, self.spn_err)
        self.cmb_filt = ui.cmb_filt
        self.cmb_filt.addItems(_FILTERS)
        ui.vp_btn_add_meas.clicked.connect(self._on_add_measurement)
        ui.vp_btn_add_point.toggled.connect(self._on_add_point_fold)

    def _on_add_point_fold(self, open_):
        # The entry opens on demand; the arrow says which state it is in.
        self._ui_meas.w_meas.setVisible(open_)
        self._ui_meas.vp_btn_add_point.setArrowType(
            Qt.DownArrow if open_ else Qt.RightArrow)

    def _session_mjd(self, s):
        # The visit's MJD: its observing date when parseable, else its
        # creation epoch; never 0 (a zero MJD corrupts the curve order).
        from ...core.coords import jd_from_datetime
        date_str = (s.get("obs_date") or "").strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y/%m/%d"):
            if date_str:
                try:
                    dt = datetime.datetime.strptime(date_str, fmt) \
                        .replace(tzinfo=datetime.timezone.utc)
                    return jd_from_datetime(dt) - 2400000.5
                except ValueError:
                    pass
        created = s.get("created")
        dt = (datetime.datetime.fromtimestamp(created,
                      tz=datetime.timezone.utc) if created
              else datetime.datetime.now(datetime.timezone.utc))
        return jd_from_datetime(dt) - 2400000.5

    def _on_add_measurement(self):
        # A hand measurement: the point joins the visit's curve AND the
        # Results list (one datum, one place to see it).
        from ...core import followup as fu
        mag = self.spn_mag.value()
        err = self.spn_err.value() if self.spn_err.value() > 0 else None
        filt = self.cmb_filt.currentText().strip() or "Clear"
        s = fu.get_session(self._db, self._sid)
        fu.add_point(self._db, self._pid, self._session_mjd(s), filt,
                     mag, err=err, source="manual", session_id=self._sid)
        self._populate_content()
        self._emit_change()

    # --------------------------------------------------- MPC astrometry

    def _project(self):
        # @return: the project dict (or None)
        from ...core import project as proj_mod
        return proj_mod.get(self._db, self._pid)

    def _build_mpc_block(self):
        # The night's astrometry (NEO/PCCP): the report window is the SAME one
        # the editor's Astrometry tab opens (ADR-080), through the shared
        # controller. The visit keeps a button and one status line: there is
        # nothing to paste here, because the report is built from the visit's
        # own astrometry run. It registers to THIS visit (the measurements are
        # the visit's product, ADR-045 form A), so the block lives here and
        # nowhere else. The structure is the fragment ui/visit_mpc_block.ui,
        # loaded only for the MPC kinds (absent means absent).
        from ..mpc_report_controller import MpcReportController
        ui = load_ui("visit_mpc_block", self)
        self.layout().insertWidget(4, ui)   # under the actions, above Results
        self.lbl_mpc_status = ui.vp_mpc_status
        self._report = MpcReportController(
            self, self._build_mpc_report,
            is_neocp=self._mpc_is_neocp, object_name=self._mpc_object_name,
            save_dir=self._mpc_save_dir,
            on_saved=self._on_mpc_saved, on_report=self._on_mpc_ready,
            say=self.lbl_mpc_status.setText)
        ui.vp_mpc_open.clicked.connect(self._report.open_window)
        # the visit opens knowing whether it has something to report
        self._report.regenerate(quiet=True)

    def _mpc_is_neocp(self):
        # @return: True while the object is on the confirmation page, so the
        #          send dialog starts on the NEOCP target
        return bool((self._project() or {}).get("context", {}).get("neocp"))

    def _mpc_object_name(self):
        # @return: the object's name, for the saved file's default name
        return (self._project() or {}).get("object_name") or ""

    def _mpc_save_dir(self):
        # @return: the project's own folder, where the report belongs (the
        #          measurements are the visit's product and hang from it)
        from ...core import project as proj_mod
        p = self._project()
        return proj_mod.storage_dir(p) if p else None

    def _build_mpc_report(self, fmt, submission, quiet):
        # @args: fmt - the generator's format key, submission - the ACK/target
        #        the header carries, quiet - True when the rebuild is not news
        # @return: {"text", "kept"} or None. The host rebuilds the report from
        #          the visit's own astrometry run (the run and its points live
        #          in the database, and the host owns them). Nothing is written
        #          here. The status line is the visit's only voice, so it says
        #          WHY there is nothing even on a quiet rebuild: with the
        #          window shut, an unexplained click reads as broken.
        if not callable(self._mpc_build):
            self.lbl_mpc_status.setText(
                self.tr("This visit has no astrometry to report."))
            return None
        try:
            out = self._mpc_build(self._sid, fmt, submission)
        except Exception as err:
            logger.warning("the visit's MPC report could not be built: %s", err)
            self.lbl_mpc_status.setText(
                self.tr("The visit's astrometry could not be rebuilt."))
            return None
        if not out or not str(out.get("text") or "").strip():
            self.lbl_mpc_status.setText(
                self.tr("This visit has no astrometry run to report yet."))
            return None
        return out

    def _on_mpc_ready(self):
        # @return: None. The report is in the window: the status line says how
        #          many observations it carries and what the button does.
        self.lbl_mpc_status.setText(self.tr(
            "%1 observation(s) ready to report. Open the report window to "
            "review, save or send it.").replace(
                "%1", str(self._report.kept)))

    def _on_mpc_saved(self, path, text):
        # @return: None. Register the saved report to THIS visit; when the
        #          report's own first measurement disagrees with the visit's
        #          date, say so (a report hung on the wrong night is a silent
        #          database sin), without blocking.
        from ...core import followup as fu, mpc_report
        from ...core import project as proj_mod
        proj_mod.add_file(self._db, self._pid, path, "report",
                          session_id=self._sid)
        note = ""
        rep_date = mpc_report.first_obs_date(text)
        s = fu.get_session(self._db, self._sid)
        if rep_date and s and s["obs_date"] and rep_date != s["obs_date"]:
            note = " " + self.tr(
                "⚠ the report's first measurement is from %1, not this "
                "visit's date").replace("%1", rep_date)
        self.lbl_mpc_status.setText(
            self.tr("Saved: %1").replace("%1", path) + note)
        self._populate_content()
        self._emit_change()

    # ------------------------------------------------------------ notes

    def _on_notes_changed(self):
        from ...core import followup as fu
        fu.update_session_notes(self._db, self._sid,
                                self._notes.toPlainText())

    # ------------------------------------------------------------ misc

    def _emit_change(self):
        # Tells the panel (and through it the host) that data changed.
        if self._data_changed is not None:
            self._data_changed()
