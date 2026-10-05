############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE Track & Stack tab (astrometry plan,
# phase 7)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_trackstack_tab.py: the tab is built
standalone against a host double that provides the visit context (no
network, and no worker is ever started here: the pipeline's physics lives
in test_track_stack_*). What is proven is the wiring (D22): the expected
SNR table recalculates when the number of observations changes, the stack
button stays disabled without a visit, the workers carry their cancel,
and no widget declared in the Designer file is left orphaned."""

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

UI = Path(__file__).parents[2] / "nightscribe" / "gui" / "ui" \
    / "ufe_trackstack_tab.ui"


def _write_frames(tmp_path, n=4):
    # @args: tmp_path - where, n - how many
    # @return: n small FITS paths with DATE-OBS/EXPTIME (headers are all
    #          load_sequence reads, so the frames stay tiny)
    from astropy.io import fits
    out = []
    for i in range(n):
        hdu = fits.PrimaryHDU(np.zeros((64, 64), dtype=np.float32))
        h = hdu.header
        h["DATE-OBS"] = f"2026-09-20T23:{30 + i}:00"
        h["EXPTIME"] = 30.0
        h["GAIN"] = 2.0
        h["INSTRUME"] = "TestCam"
        p = tmp_path / f"frame{i}.fits"
        hdu.writeto(str(p), overwrite=True)
        out.append(str(p))
    return out


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def _tab(qapp, tmp_path, visit=True, n=4):
    # @args: qapp - the offscreen app, tmp_path - where the frames go,
    #        visit - False builds the tab with no visit behind it, n -
    #        frames of the visit
    # @return: (tab, host): the tab over a host double with
    #          astrometry_context(), which is what the real dialog exposes
    #          (the tab asks its window(), so a plain parentless QWidget
    #          with the method is a faithful double)
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()           # parentless: it IS the tab's window()
    if visit:
        paths = _write_frames(tmp_path, n)
        ctx = {"pid": 1, "session_id": 2, "paths": paths,
               "object_name": "2026 QX"}
    else:
        ctx = None
    host.astrometry_context = lambda: ctx
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", parent=host)
    tab.set_active(True)
    return tab, host


# ------------------------------------------------------------ the visit

def test_stack_button_disabled_without_visit(qapp, tmp_path):
    # D15: without a visit there is no sequence. The button does not
    # pretend otherwise, and the object line says what is missing.
    tab, _host = _tab(qapp, tmp_path, visit=False)
    assert tab.btn_stack.isEnabled() is False
    assert tab.spn_nobs.isEnabled() is False
    assert tab.tbl_snr.rowCount() == 0
    assert tab.lbl_object.text()          # says why, never empty


def test_visit_arms_the_tab(qapp, tmp_path):
    tab, _host = _tab(qapp, tmp_path)
    assert tab.btn_stack.isEnabled() is True
    assert tab.spn_nobs.isEnabled() is True
    assert tab.spn_nobs.maximum() == 4    # never more groups than frames
    assert "2026 QX" in tab.lbl_object.text()


def test_the_tab_finds_an_embedded_host(qapp, tmp_path):
    # ADR-053: the editor is a PAGE of the shell, so window() from a tab is
    # the MAIN window and the hooks live in an ancestor. The helper above
    # mounts the host parentless, which is what production does NOT do, so
    # it never caught this; here the host is embedded and the trap is
    # reproduced. Before the fix the buttons stayed disabled with a visit
    # open (the visit reached the hook, the tab never found it).
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    outer = QWidget()                     # the shell's page
    host = QWidget(outer)                 # the embedded UfeDialog
    paths = _write_frames(tmp_path, 3)
    host.astrometry_context = lambda: {"pid": 1, "session_id": 2,
                                       "paths": paths,
                                       "object_name": "2026 QX"}
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", parent=host)
    assert tab.window() is outer          # the trap, reproduced
    assert tab._context() is not None     # host_of walks up to the host
    tab.set_active(True)
    assert tab.btn_stack.isEnabled() is True
    assert tab.spn_nobs.isEnabled() is True


# ------------------------------------------------- the expected SNR (D22)

def test_preview_table_follows_n_obs(qapp, tmp_path):
    # The user says how many observations; the table shows the split
    # (contiguous groups, as equal as they can be) on every change.
    tab, _host = _tab(qapp, tmp_path)
    tab.spn_nobs.setValue(2)
    assert tab.tbl_snr.rowCount() == 2
    assert [tab.tbl_snr.item(r, 1).text() for r in range(2)] == ["2", "2"]
    tab.spn_nobs.setValue(3)
    assert tab.tbl_snr.rowCount() == 3
    assert [tab.tbl_snr.item(r, 1).text() for r in range(3)] == \
        ["2", "1", "1"]
    # every group carries its own middle-of-exposure instant
    assert tab.tbl_snr.item(0, 2).text() != "–"


def test_expected_snr_splits_with_sqrt_n(qapp, tmp_path):
    # SNR grows with sqrt(n): with a measured base SNR of 40 for the four
    # frames, two observations get 40*sqrt(2/4) and four get 40*sqrt(1/4).
    tab, _host = _tab(qapp, tmp_path)
    tab.spn_nobs.setValue(2)
    # before the first run there is no measurement: the column stays "–"
    # (an estimate without a base would be invented)
    assert tab.tbl_snr.item(0, 3).text() == "–"
    tab._base_snr = 40.0
    tab._refresh_preview()
    assert tab.tbl_snr.item(0, 3).text() == "28.3"
    tab.spn_nobs.setValue(4)
    assert [tab.tbl_snr.item(r, 3).text() for r in range(4)] == \
        ["20.0"] * 4


def test_low_snr_group_is_marked_before_stacking(qapp, tmp_path):
    # D26: a group below the submission floor is SEEN before the run,
    # with the reason in the cell's tooltip (a figure is never shown
    # without its explanation, ADR-058). The floor's default is 10 (the
    # MPC recommends 20 but the author's accepted submissions ran at ~16),
    # so a group projected at 6 is below it.
    tab, _host = _tab(qapp, tmp_path)
    tab._base_snr = 12.0
    tab.spn_nobs.setValue(4)      # 12*sqrt(1/4) = 6.0, below the floor of 10
    text = tab.tbl_snr.item(0, 3).text()
    assert text.startswith("6.0")
    assert "⚠" in text
    assert tab.tbl_snr.item(0, 3).toolTip()


# ------------------------------------------------------------- no orphans

def test_no_orphan_widgets(qapp, tmp_path):
    # Every widget the Designer file declares resolves to a real widget
    # (the load that came back wrong is retried by ui_loader, and this
    # reads the .ui itself so nothing can be guessed away), and the
    # viewer's placeholder gave its slot to the real view: a visible
    # placeholder floats at (0, 0) over the first row and eats its
    # clicks (ADR-005).
    from PySide6.QtWidgets import QWidget
    tab, _host = _tab(qapp, tmp_path)
    tree = ET.parse(UI).getroot()
    root = tree.find("widget")
    names = [w.get("name") for w in tree.iter("widget")
             if w.get("name") and w.get("name") != root.get("name")]
    assert names, "the Designer file declares its widgets"
    for name in names:
        w = getattr(tab._ui, name, None)
        assert isinstance(w, QWidget), name
    assert not tab._ui.ph_stack_view.isVisibleTo(tab)
    assert not tab._ui.ph_thumbs.isVisibleTo(tab)
    # the real view took the placeholder's slot, inside the tab's
    # scrollable column (the column is taller than the panel)
    assert tab.isAncestorOf(tab._stack_view)
    # and the tab's own viewer never touches the dialog's plate state
    assert tab._stack_state is not tab._state


# ------------------------------------------------------------- workers

def test_workers_carry_their_cancel(qapp):
    # No thread may be left hanging (the trap every tab documents): the
    # workers are cancellable before, during and after a run, and cancel
    # on a worker that never started is a no-op, not a crash.
    from nightscribe.gui.workers import CalibrationWorker, TrackStackWorker
    w = TrackStackWorker(["missing.fits"], "2026 QX", 2)
    assert w.isRunning() is False
    w.cancel()
    assert w._cancel is True
    c = CalibrationWorker(["missing.fits"], None)
    c.cancel()
    assert c._cancel is True
    assert c.isRunning() is False
    # shutdown() on a tab with no worker behind it is safe too
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    tab = UfeTrackStackTab(UfeImageState(), "en")
    tab.shutdown()


def test_the_group_stack_goes_to_the_main_stage(qapp, tmp_path):
    # The stack must be shown in the SHARED stage (so the histogram, the
    # stretch and the marks work on it) and saved in the project, not left
    # in a private little viewer and a temp file (the observer's ask).
    import numpy as np
    from PySide6.QtWidgets import QWidget
    from nightscribe.core import astrometry
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.widgets.ufe_image_view import UfeImageView
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    saved = []
    host = QWidget()
    host.astrometry_context = lambda: {"pid": 1, "session_id": 2,
                                       "paths": [], "object_name": "2026 QX"}
    host.export_folder = lambda: str(tmp_path)
    host.notify_saved = lambda paths, kind: saved.append((list(paths), kind))
    state = UfeImageState(host)
    view = UfeImageView(state)
    tab = UfeTrackStackTab(state, "en", view=view, parent=host)
    point = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0)
    tab._result = {"stacks": [(np.zeros((16, 16), dtype=np.float32), None)],
                   "points": [(point, None, [])], "n_failed": 0}
    tab._show_group(0)
    # the SHARED state now holds the stack, not a private one, and the
    # file name says what the stack is (the object, the observation)
    assert state.path.endswith("2026QX_obs1.fits")
    # and the stack was registered in the project (kind "stack")
    assert saved and saved[0][1] == "stack"
    assert saved[0][0][0].endswith("2026QX_obs1.fits")


def test_the_run_is_persisted_and_can_be_undone(qapp, tmp_path):
    # Phase 8: the HOST persists the run (the tab never touches the
    # database) and hands back its id; "undo this run" takes back only that
    # execution. The tab is a facade over the two hooks.
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    calls = {}
    host = QWidget()
    host.astrometry_context = lambda: None
    host.persist_astrometry = lambda payload: calls.setdefault("run", 7)
    host.undo_astrometry = lambda run_id: (calls.__setitem__("undone", run_id)
                                           or 3)
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", parent=host)
    tab._on_finished({"status": "ok", "points": [], "method": "sigma"})
    assert calls.get("run") == 7 and tab._run_id == 7
    assert tab.btn_undo.isEnabled()
    tab._on_undo()
    assert calls.get("undone") == 7
    assert tab._run_id is None and not tab.btn_undo.isEnabled()


# ----------------------------------------------------- the strip and blink

def test_the_strip_shows_every_observation_and_picks_one(qapp, tmp_path):
    # D22: with two or three observations the eye wants them side by side
    # at ONE stretch (auto-stretching each panel would make a faint one
    # look as bright as a real one), and a click must bring that stack to
    # the main view.
    tab, _host = _tab(qapp, tmp_path)
    shown = []
    tab._show_group = lambda index: shown.append(index)
    stack_a = np.zeros((24, 24), dtype=np.float32)
    stack_a[12, 12] = 100.0
    stack_b = np.zeros((24, 24), dtype=np.float32)
    stack_b[12, 12] = 50.0
    tab._thumbs.set_stacks([stack_a, stack_b],
                           [(12.0, 12.0), (12.0, 12.0)],
                           ["Obs. 1", "Obs. 2"])
    panels = [tab._thumbs._row.itemAt(i).widget()
              for i in range(tab._thumbs._row.count())
              if tab._thumbs._row.itemAt(i).widget() is not None]
    assert len(panels) == 2
    tab._thumbs.picked.emit(1)
    assert shown == [1]
    # a new run empties it: a stale strip next to a fresh run is a lie
    tab._thumbs.clear()
    assert tab._thumbs._row.count() == 0


def test_the_blink_figure_is_written(qapp, tmp_path):
    # The figure lands in the project's folder with a name that says what
    # it is, and every panel shares one stretch.
    tab, host = _tab(qapp, tmp_path)
    host.export_folder = lambda: str(tmp_path)
    saved = []
    host.notify_saved = lambda paths, kind: saved.append((list(paths), kind))
    state = tab._state
    from nightscribe.gui.widgets.ufe_image_view import UfeImageView
    tab._view = UfeImageView(state)
    tab._result = {"stacks": [(np.zeros((32, 32), dtype=np.float32), None),
                              (np.ones((32, 32), dtype=np.float32), None)],
                   "qs": [(16.0, 16.0), (16.0, 16.0)],
                   "boxes": [(0, 0, 32, 32), (0, 0, 32, 32)],
                   "mids": [61000.5, 61000.6]}
    path = tab._write_blink("png")
    assert path is not None and Path(path).exists()
    assert path.name.endswith("_observations.png")
    assert "2026QX" in path.name
    assert saved and saved[0][1] == "sequence"


def test_the_run_paints_the_strip_the_magnitude_and_the_brightness(qapp,
                                                                   tmp_path):
    # The strip, the magnitude column and the brightness note all come from
    # the SAME payload: a run with photometry must show the three, and the
    # note must say where the comparison stars came from (an automatic
    # proposal is a first guess, not the observer's own sequence).
    from nightscribe.core import astrometry, track_stack
    tab, _host = _tab(qapp, tmp_path)
    sp = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0,
                                    snr=15.2, mag=18.05, band="G")
    tab._result = {
        "status": "ok", "groups": [(0, 5), (5, 10)], "n_failed": 0,
        "stacks": [(np.zeros((16, 16), dtype=np.float32), None),
                   (np.ones((16, 16), dtype=np.float32), None)],
        "boxes": [(0, 0, 16, 16), (0, 0, 16, 16)],
        "qs": [(8.0, 8.0), (8.0, 8.0)], "mids": [2461000.5, 2461000.6],
        "points": [(sp, None, []), (sp, None, [])],
        "detection": track_stack.DetectionReport(detected=True, snr=15.2),
        "photometry": {"mag": 18.05, "err": 0.12, "band": "G",
                       "n_comps": 8, "n_frames": 47, "source": "auto"},
    }
    tab._paint_run()
    assert tab.tbl_points.item(0, 6).text() == "18.050"
    assert "18.050" in tab.lbl_notes.text()
    assert "an automatic proposal" in tab.lbl_notes.text()
    assert tab.btn_blink.isEnabled()
    panels = [tab._thumbs._row.itemAt(i).widget()
              for i in range(tab._thumbs._row.count())
              if tab._thumbs._row.itemAt(i).widget() is not None]
    assert len(panels) == 2


def test_the_brightness_row_says_what_the_run_will_measure_with(qapp,
                                                               tmp_path):
    # The recipe is read LIVE from the Photometry tab and shown BEFORE the
    # run: a magnitude measured with a recipe nobody saw is a number
    # nobody can question. The button is the deep link to the one editor.
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()
    host.astrometry_context = lambda: None
    host.photometry_recipe = lambda: {"band": "G", "rap": 5.0, "rin": 9.0,
                                      "rout": 14.0, "seeing": False,
                                      "sky": "median"}
    shown = []
    host.show_tab = lambda name: shown.append(name)
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", parent=host)
    tab._sync_recipe_row()
    text = tab.lbl_recipe.text()
    assert "G" in text and "5.0/9.0/14.0" in text and "median" in text
    tab.btn_recipe.click()
    assert shown == ["measure"]
    # with the box off the row says what the run will NOT do, and it is
    # disarmed: there is nothing to edit for a measurement that is not run
    tab.chk_brightness.setChecked(False)
    assert "positions only" in tab.lbl_recipe.text()
    assert not tab.btn_recipe.isEnabled()


def test_the_brightness_row_handles_a_recipe_that_sizes_from_the_seeing(
        qapp, tmp_path):
    # "From the seeing" is a CHOICE, not a number: the recipe hands the
    # radii to the measured FWHM, so there is no triple to print.
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()
    host.astrometry_context = lambda: None
    host.photometry_recipe = lambda: {"band": None, "seeing": True,
                                      "radii_manual": False, "sky": "plane"}
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", parent=host)
    tab._sync_recipe_row()
    assert "from the seeing" in tab.lbl_recipe.text()
    # and with no host answering, the row says so instead of inventing one
    host.photometry_recipe = None
    tab._sync_recipe_row()
    assert "defaults" in tab.lbl_recipe.text()


def test_the_stack_is_written_with_its_own_wcs(qapp, tmp_path):
    # The stars on an object's stack are TRAILS, so a blind solve finds
    # nothing and fails (that is what the observer sees when the stack is
    # opened in the Photometry tab). But the plate is KNOWN: the reference
    # WCS shifted by the cutout's origin. The file now carries it, so
    # opening the stack needs no solver at all, and any external tool can
    # read it too.
    from astropy.wcs import WCS
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.widgets.ufe_image_view import UfeImageView
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()
    host.astrometry_context = lambda: None
    host.export_folder = lambda: str(tmp_path)
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", view=UfeImageView(state), parent=host)
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [30.0, 10.0]
    w.wcs.crpix = [8.5, 8.5]
    w.wcs.cd = [[-1e-4, 0.0], [0.0, 1e-4]]
    w.pixel_shape = (16, 16)
    tab._result = {"stacks": [(np.zeros((16, 16), dtype=np.float32), None)],
                   "points": [], "n_failed": 0, "wcs_by_group": [w]}
    tab._show_group(0)
    assert state.wcs is not None
    assert state.wcs.crval1 == pytest.approx(30.0)
    assert state.wcs.crval2 == pytest.approx(10.0)


# ---------------------------------------------- prominence (ADR-038)

def test_the_nightly_flow_is_visible_and_the_knobs_are_folded(qapp, tmp_path):
    # ADR-038: three levels. The nightly flow stays in the column (the
    # plan with its one-line SNR, the table behind it, the run, and the
    # report block) and the knobs most observers never touch go into
    # blocks that say what they hold. The STACKING SETTINGS open by
    # default (the method, the field, the margin, the brightness and the
    # recipe are the planning decisions); the two that are READ, not
    # chosen, start folded.
    tab, _host = _tab(qapp, tmp_path)
    assert tab.btn_stack.isVisibleTo(tab)          # the primary action
    assert tab.lbl_snr_line.isVisibleTo(tab)       # the plan, in one line
    # the SNR table is part of the plan, not a fold: it is read BEFORE the
    # run to decide how many observations to ask for
    assert tab.tbl_snr.isVisibleTo(tab)
    assert len(tab._sections) == 3
    assert tab._sections["advanced"]._expanded
    for key in ("check", "report"):
        assert not tab._sections[key]._expanded
    # the open block shows its knobs; the folded ones hide theirs
    assert tab.cmb_method.isVisibleTo(tab)
    assert not tab.chk_force.isVisibleTo(tab)
    assert not tab.txt_report.isVisibleTo(tab)
    # folding one takes its content away with it
    tab._sections["advanced"]._toggle()
    assert not tab.cmb_method.isVisibleTo(tab)


def test_the_result_area_starts_hidden(qapp, tmp_path):
    # What belongs to the result appears with a run and goes away with it:
    # an empty grid and a blank strip say nothing, and a check about a
    # verdict that does not exist yet is a paragraph about nothing. The
    # REPORT block stays visible (disabled) because it says what the flow
    # will produce, which is part of planning.
    tab, _host = _tab(qapp, tmp_path)
    assert not tab.tbl_points.isVisibleTo(tab)
    assert not tab.lbl_points_title.isVisibleTo(tab)
    assert not tab._thumbs.isVisibleTo(tab)
    assert not tab.cmb_group.isVisibleTo(tab)      # which stack to look at
    assert not tab._check_section.isVisibleTo(tab)
    assert not tab._sections["report"].isVisibleTo(tab)
    assert tab._ui.grp_report.isVisibleTo(tab)
    assert not tab.btn_report.isEnabled()          # and honest about it


def test_nothing_absorbs_the_extra_height_of_a_tall_window(qapp, tmp_path):
    # The column ends with a vertical STRETCH that collects the extra space
    # of a tall window. Dropping it (a QSpacerItem is neither a widget nor
    # a layout, and the move into the scroll area missed it) let Qt hand
    # that space to whatever could grow: the observations row came out
    # 141 px tall and pushed the Stack button out of sight, behind a black
    # void. A tall, narrow window is where it shows.
    tab, _host = _tab(qapp, tmp_path)
    tab.resize(380, 900)
    tab.show()
    qapp.processEvents()
    area = tab.layout().itemAt(0).widget()
    inner = area.widget()
    lay = inner.layout()
    last = lay.itemAt(lay.count() - 1)
    assert last.spacerItem() is not None, "the column must end with a stretch"
    # and the primary action is inside the view, not behind the void
    assert tab.btn_stack.y() + tab.btn_stack.height() \
        < area.viewport().height()
    tab.hide()


def test_the_column_fits_the_narrow_panel_it_lives_in(qapp, tmp_path):
    # The editor is a splitter: the stage takes ~880 px and the tabs 380,
    # so the astrometry column has to FIT there. A widget whose text cannot
    # wrap (a checkbox label) once demanded 404 px, and the content came
    # out 52 px wider than the scroll viewport with the horizontal bar off,
    # so the right edge was unreachable (half the Stack button with it).
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()
    host.astrometry_context = lambda: None
    tab = UfeTrackStackTab(UfeImageState(host), "en", parent=host)
    tab.resize(380, 617)
    tab.show()
    qapp.processEvents()
    area = tab.layout().itemAt(0).widget()
    inner = area.widget()
    assert inner.minimumSizeHint().width() <= area.viewport().width()
    tab.hide()


def test_the_door_holds_the_occasional_actions(qapp, tmp_path):
    # The blink figure and the undo are not nightly actions: they live
    # behind ⋯, and the items drive the very same buttons (so their text,
    # state and slot are untouched).
    tab, _host = _tab(qapp, tmp_path)
    menu = tab.btn_more.menu()
    assert menu is not None
    names = [act.data() for act in menu.actions()]
    assert names == ["btn_blink", "btn_undo"]
    # the buttons left the column: no floating widget where they were
    assert not tab.btn_blink.isVisibleTo(tab)
    assert not tab.btn_undo.isVisibleTo(tab)


def test_the_whole_column_is_inside_the_scroll_area(qapp, tmp_path):
    # Moving the column into the scroll area has to reparent EVERY widget.
    # A nested row layout moved with addItem keeps its widgets as children
    # of the tab, and the scroll area's viewport then paints OVER them: the
    # observations row and the ⋯ button went missing that way, and the
    # column showed a black void exactly where they should have been.
    # addLayout is the call that carries the widgets with it.
    tab, _host = _tab(qapp, tmp_path)
    area = tab.layout().itemAt(0).widget()
    inner = area.widget()
    assert inner is not None
    for name in ("lbl_object", "btn_more", "lbl_nobs", "spn_nobs",
                 "lbl_snr_line", "btn_stack", "tbl_snr", "cmb_method",
                 "cmb_final_size", "spn_margin", "chk_brightness",
                 "lbl_recipe", "btn_recipe", "tbl_points", "grp_report"):
        widget = getattr(tab._ui, name, None)
        assert widget is not None, name
        assert inner.isAncestorOf(widget), f"{name} no vive en la columna"
