############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometry report export module (ADR-035)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Photometry report export (V-i): the project's photometry points as a
plain CSV or an AAVSO Extended File Format text, with heliocentric Julian
dates computed in-app (variables.jd_to_hjd). Quick-look points are
"indicative" (T6) and only leave the app on explicit request.
"""

import logging
from pathlib import Path

from . import followup, variables

logger = logging.getLogger(__name__)

CSV_HEADER = ("name", "hjd", "mag", "err", "filter", "comp_stars",
              "observer", "notes")

# Every column a report can carry, in the order a reader expects them.
# The Photometrica tool of our group lets the observer tick which ones go
# into the file, and the reason is good: one colleague wants the curve,
# another wants the quality controls (FWHM, sky, aperture), and a third
# wants to reproduce the measurement. A fixed set of columns is always
# either too much or too little.
#
# Each entry is (key, label_es, label_en). The values come from the point
# dict plus the two magnitudes that are computed for the report (HJD and
# the detrended one when the series carried it).
REPORT_COLUMNS = (
    ("name", "Nombre", "Name"),
    ("hjd", "HJD", "HJD"),
    ("mjd", "MJD (UT)", "MJD (UT)"),
    ("mag", "Magnitud", "Magnitude"),
    ("err", "Error", "Error"),
    ("err_internal", "Error (fotones)", "Error (photons)"),
    ("mag_raw", "Mag. instrumental", "Instrumental mag"),
    ("filter", "Banda", "Band"),
    ("fwhm", "FWHM (px)", "FWHM (px)"),
    ("airmass", "Masa de aire", "Airmass"),
    ("n_comps", "Comparsas usadas", "Comps used"),
    ("zp", "Punto cero", "Zero point"),
    ("flags", "Marcas", "Flags"),
    ("source", "Origen", "Source"),
    ("comp_stars", "Estrellas de comparación", "Comparison stars"),
    ("observer", "Observador", "Observer"),
    ("notes", "Notas", "Notes"),
)

# What a report carries when nobody chooses (the historical set, so an
# existing script that reads our CSV keeps working).
DEFAULT_COLUMNS = ("name", "hjd", "mag", "err", "filter", "comp_stars",
                   "observer", "notes")


def column_labels(lang="es"):
    # @args: lang - "es"|"en"
    # @return: [(key, label)] in the canonical order
    idx = 1 if (lang or "es") != "en" else 2
    return [(c[0], c[idx]) for c in REPORT_COLUMNS]


def _cell(point, key, comps, observer, hjd):
    # The value of one column for one point, already formatted for a
    # spreadsheet: a missing value is an empty cell, never a zero (a zero
    # magnitude is a real, extremely bright star).
    # @return: the string for that cell
    if key == "name":
        return point.get("_name") or ""
    if key == "hjd":
        return f"{hjd:.5f}" if hjd is not None else ""
    if key == "mjd":
        mjd = point.get("mjd")
        return f"{mjd:.5f}" if mjd is not None else ""
    if key == "mag":
        mag = point.get("mag")
        return f"{mag:.3f}" if mag is not None else ""
    if key == "err":
        err = point.get("err")
        return f"{err:.3f}" if err is not None else ""
    if key == "err_internal":
        err = point.get("err_internal")
        return f"{err:.4f}" if err is not None else ""
    if key == "mag_raw":
        raw = point.get("mag_raw")
        return f"{raw:.3f}" if raw is not None else ""
    if key == "filter":
        return point.get("filter") or ""
    if key == "fwhm":
        fwhm = point.get("fwhm")
        return f"{fwhm:.2f}" if fwhm is not None else ""
    if key == "airmass":
        air = point.get("airmass")
        return f"{air:.3f}" if air is not None else ""
    if key == "n_comps":
        n = point.get("n_comps")
        return str(n) if n is not None else ""
    if key == "zp":
        zp = point.get("zp")
        return f"{zp:.3f}" if zp is not None else ""
    if key == "flags":
        flags = point.get("flags") or []
        return " ".join(str(f) for f in flags)
    if key == "source":
        return point.get("source") or ""
    if key == "comp_stars":
        return comps
    if key == "observer":
        return observer or ""
    if key == "notes":
        return point.get("_notes") or ""
    return ""


def collect_points(db, project_id, include_quicklook=False):
    # The exportable points of the project, MJD-ordered.
    # @args: include_quicklook - quick-look points are indicative (T6) and
    #        only export on explicit request
    # @return: list of point dicts
    pts = followup.list_points(db, project_id)
    return [p for p in pts
            if include_quicklook or (p.get("source") or "") != "quicklook"]


def hjd_of(point, ra_deg, dec_deg):
    # @return: the point's HJD (MJD -> JD -> HJD), or None when the instant
    #          or the coordinates are missing
    if point.get("mjd") is None or ra_deg is None or dec_deg is None:
        return None
    return variables.jd_to_hjd(point["mjd"] + variables.MJD0, ra_deg,
                               dec_deg)


def export_csv(points, out, name, ra_deg=None, dec_deg=None, observer="",
               comp_stars=None, columns=None):
    # One row per point, dot decimal, comma-separated.
    #
    # The columns are the observer's choice (REPORT_COLUMNS); the default
    # set is the one the group has always exchanged, so an existing script
    # that reads our CSV keeps working.
    # The header is the CANONICAL key of each column, never a translated
    # label: this file is a documented interchange format and a colleague's
    # reader must not break because the app was in Spanish. The friendly
    # labels belong to the dialog that chooses the columns.
    # @args: points - the point dicts, out - path, name - the object's
    #        name (the "name" column), ra_deg/dec_deg - for the HJD,
    #        observer - free text, comp_stars - the comparison sequence,
    #        columns - the keys to write (None: DEFAULT_COLUMNS)
    # @return: Path written
    keys = list(columns or DEFAULT_COLUMNS)
    known = {c[0] for c in REPORT_COLUMNS}
    unknown = [k for k in keys if k not in known]
    if unknown:
        logger.warning("unknown report columns ignored: %s", unknown)
        keys = [k for k in keys if k in known]
    comps = "+".join(comp_stars or [])
    # a comment block says how the file was made, so a reader three months
    # later (or a colleague) is not guessing
    lines = [f"# name: {name}",
             "# generated by NightScribe — dates are HJD (heliocentric)",
             ",".join(keys)]
    for p in points:
        hjd = hjd_of(p, ra_deg, dec_deg)
        row = dict(p)
        row["_name"] = name
        cells = [_cell(row, k, comps, observer, hjd) for k in keys]
        lines.append(",".join(cell.replace(",", ";") for cell in cells))
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("photometry CSV written: %s (%d points, %d columns)",
                out, len(points), len(keys))
    return Path(out)


# ---------------- AAVSO Extended File Format ----------------

EFF_FIELDS = ("NAME,DATE,MAG,MERR,FILT,TRANS,MTYPE,CNAME,CMAG,KNAME,KMAG,"
              "AMASS,GROUP,CHART,NOTES")


def export_eff(points, out, name, ra_deg=None, dec_deg=None, obscode="",
               comp=None, check=None):
    # AAVSO Extended File Format (the WebObs/FotoDif interchange): header
    # lines starting with '#', then one line per point. Dates are HJD
    # (#DATE=HJD). Points without a full HJD are skipped — EFF has no
    # empty-date concept.
    # @args: obscode - the AAVSO observer code (config aavso_code),
    #        comp - optional {"name", "mag"} of the first comparison star
    #        (ADR-042: from the project's saved sequence; CNAME/CMAG),
    #        check - optional {"name", "mag"} of the check star (KNAME/KMAG)
    # @return: Path written
    def _fmt(star):
        # @return: (name, mag) EFF cells for a sequence star, "na" without it
        if not star:
            return "na", "na"
        mag = star.get("mag")
        return (star.get("name") or "na",
                f"{mag:.3f}" if mag is not None else "na")

    cname, cmag = _fmt(comp)
    kname, kmag = _fmt(check)
    lines = ["#TYPE=EXTENDED",
             f"#OBSCODE={obscode or 'UNKNOWN'}",
             "#SOFTWARE=NightScribe",
             "#DELIM=,",
             "#DATE=HJD",
             "#OBSTYPE=CCD",
             EFF_FIELDS]
    n = 0
    for p in points:
        hjd = hjd_of(p, ra_deg, dec_deg)
        if hjd is None:
            continue
        merr = f"{p['err']:.3f}" if p.get("err") is not None else "0.000"
        filt = p.get("filter") or "Clear"
        # TRANS is WebObs' YES/NO transformation flag (anything else can be
        # rejected on import): NightScribe never transforms to the standard
        # system, so the honest value is "NO"
        lines.append(f"{name.upper()},{hjd:.5f},{p['mag']:.3f},{merr},"
                     f"{filt},NO,STD,{cname},{cmag},{kname},{kmag},"
                     "na,na,na,")
        n += 1
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("photometry EFF written: %s (%d points)", out, n)
    return Path(out)


def export_report(points, out, fmt="csv", **meta):
    # Single entry point for the GUI.
    # @args: fmt - "csv" | "eff", meta - export_csv/export_eff keywords
    if fmt == "eff":
        return export_eff(points, out, **meta)
    return export_csv(points, out, **meta)
