############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: HADS sheet XLSX reader (subplan H0.1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import io
import zipfile

import pytest

from nightscribe.core.sources.hads_sheet import _read_xlsx

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PNS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _cell(ref, value, style=None, kind=None):
    # @return: one <c> element: shared-string, inline-string or numeric
    s = f' s="{style}"' if style is not None else ""
    if kind == "s":
        return f'<c r="{ref}"{s} t="s"><v>{value}</v></c>'
    if kind == "inlineStr":
        return f'<c r="{ref}"{s} t="inlineStr"><is><t>{value}</t></is></c>'
    return f'<c r="{ref}"{s}><v>{value}</v></c>'


def _make_xlsx(sheets, shared=(), font_colors=()):
    # Builds a minimal but valid .xlsx workbook in memory (no binary fixture).
    # @args: sheets - [(name, [[cell_xml, ...], ...])], shared - strings,
    #        font_colors - [None | "FF0000", ...] one per font
    # @return: bytes of the zipped workbook
    wb_sheets = "".join(
        f'<sheet name="{name}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
        for i, (name, _rows) in enumerate(sheets))
    wb = (f'<?xml version="1.0"?><workbook xmlns="{_NS}" '
          f'xmlns:r="{_RNS}"><sheets>{wb_sheets}</sheets></workbook>')
    rels = "".join(
        f'<Relationship Id="rId{i + 1}" Type="x" Target="worksheets/sheet{i + 1}.xml"/>'
        for i in range(len(sheets)))
    rels = f'<?xml version="1.0"?><Relationships xmlns="{_PNS}">{rels}</Relationships>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/workbook.xml", wb)
        zf.writestr("xl/_rels/workbook.xml.rels", rels)
        if shared:
            sis = "".join(f'<si><t>{s}</t></si>' for s in shared)
            zf.writestr("xl/sharedStrings.xml",
                        f'<?xml version="1.0"?><sst xmlns="{_NS}">{sis}</sst>')
        if font_colors:
            fonts = "".join(
                f'<font>{"<color rgb=\"FF" + c + "\"/>" if c else ""}</font>'
                for c in font_colors)
            xfs = "".join(f'<xf fontId="{i}"/>'
                          for i in range(len(font_colors)))
            zf.writestr(
                "xl/styles.xml",
                f'<?xml version="1.0"?><styleSheet xmlns="{_NS}">'
                f'<fonts>{fonts}</fonts><cellXfs>{xfs}</cellXfs></styleSheet>')
        for i, (_name, rows) in enumerate(sheets):
            body = "".join(
                f'<row r="{r + 1}">{"".join(cells)}</row>'
                for r, cells in enumerate(rows))
            zf.writestr(
                f"xl/worksheets/sheet{i + 1}.xml",
                f'<?xml version="1.0"?><worksheet xmlns="{_NS}">'
                f'<sheetData>{body}</sheetData></worksheet>')
    return buf.getvalue()


def test_two_sheets_keep_names_and_order():
    data = _make_xlsx(
        [("2026", [[_cell("A1", "0", kind="s"), _cell("B1", "10.4")]]),
         ("2025", [[_cell("A1", "1", kind="s")]])],
        shared=("GP And", "CY Aqr"))
    out = _read_xlsx(data)
    assert list(out) == ["2026", "2025"]
    assert out["2026"][0]["A"] == ("GP And", None)
    assert out["2025"][0]["A"] == ("CY Aqr", None)


def test_font_color_is_read_per_cell():
    data = _make_xlsx(
        [("2026", [[_cell("A1", "0", style=1, kind="s"),
                    _cell("B1", "10.4")]])],
        shared=("GP And",), font_colors=(None, "FF0000"))
    row = _read_xlsx(data)["2026"][0]
    assert row["A"] == ("GP And", "FF0000")   # red name: period change!
    assert row["B"] == ("10.4", None)


def test_inline_strings_and_unstyled_numbers():
    data = _make_xlsx(
        [("2026", [[_cell("A1", "GP And", kind="inlineStr"),
                    _cell("F1", "1.89")]])])
    row = _read_xlsx(data)["2026"][0]
    assert row["A"] == ("GP And", None)
    assert row["F"] == ("1.89", None)


def test_missing_shared_strings_is_tolerated():
    data = _make_xlsx([("2026", [[_cell("A1", "just text", kind="inlineStr")]])])
    assert _read_xlsx(data)["2026"][0]["A"] == ("just text", None)


def test_empty_cells_are_skipped():
    data = _make_xlsx(
        [("2026", [[_cell("A1", "x", kind="inlineStr"),
                    '<c r="B1"/>', _cell("C1", "1.5")]])])
    row = _read_xlsx(data)["2026"][0]
    assert set(row) == {"A", "C"}


def test_garbage_bytes_raise_value_error():
    with pytest.raises(ValueError):
        _read_xlsx(b"this is not a zip file")
