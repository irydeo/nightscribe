############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the visit's frame previews (ADR-044 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The preview list of the editor's left panel (asked for 2026-10-06: the
column had almost nothing in it and an observer wants to flick through the
night's frames and act on what is wrong).

What is pinned: one row per frame with its own preview, the marks that make
a bad frame visible before opening it (unreadable, not registered), the
"only problems" filter, the click that opens the frame, the menu that takes
frames out of the visit or moves them aside, and the worker that reads them
sampled (never the whole frame).
"""

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def _frame(path, value=1000.0, size=64):
    # @args: path - where to write, value - the sky level, size - the side
    # @return: the path as a string
    from astropy.io import fits
    data = np.full((size, size), value, dtype=np.float32)
    data[8:24, 8:24] += 500.0
    hdu = fits.PrimaryHDU(data)
    hdu.header["INSTRUME"] = "TestCam"
    hdu.header["FILTER"] = "Clear"
    hdu.header["EXPTIME"] = 1.0
    hdu.writeto(str(path), overwrite=True)
    return str(path)


def test_one_row_per_frame_with_its_preview_and_its_numbers(qapp, tmp_path):
    from nightscribe.gui.widgets.frame_previews import FramePreviews
    from nightscribe.gui.workers import FrameThumbWorker
    paths = [_frame(tmp_path / f"f{i}.fits", 900.0 + 100 * i)
             for i in range(3)]
    widget = FramePreviews()
    widget.resize(300, 600)
    widget.show()
    widget.set_frames(paths)
    qapp.processEvents()
    assert widget.count() == 3
    assert widget.item(0).text().startswith("Frame 1")
    assert "f0.fits" in widget.item(0).text()
    # the previews arrive from the worker, one frame at a time
    worker = FrameThumbWorker(paths)
    landed = []
    worker.sampled.connect(
        lambda i, s, f: (landed.append(i),
                         widget.set_fact(i, s, f)))
    worker.run()                        # in this thread: it is a plain loop
    assert landed == [0, 1, 2]
    assert not widget.item(0).icon().isNull()
    # the tooltip carries the frame's own numbers (the comparison the
    # preview cannot make by itself)
    tip = widget.item(0).toolTip()
    assert "f0.fits" in tip and "64 × 64 px" in tip
    assert "sky 900 ADU" in tip and "Clear" in tip and "1 s" in tip
    # and a frame without a solution says so in the tooltip (but is NOT a
    # "problem": a whole visit can be unsolved before Solve the visit runs)
    assert "No astrometric solution" in tip
    assert widget.problems() == 0
    widget.deleteLater()


def test_a_frame_that_cannot_be_read_is_marked_and_counted(qapp, tmp_path):
    # The author's own visit ended with a 0-byte frame: it is exactly what
    # this list is for. It comes back marked, never as a crash.
    from nightscribe.gui.widgets.frame_previews import FramePreviews
    from nightscribe.gui.workers import FrameThumbWorker
    good = _frame(tmp_path / "good.fits")
    broken = tmp_path / "half.fits"
    broken.write_bytes(b"")
    widget = FramePreviews()
    widget.set_frames([good, str(broken)])
    worker = FrameThumbWorker([good, str(broken)])
    worker.sampled.connect(widget.set_fact)
    worker.run()
    assert "unreadable" in widget.item(1).text()
    assert widget.problems() == 1
    assert "Could not be read" in widget.item(1).toolTip()
    widget.deleteLater()


def test_only_problems_is_a_view_not_a_delete(qapp, tmp_path):
    from nightscribe.gui.widgets.frame_previews import FramePreviews
    paths = [_frame(tmp_path / f"f{i}.fits") for i in range(3)]
    widget = FramePreviews()
    widget.set_frames(paths)
    widget.set_fact(1, None, {"path": paths[1], "failed_register": True})
    assert widget.count() == 3
    assert widget.problems() == 1
    widget.set_problems_only(True)
    assert [widget.item(i).isHidden() for i in range(3)] == [True, False, True]
    assert "not registered" in widget.item(1).text()
    widget.set_problems_only(False)
    assert not any(widget.item(i).isHidden() for i in range(3))
    # the frames are all still there: the filter is a view
    assert widget.paths() == paths
    widget.deleteLater()


def test_a_click_opens_the_frame_and_the_menu_acts_on_the_selection(
        qapp, tmp_path):
    from nightscribe.gui.widgets.frame_previews import FramePreviews
    paths = [_frame(tmp_path / f"f{i}.fits") for i in range(3)]
    widget = FramePreviews()
    widget.resize(300, 600)
    widget.show()
    widget.set_frames(paths)
    seen = {}
    widget.picked.connect(lambda i: seen.setdefault("picked", i))
    widget.remove_requested.connect(
        lambda ps: seen.setdefault("removed", list(ps)))
    widget.discard_requested.connect(
        lambda ps: seen.setdefault("discarded", list(ps)))
    # a click on a row opens that frame (the editor's own frame navigator
    # does the loading)
    widget.itemClicked.emit(widget.item(2))
    widget.picked.emit(2)
    assert seen["picked"] == 2
    # the menu works on the SELECTION: one frame, or a batch
    widget.item(0).setSelected(True)
    widget.item(2).setSelected(True)
    assert widget.selected_paths() == [paths[0], paths[2]]
    menu = widget._build_menu(widget.item(0))
    actions = [a.text() for a in menu.actions() if a.text()]
    assert any("out of the visit" in a for a in actions)
    assert any("discarded" in a for a in actions)
    for action in menu.actions():
        if "out of the visit" in action.text():
            action.trigger()
        elif "discarded" in action.text():
            action.trigger()
    assert seen["removed"] == [paths[0], paths[2]]
    assert seen["discarded"] == [paths[0], paths[2]]
    widget.deleteLater()


def test_the_editor_shows_the_visit_s_frames_and_follows_the_navigator(
        qapp, tmp_path):
    # The list belongs to the visit: it appears with the hook, the frame on
    # stage is the one highlighted, and stepping with the navigator moves
    # the highlight (and the other way round).
    from nightscribe.gui.ufe_dialog import UfeDialog
    paths = [_frame(tmp_path / f"f{i}.fits") for i in range(4)]
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    d.set_series_hook(lambda scope="visit": {"pid": 1, "session_id": 2,
                                             "paths": paths, "kind": "neo",
                                             "context": {}, "scope": "visit"})
    qapp.processEvents()
    assert d.series_pane.isVisibleTo(d)
    assert d.frames_list.count() == 4
    assert d.lbl_frames_count.text().startswith("4 frames")
    d.state.load(paths[0])
    d._sync_frame_nav()
    assert d.frames_list.currentRow() == 0
    d._goto_frame(2)
    assert d.frames_list.currentRow() == 2
    # the worker is asked to stop when the workbench goes away
    d.shutdown()
    assert d._thumb_worker is None
    d.deleteLater()


def test_the_host_hooks_take_frames_out_and_move_them_aside(qapp, tmp_path,
                                                            monkeypatch):
    # The panel never touches the registry: it asks the host (ADR-045). The
    # two actions are the safe ones: unlink (the file stays) and move into
    # discarded/ (nothing is deleted).
    import nightscribe.gui.main_window as mw
    from nightscribe.config import config
    from nightscribe.core import followup as fu
    from nightscribe.core import project
    orig = config.is_configured
    config.is_configured = lambda: False
    window = mw.MainWindow()
    window._now_timer.stop()
    try:
        p = project.create(mw.db, "neo", "2025 UR",
                           {"ra_deg": 10.0, "dec_deg": 20.0})
        sid = fu.create_session(mw.db, p["id"], obs_date="2026-10-06")
        paths = [_frame(tmp_path / f"v{i}.fits") for i in range(3)]
        for path in paths:
            project.add_file(mw.db, p["id"], path, "fits", session_id=sid)
        # taking them out of the visit leaves the FILES alone
        words = window._ufe_frames_remove(p["id"], sid, paths[:2])
        assert "2 frames" in words
        left = [f["path"] for f in project.files_for_session(mw.db, sid)]
        assert left == [paths[2]]
        assert all(os.path.exists(x) for x in paths)
        # moving one aside really moves it, and the registry follows it
        words = window._ufe_frames_discard(p["id"], sid, [paths[2]])
        assert "discarded" in words
        assert not os.path.exists(paths[2])
        storage = project.storage_dir(project.get(mw.db, p["id"]))
        moved = os.path.join(storage, "descartados", os.path.basename(paths[2]))
        assert os.path.exists(moved)
        rows = [f for f in project.files_for_session(mw.db, sid)]
        assert rows == [] or rows[0]["path"] == moved
    finally:
        config.is_configured = orig
        window.close()


def test_the_run_marks_the_frames_it_could_not_register(qapp, tmp_path):
    # The astrometry run knows which frames it left out (its own report); the
    # previews say so before anybody opens the frame, which is the whole
    # point of the list.
    from nightscribe.gui.ufe_dialog import UfeDialog
    paths = [_frame(tmp_path / f"f{i}.fits") for i in range(3)]
    d = UfeDialog()
    d.set_series_hook(lambda scope="visit": {"pid": 1, "session_id": 2,
                                             "paths": paths, "kind": "neo",
                                             "context": {}, "scope": "visit"})
    qapp.processEvents()
    d.mark_unregistered_frames([paths[1]])
    assert d.frames_list.problems() == 1
    assert "not registered" in d.frames_list.item(1).text()
    assert d.lbl_frames_count.text().endswith("1 with problems")
    d.shutdown()
    d.deleteLater()


def test_the_preview_takes_the_column_and_the_caption_rides_on_it(
        qapp, tmp_path):
    # Asked for 2026-10-06: the image as big as the column allows and the
    # caption ON the image (small, in the object's own hue), so the row costs
    # the picture and nothing else. The row is the preview, and the preview
    # follows the column's width.
    from nightscribe.gui import theme
    from nightscribe.gui.widgets.frame_previews import FLAG_RED, FramePreviews
    paths = [_frame(tmp_path / f"f{i}.fits") for i in range(2)]
    widget = FramePreviews()
    widget.resize(320, 600)
    widget.show()
    widget.set_frames(paths)
    qapp.processEvents()
    thumb = widget._thumb
    assert thumb > 240                      # ~the whole column, not 140
    assert widget.iconSize().width() == thumb
    row = widget.item(0).sizeHint().height()
    assert row == thumb + 12                # the image plus the list's gap
    # the caption is the item's text (the delegate paints it over the image)
    assert "f0.fits" in widget.item(0).text()
    # and a wider column means a bigger preview
    widget.resize(400, 600)
    qapp.processEvents()
    assert widget._thumb > thumb
    # the delegate paints: no text beside the image, and a red border for a
    # frame with something wrong
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QStyleOptionViewItem
    widget.set_fact(1, None, {"path": paths[1], "failed_register": True})
    assert widget.item(1).data(258) is True          # the flag role
    pix = QPixmap(thumb, thumb)
    painter = QPainter(pix)
    try:
        widget.itemDelegate().paint(painter, QStyleOptionViewItem(),
                                    widget.model().index(1, 0))
    finally:
        painter.end()
    # the caption wears the object's hue (the app's accent with no project)
    # and the warning keeps the alert red: red means a problem, nothing else
    assert widget._hue == theme.C_ACCENT
    widget.set_accent("#4484ef")
    assert widget._hue == "#4484ef"
    assert FLAG_RED == theme.C_EVENT
    # and the caption is split where the warning starts, so the delegate can
    # paint the two halves in two colours
    delegate = widget.itemDelegate()
    head, flag = delegate._split("Frame 3 · f2.fits ⚠ not registered")
    assert head == "Frame 3 · f2.fits"
    assert flag == "⚠ not registered"
    assert delegate._split("Frame 3 · f2.fits")[1] == ""
    widget.deleteLater()


def test_the_list_fills_the_panel_s_height(qapp, tmp_path):
    # Reported 2026-10-06: the list was 264 px of a 640 px panel because the
    # panel's trailing spacer was Expanding and took the rest. It is Fixed
    # now: the previews get every pixel the labels do not need.
    from nightscribe.gui.ufe_dialog import UfeDialog
    paths = [_frame(tmp_path / f"f{i}.fits") for i in range(3)]
    d = UfeDialog()
    d.resize(1360, 900)
    d.show()
    d.set_series_hook(lambda scope="visit": {"pid": 1, "session_id": 2,
                                             "paths": paths, "kind": "neo",
                                             "context": {}, "scope": "visit"})
    qapp.processEvents()
    panel = d.visit_panel
    spare = panel.height() - sum(
        panel.layout().itemAt(i).geometry().height()
        for i in range(panel.layout().count()))
    assert d.frames_list.height() >= panel.height() - 130   # it owns the room
    assert abs(spare) <= 40                                 # no dead strip
    d.shutdown()
    d.deleteLater()
