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
import re
from pathlib import Path

from . import coords, ephem_minor, orbits

logger = logging.getLogger(__name__)

# Earth's circular-orbit speed, used to scale the two-body state velocity
# when reporting the Barbee-style encounter speed (km/s).
_KM_S_PER_AU_DAY = orbits.AU_KM / 86400.0

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


# ---------------- MPC / Find_Orb-style orbit report -----------------------

# Body short codes for the MOID lines, in the order Find_Orb prints them.
_MOID_ORDER = (("Mercury", "Me"), ("Venus", "Ve"), ("Earth", "Ea"),
               ("Mars", "Ma"), ("Jupiter", "Ju"), ("Saturn", "Sa"),
               ("Uranus", "Ur"), ("Neptune", "Ne"))


def _jd_parts(jd):
    # Calendar date + time-of-day as a fraction of a day (kept in days, high
    # precision straight from the JD rather than a truncated datetime).
    # @args: jd - Julian date
    # @return: (datetime, frac_days where 0<frac<=1, 1.0 == midnight/next day)
    t = coords.datetime_from_jd(jd)
    z = int(jd + 0.5)
    frac = jd + 0.5 - z          # fraction of the day, 0.0==midnight
    return t, frac


def _jd_day_frac(jd):
    # "day.FFFFFFFF" with the calendar day and the fractional part of the
    # day (leading zero dropped), e.g. "14.222631" — the Find_Orb / MPC
    # perihelion-date convention.
    # @args: jd - Julian date
    # @return: string
    t, frac = _jd_parts(jd)
    return f"{t.day}.{int(round(frac * 1e6)):06d}"


def _jd_date_line(jd):
    # "2026 Sep 14.222631" — the Find_Orb perihelion/epoch date line.
    # @args: jd - Julian date
    # @return: string
    t, _ = _jd_parts(jd)
    return f"{t.year} {_MONTHS_EN[t.month - 1]} {_jd_day_frac(jd)}"


def _fmt_arc(arc_days):
    # Observation arc, shown in hours when sub-two-day (like the sample).
    # @args: arc_days - arc span in days, or None
    # @return: "21.4 hr" / "12.3 d" / "" when unknown
    if arc_days is None:
        return ""
    hrs = arc_days * 24.0
    return f"{hrs:.1f} hr" if hrs < 48.0 else f"{arc_days:.1f} d"


def _moids_lines(moids):
    # Two "# MOIDs:" lines (inner / outer) when the full set is available,
    # otherwise a single line with whatever bodies are known.
    # @args: moids - {full_body_name: AU}, or None
    # @return: list of lines
    if not moids:
        return []
    pairs = [(code, moids[name]) for name, code in _MOID_ORDER
             if name in moids and isinstance(moids[name], (int, float))]
    if not pairs:
        return []
    if len(pairs) <= 4:
        inner, outer = pairs, []
    else:
        inner, outer = pairs[:4], pairs[4:]
    lines = []
    if inner:
        lines.append("# MOIDs: " + " ".join(f"{c} {v:.4f}" for c, v in inner))
    if outer:
        lines.append("# MOIDs: " + " ".join(f"{c} {v:.4f}" for c, v in outer))
    return lines


def _resolve_body(name, packed, force):
    # Resolves the orbital data from JPL SBDB first, then the preliminary
    # NEOfixer orbit (the only route for unconfirmed NEOCP objects).
    # @args: name - designation, packed - packed code (NEOCP), force - fresh
    # @return: body dict or None
    from .sources import sbdb, neofixer
    body = sbdb.get(name, force=force)
    if body and body.get("elements"):
        return body
    if force:
        body = sbdb.get(name, force=True)
        if body and body.get("elements"):
            return body
    key = packed or name
    if key and key.upper() != (name or "").upper():
        body2 = neofixer.orbit(key, force=force)
        if body2 and body2.get("elements"):
            return body2
    body2 = neofixer.orbit(name, force=force)
    if body2 and body2.get("elements"):
        return body2
    return body


