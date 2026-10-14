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
    # @return: the path as a string, a minimal float32 master. It says what
    #          it IS in IMAGETYP (a Dark by default), because the library is
    #          filled by classification now, not by a kind the observer picks
    #          (ADR-061 rev).
    from astropy.io import fits
    hdu = fits.PrimaryHDU(np.full((16, 16), 100.0, dtype=np.float32))
    hdu.header["IMAGETYP"] = "Dark"
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


def _patch_dir_picker(monkeypatch, folder):
    # @args: monkeypatch - pytest's, folder - what the folder picker returns
    # @return: None. Same idea as _patch_picker, for "Add a folder…".
    from nightscribe.gui import main_window as mw

    class _Fake:
        @staticmethod
        def getExistingDirectory(*_a, **_k):
            return folder

    monkeypatch.setattr(mw, "QFileDialog", _Fake)


def _names(dlg, index):
    # @args: dlg - settings dialog, index - page index in the rail
    # @return: objectName of every widget on that page
    from PySide6.QtWidgets import QWidget
    page = dlg.stk_pages.widget(index).widget()
    return {w.objectName() for w in page.findChildren(QWidget)
            if w.objectName()}


def test_the_calibration_library_lives_on_the_measurement_page(qapp):
    dlg = _dlg()
    found = None
    for i in range(dlg.stk_pages.count()):
        if "grp_calibration" in _names(dlg, i):
            found = i
    assert found is not None, "the master library must live on a page"
    names = _names(dlg, found)
    for w in ("lblH_masters", "btn_master_add", "btn_master_add_dir",
              "tbl_masters", "btn_master_remove", "lbl_master_status",
              "lblH_master_kind", "chk_calib_pseudo_flat",
              "spn_calib_temp_tol", "lblH_calib_tol"):
        assert w in names, f"{w} expected on the calibration page"
    dlg.deleteLater()


def test_there_are_three_kinds_and_no_combo(qapp, tmp_db, monkeypatch):
    # ADR-061 rev: a "dark of the flats" is a dark (the exposure tells them
    # apart), so there are three kinds and the observer does not classify
    # anything: the frame's own IMAGETYP does.
    from nightscribe.core import calibration
    assert calibration.KINDS == ("bias", "dark", "flat")
    dlg = _dlg()
    _prep(qapp, tmp_db, monkeypatch, dlg)
    assert not hasattr(dlg, "cmb_master_kind")
    dlg.deleteLater()


def test_a_batch_is_classified_and_a_light_is_refused(qapp, tmp_db,
                                                      monkeypatch, tmp_path):
    # One picker, mixed frames: each goes to its own kind by its header, and
    # a light is refused (pointing at the wrong folder cannot fill the
    # library with science frames).
    from nightscribe.core import calibration
    dark = _write_master(tmp_path / "dark.fits", IMAGETYP="Dark",
                         INSTRUME="TestCam", EXPTIME=120.0)
    flat = _write_master(tmp_path / "flat.fits", IMAGETYP="Flat",
                         INSTRUME="TestCam", FILTER="R", EXPTIME=2.0)
    light = _write_master(tmp_path / "light.fits", IMAGETYP="Light",
                          INSTRUME="TestCam")
    dlg = _dlg()
    win = _prep(qapp, tmp_db, monkeypatch, dlg)
    _patch_picker(monkeypatch, [dark, flat, light])
    win._settings_master_add(dlg)
    kinds = sorted(m.kind for m in calibration.list_masters(tmp_db))
    assert kinds == ["dark", "flat"]
    text = dlg.lbl_master_status.text()
    assert "Indexed 2 masters" in text and "1 dark" in text and "1 flat" in text
    assert "light.fits" in text
    dlg.deleteLater()


def test_a_folder_is_indexed_in_one_go(qapp, tmp_db, monkeypatch, tmp_path):
    # The usual way: a whole night of darks or flats in one folder. Its
    # subfolders are walked too.
    from nightscribe.core import calibration
    sub = tmp_path / "night"
    sub.mkdir()
    _write_master(sub / "d1.fits", INSTRUME="TestCam")
    _write_master(sub / "d2.fits", INSTRUME="TestCam")
    dlg = _dlg()
    win = _prep(qapp, tmp_db, monkeypatch, dlg)
    _patch_dir_picker(monkeypatch, str(tmp_path))
    win._settings_master_add_dir(dlg)
    assert dlg.tbl_masters.rowCount() == 2
    assert len(calibration.list_masters(tmp_db)) == 2
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
