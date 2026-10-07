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
    assert "18.050" in tab.txt_notes.toPlainText()
    assert "an automatic proposal" in tab.txt_notes.toPlainText()
    assert tab.btn_blink.isEnabled()
    panels = [tab._thumbs._row.itemAt(i).widget()
              for i in range(tab._thumbs._row.count())
              if tab._thumbs._row.itemAt(i).widget() is not None]
    assert len(panels) == 2


def test_generating_the_report_shows_why_an_observation_was_left_out(
        qapp, tmp_path, monkeypatch):
    # The report's own notes ("left out and why") land in the SAME notes box
    # the run fills. The rename lbl_notes -> txt_notes missed this spot, so
    # Generate crashed with AttributeError; nothing covered _on_report, and
    # this test is the one that would have caught it.
    from nightscribe.config import config
    from nightscribe.core import astrometry
    monkeypatch.setitem(config._data, "mpc_code", "Z41")
    tab, _host = _tab(qapp, tmp_path)
    good = astrometry.AstrometryPoint(
        ra=322.0, dec=-12.0, rms_ra=0.2, rms_dec=0.2, mag=18.0, band="G",
        snr=35.0, n_frames=5, group_index=0, mjd=59288.5)
    weak = astrometry.AstrometryPoint(
        ra=322.0, dec=-12.0, rms_ra=0.2, rms_dec=0.2, mag=18.0, band="G",
        snr=6.0, n_frames=5, group_index=1, mjd=59288.5)
    tab._result = {"status": "ok", "points": [(good, None, []),
                                              (weak, None, [])]}
    tab.txt_notes.setPlainText("the run's own notes")
    tab._on_report()                       # used to raise AttributeError
    assert tab.txt_report.toPlainText().strip()      # the block is there
    # the group is closed by default (2026-10-06): the box is inside it, so
    # the test opens it (the observer is TOLD by the notice)
    tab._sections["notes"].setCollapsed(False)
    assert tab.txt_notes.isVisibleTo(tab)
    text = tab.txt_notes.toPlainText()
    assert "left out" in text and "6.0" in text
    # the box is shared with the run notes, as it was before the rename
    assert "the run's own notes" not in text


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


def test_the_brightness_row_says_which_method_will_measure(qapp, tmp_path):
    # The filter is the app's default and it MOVES the published magnitude,
    # so the row that says what the run will do has to say it too: a recipe
    # read silently is a number nobody can question.
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()
    host.astrometry_context = lambda: None
    base = {"band": "G", "rap": 5.0, "rin": 9.0, "rout": 14.0,
            "sky": "median", "matched": True}
    host.photometry_recipe = lambda: dict(base)
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", parent=host)
    tab._sync_recipe_row()
    assert "matched filter" in tab.lbl_recipe.text()
    # with the aperture pinned, the row says the aperture and nothing else
    base["matched"] = False
    tab._sync_recipe_row()
    assert "aperture" in tab.lbl_recipe.text()
    assert "matched filter" not in tab.lbl_recipe.text()


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

def test_the_panel_opens_with_one_action_and_every_knob_folded(qapp, tmp_path):
    # ADR-038 (rev 2026-10-06): what the observer SEES on entering is the
    # object, the ONE action of the panel (a hero button) and a line saying
    # what that action will do with the current defaults. Every knob lives in
    # a collapsible group, ALL OF THEM CLOSED, and the result's groups do not
    # exist yet: they appear with the run (nothing lives outside a group).
    tab, _host = _tab(qapp, tmp_path)
    assert tab.btn_stack.isVisibleTo(tab)          # the one action
    assert tab.lbl_plan_line.isVisibleTo(tab)      # what it will do
    assert tab.lbl_plan_line.text()                # and it says something
    assert tab.lbl_object.isVisibleTo(tab)         # the context it works on
    # the decisions: present and closed
    for key in ("plan", "advanced"):
        assert tab._sections[key].isVisibleTo(tab), key
        assert not tab._sections[key]._expanded, key
    # the result: not on screen until there is one
    for key in ("notes", "view", "points", "manual", "check", "report"):
        assert not tab._sections[key].isVisibleTo(tab), key
    # the plan and the knobs are inside the closed groups
    assert not tab.spn_nobs.isVisibleTo(tab)
    assert not tab.tbl_snr.isVisibleTo(tab)
    assert not tab.cmb_method.isVisibleTo(tab)
    assert not tab.txt_report.isVisibleTo(tab)
    # opening one brings its content back
    tab._sections["advanced"]._toggle()
    assert tab.cmb_method.isVisibleTo(tab)
    tab._sections["plan"]._toggle()
    assert tab.spn_nobs.isVisibleTo(tab)


def test_every_group_is_a_bordered_card(qapp, tmp_path):
    # Asked for: the group must be BORDERED, so an expanded group has a
    # visible beginning and end. The skin is the object card's own section
    # skin (theme.block_card_style): a hairline, a 10 px radius and a 3 px
    # spine, with the title inside in the card's accent.
    from nightscribe.gui import theme
    tab, _host = _tab(qapp, tmp_path)
    section = tab._sections["advanced"]
    assert section.objectName() == "sectionCard"
    assert "border: 1px solid" in section.styleSheet()
    assert "border-left: 3px solid" in section.styleSheet()
    assert "border-radius: 10px" in section.styleSheet()
    # the title wears the accent, and the content is indented inside the card
    assert theme.C_ACCENT in section._btn.styleSheet()
    margins = section._content_layout.contentsMargins()
    assert (margins.left(), margins.right()) == (12, 12)


def test_the_result_arrives_in_groups(qapp, tmp_path):
    # Asked for: the RESULT is grouped too. With a run the groups appear (and
    # the ones that carry news start open); without one, none of them exists.
    from nightscribe.core import astrometry, track_stack
    tab, _host = _tab(qapp, tmp_path)
    sp = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0, snr=12.0)
    tab._result = {
        "status": "ok", "groups": [(0, 2)], "n_failed": 0,
        "stacks": [(np.zeros((8, 8), dtype=np.float32), None)],
        "boxes": [(0, 0, 8, 8)], "qs": [(8.0, 8.0)], "mids": [2461000.5],
        "points": [(sp, None, [])], "phot_skipped": True,
        "detection": track_stack.DetectionReport(detected=True, snr=12.0),
    }
    tab._paint_run()
    for key in ("view", "points", "manual", "check", "notes"):
        assert tab._sections[key].isVisibleTo(tab), key
        # EVERY group is closed by default (asked for 2026-10-06): the
        # observer opens what they want to read
        assert not tab._sections[key]._expanded, key
    assert not tab.txt_notes.isVisibleTo(tab)      # inside the closed group
    assert not tab._sections["report"]._expanded   # nothing to read in it yet
    # ... and the news ANNOUNCES itself on the header of the closed group
    assert tab._sections["notes"].notice() is not None
    assert tab._sections["points"].notice() == ("1", "info")
    assert tab._sections["view"].notice() == ("1", "info")
    # opening one consumes its notice
    tab._sections["notes"]._toggle()
    assert tab._sections["notes"].notice() is None
    assert tab.txt_notes.isVisibleTo(tab)


def test_the_action_wears_the_objects_hue(qapp, tmp_path):
    # The hero button is painted in the kind's hue (the same grammar the
    # masthead's active tab already uses) and carries the kind's glyph,
    # drawn in the button's own text colour: on a surface of the kind's hue
    # the glyph's hue would vanish.
    from nightscribe.gui import theme
    tab, host = _tab(qapp, tmp_path)
    host.project_accent = lambda: {"hue": "#4484ef", "kind": "neo",
                                   "label": "NEO"}
    tab.refresh_accent()
    assert "#4484ef" in tab.btn_stack.styleSheet()
    assert not tab.btn_stack.icon().isNull()
    # the CARD carries the quiet spine of the hue (the list grammar: the hue
    # carries the meaning, it does not shout) and its title wears the accent;
    # the progress bar fills with the hue itself
    spine = theme.composite("#4484ef", "70", over=theme.C_BASE)
    assert spine in tab._sections["advanced"].styleSheet()
    assert "#4484ef" in tab._sections["advanced"]._btn.styleSheet()
    assert "#4484ef" in tab.prg_stack.styleSheet()
    # without a project (an ad-hoc open) the app's own accent is used and
    # there is no kind glyph to draw
    host.project_accent = None
    tab.refresh_accent()
    assert theme.C_ACCENT in tab.btn_stack.styleSheet()
    assert tab.btn_stack.icon().isNull()


