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

"""Unit tests for core.fits_annotate.

Small hand-made FITS files (no network, no real observer data): the tests
check the AIJ ANNOTATE card and the NS_* tail read back through the
minimal reader, byte-for-byte preservation of the image and of the
original file, the multi-block header case, the accent round trip and
the real AIJ output as a smoke test.
"""

from pathlib import Path

import pytest

from nightscribe.core import fits_annotate, fits_io

_BLOCK = 2880


def _card(key, value=None, comment=""):
    # One 80-column FITS card with the "=" in column 9, the way AIJ
    # writes it.
    # @args: key - keyword (<= 8 chars), value - text with quotes for
    #        FITS strings (None for a key only, e.g. END), comment - text
    #        after " / "
    # @return: exactly 80 chars
    s = key.ljust(8) if value is None else f"{key.ljust(8)}= {value}"
    if comment:
        s += f" / {comment}"
    return s[:80].ljust(80)


def _make_fits(path, n_filler=0, naxis=(16, 16), with_ext=False, extra=()):
    # A small valid FITS: base cards, optional filler cards (to push the
    # header into a second 2880-byte block), optional extra cards, a
    # 16x16 uint8 image and, optionally, a dummy extension after it.
    # @args: path - destination, n_filler - filler cards, naxis - (w, h),
    #        with_ext - add an extension HDU, extra - additional cards
    # @return: the path written
    n1, n2 = naxis
    cards = [_card("SIMPLE", "T"), _card("BITPIX", "8"),
             _card("NAXIS", str(len(naxis))),
             _card("NAXIS1", str(n1)), _card("NAXIS2", str(n2))]
    cards += [_card(f"FILL{i:03d}", "1") for i in range(n_filler)]
    cards += list(extra)
    header = "".join(cards + [_card("END")]).encode("latin-1")
    header += b" " * ((_BLOCK - len(header) % _BLOCK) % _BLOCK)
    image = bytes(((i * 31 + j * 17) % 256)
                  for i in range(n1) for j in range(n2))
    raw = header + image
    if with_ext:
        ext = (_card("SIMPLE", "T") + _card("BITPIX", "8") +
               _card("NAXIS", "2") + _card("NAXIS1", "4") +
               _card("NAXIS2", "4") + _card("END"))
        ext = ext.encode("latin-1")
        ext += b" " * ((_BLOCK - len(ext) % _BLOCK) % _BLOCK)
        raw += ext + b"EXTDATA!"
    path.write_bytes(raw)
    return path


def test_full_annotation_reads_back(tmp_path):
    # The AIJ ANNOTATE card (value + label comment) and the NS_* tail
    # read back through the minimal reader as real values.
    src = tmp_path / "in.fits"
    _make_fits(src)
    before = src.read_bytes()
    out = tmp_path / "annotated.fits"
    res = fits_annotate.write_annotated_fits(
        src, out, sn_xy=(100.0, 100.0), scale=0.5, north_pa=17.0,
        obj_name="SN2026ann", ra_deg=10.0, dec_deg=20.0,
        notes="Clear night")
    assert res == out and out.is_file()
    header, _data = fits_io.read_fits(out)
    assert header["ANNOTATE"] == "100.00,100.00,30,1,0,1,1,orange"
    # the label lives in the card comment (the reader drops it) and the
    # "=" sits in column 9, the AIJ layout
    text = out.read_bytes().decode("latin-1")
    assert "ANNOTATE= '100.00,100.00,30,1,0,1,1,orange' / SN2026ann" in text
    assert float(header["NS_RA"]) == 10.0
    assert float(header["NS_DEC"]) == 20.0
    assert float(header["NS_SCALE"]) == 0.5
    assert float(header["NS_NORTH"]) == 17.0
    assert header["NS_NOTES"] == "Clear night"
    # the original is never modified
    assert src.read_bytes() == before


def test_image_and_extensions_kept_verbatim(tmp_path):
    # A multi-block header with 40 filler cards and a trailing extension:
    # everything from the image on survives byte for byte, and the filler
    # cards are kept.
    src = tmp_path / "big.fits"
    _make_fits(src, n_filler=40, with_ext=True)
    before = src.read_bytes()
    out = tmp_path / "big_annotated.fits"
    fits_annotate.write_annotated_fits(src, out, sn_xy=(5, 5),
                                       scale=1.0, obj_name="SNbig")
    out_raw = out.read_bytes()
    text = out_raw[:fits_annotate._split_header(out_raw)[1]].decode("latin-1")
    assert all(f"FILL{i:03d}" in text for i in range(40))
    assert "EXTDATA!" in out_raw.decode("latin-1")
    _, off_in = fits_annotate._split_header(before)
    _, off_out = fits_annotate._split_header(out_raw)
    assert out_raw[off_out:] == before[off_in:]
    header, _ = fits_io.read_fits(out)
    assert header["NAXIS2"] == 16


def test_no_annotations_verbatim_copy(tmp_path):
    # Nothing to annotate -> a byte-for-byte copy (the old contract).
    src = tmp_path / "plain.fits"
    _make_fits(src)
    out = tmp_path / "plain_copy.fits"
    res = fits_annotate.write_annotated_fits(src, out)
    assert res == out
    assert out.read_bytes() == src.read_bytes()


def test_creates_output_dir(tmp_path):
    src = tmp_path / "in.fits"
    _make_fits(src)
    out = tmp_path / "sub" / "dir" / "annotated.fits"
    res = fits_annotate.write_annotated_fits(src, out, obj_name="SNx")
    assert res == out and out.is_file()


