############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the project files window (ADR-019, UX v3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/project_files_dialog.py: the table layout,
the per-row menus (plates get the editor first, everyone gets system /
folder / copy path), the double-click and right-click routes emitting
the open signals, the empty state, and the OS helpers with
QDesktopServices and the clipboard stubbed. No network, no db.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture
def dlg(qapp):
    from nightscribe.gui.project_files_dialog import ProjectFilesDialog
    d = ProjectFilesDialog()
    d.show()
    yield d
    d.deleteLater()


def _mk(tmp_path, name, body=b"x" * 2048):
    # one stand-in file on disk (the Size column stats it)
    p = tmp_path / name
    p.write_bytes(body)
    return str(p)


def _menu_row_texts(dlg, row):
    # the row's tool button and the enabled texts of its menu
    from PySide6.QtWidgets import QToolButton
    btn = dlg.tbl.cellWidget(row, 4)
    assert isinstance(btn, QToolButton)
    texts = [a.text() for a in btn.menu().actions() if not a.isSeparator()]
    return [t for t in texts if t], btn


def test_empty_state_message(dlg):
    dlg.set_files([])
    assert dlg.lbl_status.isVisible()
    assert dlg.lbl_status.text()
    assert dlg.tbl.rowCount() == 0
    assert dlg.project_id is None


def test_set_project_title_and_id(dlg):
    dlg.set_project({"id": 7, "object_name": "SN 2026 zji"})
    assert dlg.project_id == 7
    assert "SN 2026 zji" in dlg.windowTitle()
    dlg.set_project(None)
    assert dlg.project_id is None
    assert "SN 2026 zji" not in dlg.windowTitle()


def test_table_layout(dlg):
    # kind, name, date, size + the row menu column
    assert dlg.tbl.columnCount() == 5
    assert dlg.tbl.horizontalHeaderItem(0).text()
    assert dlg.tbl.verticalHeader().isHidden()


def test_rows_show_registered_order(dlg, tmp_path):
    files = [
        {"id": 1, "project_id": 1, "path": _mk(tmp_path, "plate.fits"),
         "kind": "fits", "created": 1700000000},
        {"id": 2, "project_id": 1, "path": _mk(tmp_path, "report.csv"),
         "kind": "report", "created": 1700600000},
    ]
    dlg.set_files(files)
    assert dlg.tbl.rowCount() == 2
    assert dlg.tbl.item(0, 1).text() == "plate.fits"
    assert dlg.tbl.item(1, 1).text() == "report.csv"
    assert dlg.lbl_status.isHidden()


def test_size_column_reads_the_disk(dlg, tmp_path):
    big = tmp_path / "big.fits"
    big.write_bytes(b"0" * (2 * 1024 * 1024))
    dlg.set_files([
        {"id": 1, "project_id": 1, "path": str(big),
         "kind": "fits", "created": 1700000000},
    ])
    assert dlg.tbl.item(0, 3).text() == "2 MB"


def test_size_column_empty_for_missing_file(dlg):
    dlg.set_files([
        {"id": 1, "project_id": 1, "path": "/no/such/file.fits",
         "kind": "fits", "created": 1700000000},
    ])
    assert dlg.tbl.item(0, 3).text() == ""


def test_plate_row_menu_has_editor_first(dlg, tmp_path):
    dlg.set_files([
        {"id": 1, "project_id": 1, "path": _mk(tmp_path, "plate.fits"),
         "kind": "fits", "created": 1700000000},
        {"id": 2, "project_id": 1, "path": _mk(tmp_path, "annotated.fits"),
         "kind": "image", "created": 1700000001},
    ])
    fits = dlg.tr("Open in the FITS editor")
    for row in (0, 1):
        texts, _ = _menu_row_texts(dlg, row)
        assert texts[0] == fits          # the editor leads for plates
    # the "image" kind is an annotated copy: the editor loads it too


def test_report_row_menu_has_no_editor(dlg, tmp_path):
    dlg.set_files([
        {"id": 1, "project_id": 1, "path": _mk(tmp_path, "report.csv"),
         "kind": "report", "created": 1700000000},
    ])
    texts, _ = _menu_row_texts(dlg, 0)
    assert dlg.tr("Open in the FITS editor") not in texts
    for expected in ("Open with the system", "Show in folder",
                     "Copy path"):
        assert dlg.tr(expected) in texts