def test_the_plan_line_says_what_the_run_will_do(qapp, tmp_path):
    # The subtitle of the hero button, built from the same sources the blocks
    # show: the frames, how many observations, what the brightness is
    # measured with, whether the frames are calibrated and whether the check
    # runs. It is the answer to "what happens if I press this?".
    tab, host = _tab(qapp, tmp_path)
    host.photometry_recipe = lambda: {"band": "G", "rap": 5.0, "rin": 9.0,
                                      "rout": 14.0, "sky": "median"}
    host.calibration_summary = lambda: "dark · flat: flatG.fits"
    tab._sync_recipe_row()
    text = tab.lbl_plan_line.text()
    assert "4 frames" in text
    assert "1 observation" in text
    assert "G" in text and "5.0/9.0/14.0" in text
    assert "no calibration" in text          # off by default here
    assert "check" in text
    # and it follows the knobs: more observations, calibration on
    tab.spn_nobs.setValue(2)
    assert "2 observations" in text or "2 observations" in \
        tab.lbl_plan_line.text()
    tab.chk_calibrate.setChecked(True)
    assert "flatG.fits" in tab.lbl_plan_line.text()


def test_the_calibration_default_follows_the_library(qapp, tmp_path):
    # ADR-061 (rev): with a dark or a flat that matches this visit, applying
    # the calibration is what the measurement needs (0.087 mag of smooth
    # vignetting, measured), so it comes ON by itself. The stored key is
    # three-state: while nobody has chosen, the library decides.
    from nightscribe.config import config
    original = config.get("calib_astrometry", None)
    config._data.pop("calib_astrometry", None)
    try:
        tab, host = _tab(qapp, tmp_path)
        assert config.get("calib_astrometry", None) is None
        host.calibration_masters = lambda: True
        tab._auto_calibrate()
        assert tab.chk_calibrate.isChecked()
        # and the automatic choice is NOT written: it is not the observer's
        assert config.get("calib_astrometry", None) is None
        # once the observer touches it, their word is the law
        tab.chk_calibrate.setChecked(False)
        assert config.get("calib_astrometry", None) == 0
        host.calibration_masters = lambda: True
        tab._auto_calibrate()
        assert not tab.chk_calibrate.isChecked()
    finally:
        # the config is the observer's file, not the test's: put it back
        config._data["calib_astrometry"] = original
        config.save()


def test_the_calibration_stays_off_when_no_master_matches(qapp, tmp_path):
    # A library with nothing for this camera and filter leaves the
    # calibration off, and an UNKNOWN answer too: turning it on without
    # knowing would promise a calibration nobody verified.
    from nightscribe.config import config
    original = config.get("calib_astrometry", None)
    config._data.pop("calib_astrometry", None)
    try:
        tab, host = _tab(qapp, tmp_path)
        host.calibration_masters = lambda: False
        tab._auto_calibrate()
        assert not tab.chk_calibrate.isChecked()
        host.calibration_masters = lambda: None
        tab._auto_calibrate()
        assert not tab.chk_calibrate.isChecked()
    finally:
        config._data["calib_astrometry"] = original
        config.save()


def test_the_result_area_starts_hidden(qapp, tmp_path):
    # What belongs to the result appears with a run and goes away with it:
    # an empty grid and a blank strip say nothing, and a check about a
    # verdict that does not exist yet is a paragraph about nothing, and the
    # report's block (its format, its buttons and its text) is the RESULT of
    # a run too: it appears with it.
    tab, _host = _tab(qapp, tmp_path)
    assert not tab.tbl_points.isVisibleTo(tab)
    assert not tab.lbl_points_title.isVisibleTo(tab)
    assert not tab._thumbs.isVisibleTo(tab)
    assert not tab.cmb_group.isVisibleTo(tab)      # which stack to look at
    assert not tab._check_section.isVisibleTo(tab)
    assert not tab._sections["report"].isVisibleTo(tab)
    assert not tab._ui.grp_report.isVisibleTo(tab)
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


def test_a_single_operation_stage_shows_a_busy_bar(qapp, tmp_path):
    # The base stack, the comparison windows and the check's round trip are
    # ONE operation each: they report total=1, and a determinate bar pinned
    # at 0 for their whole duration reads as a freeze. It goes BUSY instead,
    # with the status line saying what is happening.
    tab, _host = _tab(qapp, tmp_path)
    tab._on_progress("base", 0, 1)
    assert tab.prg_stack.minimum() == 0 and tab.prg_stack.maximum() == 0
    # the FULL line is the record (and the tooltip); what is painted is that
    # same line elided to the width it has (2026-10-06: it used to wrap and
    # grow to 204 px of the column)
    assert "Stacking the whole sequence" in tab._status_text
    assert tab.lbl_status.toolTip() == tab._status_text
    # a stage with an inside to count stays determinate
    tab._on_progress("sweep", 3, 25)
    assert tab.prg_stack.maximum() == 25 and tab.prg_stack.value() == 3
    assert "(3/25)" in tab._status_text


def test_the_long_texts_are_boxes_with_a_height_and_a_scroll(qapp, tmp_path):
    # A long text in a LABEL has no middle ground: either it grows without
    # limit (and pushes the rest of the column out) or it clips its lines.
    # The run's notes and the check's verdict are read-only text boxes with
    # a floor and a ceiling and their own scrollbar, so they are always
    # readable and never eat the panel. The report's box gets a floor too.
    from PySide6.QtWidgets import QPlainTextEdit
    tab, _host = _tab(qapp, tmp_path)
    for name in ("txt_notes", "txt_check", "txt_report"):
        box = getattr(tab, name, None) or getattr(tab._ui, name, None)
        assert isinstance(box, QPlainTextEdit), name
        assert box.isReadOnly(), name
        assert box.minimumHeight() >= 70, name      # a floor to read from
        assert box.maximumHeight() <= 200, name     # a ceiling to live with
    # the notes keep their own height whatever the text says
    tab.txt_notes.setVisible(True)
    tab.txt_notes.setPlainText("\n".join("• note %d" % i for i in range(40)))
    qapp.processEvents()
    assert tab.txt_notes.height() <= tab.txt_notes.maximumHeight()


