############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: annotated FITS export (Track B, B10)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import os

from nightscribe.core.fits_annotate import write_annotated_fits, _inject_cards
from nightscribe.core.fits_io import FitsError


def _make_minimal_fits(path):
    # Writes a minimal valid FITS file (header + tiny data) for testing.
    # Primary HDU: SIMPLE = T, BITPIX = 8, NAXIS = 2, NAXIS1/2, END
    header = (
        "SIMPLE  =                    T                                                  "
        "BITPIX  =                    8                                                  "
        "NAXIS   =                    2                                                  "
        "NAXIS1  =                   16                                                  "
        "NAXIS2  =                   16                                                  "
        "END                                                                             "
    )
    # pad to 2880
    header_bytes = header.encode("ascii")
    header_bytes += b" " * (2880 - len(header_bytes))
    # data: 16x16 uint8
    data = b"\x00" * (16 * 16)
    path.write_bytes(header_bytes + data)
    return path


def test_inject_cards_inserts_before_end():
    header = (
        "SIMPLE  =                    T                                                  "
        "BITPIX  =                    8                                                  "
        "NAXIS   =                    2                                                  "
        "NAXIS1  =                   16                                                  "
        "NAXIS2  =                   16                                                  "
        "END                                                                             "
    )
    raw = header.encode("ascii")
    raw += b" " * (2880 - len(raw))
    new = _inject_cards(raw, [("NS_OBJ", "SN2026abc"),
                               ("NS_SN_X", 100)])
    text = new.decode("ascii")
    assert "NS_OBJ" in text
    assert "SN2026abc" in text
    assert "NS_SN_X" in text
    # END is still present after the injected cards
    assert "END" in text


def test_write_annotated_fits_copies_with_keywords(tmp_path):
    src = tmp_path / "input.fits"
    _make_minimal_fits(src)
    out = tmp_path / "annotated.fits"
    result = write_annotated_fits(src, out, sn_xy=(100, 100),
                                 scale=0.5, obj_name="SN2026abc",
                                 ra_deg=10.0, dec_deg=20.0,
                                 notes="Clear night")
    assert result is not None
    assert out.exists()
    # the output should differ from the input (annotation injected)
    assert out.read_bytes() != src.read_bytes()
    # the original is untouched
    src2 = tmp_path / "input2.fits"
    _make_minimal_fits(src2)
    assert src2.read_bytes() == src.read_bytes()


def test_write_annotated_fits_no_annotations(tmp_path):
    # no annotation fields → just a copy
    src = tmp_path / "plain.fits"
    _make_minimal_fits(src)
    out = tmp_path / "plain_copy.fits"
    result = write_annotated_fits(src, out)
    assert result is not None
    assert out.exists()
    # identical copy when no cards to inject
    assert out.read_bytes() == src.read_bytes()


def test_write_annotated_fits_creates_output_dir(tmp_path):
    src = tmp_path / "src2.fits"
    _make_minimal_fits(src)
    out = tmp_path / "subdir" / "annotated.fits"
    result = write_annotated_fits(src, out, obj_name="SNx")
    assert result is not None
    assert out.exists()