def _perihelion_jd(el, epoch):
    # Perihelion time: straight from `tp`, or derived from the mean anomaly
    # (next time M wraps to 0) when only ma/epoch are present.
    # @args: el - elements dict, epoch - JD
    # @return: JD float or None
    tp = el.get("tp")
    if tp is not None:
        return tp
    a = el.get("a")
    m = el.get("ma")
    if a is None or a <= 0 or m is None:
        return None
    n = 360.0 / (365.25 * a ** 1.5)          # deg/day
    to_zero = (360.0 - m) % 360.0
    return epoch + to_zero / n


def export_fo_report(name, out, packed=None, force=False, data=None):
    # Builds a human-readable orbital report in the Find_Orb / MPC style
    # (see docs/Sar2911-sample-ephemerids.txt): orbital elements, perihelion,
    # P/Q unit vectors, heliocentric state vector, MOIDs, Tisserand parameter,
    # Barbee-style encounter velocity and a diameter estimate, plus an MPC
    # `$`-syntax element footer. Everything is derived by pure math from the
    # resolved elements — no ephemeris table required, so it works for
    # unconfirmed NEOCP orbits too. Per the plan: engine is labelled
    # NightScribe, perturbers are "none (two-body Kepler)", the Find_Orb
    # "Score" line is dropped in favour of the fit residual.
    # @args: name - designation, out - output path, packed - packed code,
    #        force - bypass source cache, data - pre-resolved body dict
    # @return: the written path
    body = data if (data and data.get("elements")) else _resolve_body(
        name, packed, force)
    el = (body or {}).get("elements") or {}
    phys = (body or {}).get("phys") or {}
    if "mo" in el and "ma" not in el:            # SBDB mean-anomaly key
        el = dict(el, ma=el["mo"])
    name = (name or (body or {}).get("des") or "").strip()
    from ..config import config as _cfg
    site = _cfg.get("observatory_name", "")
    mpc = _cfg.get("mpc_code", "")

    a, e, i = el.get("a"), el.get("e"), el.get("i")
    om, w = el.get("om", 0.0), el.get("w", 0.0)
    ma = el.get("ma")
    epoch = el.get("epoch")
    if epoch is None:
        today = datetime.datetime.now(datetime.timezone.utc)
        epoch = coords.jd_from_datetime(today)
    H = phys.get("H")
    albedo = phys.get("albedo") or 0.10
    moid_earth = (body or {}).get("moid")
    if moid_earth is None:
        moids = (body or {}).get("moids") or {}
        moid_earth = moids.get("Earth")
    moids = (body or {}).get("moids") or (
        {"Earth": moid_earth} if moid_earth is not None else {})
    n_resids = (body or {}).get("n_resids")
    arc_days = (body or {}).get("arc_days")
    rms = (body or {}).get("rms_residual")
    sigmas = (body or {}).get("sigmas") or {}

    perij = _perihelion_jd(el, epoch)

    # derived, pure-math quantities
    tisserand = orbits.tisserand_earth(a, e, i)
    sv = ephem_minor.state_vector_j2000(el, epoch) if a else None
    v_earth = ephem_minor.earth_velocity_j2000(epoch)
    venc = orbits.encounter_velocity(sv[3:], v_earth) * _KM_S_PER_AU_DAY \
        if sv else None
    diam_km = orbits.diameter_from_h(H, albedo) if H is not None else None
    pq = ephem_minor.pq_vectors_j2000(el, epoch)

    # mean motion + period (prefer source values, else derive from a)
    period_days = el.get("P") or el.get("per")
    n_motion = el.get("n")
    if a and a > 0 and e is not None and e < 1.0 and not period_days:
        period_days = 365.25 * a ** 1.5
    if not n_motion and period_days:
        n_motion = 360.0 / period_days

    now = datetime.datetime.now(datetime.timezone.utc)
    lines = []
    lines.append("# NightScribe orbital report (two-body Kepler, no perturbers)")
    lines.append(f"# Object: {name or '?'}    Site: {site}"
                 + (f" ({mpc})" if mpc else ""))
    lines.append(f"Created {now:%d %b %Y %H:%M:%S} UTC")
    lines.append("Positions/velocities are in equatorial J2000; times are TT")
    lines.append("Orbital elements:")
    lines.append(name or "?")

    if perij is not None:
        t, _ = _jd_parts(perij)
        lines.append(f"   Perihelion {_jd_date_line(perij)}"
                     f" TT = {t.hour:02d}:{t.minute:02d}:{t.second:02d}"
                     f" (JD {perij:.6f})")
    lines.append(f"Epoch {_jd_date_line(epoch)} (JDT {epoch:.6f})"
                 + (f"   Earth MOID: {moid_earth:.4f}" if moid_earth is not None
                    else "") + "   NightScribe")

    # elements table (Find_Orb column layout: values on the left, the
    # orientation angles P/Q-referenced values on the right)
    eq = "2000.0"
    if ma is not None:
        lines.append(f"M {ma:.8f}        ({eq})            P               Q")
    if n_motion:
        lines.append(f"n   {n_motion:.8f}"
                     + (f"     Peri.  {w:.5f}" if w is not None else ""))
    if a is not None:
        lines.append(f"a   {a:.8f}"
                     + (f"     Node   {om:.5f}" if om is not None else ""))
    if e is not None:
        lines.append(f"e   {e:.7f}"
                     + (f"      Incl.    {i:.5f}" if i is not None else ""))
    pline = ""
    if period_days:
        pline += (f"P   {period_days / 365.25:.2f}"
                  f"/{period_days:.2f}d   ")
    if H is not None:
        pline += f"H   {H:.1f}     "
    if el.get("q") is not None:
        pline += f"q {el['q']:.8f}  "
    Qval = el.get("Q") or (a * (1 + e) if (a and e is not None) else None)
    if Qval is not None:
        pline += f"Q {Qval:.8f}"
    pline = pline.rstrip()
    if pline:
        lines.append(pline)

    if n_resids is not None:
        arc = _fmt_arc(arc_days)
        arc = f" ({arc})" if arc else ""
        rms = f' mean residual {rms:.2f}"' if rms is not None else ""
        lines.append(f"From {n_resids} observations{arc};{rms}")

    # P/Q unit vectors of the orbit (equatorial J2000), for importers that
    # prefer a plane definition over the Euler angles.
    if pq:
        (px_, py_, pz_), (qx_, qy_, qz_) = pq
        lines.append(f"  P   {px_:+.8f}     {py_:+.8f}     {pz_:+.8f}")
        lines.append(f"  Q   {qx_:+.8f}     {qy_:+.8f}     {qz_:+.8f}")

    if sv:
        px, py, pz, vx, vy, vz = sv
        lines.append("# State vector (heliocentric equatorial J2000):")
        lines.append(f"#   {px:+.12f}  {py:+.12f}  {pz:+.12f} AU")
        lines.append(f"#   {vx * 1000:+.12f} {vy * 1000:+.12f}"
                     f"  {vz * 1000:+.12f} mAU/day")

    lines.extend(_moids_lines(moids))
    if perij is not None:
        lines.append(f"# Elements written:  {now:%d %b %Y %H:%M:%S}"
                     f" (JD {epoch:.6f})")
    lines.append(f"# Perturbers: none (two-body Kepler, NightScribe)")
    if tisserand is not None:
        lines.append(f"# Tisserand relative to Earth: {tisserand:.5f}")
    if venc is not None:
        lines.append(f"# Barbee-style encounter velocity: {venc:.4f} km/s")
    if diam_km is not None:
        if diam_km < 1.0:
            lines.append(f"# Diameter {diam_km * 1000:.1f} meters"
                         f" (assuming {albedo * 100:.0f}% albedo)")
        else:
            lines.append(f"# Diameter {diam_km:.2f} km"
                         f" (assuming {albedo * 100:.0f}% albedo)")
    if sigmas:
        lines.append(f"# Sigmas avail: {len(sigmas)}")

    # MPC $-syntax element footer (clean, single logical fields)
    if perij is not None:
        t, _ = _jd_parts(perij)
        lines.append(f"#  $Name={name or '?'}  $Ty={t.year}  $Tm={t.month:02d}"
                     f"  $Td={_jd_day_frac(perij)}  $MA={ma}".rstrip())
    lines.append(f"#  $Eqnx=2000."
                 + (f"  $E={e:.7f}" if e is not None else "")
                 + (f"  $Peri={w:.5f}" if w is not None else "")
                 + (f"  $Node={om:.5f}" if om is not None else "")
                 + (f"  $Incl={i:.5f}" if i is not None else "")
                 + (f"  $a={a:.7f}" if a is not None else ""))
    lines.append(
        f"#  " + (f"$q={el['q']:.8f}" if el.get("q") is not None else "$q=?")
        + (f"  $T={perij:.6f}" if perij is not None else "")
        + (f"  $H={H:.1f}" if H is not None else "").rstrip())

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    logger.info("FO orbital report for %s written to %s", name, out)
    return str(out)