def test_the_star_stack_is_saved_next_to_the_object_stack(qapp, tmp_path):
    # C3: when the run kept the star stack (the observer asked for it to
    # measure by hand in the Photometry tab), the tab writes it as its own
    # file, with the same WCS and its own word about what it is, and
    # registers it in the visit.
    from astropy.io import fits
    from astropy.wcs import WCS
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.widgets.ufe_image_view import UfeImageView
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()
    host.astrometry_context = lambda: {"pid": 1, "session_id": 2,
                                       "paths": [], "object_name": "2025 UR"}
    host.export_folder = lambda: str(tmp_path)
    saved = []
    host.notify_saved = lambda paths, kind: saved.append((list(paths), kind))
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", view=UfeImageView(state),
                           parent=host)
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [30.0, 10.0]
    w.wcs.crpix = [8.5, 8.5]
    w.wcs.cd = [[-1e-4, 0.0], [0.0, 1e-4]]
    w.pixel_shape = (16, 16)
    obj = np.zeros((16, 16), dtype=np.float32)
    stars = np.ones((16, 16), dtype=np.float32)
    from nightscribe.core import astrometry
    point = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0)
    tab._result = {"stacks": [(obj, None)], "points": [(point, None, [])],
                   "n_failed": 0, "groups": [(0, 5)], "mids": [2460965.5],
                   "wcs_by_group": [w], "star_stacks": [(stars, None)]}
    tab._show_group(0)
    # the name carries the observation's UT: the run's mids are JULIAN
    # dates and the MJD offset is what turns 2460965.5 into 2025-10-17
    star_path = tmp_path / "2025UR_obs1_20251017T000000_stars.fits"
    assert star_path.exists()
    # the two stacks name each other (the pair the Photometry tab reads)
    from astropy.io import fits as _fits
    from nightscribe.core import fits_annotate
    obj_path = tmp_path / "2025UR_obs1_20251017T000000.fits"
    assert _fits.getheader(str(obj_path))["NS_PAIR"] == star_path.name
    assert _fits.getheader(str(star_path))["NS_PAIR"] == obj_path.name
    # and the object's measured position travels as the annotation the
    # editor paints, so the Photometry tab shows where to click
    marks = fits_annotate.read_annotations(str(obj_path))
    assert marks and marks[0]["x"] == pytest.approx(8.0)
    assert marks[0]["y"] == pytest.approx(8.0)
    header = fits.getheader(str(star_path))
    assert header["NS_STACK"] == "stars"
    assert header["CRVAL1"] == pytest.approx(30.0)
    assert any(p.endswith("_stars.fits") and kind == "stack"
               for paths, kind in saved for p in paths)


def test_the_band_reads_the_motion_and_brightness_of_a_stack(qapp, tmp_path):
    # The heading of an asteroid's stack says the motion the sweep measured
    # and the brightness measured on it, written into the file so a stack
    # reopened later says the same. band_facts reads exactly that, from the
    # header alone (no run in memory, no database round trip).
    from astropy.io import fits
    from PySide6.QtWidgets import QWidget
    from nightscribe.core import astrometry, track_stack
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()
    host.astrometry_context = lambda: {"pid": 1, "session_id": 2,
                                       "paths": [], "object_name": "2025 UR"}
    host.export_folder = lambda: str(tmp_path)
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", parent=host)
    tab._run_id = 7
    frame = track_stack.Frame(path="f.fits",
                              header={"EXPTIME": 30.0, "FILTER": "Clear",
                                      "INSTRUME": "TestCam"},
                              exptime_s=30.0,
                              date_obs="2026-09-20T23:30:00")
    point = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0)
    tab._result = {
        "stacks": [(np.zeros((16, 16), dtype=np.float32), None)],
        "points": [(point, None, [])],
        "groups": [(0, 4)], "mids": [2460965.5], "frames": [frame],
        "sweep": track_stack.SweepResult(
            best={"rate": 1.234, "pa": 245.4, "score": 3.0}, grid=[]),
        "photometry": {"mag": 18.05, "err": 0.12, "band": "G",
                       "n_comps": 8, "n_frames": 4,
                       "per_obs": [{"mag": 18.05, "err": 0.12,
                                    "n_comps": 8, "check": True}]},
    }
    tab._show_group(0)
    path = tmp_path / "2025UR_obs1_20251017T000000.fits"
    header = fits.getheader(str(path))
    assert header["NS_RATE"] == pytest.approx(1.234)
    assert header["NS_PA"] == pytest.approx(245.4)
    assert header["NS_MOT"] == "sweep"
    assert header["NS_MAG"] == pytest.approx(18.05)
    assert header["NS_MAGER"] == pytest.approx(0.12)
    assert header["NS_MAGNC"] == 8
    assert header["NS_MAGOK"] == 1
    assert header["NS_MAGB"] == "G"
    assert header["NS_NFRAM"] == 4
    assert header["EXPTIME"] == pytest.approx(30.0)
    assert header["DATE-OBS"].startswith("2025-10-17")
    assert header["NS_MAGSR"] == "measured"
    # the tab hands the band the same facts, from the header alone
    facts = tab.band_facts(dict(header))
    assert facts["motion"] == {"rate_arcsec_min": 1.234, "pa_deg": 245.4,
                               "measured": True}
    assert facts["measured"]["mag"] == pytest.approx(18.05)
    assert facts["measured"]["comps"] == 8
    assert facts["measured"]["check_ok"] is True
    assert facts["measured_pos"] == (30.0, 10.0)
    # ... and the LIVE state's header (read before the annotate pass) says
    # the same, so the band is right the moment the stack lands
    live = tab.band_facts(dict(tab._stack_state.header))
    assert live["measured_pos"] == (30.0, 10.0)
    assert live["motion"]["rate_arcsec_min"] == pytest.approx(1.234)
    # a plain frame is not one of the run's stacks
    assert tab.band_facts({"OBJECT": "2025 UR"}) is None


def test_the_band_marks_a_predicted_motion_and_the_star_stack_has_no_mag(
        qapp, tmp_path):
    # Without a sweep the ephemeris still gives the motion, marked (eph);
    # and the star stack, where the object is a trail, carries the motion
    # but never a brightness that was not measured there.
    from astropy.io import fits
    from PySide6.QtWidgets import QWidget
    from nightscribe.core import astrometry
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()
    host.astrometry_context = lambda: {"pid": 1, "session_id": 2,
                                       "paths": [], "object_name": "2025 UR"}
    host.export_folder = lambda: str(tmp_path)
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", parent=host)
    tab._run_id = 3
    point = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0)
    obj = np.zeros((16, 16), dtype=np.float32)
    stars = np.ones((16, 16), dtype=np.float32)
    tab._result = {
        "stacks": [(obj, None)], "star_stacks": [(stars, None)],
        "points": [(point, None, [])], "groups": [(0, 4)],
        "mids": [2460965.5], "base_rate": 30.6, "base_pa": 90.0,
    }
    tab._show_group(0)
    obj_header = fits.getheader(str(
        tmp_path / "2025UR_obs1_20251017T000000.fits"))
    star_header = fits.getheader(str(
        tmp_path / "2025UR_obs1_20251017T000000_stars.fits"))
    assert obj_header["NS_MOT"] == "eph"
    assert obj_header["NS_RATE"] == pytest.approx(30.6)
    assert "NS_MAG" not in star_header
    facts = tab.band_facts(dict(star_header))
    assert facts["motion"]["measured"] is False
    assert "measured" not in facts and "measured_pos" not in facts


def test_the_base_stack_is_saved_with_its_own_band_cards(qapp, tmp_path):
    # Asked for: the whole-sequence stack (the image the manual mark is
    # placed on) is a PRODUCT of the run, saved with its measurements: what
    # the band needs (motion and brightness with their source) and the
    # detection that was made on it (SNR, gate, limit magnitude). Without
    # those cards the band over it said nothing about the object.
    from astropy.io import fits
    from PySide6.QtWidgets import QWidget
    from nightscribe.core import track_stack
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.widgets.ufe_image_view import UfeImageView
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    saved = []
    host = QWidget()
    host.astrometry_context = lambda: {"pid": 1, "session_id": 2,
                                       "paths": [], "object_name": "2026 PY9"}
    host.export_folder = lambda: str(tmp_path)
    host.notify_saved = lambda paths, kind: saved.append((list(paths), kind))
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", view=UfeImageView(state), parent=host)
    tab._run_id = 7
    frame = track_stack.Frame(path="f.fits",
                              header={"EXPTIME": 60.0, "FILTER": "Clear"},
                              exptime_s=60.0, date_obs="2026-10-06T22:00:00",
                              t_mid_jd=2461319.5)
    tab._result = {
        "base_stack": np.zeros((32, 32), dtype=np.float32),
        "box_all": (10, 20, 42, 52), "q_all": (26.0, 36.0),
        "frames": [frame], "n_failed": 0,
        "base_rate": 0.42, "base_pa": 271.0,
        "detection": track_stack.DetectionReport(detected=False, snr=1.4,
                                                 mag_limit=19.4),
        "ephem_mag": 22.21, "ephem_band": "V",
        "ephem_mag_source": "horizons",
    }
    tab._save_base_stack(tab._result)
    path = tmp_path / "2026PY9_base.fits"
    assert path.exists()
    # and it is registered on the visit, like the observations' stacks
    assert saved and saved[0][1] == "stack"
    assert saved[0][0][0].endswith("2026PY9_base.fits")
    header = fits.getheader(str(path))
    assert header["NS_STACK"] == "base"
    assert header["NS_RUN"] == 7
    assert header["NS_WHOLE"] == 1
    assert header["NS_NFRAM"] == 1
    assert header["NS_MOT"] == "eph"           # no sweep: a prediction
    assert header["NS_RATE"] == pytest.approx(0.42)
    # the brightness was NOT measured: the ephemeris' figure rides along,
    # labelled, instead of the plate saying nothing about the object's light
    assert header["NS_MAG"] == pytest.approx(22.21)
    assert header["NS_MAGSR"] == "ephemeris"
    assert header["NS_MAGB"] == "V"
    # and the detection made ON this image
    assert header["NS_FOUND"] == 0
    assert header["NS_SNR"] == pytest.approx(1.4)
    assert header["NS_GATE"] == pytest.approx(3.5)
    assert header["NS_LIMIT"] == pytest.approx(19.4)
    # the tab hands the band all of it, from the header alone
    facts = tab.band_facts(dict(header))
    assert facts["motion"]["measured"] is False
    assert facts["predicted"] == {"mag": 22.21, "band": "V"}
    assert "measured" not in facts
    assert facts["detection"]["snr"] == pytest.approx(1.4)
    assert facts["detection"]["limit"] == pytest.approx(19.4)