def test_menu_action_emits_the_ufe_signal(dlg, tmp_path):
    seen = []
    path = _mk(tmp_path, "plate.fits")
    dlg.set_files([
        {"id": 1, "project_id": 1, "path": path,
         "kind": "fits", "created": 1700000000},
    ])
    dlg.sig_open_ufe.connect(lambda p: seen.append(("ufe", p)))
    dlg.sig_open_os.connect(lambda p: seen.append(("os", p)))
    btn = dlg.tbl.cellWidget(0, 4)
    action = [a for a in btn.menu().actions()
              if a.text() == dlg.tr("Open in the FITS editor")][0]
    action.trigger()
    assert seen == [("ufe", path)]


def test_menu_os_action_emits_the_os_signal(dlg, tmp_path):
    seen = []
    path = _mk(tmp_path, "report.csv")
    dlg.set_files([
        {"id": 1, "project_id": 1, "path": path,
         "kind": "report", "created": 1700000000},
    ])
    dlg.sig_open_os.connect(lambda p: seen.append(("os", p)))
    btn = dlg.tbl.cellWidget(0, 4)
    action = [a for a in btn.menu().actions()
              if a.text() == dlg.tr("Open with the system")][0]
    action.trigger()
    assert seen == [("os", path)]


def test_double_click_routes_by_kind(dlg, tmp_path):
    # the table's itemDoubleClicked is what the user's double-click
    # delivers (Qt input -> QAbstractItemView -> signal); we fire it
    # the same way test_tonight_table.py does
    seen = []
    plate = _mk(tmp_path, "plate.fits")
    csv = _mk(tmp_path, "report.csv")
    dlg.set_files([
        {"id": 1, "project_id": 1, "path": plate, "kind": "fits",
         "created": 1700000000},
        {"id": 2, "project_id": 1, "path": csv, "kind": "report",
         "created": 1700000001},
    ])
    dlg.sig_open_ufe.connect(lambda p: seen.append(("ufe", p)))
    dlg.sig_open_os.connect(lambda p: seen.append(("os", p)))
    for row in (0, 1):
        dlg.tbl.itemDoubleClicked.emit(dlg.tbl.item(row, 1))
    assert ("ufe", plate) in seen        # the plate went to the editor
    assert ("os", csv) in seen           # the csv went to the system
    assert len(seen) == 2


def test_right_click_builds_the_row_menu(dlg, tmp_path, monkeypatch):
    # the context route finds the row under the cursor; we stub the
    # blocking menu.exec on the built instance (Shiboken does not honour
    # class-level shadowing, so we spy on the dialog's menu builder)
    executed = []
    made = []
    orig = dlg._row_menu

    def spy(f, parent=None):
        menu = orig(f, parent)
        made.append(menu)
        menu.exec = lambda *a, **k: executed.append(a)
        return menu

    monkeypatch.setattr(dlg, "_row_menu", spy)
    plate = _mk(tmp_path, "plate.fits")
    dlg.set_files([
        {"id": 1, "project_id": 1, "path": plate, "kind": "fits",
         "created": 1700000000},
    ])
    # customContextMenuRequested hands over a view-local position
    pos = dlg.tbl.visualRect(dlg.tbl.model().index(0, 0)).center()
    dlg._on_context(pos)
    assert made and executed


def test_show_in_folder_via_desktop_services(dlg, tmp_path, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    seen = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        staticmethod(lambda u: seen.append(u.toString())))
    f = tmp_path / "plate.fits"
    f.write_bytes(b"0" * 16)
    dlg.show_in_folder(str(f))
    assert seen and str(tmp_path) in seen[0]


def test_copy_path_via_clipboard(dlg, monkeypatch):
    from PySide6.QtWidgets import QApplication
    holder = {"text": None}

    class _Clp:
        def setText(self, t):
            holder["text"] = t

    monkeypatch.setattr(QApplication, "clipboard",
                        staticmethod(lambda: _Clp()))
    dlg.copy_path("/tmp/plate.fits")
    assert holder["text"] == "/tmp/plate.fits"


def test_refresh_survives_project_switch(dlg, tmp_path):
    # the dialog is a persistent single instance: repopulating for
    # another project swaps the rows without rebuilding the window
    files = [
        {"id": 1, "project_id": 1, "path": _mk(tmp_path, "a.fits"),
         "kind": "fits", "created": 1700000000},
    ]
    dlg.set_project({"id": 1, "object_name": "A"})
    dlg.set_files(files)
    assert dlg.tbl.rowCount() == 1
    dlg.set_project({"id": 2, "object_name": "B"})
    dlg.set_files([])
    assert dlg.tbl.rowCount() == 0
    assert dlg.project_id == 2
