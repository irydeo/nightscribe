############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - HADS sheet source (P. Wils' monitoring workbook)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Patrick Wils' HADS monitoring workbook as a live source (ADR-034).

Source of truth: a public Google Sheets workbook (one tab per year) that
Wils updates daily. We download the whole workbook as .xlsx — the only
export that carries the *font colors* encoding the programme legend:
red/orange star names flag found/possible period changes (priority!),
blue coordinates mark stars not yet observed, purple names are
multiperiodic. The CSV bundled in assets/ stays as the offline fallback
and the alias source; the merge lives in core/hads.py.

The .xlsx reader below is stdlib-only (zipfile + xml.etree): openpyxl
would do it too, but a runtime dependency just to read a handful of
font colors is not worth it (decision H-j).
"""

import io
import logging
import zipfile
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# SpreadsheetML namespaces, fully qualified for ElementTree lookups
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PNS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _read_xlsx(data):
    # Minimal .xlsx grid reader: values plus per-cell font colors.
    # @args: data - raw bytes of an .xlsx workbook
    # @return: dict {sheet_name: [row, ...]} where each row maps
    #          column letter -> (text, font_rgb); font_rgb is the 6-hex
    #          font color ("FF0000") or None when the cell is unstyled.
    #          Raises ValueError when the bytes are not a valid workbook
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        shared = _shared_strings(zf)
        fonts, xfs = _styles(zf)
        out = {}
        for name, member in _sheet_list(zf):
            out[name] = _read_sheet(zf, member, shared, fonts, xfs)
        return out
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as err:
        raise ValueError(f"not a valid xlsx workbook: {err}") from err


def _shared_strings(zf):
    # @return: the shared strings table ([] when the file has none)
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(_NS + "t"))
            for si in root.findall(_NS + "si")]


def _styles(zf):
    # @return: (fonts, xfs) — fonts: 6-hex color per font index (None when
    #          theme/auto); xfs: fontId per cellXfs style index
    if "xl/styles.xml" not in zf.namelist():
        return [], []
    root = ET.fromstring(zf.read("xl/styles.xml"))
    fonts = []
    fonts_el = root.find(_NS + "fonts")
    if fonts_el is not None:
        for font in fonts_el.findall(_NS + "font"):
            color = font.find(_NS + "color")
            rgb = (color.get("rgb") or "")[-6:].upper() \
                if color is not None else ""
            fonts.append(rgb or None)
    xfs = []
    xfs_el = root.find(_NS + "cellXfs")
    if xfs_el is not None:
        for xf in xfs_el.findall(_NS + "xf"):
            try:
                xfs.append(int(xf.get("fontId", 0)))
            except ValueError:
                xfs.append(0)
    return fonts, xfs


def _sheet_list(zf):
    # @return: [(sheet_name, zip member path)] in workbook order
    rels = {}
    rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rel_root.findall(_PNS + "Relationship"):
        target = rel.get("Target", "").lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        rels[rel.get("Id")] = target
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    sheets_el = wb.find(_NS + "sheets")
    out = []
    for sheet in sheets_el.findall(_NS + "sheet"):
        rid = sheet.get(_RNS + "id")
        if rid in rels:
            out.append((sheet.get("name"), rels[rid]))
    return out


def _read_sheet(zf, member, shared, fonts, xfs):
    # @return: list of rows; each row maps column letter -> (text, font_rgb)
    root = ET.fromstring(zf.read(member))
    rows = []
    for row in root.iter(_NS + "row"):
        cells = {}
        for c in row.findall(_NS + "c"):
            ref = c.get("r")
            if not ref:
                continue
            col = "".join(ch for ch in ref if ch.isalpha())
            text = _cell_text(c, shared)
            if text is None:
                continue
            cells[col] = (text, _cell_color(c, fonts, xfs))
        if cells:
            rows.append(cells)
    return rows


def _cell_text(c, shared):
    # @return: the cell text (shared/inline/number) or None when empty
    kind = c.get("t")
    if kind == "inlineStr":
        node = c.find(_NS + "is/" + _NS + "t")
        return node.text if node is not None else None
    v = c.find(_NS + "v")
    if v is None or v.text is None:
        return None
    if kind == "s":
        try:
            return shared[int(v.text)]
        except (ValueError, IndexError):
            return None
    return v.text


def _cell_color(c, fonts, xfs):
    # @return: the 6-hex font color of the cell, or None when unstyled
    s = c.get("s")
    if s is None or not xfs or not fonts:
        return None
    try:
        font_id = xfs[int(s)]
    except (ValueError, IndexError):
        return None
    return fonts[font_id] if font_id < len(fonts) else None