def test_the_band_says_when_the_brightness_is_a_prediction(qapp, tmp_path):
    # The magnitude's origin travels in the file (NS_MAGSR) and band_facts
    # respects it: a prediction is handed over as `predicted`, never as a
    # measurement, so it cannot wear the quality colours of one. And a stack
    # written BEFORE the card existed is still read as a measurement, which
    # is what all of them were.
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()
    host.astrometry_context = lambda: None
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", parent=host)
    base = {"NS_STACK": "object", "NS_RUN": 7, "NS_MAG": 18.05,
            "NS_MAGB": "G", "NS_MAGER": 0.12, "NS_MAGNC": 8}
    facts = tab.band_facts(dict(base))
    assert facts["measured"]["mag"] == pytest.approx(18.05)
    assert "predicted" not in facts
    facts = tab.band_facts({**base, "NS_MAGSR": "ephemeris"})
    assert facts["predicted"] == {"mag": 18.05, "band": "G"}
    assert "measured" not in facts


def test_the_registration_note_says_what_happened(qapp, tmp_path):
    # P0: the bare "N frames were left out" is gone. The tab says how many
    # came back and how, why the rest failed, and whether the visit is
    # really two runs (measured on 2025 UR: 47 saved by rotation, 2 runs,
    # 884 px and 289 s apart).
    tab, _host = _tab(qapp, tmp_path)
    text = tab._register_note({
        "n_total": 140, "n_ok": 139, "n_failed": 1, "n_rotation": 47,
        "multi_run": True, "reasons": {"few_stars": 1},
        "blocks": [{"n": 77, "dx": 0.0, "dy": 0.0, "angle_deg": 0.0,
                    "gap_s": None},
                   {"n": 62, "dx": -818.9, "dy": 334.7, "angle_deg": -0.118,
                    "gap_s": 289.0}]})
    import math as _math
    assert "47 frames were saved" in text
    assert "1 frames could not be aligned (too few stars)" in text
    assert "2 runs" in text and "5 min later" in text
    # the distance is the hypot of the block's offset, rounded for reading
    assert f"{_math.hypot(-818.9, 334.7):.0f} px away" in text
    # nothing to say, nothing said
    assert tab._register_note({"n_total": 10, "n_ok": 10, "n_failed": 0,
                               "n_rotation": 0, "multi_run": False,
                               "blocks": [], "reasons": {}}) == ""


def test_the_register_reasons_are_words_not_codes(qapp, tmp_path):
    # The core speaks English keys; the interface speaks the language, and
    # a code we do not know is passed through rather than hidden.
    tab, _host = _tab(qapp, tmp_path)
    assert tab._register_reasons({"few_stars": 3}) == "too few stars"
    assert tab._register_reasons({"rms": 2, "few_stars": 1}) == \
        "their stars did not agree on the fit: 2, too few stars: 1"
    assert tab._register_reasons({"weird": 1}) == "weird"
    assert tab._register_reasons({}) == ""


def test_the_shape_note_says_the_trail(qapp, tmp_path):
    # P2: a trailed object is SAID, with its pixels and its position angle,
    # so the next exposure can be shortened instead of the loss being found
    # later as a low SNR. The matched filter's gain is said too.
    tab, _host = _tab(qapp, tmp_path)
    text = tab._shape_note({"trail_px": 2.4, "trail_pa_deg": 245.0,
                            "snr_gain": 1.58})
    assert "trailed by 2.4 px" in text
    assert "PA 245" in text
    assert "1.58x" in text
    # a round object with nothing to gain says nothing at all
    assert tab._shape_note({"trail_px": None, "snr_gain": 1.0}) == ""
    assert tab._shape_note(None) == ""


def test_the_diagnosis_note_says_the_night(qapp, tmp_path):
    # P3: how faint the night went and whether the solution is even, both
    # measured on the run's own comps.
    tab, _host = _tab(qapp, tmp_path)
    text = tab._diag_note({
        "limit": {"ok": True, "mag": 19.8, "sky_limited": True},
        "grid": {"ok": True, "median": 0.18, "worst": 0.9}})
    assert "Limiting magnitude (5σ): 19.8" in text
    assert "0.18" in text and "up to 0.90" in text
    # a field that is not sky-limited says so instead of quoting the figure
    text = tab._diag_note({"limit": {"ok": True, "mag": 21.0,
                                     "sky_limited": False}, "grid": {}})
    assert "do not trust it" in text
    # an even solution does not shout about its worst cell
    text = tab._diag_note({"limit": {"ok": False},
                           "grid": {"ok": True, "median": 0.20,
                                    "worst": 0.25}})
    assert "worst cell" not in text
    assert tab._diag_note(None) == ""


def test_calibrating_the_frames_is_optional_and_off_by_default(qapp, tmp_path):
    # The observer asked for it explicitly: applying a pseudo-flat (and the
    # calibration at all) has to be a choice, visible in the tab where the
    # faint object is measured, and off unless it is asked for.
    tab, _host = _tab(qapp, tmp_path)
    assert tab.chk_calibrate.text()
    assert tab.chk_calibrate.isChecked() is False
    assert "0.087" in tab.chk_calibrate.toolTip()      # the why, measured
    assert "dithered" in tab.chk_calibrate.toolTip()


def test_applying_the_calibration_survives_and_the_hint_says_what_it_will_do(
        qapp, tmp_path, monkeypatch):
    # The choice is SAVED now (it used to reset on every rebuild), and the
    # hint says the vignetting's fate BEFORE the run. The hint's recipe comes
    # from the Calibration tab, the single source, so the two cannot disagree.
    from nightscribe.config import config
    monkeypatch.setitem(config._data, "calib_astrometry", 0)
    tab, host = _tab(qapp, tmp_path)
    assert tab.chk_calibrate.isChecked() is False
    assert "vignetting" in tab.lbl_calibration_hint.text()
    tab.chk_calibrate.setChecked(True)
    assert int(config.get("calib_astrometry")) == 1
    host.calibration_summary = lambda: "bias · pseudo-flat from the frames"
    tab._sync_calibration_hint()
    assert "pseudo-flat from the frames" in tab.lbl_calibration_hint.text()


def test_the_calibration_link_opens_the_calibration_tab(qapp, tmp_path):
    # The recipe, the library and the pseudo-flat policy live in the
    # Calibration tab: this button is the deep link to it, the same pattern
    # as the photometry recipe's.
    tab, host = _tab(qapp, tmp_path)
    seen = []
    host.show_tab = lambda name: seen.append(name)
    tab.btn_calibration.click()
    assert seen == ["calibration"]


