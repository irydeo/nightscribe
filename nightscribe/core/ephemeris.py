############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Ephemeris exporters for planetariums (ADR-021)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import csv
import datetime
import logging
from pathlib import Path

from . import coords

logger = logging.getLogger(__name__)

# Ephemeris generation (via JPL Horizons, cached through db) and export to
# formats importable by TheSkyX, Cartes du Ciel and any CSV reader. The
# native TheSkyX/CdC formats are validated against the user's installations
# during phase 5; the CSV base always works.


def generate(name, site, lat=None, lon=None, start=None, stop=None,
             step="30m"):
    # Queries Horizons for the ephemeris and enriches each row with
    # alt/az computed locally (pure math, no extra network call).
    # @args: name - Horizons target designation, site - MPC code,
    #        lat/lon - for alt/az (defaults from config), start/stop - dates,
    #        step - Horizons step string (e.g. '30m', '1h')
    # @return: list of dicts with time, ra, dec, ra_deg, dec_deg, r, delta,
    #          alt, az; empty on failure
    from .sources import horizons
    from ..config import config
    lat = lat if lat is not None else config.get("lat")
    lon = lon if lon is not None else config.get("lon")
    rows = horizons.ephemeris(name, center=site, start=start, stop=stop,
                              step=step)
    if not rows:
        return []
    out = []
    for r in rows:
        try:
            ra_deg = coords.ra_hms_to_deg(r["ra"])
            dec_deg = coords.dec_dms_to_deg(r["dec"])
        except (ValueError, KeyError):
            continue
        # alt/az at the ephemeris time
        try:
            t = datetime.datetime.strptime(r["time"], "%Y-%b-%d %H:%M")
            t = t.replace(tzinfo=datetime.timezone.utc)
            jd = coords.jd_from_datetime(t)
            alt, az = coords.altaz(ra_deg, dec_deg, lat,
                                   coords.lst_degrees(jd, lon))
        except ValueError:
            alt, az = None, None
        out.append({"time": r["time"], "ra": r["ra"], "dec": r["dec"],
                     "ra_deg": round(ra_deg, 6),
                     "dec_deg": round(dec_deg, 6),
                     "r": r.get("r"), "delta": r.get("delta"),
                     "alt": round(alt, 1) if alt is not None else None,
                     "az": round(az, 1) if az is not None else None})
    return out


def export_csv(rows, out, obj_name=""):
    # CSV ephemeris: time, RA, Dec, RA(deg), Dec(deg), r, delta, alt, az.
    # @args: rows - list from generate(), out - path, obj_name - header
    # @return: the output path
    headers = ["time", "ra", "dec", "ra_deg", "dec_deg", "r", "delta",
               "alt", "az"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)
    logger.info("CSV ephemeris written to %s", out)
    return str(out)


def export_skyx(rows, out, obj_name=""):
    # TheSkyX text ephemeris: a simple table that can be imported as a Sky
    # Database or pasted into the console. Validate against your TheSkyX
    # version (the import path depends on the build).
    # @args: rows - list from generate(), out - path, obj_name - label
    # @return: the output path
    lines = [f"# NightScribe ephemeris for {obj_name or 'target'}"]
    lines.append("# Format: time(UTC) RA(deg) Dec(deg) mag alt(deg) az(deg)")
    for r in rows:
        mag = ""  # Horizons observer ephemeris does not include magnitude
        lines.append(
            f"{r['time']}\t{r['ra_deg']:.6f}\t{r['dec_deg']:+.6f}\t"
            f"{mag}\t{r['alt'] or ''}\t{r['az'] or ''}")
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("TheSkyX ephemeris written to %s", out)
    return str(out)


def export_cdc(rows, out, obj_name=""):
    # Cartes du Ciel ephemeris: a text table importable via File > Ephemeris
    # or pasted into the object search. Validate against your CdC version.
    # @args: rows - list from generate(), out - path, obj_name - label
    # @return: the output path
    lines = [f"# NightScribe ephemeris for {obj_name or 'target'}"]
    lines.append("# Cartes du Ciel import format (tab-separated)")
    lines.append("# time(UTC)\tRA\tDec\talt\taz")
    for r in rows:
        lines.append(f"{r['time']}\t{r['ra']}\t{r['dec']}\t"
                     f"{r['alt'] or ''}\t{r['az'] or ''}")
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("CdC ephemeris written to %s", out)
    return str(out)


def export(rows, out, fmt="csv", obj_name=""):
    # Dispatcher: picks the exporter for the given planetarium format.
    # @args: rows - list from generate(), out - path, fmt - "csv"|"skyx"|"cdc",
    #        obj_name - target name for headers
    # @return: output path
    out = Path(out)
    if fmt == "skyx":
        return export_skyx(rows, out.with_suffix(".txt"), obj_name)
    if fmt == "cdc":
        return export_cdc(rows, out.with_suffix(".txt"), obj_name)
    return export_csv(rows, out.with_suffix(".csv"), obj_name)