def test_annotate_twice_keeps_one_set(tmp_path):
    # Idempotency: the cards we own are stripped before the new ones go
    # in, so a re-save leaves exactly one clean set, no duplicates.
    src = tmp_path / "in.fits"
    _make_fits(src)
    one = tmp_path / "once.fits"
    two = tmp_path / "twice.fits"
    kw = dict(sn_xy=(10, 20), scale=0.4, north_pa=5.5, obj_name="SNtwice",
              ra_deg=1.0, dec_deg=2.0, notes="first pass")
    fits_annotate.write_annotated_fits(src, one, **kw)
    fits_annotate.write_annotated_fits(one, two, **kw)
    cards = fits_annotate._split_header(two.read_bytes())[0]

    def count(key):
        return sum(1 for c in cards if c[:8].strip() == key)

    for key in ("ANNOTATE", "NS_RA", "NS_DEC", "NS_SCALE", "NS_NORTH",
                "NS_NOTES"):
        assert count(key) == 1, key
    header, _ = fits_io.read_fits(two)
    assert header["ANNOTATE"].startswith("10.00,20.00,")
    assert header["NS_NOTES"] == "first pass"


def test_foreign_annotate_is_replaced(tmp_path):
    # An AIJ-style ANNOTATE card left by the observer is replaced, not
    # accumulated: ANNOTATE is one of the cards we own on re-save.
    src = tmp_path / "aij.fits"
    _make_fits(src, extra=[
        _card("ANNOTATE", "'926.35,1052.57,30,1,0,1,1,orange'", "NGC 7326")])
    out = tmp_path / "aij_annotated.fits"
    fits_annotate.write_annotated_fits(src, out, sn_xy=(1.5, 2.5),
                                       obj_name="SNmine")
    cards = fits_annotate._split_header(out.read_bytes())[0]
    assert sum(1 for c in cards if c[:8].strip() == "ANNOTATE") == 1
    header, _ = fits_io.read_fits(out)
    assert header["ANNOTATE"].startswith("1.50,2.50,")
    assert "NGC 7326" not in out.read_bytes().decode("latin-1")


def test_accented_text_roundtrips(tmp_path):
    # The latin-1 rebuild must keep accented comments and notes byte for
    # byte (the reader decodes ascii, so we compare the raw header text).
    src = tmp_path / "accent.fits"
    _make_fits(src, extra=[
        _card("OBSNOTE", "'Noche clara, cielo limpio'")])
    out = tmp_path / "accent_annotated.fits"
    fits_annotate.write_annotated_fits(src, out, obj_name="SNacc",
                                       notes="Noche fría, seeing 1.5")
    raw = out.read_bytes()
    end = fits_annotate._split_header(raw)[1]
    text = raw[:end].decode("latin-1")
    assert "Noche clara, cielo limpio" in text
    assert "Noche fría, seeing 1.5" in text


def test_aij_fixture_round_trip(tmp_path):
    # The real AIJ output is the acceptance target: it must remain
    # readable and valid after we re-annotate it, with one clean ANNOTATE
    # card and the data bytes untouched.
    fixture = (Path(__file__).resolve().parent.parent / "fixtures" /
               "sample_annotated_image_from_aij.fits")
    if not fixture.exists():
        pytest.skip("AIJ sample image not present in tests/fixtures")
    before = fixture.read_bytes()
    out = tmp_path / "aij_annotated.fits"
    fits_annotate.write_annotated_fits(
        fixture, out, sn_xy=(876.74, 868.43), scale=0.8, north_pa=90.0,
        obj_name="SNtest", ra_deg=1.0, dec_deg=-1.0, notes="smoke test")
    header, data = fits_io.read_fits(out)
    assert header["ANNOTATE"].startswith("876.74,868.43,")
    assert data.shape == (2048, 2048)
    cards = fits_annotate._split_header(out.read_bytes())[0]
    assert sum(1 for c in cards if c[:8].strip() == "ANNOTATE") == 1
    _, off_in = fits_annotate._split_header(before)
    out_raw = out.read_bytes()
    _, off_out = fits_annotate._split_header(out_raw)
    assert out_raw[off_out:] == before[off_in:]
    assert fixture.read_bytes() == before


def _fixture(name):
    from pathlib import Path
    return Path(__file__).resolve().parent.parent / "fixtures" / name


def test_read_annotations_aij_fixture():
    # The real AIJ output carries 13 ANNOTATE cards (the header dict
    # collapses repeats; the reader walks the raw cards).
    anns = fits_annotate.read_annotations(_fixture(
        "sample_annotated_image_from_aij.fits"))
    assert len(anns) == 13
    first = anns[0]
    assert first["x"] == pytest.approx(876.74)
    assert first["y"] == pytest.approx(868.43)
    assert first["size"] == 30.0 and first["color"] == "orange"
    assert first["label"] == "NGC 7325"
    manual = anns[-1]
    assert manual["size"] == 5.0                       # AIJ's own radius
    assert manual["label"].startswith("Ejemplo")


def test_read_annotations_roundtrip(tmp_path):
    src = tmp_path / "src.fits"
    _make_fits(src)
    out = tmp_path / "out.fits"
    fits_annotate.write_annotated_fits(
        src, out, sn_xy=(10.5, 12.25), obj_name="SN test", notes="n")
    anns = fits_annotate.read_annotations(out)
    assert anns == [{"x": 10.5, "y": 12.25, "size": 30.0,
                     "color": "orange", "label": "SN test"}]


def test_read_annotations_plain_and_broken(tmp_path):
    src = tmp_path / "plain.fits"
    _make_fits(src)
    assert fits_annotate.read_annotations(src) == []   # no ANNOTATE cards
    bad = tmp_path / "bad.fits"
    _make_fits(bad, extra=[_card("ANNOTATE", "'not-a-position'")])
    assert fits_annotate.read_annotations(bad) == []   # junk is skipped
    assert fits_annotate.read_annotations(tmp_path / "missing.fits") == []