# ------------------------------------------------------- manual mode (ADR-065)

def _manual_result():
    import numpy as np
    return {"status": "not_detected", "detection": None,
            "base_stack": np.zeros((64, 64), dtype=np.float32),
            "box_all": (10, 20, 74, 84), "q_all": (42.0, 52.0),
            "w0": None, "shape": (64, 64)}


def test_the_manual_door_is_always_available_once_there_is_a_run(qapp,
                                                                tmp_path):
    # Asked for: the manual mark is not a door that only opens when a run
    # finds nothing. It is useful on ANY run (to place a faint object's
    # centroid by eye), so it is enabled whenever there is a visit to stack
    # and it is THERE as soon as a run exists. Before any run there is no
    # whole-sequence stack to mark on, so it waits with the rest of the
    # result (a door onto nothing is furniture).
    tab, _host = _tab(qapp, tmp_path)
    assert not tab.chk_manual.isVisibleTo(tab)    # no run yet: no stack
    tab._result = _manual_result()
    tab._paint_not_detected()                     # below the gate
    # the door is there, inside its group; every group is closed by default
    # (2026-10-06), so the observer opens it first
    assert tab._sections["manual"].isVisibleTo(tab)
    tab._sections["manual"].setCollapsed(False)
    assert tab.chk_manual.isVisibleTo(tab)
    assert tab.chk_manual.isEnabled()
    tab._hide_manual()                            # a new visit or an undo
    assert tab.chk_manual.isEnabled()             # the door stays open
    assert not tab.chk_manual.isChecked()
    # with no visit there is no sequence to stack: the door is closed (and,
    # with no run either, it is not even on screen)
    no_visit, _h = _tab(qapp, tmp_path, visit=False)
    assert not no_visit.chk_manual.isEnabled()
    assert not no_visit.chk_manual.isVisibleTo(no_visit)


def test_the_manual_mark_is_nudged_and_measured_from_the_reference_grid(
        qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QPointF
    tab, _host = _tab(qapp, tmp_path)
    # a plate must be on the stage for the click to land
    tab._stack_state.load(tab._context()["paths"][0])
    tab._result = _manual_result()
    tab._paint_not_detected()
    tab.chk_manual.setChecked(True)
    tab._manual_armed = True
    tab._on_manual_click(QPointF(32.0, 32.0))
    assert tab._manual_base is not None
    assert tab.btn_manual_measure.isEnabled()
    tab._nudge_step(0.1, -0.2)
    assert tab.lbl_nudge.text() == "(+0.1, -0.2)"
    # "Measure at the mark" hands the mark in REFERENCE-GRID pixels: the
    # base stack's data coordinates plus the cutout's origin
    seen = {}
    monkeypatch.setattr(
        tab, "_start_run",
        lambda manual_ref=None: seen.setdefault("ref", manual_ref))
    tab._on_manual_measure()
    mx, my = tab._manual_base
    assert seen["ref"] == pytest.approx((10 + mx + 0.1, 20 + my - 0.2))
    assert tab._manual_armed is False


def test_a_manual_run_says_the_detection_was_the_observers(qapp, tmp_path):
    # The position of a manual run is still MEASURED on the plate, but the
    # decision that there was something to measure was the observer's. A note
    # that says it is not a nicety: without it the run reads as an automatic
    # detection that bypassed the gate (ADR-065, point 5).
    from nightscribe.core import astrometry
    tab, _host = _tab(qapp, tmp_path)
    sp = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0,
                                    snr=2.1, flags=["manual"])
    tab._result = {"status": "ok", "manual": True, "points": [(sp, None,
                                                               ["manual"])],
                   "groups": [(0, 2)], "stacks": [(np.zeros((8, 8),
                                                             dtype=np.float32),
                                                   None)],
                   "qs": [(8.0, 8.0)], "boxes": [(0, 0, 8, 8)],
                   "mids": [2461000.5], "phot_skipped": True}
    tab._paint_run()
    text = tab.txt_notes.toPlainText()
    assert "HUMAN MARK" in text and "manual mode" in text
    # and the point's flag reaches the table as words, never as a code
    assert "mark" in tab.tbl_points.item(0, 7).text()


def test_the_manual_flag_travels_with_the_point():
    # The worker's own half: every point of a manual run is flagged, once, and
    # the flag list is the one the measurement already returned (the table and
    # the persisted row read that same list).
    from nightscribe.core import astrometry
    from nightscribe.gui import workers
    a = astrometry.AstrometryPoint(ra=1.0, dec=2.0, flags=["disagree"])
    b = astrometry.AstrometryPoint(ra=3.0, dec=4.0)
    points = [(a, None, a.flags), (b, None, b.flags)]
    workers._mark_as_manual(points)
    workers._mark_as_manual(points)          # idempotent: never twice
    assert a.flags == ["disagree", "manual"]
    assert b.flags == ["manual"]


def test_the_calibration_note_says_what_the_magnitude_was_measured_with(
        qapp, tmp_path):
    # ADR-061: a brightness never goes out without saying whether the frames
    # were calibrated and with which masters.
    tab, _host = _tab(qapp, tmp_path)
    text = tab._calibration_note({"n": 139, "offsets": ["dark120.fits"],
                                  "flats": ["flatR.fits"], "warnings": []})
    assert "Calibrated 139 frames" in text
    assert "dark120.fits" in text and "flatR.fits" in text
    # the pseudo-flat says so, and repeats its own warning when it has one
    text = tab._calibration_note({"n": 12, "offsets": [],
                                  "flats": ["pseudo-flat"],
                                  "pseudo_flat": {"note": "the flat still "
                                                  "carries the stars"}})
    assert "pseudo-flat" in text and "carries the stars" in text
    # no masters at all: it says that too, instead of pretending
    assert "no master matched" in tab._calibration_note(
        {"n": 3, "offsets": [], "flats": []})
    assert tab._calibration_note(None) == ""


def test_the_manual_mark_cross_is_drawn_and_can_be_hidden(qapp, tmp_path,
                                                          monkeypatch):
    # Asked for: a subtle cross on the marked centroid so it is clear WHERE
    # the point is, and a switch to take it off (a cross over a 19th
    # magnitude object is a cross over the object).
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QGraphicsLineItem
    tab, _host = _tab(qapp, tmp_path)
    tab._stack_state.load(tab._context()["paths"][0])
    tab._result = _manual_result()
    tab._paint_not_detected()
    tab.chk_manual.setChecked(True)
    tab._manual_armed = True
    view = tab._stack_view

    def lines():
        return [it for it in view._items_registered
                if isinstance(it, QGraphicsLineItem)]

    tab._draw_marks()                    # nothing is marked yet
    assert lines() == []
    tab._on_manual_click(QPointF(32.0, 32.0))
    # the mark's own cross: two arms, two passes each (a shadow and the
    # colour), and nothing else (this result has no measured point)
    assert tab._manual_base is not None
    assert len(lines()) == 4
    tab._manual.chk_show_cross.setChecked(False)
    assert lines() == []
    tab._manual.chk_show_cross.setChecked(True)
    assert len(lines()) == 4
    # nudging moves the cross with the mark (it is redrawn, not duplicated)
    tab._nudge_step(0.1, 0.1)
    assert len(lines()) == 4
    # and measuring takes the mark's cross away
    monkeypatch.setattr(tab, "_start_run", lambda manual_ref=None: None)
    tab._on_manual_measure()
    assert lines() == []