# ---------------- MPC MPOrbit elements line (universal) --------------------
#
# The Minor Planet Center "Export Format for Minor-Planet Orbits" line: one
# 202-character line per object, importable by any planetarium or orbit
# reader (the universal MPC MPCORB handover, no vendor-specific format). We
# reproduce the exact layout Find_Orb writes (validated byte-for-byte
# against docs/Sar2911-sample-ephemerids.txt) so software that already
# digests Find_Orb elements lists digests ours unchanged.


def _pack_epoch(jd):
    # Packed epoch, 5 chars: century letter (I=18, J=19, K=20, L=21), two
    # year digits, month (1-9, A=Oct, B=Nov, C=Dec) and day (0-9, A=10..
    # V=31). 2461291.5 (2026 Sep 8.0) -> "K2698".
    # @args: jd - Julian date of the epoch (TT)
    # @return: packed string
    t = coords.datetime_from_jd(jd)
    month = t.month
    day = t.day
    mchar = str(month) if month <= 9 else chr(ord("A") + month - 10)
    dchar = str(day) if day <= 9 else chr(ord("A") + day - 10)
    return (f"{chr(t.year // 100 + 55)}" + f"{t.year % 100:02d}"
            f"{mchar}{dchar}")


def _pack_provisional(des):
    # MPC packed provisional designation, e.g. "2021 EQ3" -> "K21E03Q":
    # century/year (3), half-month letter (1), repeat count (2) and order
    # letter (1). Only the 2000-2099 classic scheme is packed here; anything
    # else returns None so the caller falls back to the raw name.
    # @args: des - readable provisional designation
    # @return: packed string or None
    m = re.match(r"^(\d{4})\s*([A-Z])([A-Z])\s*(\d{1,2})$",
                 (des or "").strip().upper())
    if not m or m.group(1)[:2] != "20":
        return None
    month_letter, order_letter = m.group(2), m.group(3)
    count = int(m.group(4))
    if count < 100:
        return f"K{m.group(1)[2:]}{month_letter}{count:02d}{order_letter}"
    # counts above 99: a capital letter in column 5 (A=10..Z=35, a-z for
    # 36..61) plus the unit digit — the two-column MPC cycle encoding
    tens, units = count // 10, count % 10
    if tens <= 9:
        return None
    col = chr(ord("A") + tens - 10) if tens <= 35 \
        else chr(ord("a") + tens - 36) if tens <= 61 else None
    if col is None:
        return None
    return f"K{m.group(1)[2:]}{month_letter}{col}{units}{order_letter}"


