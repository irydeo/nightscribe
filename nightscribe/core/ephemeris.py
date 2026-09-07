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
import math
from pathlib import Path

from . import coords, ephem_minor

logger = logging.getLogger(__name__)

# Ephemeris generation (via JPL Horizons, cached through db) and export to
# formats importable by TheSkyX, Cartes du Ciel and any CSV reader. The
# native TheSkyX/CdC formats are validated against the user's installations
# during phase 5; the CSV base always works. For unconfirmed objects that
# Horizons does not know, the preliminary NEOfixer (Find_Orb) orbit is
# propagated locally with our two-body Kepler engine (ADR-021).

_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def generate(name, site, lat=None, lon=None, start=None, stop=None,
             step="30m"):
    # Queries Horizons for the ephemeris and enriches each row with
    # alt/az computed locally (pure math, no extra network call). When
    # Horizons does not know the object (unconfirmed NEOCP), falls back
    # to the preliminary NEOfixer orbit propagated locally; those rows
    # are flagged "preliminary".
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
        rows = _preliminary_rows(name, start, stop, step)
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
        row = {"time": r["time"], "ra": r["ra"], "dec": r["dec"],
               "ra_deg": round(ra_deg, 6),
               "dec_deg": round(dec_deg, 6),
               "r": r.get("r"), "delta": r.get("delta"),
               "alt": round(alt, 1) if alt is not None else None,
               "az": round(az, 1) if az is not None else None}
        if r.get("preliminary"):
            row["preliminary"] = True
        out.append(row)
    return out


def _preliminary_rows(name, start, stop, step):
    # Local two-body ephemeris from a preliminary NEOfixer orbit — the
    # only route for unconfirmed NEOCP objects (Horizons has no orbit).
    # @args: name - packed designation, start/stop - 'YYYY-MM-DD' or None,
    #        step - '30m'/'1h' style
    # @return: list of rows shaped like horizons.parse_ephemeris output,
    #          each flagged preliminary; empty if NEOfixer has no orbit
    from .sources import neofixer
    orb = neofixer.orbit(name)
    if not orb or not orb.get("elements"):
        return []
    elements = orb["elements"]
    today = datetime.datetime.now(datetime.timezone.utc)
    t0 = _parse_date(start) or today
    t1 = _parse_date(stop) or (today + datetime.timedelta(days=1))
    jd0 = coords.jd_from_datetime(t0)
    jd1 = coords.jd_from_datetime(t1)
    step_days = _parse_step_days(step)
    rows = []
    jd = jd0
    while jd <= jd1 + 1e-9:
        pos = ephem_minor.kepler_ra_dec(elements, jd)
        if pos:
            ra_deg, dec_deg, r, delta = pos
            rows.append({"time": _fmt_time(jd),
                         "ra": coords.ra_deg_to_hms(ra_deg),
                         "dec": coords.dec_deg_to_dms(dec_deg),
                         "r": round(r, 6), "delta": round(delta, 6),
                         "preliminary": True})
        jd += step_days
    return rows


def _parse_date(s):
    # @args: s - 'YYYY-MM-DD' string or None
    # @return: aware UTC datetime or None
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").replace(
            tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def _parse_step_days(step):
    # @args: step - '30m' | '1h' | '2h' | '1 d' style string
    # @return: step in days (float)
    s = (step or "30m").strip().lower().replace(" ", "")
    try:
        if s.endswith("m"):
            return float(s[:-1]) / 1440.0
        if s.endswith("h"):
            return float(s[:-1]) / 24.0
        return float(s.rstrip("d"))
    except ValueError:
        return 30.0 / 1440.0


def _fmt_time(jd):
    # Horizons-style timestamp: "2026-Aug-24 22:30" (locale-independent).
    # @args: jd - Julian date
    # @return: string
    t = coords.datetime_from_jd(jd)
    return f"{t.year}-{_MONTHS_EN[t.month - 1]}-{t.day:02d} " \
           f"{t.hour:02d}:{t.minute:02d}"