def test_the_measured_cross_survives_a_new_plate_and_a_tab_switch(qapp,
                                                                 tmp_path):
    # Reported: the red measured-position cross was lost when another image
    # of the series was loaded and when the Photometry tab took the stage.
    # It is anchored to the SKY (the point's RA/Dec) and placed with the
    # open plate's own WCS, so it comes back on every plate of the visit.
    import numpy as np
    from astropy.wcs import WCS
    from PySide6.QtWidgets import QGraphicsLineItem, QWidget
    from nightscribe.core import astrometry
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.widgets.ufe_image_view import UfeImageView
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()
    host.astrometry_context = lambda: None
    host.export_folder = lambda: str(tmp_path)
    state = UfeImageState(host)
    view = UfeImageView(state)
    tab = UfeTrackStackTab(state, "en", view=view, parent=host)
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [30.0, 10.0]
    w.wcs.crpix = [8.5, 8.5]
    w.wcs.cd = [[-1e-4, 0.0], [0.0, 1e-4]]
    w.pixel_shape = (16, 16)
    sp = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0)
    tab._result = {"stacks": [(np.zeros((16, 16), dtype=np.float32), None)],
                   "points": [(sp, None, [])], "wcs_by_group": [w],
                   "boxes": [(0, 0, 16, 16)], "qs": [(8.0, 8.0)],
                   "groups": [(0, 1)], "mids": [2461000.5]}
    tab._show_group(0)

    def cross_lines():
        return [it for it in view._items_registered
                if isinstance(it, QGraphicsLineItem)]

    assert len(cross_lines()) == 4       # the measured cross's four arms
    # leaving the tab does not take the mark away (it belongs to the result)
    tab.set_active(False)
    assert len(cross_lines()) == 4
    # and coming back finds it again, placed on the open plate's own sky
    tab.set_active(True)
    assert len(cross_lines()) == 4
    # without a WCS the mark can only be placed on the observation's OWN
    # stack (its own pixels): on any other plate of the visit it goes
    # rather than sitting somewhere it does not belong
    state.wcs = None
    tab._draw_marks()
    assert len(cross_lines()) == 4
    tab._shown_stack_path = str(tmp_path / "another_plate.fits")
    tab._draw_marks()
    assert cross_lines() == []


# --------------------------------------------------------- the restore

def _saved_run(tmp_path, mag=18.2):
    # @return: (run, points, stack paths) as the host hands them over
    import numpy as np
    from astropy.io import fits
    path = tmp_path / "2026QX_obs1.fits"
    fits.PrimaryHDU(np.zeros((16, 16), dtype=np.float32)).writeto(
        path, overwrite=True)
    run = {"id": 7, "session_id": 2, "status": "complete", "method": "sigma",
           "cfg": {"result": {
               "method": "sigma",
               "detection": {"detected": True, "snr": 12.0},
               "photometry": {"mag": mag, "err": 0.1, "band": "G",
                              "n_comps": 5, "n_obs": 1, "n_frames": 4,
                              "source": "project"},
               "check": {"available": True, "blocked": False},
               "box_all": [10, 20, 42, 52], "base_rate": 0.42,
               "base_pa": 271.0, "ephem_mag": 22.21, "ephem_band": "V",
               "ephem_mag_source": "horizons"}}}
    points = [{"group_index": 0, "source": "stack", "ra": 30.0, "dec": 10.0,
               "x": 8.0, "y": 8.0, "snr": 12.0, "mag": mag, "band": "G",
               "mjd": 61000.5, "n_frames": 4, "flags": []}]
    return run, points, [str(path)]


def test_a_saved_run_is_shown_again_when_the_visit_is_reopened(qapp, tmp_path):
    # Asked for: if the visit already holds a run, reopening it shows
    # everything (the notes, the table, the group viewer and the strip),
    # rebuilt from what was saved, WITHOUT stacking again. The stacks are
    # the files the run wrote; the points and the notes come from the
    # database.
    tab, host = _tab(qapp, tmp_path)
    run, points, stacks = _saved_run(tmp_path)
    host.astrometry_result = lambda: {"run": run, "points": points,
                                      "stacks": stacks}
    tab.refresh_context()
    assert tab._result is not None and tab._result.get("restored")
    assert tab._run_id == 7                      # the undo door follows it
    assert tab.btn_undo.isEnabled()
    assert tab.cmb_group.count() == 1
    assert tab.tbl_points.rowCount() == 1
    assert tab.tbl_points.item(0, 6).text() == "18.200"
    assert "18.200" in tab.txt_notes.toPlainText()
    # the strip holds the saved stack (the array was read back from disk)
    assert tab._result["stacks"][0][0] is not None
    assert tab._result["stacks"][0][0].shape == (16, 16)
    assert tab.btn_blink.isEnabled()
    # and the status line says WHERE this came from, never pretending it
    # was computed now (the whole line; what is painted is elided to fit)
    assert "saved" in tab._status_text
    # the door to a fresh run stays open: a restore is not a lock
    assert tab.btn_stack.isEnabled()


def test_a_restored_run_does_not_write_its_stacks_again(qapp, tmp_path):
    # A restored run SHOWS its stacks; rewriting them would duplicate files
    # (and cost the observer's disk). The registered files stay untouched
    # and nothing new is announced.
    tab, host = _tab(qapp, tmp_path)
    run, points, stacks = _saved_run(tmp_path)
    saved = []
    host.notify_saved = lambda paths, kind: saved.append((list(paths), kind))
    host.astrometry_result = lambda: {"run": run, "points": points,
                                      "stacks": stacks}
    before = Path(stacks[0]).stat().st_mtime_ns
    tab.refresh_context()
    tab._show_group(0)
    assert not saved
    assert Path(stacks[0]).stat().st_mtime_ns == before


def test_coming_back_with_a_cleared_plate_shows_the_observation_again(
        qapp, tmp_path):
    # A session change drops the plate but not the run held in memory:
    # coming back to the tab shows the observation on stage again, so the
    # marks are not left floating over nothing.
    tab, host = _tab(qapp, tmp_path)
    run, points, stacks = _saved_run(tmp_path)
    host.astrometry_result = lambda: {"run": run, "points": points,
                                      "stacks": stacks}
    tab.refresh_context()
    assert tab._result is not None
    tab._stack_state.clear()
    tab.set_active(False)
    tab.set_active(True)
    assert tab._stack_state.has_image
    assert tab._stack_state.path.endswith("2026QX_obs1.fits")


def test_the_report_comes_back_with_the_restored_run(qapp, tmp_path):
    # Asked for: reopening the visit shows the run WITH its report. The
    # generator is local and deterministic (the same points give the same
    # text), so it is rebuilt instead of stored; and it is rebuilt QUIETLY:
    # the notes box keeps the run's own story (the report's "left out and
    # why" notes would otherwise overwrite it).
    tab, host = _tab(qapp, tmp_path)
    run, points, stacks = _saved_run(tmp_path)
    host.astrometry_result = lambda: {"run": run, "points": points,
                                      "stacks": stacks}
    tab.refresh_context()
    assert tab.txt_report.toPlainText().strip()
    assert "18.200" in tab.txt_notes.toPlainText()
    # the report is ready to send, and it was not sent anywhere by itself
    assert tab.btn_send_mpc.isEnabled()


def test_a_restored_run_can_be_marked_by_hand(qapp, tmp_path, monkeypatch):
    # The manual mark is carried to the reference grid with the base stack's
    # cutout origin (box_all), which travels in the run's summary: without it
    # a reopened run could not be marked at all, and the door would be a lie.
    tab, host = _tab(qapp, tmp_path)
    run, points, stacks = _saved_run(tmp_path)
    host.astrometry_result = lambda: {"run": run, "points": points,
                                      "stacks": stacks}
    tab.refresh_context()
    assert tab._result["box_all"] == (10, 20, 42, 52)
    assert tab._result["ephem_mag"] == pytest.approx(22.21)
    tab._stack_state.load(stacks[0])
    tab._manual_armed = True
    tab._manual_base = (5.0, 6.0)
    seen = {}
    monkeypatch.setattr(
        tab, "_start_run",
        lambda manual_ref=None: seen.setdefault("ref", manual_ref))
    tab._on_manual_measure()
    assert seen["ref"] == pytest.approx((15.0, 26.0))
    # The saved point carries the EFFECTIVE magnitude (a measurement made by
    # hand in the Photometry tab takes over the one the report would use) and
    # mag_source says who wrote it: the table must not present it as the
    # run's own figure.
    tab, host = _tab(qapp, tmp_path)
    run, points, stacks = _saved_run(tmp_path, mag=18.9)
    points[0]["mag_source"] = "manual"
    host.astrometry_result = lambda: {"run": run, "points": points,
                                      "stacks": stacks}
    tab.refresh_context()
    assert tab.tbl_points.item(0, 6).text() == "18.900"
    assert "hand" in tab.tbl_points.item(0, 7).text()