def _mpc_desig(body, name):
    # Packed designation for columns 1-7 of the MPOrbit line: zero-padded
    # number for numbered minor planets, packed provisional, or the compact
    # MPC/NEOCP code Find_Orb itself uses (e.g. "Sar2911").
    # @args: body - resolved body dict, name - designation fallback
    # @return: packed string (<=7 chars)
    des = ((body or {}).get("des") or "").strip() or (name or "").strip()
    if not des:
        return " " * 7
    digits = re.sub(r"[^0-9]", "", des)
    if digits and digits == des.replace(" ", ""):
        n = int(digits)
        if n < 100000:
            return f"{n:05d}"
        if n <= 619999:
            div, mod = n // 10000, n % 10000
            col = (chr(ord("A") + div - 10) if 10 <= div <= 35
                   else chr(ord("a") + div - 36) if 36 <= div <= 61 else "?")
            return f"{col}{mod:04d}"
        return str(n)[:7]
    packed = _pack_provisional(des)
    if packed:
        return packed
    return re.sub(r"[^A-Za-z0-9+/_.-]", "", des)[:7] or " " * 7


def _f5(v):
    # @args: v - float or None
    # @return: 5-char field (f5.2) or blanks
    return f"{v:5.2f}" if isinstance(v, (int, float)) else " " * 5