def _preliminary_banner(rows):
    # @args: rows - list from generate()
    # @return: banner string if the ephemeris comes from a preliminary orbit
    if rows and rows[0].get("preliminary"):
        return ("PRELIMINARY ORBIT (NEOfixer/Find_Orb) — object not yet "
                "confirmed by the MPC / Órbita PRELIMINAR — objeto aún no "
                "confirmado por el MPC")
    return None


def export_csv(rows, out, obj_name=""):
    # CSV ephemeris: time, RA, Dec, RA(deg), Dec(deg), r, delta, alt, az.
    # @args: rows - list from generate(), out - path, obj_name - header
    # @return: the output path
    headers = ["time", "ra", "dec", "ra_deg", "dec_deg", "r", "delta",
               "alt", "az"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        banner = _preliminary_banner(rows)
        if banner:
            f.write(f"# {banner}\n")
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
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
    banner = _preliminary_banner(rows)
    if banner:
        lines.append(f"# {banner}")
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
    banner = _preliminary_banner(rows)
    if banner:
        lines.append(f"# {banner}")
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


# ---------------- fresh position for moving targets (goto) ---------------

def _floor_30min(dt):
    # @args: dt - aware UTC datetime
    # @return: dt floored to the nearest half-hour boundary (cache key stays
    #          stable for repeated gotos within 30 min)
    return dt.replace(second=0, microsecond=0,
                      minute=(dt.minute // 30) * 30)


def _iso(when):
    # @args: when - datetime
    # @return: "YYYY-MM-DD HH:MM:SS" UTC string
    return when.strftime("%Y-%m-%d %H:%M:%S")


def _row_jd(row):
    # @args: row - Horizons-style row with "time" "YYYY-Mon-DD HH:MM"
    # @return: Julian date (float) or None on parse error
    try:
        t = datetime.datetime.strptime(row["time"], "%Y-%b-%d %H:%M")
        return coords.jd_from_datetime(
            t.replace(tzinfo=datetime.timezone.utc))
    except (ValueError, KeyError):
        return None


def _motion(j0, ra0, dec0, j1, ra1, dec1):
    # Apparent angular rate (arcsec/min) and position angle (deg, east of
    # north) of the motion between two positions. RA is expected already
    # unwrapped across the 0h/24h seam.
    # @return: (rate_arcsec_min, pa_deg)
    dt_min = (j1 - j0) * 1440.0
    if dt_min <= 0:
        return 0.0, 0.0
    dra = ra1 - ra0
    ddec = dec1 - dec0
    dec_mid = math.radians((dec0 + dec1) / 2.0)
    rate = math.hypot(dra * math.cos(dec_mid), ddec) * 3600.0 / dt_min
    pa = math.degrees(math.atan2(dra * math.cos(dec_mid), ddec)) % 360.0
    return rate, pa


def _interpolate(rows, jd):
    # Linear interpolation of (ra_deg, dec_deg) to jd between the two
    # bracketing rows (RA unwrapped at the 0h/24h seam); the apparent rate
    # and PA come from the same pair.
    # @args: rows - Horizons rows (time/ra/dec), jd - target instant
    # @return: {ra_deg, dec_deg, rate_arcsec_min, pa_deg} or None
    pts = []
    for r in rows:
        j = _row_jd(r)
        if j is None:
            continue
        try:
            ra = coords.ra_hms_to_deg(r["ra"])
            dec = coords.dec_dms_to_deg(r["dec"])
        except (ValueError, KeyError):
            continue
        pts.append((j, ra, dec))
    if not pts:
        return None
    pts.sort()
    n = len(pts)
    if n == 1:
        return {"ra_deg": pts[0][1] % 360, "dec_deg": pts[0][2],
                "rate_arcsec_min": 0.0, "pa_deg": 0.0}
    if jd <= pts[0][0]:
        i, frac = 0, 0.0
    elif jd >= pts[-1][0]:
        i, frac = n - 2, 1.0
    else:
        i = next(k for k in range(n - 1)
                 if pts[k][0] <= jd <= pts[k + 1][0])
        span = pts[i + 1][0] - pts[i][0]
        frac = (jd - pts[i][0]) / span if span else 0.0
    j0, ra0, dec0 = pts[i]
    j1, ra1, dec1 = pts[i + 1]
    dra = ra1 - ra0
    if dra > 180:
        dra -= 360
    elif dra < -180:
        dra += 360
    ra = (ra0 + frac * dra) % 360
    dec = dec0 + frac * (dec1 - dec0)
    rate, pa = _motion(j0, ra0, dec0, j1, ra0 + dra, dec1)
    return {"ra_deg": ra, "dec_deg": dec,
            "rate_arcsec_min": rate, "pa_deg": pa}


def _kepler_at(elements, jd):
    # Local two-body propagation: position at jd plus a numerical rate from
    # a +1 h delta. RA is unwrapped before differencing so the rate does not
    # spike across the 0h/24h seam.
    # @return: {ra_deg, dec_deg, rate_arcsec_min, pa_deg} or None
    p0 = ephem_minor.kepler_ra_dec(elements, jd)
    if not p0:
        return None
    ra0, dec0 = p0[0], p0[1]
    dh = 1.0 / 24.0
    p1 = ephem_minor.kepler_ra_dec(elements, jd + dh)
    if not p1:
        return {"ra_deg": ra0 % 360, "dec_deg": dec0,
                "rate_arcsec_min": 0.0, "pa_deg": 0.0}
    ra1, dec1 = p1[0], p1[1]
    dra = ra1 - ra0
    if dra > 180:
        dra -= 360
    elif dra < -180:
        dra += 360
    rate, pa = _motion(jd, ra0, dec0, jd + dh, ra0 + dra, dec1)
    return {"ra_deg": ra0 % 360, "dec_deg": dec0,
            "rate_arcsec_min": rate, "pa_deg": pa}


def _horizons_fine_rows(name, site, when):
    # Horizons ephemeris at a 2-min step over a ±2 h window around `when`,
    # rounded to a 30-min boundary so the cache key is reusable.
    # @return: list of Horizons rows (see horizons.parse_ephemeris)
    from .sources import horizons
    start = _floor_30min(when - datetime.timedelta(hours=2))
    stop = start + datetime.timedelta(hours=4)
    return horizons.ephemeris(
        name, center=site,
        start=start.strftime("%Y-%m-%d %H:%M"),
        stop=stop.strftime("%Y-%m-%d %H:%M"),
        step="2m")


def position_at(name, site, when=None, fallback_target=None):
    # Geocentric J2000 RA/Dec of a minor body at a given instant, resolved
    # fresh so a goto never points at a stale snapshot of a moving target.
    # Horizons is queried at a fine step and the two rows bracketing `when`
    # are linearly interpolated. When Horizons knows nothing of the object
    # (unconfirmed NEOCP), the position is propagated locally with Kepler:
    # SBDB elements first, then the preliminary NEOfixer orbit.
    # @args: name - Horizons designation / packed / name, site - MPC code,
    #        when - UTC datetime (default now),
    #        fallback_target - planner dict (packed/id) for NEOCP fallback
    # @return: dict {ra_deg, dec_deg, rate_arcsec_min, pa_deg, epoch_iso,
    #          source, preliminary} or None when no source resolves
    when = when or datetime.datetime.now(datetime.timezone.utc)
    jd = coords.jd_from_datetime(when)
    rows = _horizons_fine_rows(name, site, when)
    if rows:
        out = _interpolate(rows, jd)
        if out:
            out["source"] = "horizons"
            out["preliminary"] = bool(rows[0].get("preliminary"))
            out["epoch_iso"] = _iso(when)
            return out
    from .sources import sbdb
    body = sbdb.get(name)
    if body and body.get("elements"):
        out = _kepler_at(body["elements"], jd)
        if out:
            out["source"] = "kepler:sbdb"
            out["preliminary"] = False
            out["epoch_iso"] = _iso(when)
            return out
    from .sources import neofixer
    packed = (fallback_target or {}).get("packed") \
        or (fallback_target or {}).get("id") or name
    orb = neofixer.orbit(packed)
    if orb and orb.get("elements"):
        out = _kepler_at(orb["elements"], jd)
        if out:
            out["source"] = "kepler:neofixer"
            out["preliminary"] = True
            out["epoch_iso"] = _iso(when)
            return out
    return None
