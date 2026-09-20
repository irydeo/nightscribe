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

import colorsys
import io
import json
import logging
import re
import zipfile
import xml.etree.ElementTree as ET

import requests

from ..db import db

logger = logging.getLogger(__name__)

# Public Google Sheets workbook of Patrick Wils' HADS monitoring programme
# (one tab per year; the export carries the whole workbook in one request)
WORKBOOK_URL = ("https://docs.google.com/spreadsheets/d/"
                "1oGA2HaEHE8L6eX19ZoHqQQTu0LYV56HX3Srg7oCtOHo/"
                "export?format=xlsx")


def workbook(force=False):
    # The raw workbook, cached through db (12 h TTL, decision H-j).
    # @args: force - True bypasses the cache read (still stores the fresh copy)
    # @return: xlsx bytes, or None on network failure (Tonight never breaks)
    def fetch():
        r = requests.get(WORKBOOK_URL, timeout=60)
        r.raise_for_status()
        return (r.content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    try:
        body, _ = db.http_get("hads:workbook", "hads", fetch, force=force)
        return body
    except requests.RequestException as err:
        logger.warning("HADS sheet fetch failed: %s", err)
        return None

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


# ---------------- workbook → catalog mapping (decision H-i) ----------------

# Legend colors as found in the real workbook (verified 2026-09-11 against
# the live export): red FF0000 = period changes found, orange FF9900 =
# possible changes, purple 9900FF = multiperiodic, blue 0000FF on the
# COORDINATES = not yet observed. Cells explicitly black/gray (000000,
# 1F1F1F, 999999) carry no flag, so the hue mapping below only applies to
# saturated, non-dark colors.

_YEAR_TAB = re.compile(r"^\d{4}$")
_MONTH_COLS = "GHIJKLMNOPQR"          # G..R = Jan..Dec (position-based)


def _to_float(text):
    # @return: tolerant float (comma decimal, blanks) or None
    if text is None:
        return None
    try:
        return float(text.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _flag_hue(rgb):
    # @args: rgb - 6-hex font color or None
    # @return: the color hue in degrees (0-360) for saturated, non-dark
    #          colors; None for black/gray/unstyled cells (hue is
    #          meaningless there — rgb_to_hsv reports 0 = red for black!)
    if not rgb:
        return None
    try:
        r, g, b = (int(rgb[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.4 or v < 0.3:
        return None
    return h * 360


def _is_data_row(row):
    # A star row has a name AND coordinates; header rows (vvs/Ster/Star with
    # B == "RA"), legend rows and section titles ("Southern stars") don't.
    a = (row.get("A") or ("", None))[0]
    b = (row.get("B") or ("", None))[0]
    c = (row.get("C") or ("", None))[0]
    return bool(a and a.strip() and b and b.strip() and b.strip() != "RA"
                and c and c.strip())


def _parse_star_row(row):
    # One catalog row -> a star dict with the legend flags resolved.
    # @return: dict or None when the row is not a data row
    if not _is_data_row(row):
        return None
    name = row["A"][0].strip()
    out = {"sheet_name": name,
           "ra": row["B"][0].strip(), "dec": row["C"][0].strip(),
           "max": _to_float((row.get("D") or (None,))[0]),
           "min": _to_float((row.get("E") or (None,))[0]),
           "period_h": _to_float((row.get("F") or (None,))[0]),
           "priority": None, "observed": True, "multiperiodic_sheet": False}
    hue = _flag_hue(row["A"][1])
    if hue is not None:
        if hue < 15 or hue > 340:
            out["priority"] = "period_change"            # red: Priority!
        elif 15 <= hue <= 45:
            out["priority"] = "period_change_possible"   # orange: Priority!
        elif 260 <= hue <= 320:
            out["multiperiodic_sheet"] = True            # purple
        else:
            logger.debug("HADS: unknown name color #%s on %s",
                         row["A"][1], name)
    hue_b = _flag_hue(row["B"][1])
    if hue_b is not None and 200 <= hue_b <= 260:
        out["observed"] = False                          # blue coords
    return out


def _parse_workbook(data):
    # Maps the workbook onto catalog + coverage.
    # @args: data - raw xlsx bytes
    # @return: {"fetched_year": int, "stars": [...], "coverage": {year_str: {
    #          sheet_name: [covered months 1-12]}}}. The catalog comes from
    #          the LATEST year tab (freshest periods and colors); coverage
    #          is read from every year tab. Coverage years are strings so the
    #          shape survives the JSON cache round-trip unchanged
    sheets = _read_xlsx(data)
    years = sorted(int(n) for n in sheets if _YEAR_TAB.match(n))
    if not years:
        raise ValueError("no year tabs found in the workbook")
    stars = []
    for row in sheets[str(years[-1])]:
        star = _parse_star_row(row)
        if star:
            stars.append(star)
    coverage = {}
    for year in years:
        cov = {}
        for row in sheets[str(year)]:
            if not _is_data_row(row):
                continue
            name = row["A"][0].strip()
            cov[name] = [m for m, col in enumerate(_MONTH_COLS, 1)
                         if (row.get(col) or ("", None))[0]
                         and row[col][0].strip()]
        coverage[str(year)] = cov
    return {"fetched_year": years[-1], "stars": stars, "coverage": coverage}


def parsed(force=False):
    # The parsed workbook, JSON-cached so the ~1-2 s XLSX parse happens once
    # per TTL, not per Tonight run (two-level cache, decision H-j).
    # @args: force - True bypasses both cache reads (still stores fresh)
    # @return: the _parse_workbook dict, or None on network/parse failure
    cached = None if force else db.cache_get("hads:parsed")
    if cached:
        return json.loads(cached[0].decode("utf-8"))
    data = workbook(force=force)
    if data is None:
        return None
    try:
        result = _parse_workbook(data)
    except (ValueError, KeyError, zipfile.BadZipFile) as err:
        logger.warning("HADS sheet parse failed: %s", err)
        return None                              # never cache a failure
    db.cache_put("hads:parsed", "hads", json.dumps(result).encode("utf-8"))
    return result
