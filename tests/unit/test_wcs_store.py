############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: solved WCS stored in the FITS (ADR-051 rev.)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""core.wcs_store: a solved WCS is written into the plate, atomically.

Small hand-made FITS files (the test_fits_annotate helper): the new WCS
cards replace any stale astrometry, the image data survives byte for
byte, and a write problem is reported without losing the plate.
"""

import numpy as np
import pytest

from nightscribe.core import fits_io, wcs_store
from test_fits_annotate import _make_fits

_CARDS = {"CRVAL1": 123.456, "CRVAL2": -12.5, "CRPIX1": 128.0,
          "CRPIX2": 128.0, "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
          "CD1_1": -0.0003, "CD1_2": 0.0, "CD2_1": 0.0, "CD2_2": 0.0003}


def test_write_solved_wcs_keeps_the_image_and_sets_wcs(tmp_path):
    src = _make_fits(tmp_path / "plate.fits")
    before, data_before = fits_io.read_fits(src)
    assert wcs_store.write_solved_wcs(src, _CARDS)
    after, data_after = fits_io.read_fits(src)
    assert after["CRVAL1"] == pytest.approx(123.456)
    assert after["CTYPE1"] == "RA---TAN"
    # the pixels are untouched
    assert data_after.shape == data_before.shape
    assert np.array_equal(data_after, data_before)
    # no leftovers next to the file
    temps = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert temps == []


def test_write_solved_wcs_replaces_stale_astrometry(tmp_path):
    # An old CD solution goes away when the new one lands: flavours never
    # mix and no duplicate card is left behind.
    src = _make_fits(tmp_path / "old.fits", extra=(
        "CRVAL1  = 10.0".ljust(80), "CTYPE1  = 'RA---TAN'".ljust(80),
        "CRPIX1  = 1.0".ljust(80)))
    assert wcs_store.write_solved_wcs(src, _CARDS)
    raw = src.read_bytes()
    text = raw[:2880 * 4].decode("latin-1")
    assert text.count("CRVAL1") == 1        # one, the new one
    assert "10.0" not in text
    assert "123.456" in text


def test_write_solved_wcs_copies_extensions(tmp_path):
    src = _make_fits(tmp_path / "ext.fits", with_ext=True)
    raw_before = src.read_bytes()
    marker = raw_before.rindex(b"EXTDATA!")
    assert wcs_store.write_solved_wcs(src, _CARDS)
    raw_after = src.read_bytes()
    assert raw_after.endswith(b"EXTDATA!")            # extension verbatim
    assert raw_after[raw_after.rindex(b"EXTDATA!"):] == \
        raw_before[marker:]


def test_persist_solution_respects_the_setting(tmp_path, monkeypatch):
    from nightscribe.config import config
    src = _make_fits(tmp_path / "plate.fits")
    monkeypatch.setitem(config._data, "solve_save", False)
    done, err = wcs_store.persist_solution(src, _CARDS)
    assert done is False and err == ""
    header, _ = fits_io.read_fits(src)
    assert "CRVAL1" not in header              # nothing written
    monkeypatch.setitem(config._data, "solve_save", True)
    done, err = wcs_store.persist_solution(src, _CARDS)
    assert done is True and err == ""


def test_persist_solution_reports_a_write_problem(tmp_path, monkeypatch):
    from nightscribe.config import config
    monkeypatch.setitem(config._data, "solve_save", True)
    # a directory cannot be read as a FITS: the error is reported, never
    # raised (the in-memory solution survives)
    done, err = wcs_store.persist_solution(tmp_path, _CARDS)
    assert done is False and err


def test_write_solved_wcs_empty_cards_is_a_noop(tmp_path):
    src = _make_fits(tmp_path / "plate.fits")
    assert wcs_store.write_solved_wcs(src, {}) is False