def test_the_restore_pairs_a_stack_with_its_observation_number(qapp, tmp_path):
    # The stack files carry "obs<N>" in their names: the restore pairs them
    # by that number and NOT by their position in the visit's list, so an
    # observation that measured nothing cannot shift the others onto the
    # wrong file (the strip and the blink would show another night's sky).
    import numpy as np
    from astropy.io import fits
    tab, host = _tab(qapp, tmp_path)
    a = tmp_path / "2026QX_obs1.fits"
    b = tmp_path / "2026QX_obs3.fits"
    fits.PrimaryHDU(np.full((16, 16), 1.0, dtype=np.float32)).writeto(a)
    fits.PrimaryHDU(np.full((16, 16), 9.0, dtype=np.float32)).writeto(b)

    def row(gi, x):
        return {"group_index": gi, "source": "stack", "ra": 30.0,
                "dec": 10.0, "x": x, "y": 8.0, "snr": 5.0, "mjd": 61000.5,
                "n_frames": 2, "flags": []}

    # observation 2 measured nothing: only 1 and 3 are saved
    host.astrometry_result = lambda: {
        "run": {"id": 3, "session_id": 2, "status": "complete",
                "method": "sigma", "cfg": {"result": {}}},
        "points": [row(0, 8.0), row(2, 4.0)],
        "stacks": [str(b), str(a)]}
    tab.refresh_context()
    stacks = tab._result["stacks"]
    assert len(stacks) == 2
    assert stacks[0][0][0, 0] == pytest.approx(1.0)      # observation 1
    assert stacks[1][0][0, 0] == pytest.approx(9.0)      # observation 3
    # and the positions kept their own observation's numbers
    assert [p[0].group_index for p in tab._result["points"]] == [0, 2]


def test_an_undone_run_is_not_restored(qapp, tmp_path):
    # Undo takes the run back and marks its row "undone": reopening the
    # visit must not resurrect it (the host filters it out, and the tab
    # paints an empty column).
    tab, host = _tab(qapp, tmp_path)
    host.astrometry_result = lambda: None
    tab.refresh_context()
    assert tab._result is None
    assert tab.cmb_group.count() == 0
    assert not tab.btn_undo.isEnabled()


def test_the_manual_door_is_open_on_a_restored_not_detected_run(qapp,
                                                               tmp_path):
    # The base stack is saved with the run, so a restored run that found
    # nothing can still be marked by hand: the door is open and the notes
    # say how deep the night reached. (An old run with no stack on disk gets
    # the dialog's own "stack the sequence first".)
    tab, host = _tab(qapp, tmp_path)
    run, points, stacks = _saved_run(tmp_path)
    run["status"] = "not_detected"
    run["cfg"]["result"]["detection"] = {"detected": False, "snr": 1.0,
                                        "mag_limit": 18.9}
    host.astrometry_result = lambda: {"run": run, "points": [],
                                      "stacks": []}
    tab.refresh_context()
    assert tab._result is not None and tab._result["restored"]
    assert tab.chk_manual.isEnabled()
    assert "18.90" in tab.txt_notes.toPlainText()


def test_a_run_below_the_gate_measures_anyway_and_paints_it_red(qapp,
                                                               tmp_path):
    # ADR-062 rev (D10 revisited): the gate still forbids the SWEEP, but it no
    # longer throws the run away. The observer asked for the brightness to be
    # measured ALWAYS and marked when it is not to be trusted: the magnitude
    # cell comes out RED (the same role the plate's band uses) and the notes
    # say where the number comes from (the ephemeris' position) and that the
    # stack's limit magnitude is what the night really reached.
    from nightscribe.core import astrometry, track_stack
    from nightscribe.viz import palette
    tab, _host = _tab(qapp, tmp_path)
    sp = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0,
                                    snr=1.8, mag=20.4, band="G")
    tab._result = {
        "status": "ok", "below_gate": True, "groups": [(0, 5)], "n_failed": 0,
        "stacks": [(np.zeros((16, 16), dtype=np.float32), None)],
        "boxes": [(0, 0, 16, 16)], "qs": [(8.0, 8.0)],
        "mids": [2461000.5],
        "points": [(sp, None, ["below_gate"])],
        "detection": track_stack.DetectionReport(detected=False, snr=1.8,
                                                 mag_limit=20.9),
        "photometry": {"mag": 20.4, "err": 0.4, "band": "G", "n_comps": 6,
                       "n_frames": 5, "source": "auto",
                       "per_obs": [{"mag": 20.4, "err": 0.4, "n_comps": 6,
                                    "check_ok": None}]},
    }
    tab._paint_run()
    # the measurement is THERE (this is the point of the change)
    assert tab.tbl_points.item(0, 6).text() == "20.400"
    # and it wears the doubtful role: red, not green
    colour = tab.tbl_points.item(0, 6).foreground().color().name()
    assert colour.lower() == palette.DANGER.lower()
    notes = tab.txt_notes.toPlainText()
    assert "did NOT clear" in notes
    assert "20.90" in notes                     # the limit magnitude is said
    assert "not to be published" in notes


def test_a_clean_run_paints_its_magnitude_green(qapp, tmp_path):
    # The other half of the same rule: a run that DID detect the object and
    # whose comps hold the zero point wears the clean role, so red really
    # means something.
    from nightscribe.core import astrometry, track_stack
    from nightscribe.viz import palette
    tab, _host = _tab(qapp, tmp_path)
    sp = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0,
                                    snr=15.0, mag=18.05, band="G")
    tab._result = {
        "status": "ok", "groups": [(0, 5)], "n_failed": 0,
        "stacks": [(np.zeros((16, 16), dtype=np.float32), None)],
        "boxes": [(0, 0, 16, 16)], "qs": [(8.0, 8.0)],
        "mids": [2461000.5],
        "points": [(sp, None, [])],
        "detection": track_stack.DetectionReport(detected=True, snr=15.0),
        "photometry": {"mag": 18.05, "err": 0.05, "band": "G", "n_comps": 8,
                       "n_frames": 5, "source": "auto",
                       "per_obs": [{"mag": 18.05, "err": 0.05, "n_comps": 8,
                                    "check_ok": True}]},
    }
    tab._paint_run()
    colour = tab.tbl_points.item(0, 6).foreground().color().name()
    assert colour.lower() == palette.GOOD.lower()


def test_the_result_brings_its_own_widgets_not_just_the_groups(qapp,
                                                               tmp_path):
    # Regression (reported 2026-10-06: "Measurement per observation está
    # vacío; creo que las preview de cada observación las hemos perdido").
    # The refactor to collapsible groups left three widgets hidden for good:
    # the measurement table, its title and the strip of observation stacks.
    # The groups appeared with their title and NOTHING inside.
    from nightscribe.core import astrometry, track_stack
    tab, _host = _tab(qapp, tmp_path)
    sp = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0,
                                    snr=12.0, mag=18.2, band="G")
    tab._result = {
        "status": "ok", "groups": [(0, 2), (2, 4)], "n_failed": 0,
        "stacks": [(np.zeros((32, 32), dtype=np.float32), None),
                   (np.ones((32, 32), dtype=np.float32), None)],
        "boxes": [(0, 0, 32, 32), (0, 0, 32, 32)],
        "qs": [(16.0, 16.0), (16.0, 16.0)], "mids": [2461000.5, 2461000.6],
        "points": [(sp, None, []), (sp, None, [])], "phot_skipped": True,
        "detection": track_stack.DetectionReport(detected=True, snr=12.0),
    }
    tab._paint_run()
    qapp.processEvents()
    # open the two groups the widgets live in
    tab._sections["points"].setCollapsed(False)
    tab._sections["view"].setCollapsed(False)
    qapp.processEvents()
    assert tab.lbl_points_title.isVisibleTo(tab)
    assert tab.tbl_points.isVisibleTo(tab)
    assert tab.tbl_points.rowCount() == 2          # one per observation
    assert tab._thumbs.isVisibleTo(tab)            # the previews are back
    assert tab._thumbs._row.count() == 3           # two panels + the stretch
    # and they all leave again with the result
    tab._show_result_area(False)
    assert not tab.tbl_points.isVisibleTo(tab)
    assert not tab._thumbs.isVisibleTo(tab)