def _f9(v, prec=5):
    # @args: v - float or None, prec - decimals
    # @return: 9-char field (f9.5 / f9.7) or blanks
    if not isinstance(v, (int, float)):
        return " " * 9
    return f"{v:9.{prec}f}"


def _mpc_arc(arc_days):
    # @args: arc_days - observation arc in days, or None
    # @return: 9-char field, Find_Orb style ("21.4 hrs " / "12.3 days")
    if not isinstance(arc_days, (int, float)):
        return " " * 9
    hrs = arc_days * 24.0
    s = f"{hrs:.1f} hrs" if hrs < 48.0 else f"{arc_days:.1f} days"
    return f"{s[:9]:<9}"


def _mpc_elements_line(body, computer="NightScr", reference="FO", name=""):
    # Builds one MPC MPOrbit element line (202 characters) from a resolved
    # body dict. Layout validated against the Find_Orb golden sample
    # (docs/Sar2911-sample-ephemerids.txt): designations 1-7, H 9-13, G
    # 15-19, packed epoch 21-25, M 27-35, peri 38-46, node 49-57, incl 60-68,
    # e 71-79, n 81-91, a 93-103, U 106, reference 108-116, observations
    # 118-122, oppositions 124-126, arc 128-136, rms 138-141, computer
    # 151-160, flags 162-165, readable designation 167-194, last obs 195-202.
    # @args: body - body dict with elements/phys, computer - a10 computer
    #        name (the bytes-compat tests pass "Find_Orb" here), reference -
    #        a9 reference, name - designation fallback for the packed field
    # @return: the 202-character line
    el = dict(body.get("elements") or {})
    phys = body.get("phys") or {}
    if "mo" in el and "ma" not in el:          # SBDB mean-anomaly key
        el["ma"] = el["mo"]
    a, e, i = el.get("a"), el.get("e"), el.get("i")
    w, om = el.get("w"), el.get("om")
    epoch = el.get("epoch")
    if epoch is None:
        epoch = coords.jd_from_datetime(
            datetime.datetime.now(datetime.timezone.utc))
    n = el.get("n")
    if not n and a and a > 0:
        period = el.get("P") or el.get("per") or 365.25 * a ** 1.5
        n = 360.0 / period
    ma = el.get("ma")
    if ma is None and el.get("tp") is not None and n:
        ma = (n * (epoch - el["tp"])) % 360.0
    H, G = phys.get("H"), phys.get("G", 0.15)
    u = el.get("u")
    desig = _mpc_desig(body, name)
    n_obs = body.get("n_resids")
    n_opp = 1 if body.get("preliminary") else None
    rms = body.get("rms_residual")
    readable = (str(body.get("fullname") or body.get("des") or "?")
                .strip())[:28]

    # Find_Orb-style reference: "FO " + packed last-observation date YYMMDD
    last8 = ""
    last = body.get("last_obs")
    if last:
        try:
            last8 = datetime.datetime.strptime(
                str(last)[:10], "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError:
            last8 = ""
    last_packed = f"{last8[2:4]}{last8[4:6]}{last8[6:8]}" \
        if len(last8) == 8 else ""
    ref9 = f"{reference} {last_packed}" if last_packed \
        else f"{reference:<9}"

    return "".join((
        f"{desig:<7}",
        " " + _f5(H),
        " " + _f5(G),
        " " + _pack_epoch(epoch),
        " " + _f9(ma, 5),
        "  " + _f9(w, 5),
        "  " + _f9(om, 5),
        "  " + _f9(i, 5),
        "  " + _f9(e, 7),
        " " + (f"{n:11.8f}" if isinstance(n, (int, float)) else " " * 11),
        " " + (f"{a:11.7f}" if isinstance(a, (int, float)) else " " * 11),
        "  " + (f"{u:1d}" if isinstance(u, (int, float)) else " "),
        " " + ref9,
        " " + (f"{n_obs:5d}" if isinstance(n_obs, (int, float))
               else " " * 5),
        " " + (f"{n_opp:3d}" if isinstance(n_opp, (int, float))
               else " " * 3),
        " " + _mpc_arc(body.get("arc_days")),
        " " + (f"{rms:4.2f}" if isinstance(rms, (int, float))
               else " " * 4),
        " " + " " * 3,                       # coarse perturber indicator
        " " + " " * 3,                       # precise perturber indicator
        " " + f"{computer:<10}",
        " " + "0000",
        " " + f"{readable:<28}",
        last8 if len(last8) == 8 else " " * 8,
    ))


def export_mpc_elements(name, out, packed=None, force=False, data=None):
    # Writes a MPC MPOrbit elements file (universal orbit handover): a
    # Find_Orb-style header line plus one element line per resolved object.
    # Importable by any planetarium or orbit reader (the universal MPC
    # format; no vendor-specific target).
    # @args: name - designation, out - path, packed - packed code (NEOCP),
    #        force - bypass source cache, data - pre-resolved body dict
    # @return: the written path, or None when no orbit is known
    body = data if (data and data.get("elements")) else _resolve_body(
        name, packed, force)
    el = (body or {}).get("elements") or {}
    if not body or not el.get("a") or el.get("e") is None:
        logger.info("No MPC elements for %s (no orbit)", name)
        return None
    from ..config import config as _cfg
    site = _cfg.get("observatory_name", "")
    line = _mpc_elements_line(body, name=name)
    jd_now = coords.jd_from_datetime(
        datetime.datetime.now(datetime.timezone.utc))
    header = f"{jd_now:.5f} 1.000000 1 0,1,1 {site}".rstrip()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + "\n" + line + "\n", encoding="ascii",
                   errors="replace")
    logger.info("MPC elements for %s written to %s", name, out)
    return str(out)


def export(rows, out, fmt="csv", obj_name=""):
    # Dispatcher: picks the exporter for the given planetarium format.
    # @args: rows - list from generate(), out - path, fmt - "csv"|"skyx"|"cdc"|"fo"|"mpx",
    #        obj_name - target name for headers (for "fo"/"mpx" this IS the
    #        designation to resolve; force-fresh resolution goes through
    #        export_fo_report()/export_mpc_elements() directly)
    # @return: output path
    out = Path(out)
    if fmt == "fo":
        return export_fo_report(name=obj_name, out=out)
    if fmt == "mpx":
        return export_mpc_elements(name=obj_name, out=out)
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
