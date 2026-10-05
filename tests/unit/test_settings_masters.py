############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the master library in Settings (ADR-061)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The master library, where the observer can reach it.

The editor's Calibration tab resolves a recipe against the library and
names the master it uses for each piece; before this, nothing in the GUI
could put a master IN, so that tab could only ever say "missing". These
tests drive the Settings side offscreen: the tab and its widgets exist,
the library is listed, a batch of files is indexed with the chosen kind
(and the file is linked, never copied), the header fills what it can, a
file already in the library is not indexed twice, an unreadable file does
not lose the rest of the batch, and removing takes the index entry only.
"""

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _write_master(path, **cards):
    # @args: path - where to write, cards - extra FITS header cards
    # @return: the path as a string, a minimal float32 master
    from astropy.io import fits
    hdu = fits.PrimaryHDU(np.full((16, 16), 100.0, dtype=np.float32))
    for key, value in cards.items():
        hdu.header[key] = value
    hdu.writeto(str(path), overwrite=True)
    return str(path)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def _dlg():
    # @return: the settings dialog as on_open_settings loads it
    from nightscribe.gui.main_window import _load_ui
    return _load_ui("settings_dialog")


def _win():
    # @return: MainWindow's methods without building the window. The
    #          library code only needs self.tr() and the module's db, and
    #          building a full MainWindow here would drag the whole app
    #          (network, workers) into a layout test.
    from nightscribe.gui.main_window import MainWindow
    return MainWindow.__new__(MainWindow)


def _prep(qapp, tmp_db, monkeypatch, dlg):
    # @args: tmp_db - the temp database, monkeypatch - pytest's, dlg - the
    #        settings dialog
    # @return: the host object with the library wired, ready to drive
    from nightscribe.gui import main_window as mw
    monkeypatch.setattr(mw, "db", tmp_db)
    win = _win()
    win._settings_masters_init(dlg)
    return win


def _patch_picker(monkeypatch, files):
    # @args: monkeypatch - pytest's, files - what the picker returns
    # @return: None. The file dialog is a modal window: the batch it hands
    #          back is what matters here, so the picker is replaced.
    from nightscribe.gui import main_window as mw

    class _Fake:
        @staticmethod
        def getOpenFileNames(*_a, **_k):
            return (list(files), "")

    monkeypatch.setattr(mw, "QFileDialog", _Fake)


def _names(dlg, index):
    # @args: dlg - settings dialog, index - tab index
    # @return: objectName of every widget on that page
    from PySide6.QtWidgets import QWidget
    page = dlg.tabWidget.widget(index)
    return {w.objectName() for w in page.findChildren(QWidget)
            if w.objectName()}


def test_the_calibration_tab_holds_the_library(qapp):
    dlg = _dlg()
    tabs = [dlg.tabWidget.tabText(i) for i in range(dlg.tabWidget.count())]
    assert "Calibration" in tabs
    names = _names(dlg, tabs.index("Calibration"))
    for w in ("lblH_masters", "cmb_master_kind", "btn_master_add",
              "tbl_masters", "btn_master_remove", "lbl_master_status",
              "lblH_master_kind"):
        assert w in names, f"{w} expected on the Calibration tab"
    dlg.deleteLater()


def test_the_four_kinds_are_offered(qapp, tmp_db, monkeypatch):
    # The four kinds are four different arithmetics, so the observer picks
    # one when indexing; the combo carries the core's own keys as data.
    from nightscribe.core import calibration
    dlg = _dlg()
    _prep(qapp, tmp_db, monkeypatch, dlg)
    keys = [dlg.cmb_master_kind.itemData(i)
            for i in range(dlg.cmb_master_kind.count())]
    assert keys == list(calibration.KINDS)
    dlg.deleteLater()


def test_an_empty_library_says_so(qapp, tmp_db, monkeypatch):
    dlg = _dlg()
    _prep(qapp, tmp_db, monkeypatch, dlg)
    assert dlg.tbl_masters.rowCount() == 0
    assert dlg.btn_master_remove.isEnabled() is False
    dlg.deleteLater()


def test_adding_indexes_and_links_the_files(qapp, tmp_db, monkeypatch,
                                            tmp_path):
    # The files are INDEXED, not copied: the library knows where they are
    # and what makes them valid. What the header carries (camera, gain,
    # temperature, exposure, filter) is read from the file.
    from nightscribe.core import calibration
    dark = _write_master(tmp_path / "dark120.fits", INSTRUME="TestCam",
                         GAIN=2.0, **{"CCD-TEMP": -10.0}, EXPTIME=120.0)
    dlg = _dlg()
    win = _prep(qapp, tmp_db, monkeypatch, dlg)
    dlg.cmb_master_kind.setCurrentIndex(dlg.cmb_master_kind.findData("dark"))
    _patch_picker(monkeypatch, [dark])
    win._settings_master_add(dlg)
    assert dlg.tbl_masters.rowCount() == 1
    row = [dlg.tbl_masters.item(0, c).text()
           for c in range(dlg.tbl_masters.columnCount())]
    assert row[0] == "dark120.fits"
    assert row[1] == "Dark"
    assert row[2] == "TestCam"
    assert row[4] == "-10"
    assert row[5] == "120"
    # the file is where it was, untouched
    assert Path(dark).exists()
    assert calibration.list_masters(tmp_db)[0].path == dark
    assert "Indexed 1 masters" in dlg.lbl_master_status.text()
    dlg.deleteLater()


def test_the_same_file_is_not_indexed_twice(qapp, tmp_db, monkeypatch,
                                            tmp_path):
    dark = _write_master(tmp_path / "dark.fits", INSTRUME="TestCam")
    dlg = _dlg()
    win = _prep(qapp, tmp_db, monkeypatch, dlg)
    _patch_picker(monkeypatch, [dark])
    win._settings_master_add(dlg)
    win._settings_master_add(dlg)
    assert dlg.tbl_masters.rowCount() == 1
    assert "already in the library" in dlg.lbl_master_status.text()
    dlg.deleteLater()


def test_an_unreadable_file_does_not_lose_the_batch(qapp, tmp_db,
                                                    monkeypatch, tmp_path):
    good = _write_master(tmp_path / "dark.fits")
    bad = tmp_path / "not-a-fits.fits"
    bad.write_text("this is not a FITS file", encoding="utf-8")
    dlg = _dlg()
    win = _prep(qapp, tmp_db, monkeypatch, dlg)
    _patch_picker(monkeypatch, [str(bad), good])
    win._settings_master_add(dlg)
    assert dlg.tbl_masters.rowCount() == 1
    assert "not-a-fits.fits" in dlg.lbl_master_status.text()
    dlg.deleteLater()


def test_removing_takes_the_index_entry_only(qapp, tmp_db, monkeypatch,
                                             tmp_path):
    from nightscribe.core import calibration
    dark = _write_master(tmp_path / "dark.fits")
    dlg = _dlg()
    win = _prep(qapp, tmp_db, monkeypatch, dlg)
    calibration.add_master(tmp_db, dark, {"kind": "dark"})
    win._settings_masters_refresh(dlg)
    assert dlg.tbl_masters.rowCount() == 1
    # nothing selected: the button cannot act (U5)
    assert dlg.btn_master_remove.isEnabled() is False
    dlg.tbl_masters.selectRow(0)
    assert dlg.btn_master_remove.isEnabled() is True
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    win._settings_master_remove(dlg)
    assert dlg.tbl_masters.rowCount() == 0
    assert calibration.list_masters(tmp_db) == []
    assert Path(dark).exists()          # the file is the observer's data
    assert "Removed dark.fits" in dlg.lbl_master_status.text()
    dlg.deleteLater()


def test_a_missing_number_is_blank_not_zero():
    # A blank cell says "the file did not say"; a zero would be matched
    # against a light as if it were a real measurement.
    from nightscribe.gui.main_window import _master_num
    assert _master_num(None) == ""
    assert _master_num(-10.0) == "-10"