def test_the_calibration_button_opens_the_window_not_a_tab(qapp, tmp_path):
    # Regression (reported 2026-10-06): the button deep-linked with the name
    # "calibration", the tool is keyed "calibrate", and the name that matched
    # nothing fell through to tabs.setCurrentWidget("calibration") and raised
    # a TypeError on every press. The real dialog is what the test drives: the
    # one that used a host double could not see it.
    tab, _host = _tab(qapp, tmp_path)
    dlg = tab.window() if hasattr(tab, "window") else None
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    d.tabs.setCurrentWidget(d.tab_trackstack)
    qapp.processEvents()
    d.tab_trackstack.btn_calibration.click()
    qapp.processEvents()
    assert d._tools["calibrate"].isVisible()
    assert d._active_tool == "calibrate"
    # and a name that no panel claims is logged, never raised
    d.show_tab("no-existe")
    assert d._tools["calibrate"].isVisible()
    d.shutdown()
    d.deleteLater()


def test_the_report_says_what_came_out_and_never_sends_nothing(qapp,
                                                               tmp_path):
    # Reported 2026-10-06: a 2025 FG18 sequence with two observations
    # "generated nothing". Measured: both were below the MPC submission floor
    # (SNR 20 by default), so the generator returned the format's header and
    # no data lines, and the reason lived in a group that is closed by
    # default. Now the report's own group says it, the send button refuses an
    # empty report and the notes group is marked.
    from nightscribe.core import astrometry
    tab, _host = _tab(qapp, tmp_path)

    def run(snr):
        pts = [astrometry.AstrometryPoint(
            ra=322.5, dec=-12.3, rms_ra=0.2, rms_dec=0.2, mag=19.6,
            band="G", snr=snr, n_frames=100, group_index=i,
            mjd=60763.86 + i * 0.001) for i in range(2)]
        tab._result = {"status": "ok", "points": [(p, None, []) for p in pts],
                       "check": None}
        tab._sync_report_buttons()
        tab._on_report()
        qapp.processEvents()

    from nightscribe.config import config
    floor = int(float(config.get("astrometry_submit_snr", 20.0)))
    assert floor > 6                          # this test needs it below
    run(6.0)                                  # below the floor: no report
    assert "None of the 2 observations" in tab.lbl_report_note.text()
    assert f"SNR {floor}" in tab.lbl_report_note.text()
    assert tab.btn_send_mpc.isEnabled() is False
    assert tab._sections["notes"].notice() is not None
    assert "SNR 6.0" in tab.txt_notes.toPlainText()
    run(25.0)                                 # above it: a report to send
    assert tab.lbl_report_note.text() == "2 of 2 observations are in the report."
    assert tab.btn_send_mpc.isEnabled() is True
    assert tab.txt_report.toPlainText().count("\n") >= 2   # header + rows


def test_the_run_says_which_method_measured_the_brightness(qapp, tmp_path):
    # The filter is the default and it MOVES the published magnitude: the run
    # has to say which method it used and keep the other value beside it, so
    # a curve that steps by a tenth of a magnitude can be explained.
    tab, _host = _tab(qapp, tmp_path)
    text = tab._method_note({"matched": True, "band": "G",
                             "mag_aperture": 18.243})
    assert "matched filter" in text
    # the aperture's value goes WITH its caveat: it is the same zero point on
    # the aperture's flux, not a second run of the aperture (that one would
    # need its own zero point, and the run measured only one)
    assert "the aperture, with the same zero point, would give 18.243" in text
    # with the aperture, the note says so and quotes nothing else
    text = tab._method_note({"matched": False, "band": "G",
                             "mag_aperture": 18.243})
    assert "with the aperture" in text
    assert "would give" not in text
    # a run without the key (an old plate) says nothing rather than guessing
    assert tab._method_note({"mag": 18.2}) == ""
    assert tab._method_note(None) == ""
    # AND THE CASE THAT MADE THE NOTE LIE: the recipe asked for the filter,
    # the plate could not apply it (no seeing measured), and the run said
    # "measured with the matched filter" while the aperture had done it
    text = tab._method_note({"matched": False, "matched_requested": True,
                             "band": "G"})
    assert "with the aperture" in text
    assert "was asked for but the seeing could not be measured" in text


def test_the_shape_note_says_the_filter_state_and_both_signal_to_noise(
        qapp, tmp_path):
    # The author compared the SNR in the observations table with the box on
    # and off, got 5.41 bit for bit, and read it as "the filter does
    # nothing". That number is the DETECTION's (the astrometry's own
    # aperture), so it cannot change; what changes is the brightness, and the
    # note has to say by how much, with the two SNRs of the brightness
    # measurement.
    tab, _host = _tab(qapp, tmp_path)
    base = {"snr_gain": 1.51, "snr_ap": 5.8, "snr_mf": 8.7}
    text = tab._shape_note(dict(base, matched=True))
    assert "measured with the matched filter" in text
    assert "reads 1.51x the aperture's SNR" in text
    assert "SNR 8.7 against 5.8 on the brightness measurement" in text
    # with the box off it says what it WOULD read, and where the switch is
    text = tab._shape_note(dict(base, matched=False))
    assert "would read 1.51x the aperture's SNR" in text
    assert "its switch is in the Photometry panel" in text
    # without the pair the sentence still stands (an old run carries none)
    text = tab._shape_note({"snr_gain": 1.51, "matched": True})
    assert "reads 1.51x" in text
    assert "on the brightness measurement" not in text
    # and a gain that is not worth saying says nothing at all
    assert tab._shape_note({"snr_gain": 1.02, "matched": True}) == ""


def test_the_snr_column_says_what_it_is_and_that_the_filter_does_not_touch_it(
        qapp, tmp_path):
    # The author compared this number with the matched filter on and off, got
    # 5.41 bit for bit, and read it as "the filter does nothing". It is the
    # DETECTION's signal-to-noise (the astrometry's own aperture), so it
    # cannot change: the column has to say what it is and what uses it, and
    # the notes have to give the pair the filter really moves.
    from nightscribe.core import astrometry
    tab, _host = _tab(qapp, tmp_path)
    sp = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=8.0, y=8.0,
                                    snr=5.41, mag=18.48, band="G")
    tab._result = {
        "status": "ok", "groups": [(0, 5)], "n_failed": 0,
        "stacks": [(np.zeros((16, 16), dtype=np.float32), None)],
        "boxes": [(0, 0, 16, 16)], "qs": [(8.0, 8.0)],
        "mids": [2461000.5], "points": [(sp, None, [])],
        "photometry": {"mag": 18.48, "err": 0.40, "band": "G",
                       "matched": True, "matched_requested": True,
                       "snr_ap": 5.8, "snr_mf": 8.7, "snr_gain": 1.51,
                       "n_comps": 8, "n_frames": 47, "source": "auto"},
    }
    tab._paint_run()
    tip = tab.tbl_points.item(0, 5).toolTip()
    assert "detection" in tip
    assert "does not change it" in tip
    notes = tab.txt_notes.toPlainText()
    assert "SNR 8.7 against 5.8 on the brightness measurement" in notes
