############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Sky events module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime
import math

from . import coords, ephem_minor

# The sky calendar (Track SC2): the solar system as a stream of events.
# Everything here is local math over the Schlyter ephemeris
# (core/ephem_minor) and the local-sky helpers (core/coords) — no network,
# no cache. The engine finds WHAT happens; the GUI says it in words with
# self.tr(). Events are plain dicts so the tests can pin them offline.
#
# Honesty rule: this is an ephemeris of positions, not of observability —
# eclipse rows are "likely" (no contact times), meteor rows are approximate
# annual peaks, and "tonight" is a 0-deg horizon gate, not a horizon-file
# safe span.

# synodic month, days
SYNODIC = 29.53059

# scan step, days (the plan pacts <= 0.1 d)
STEP = 0.1

# phase targets: (moon age in days, kind, icon)
_PHASES = (
    (0.00, "new_moon", "🌑"),
    (7.38, "first_quarter", "🌓"),
    (14.77, "full_moon", "🌕"),
    (22.15, "last_quarter", "🌗"),
)

_ALL = ("mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune")
_OUTER = ("mars", "jupiter", "saturn", "uranus", "neptune")
_INNER = ("mercury", "venus")  # the Sun's shadows: elongations & inferior conjunctions

# listing thresholds, degrees
MOON_CONJ_DEG = 4.0       # Moon-planet closeness
PAIR_CONJ_DEG = 1.5       # planet-planet closeness
MAXEL_MIN_DEG = 10.0      # a maximum elongation below this is noise
# Oppositions and Sun conjunctions are detected as ECLIPTIC LONGITUDE
# crossings (lambda_planet - lambda_sun = 180 / 0), never by elongation:
# a planet off the ecliptic tops out below 180 deg of elongation (Saturn
# 2026-10-04 peaked at 177.28 deg with beta=-2.7 deg and a 178.5 deg
# elongation gate lost a real opposition — the one true bug of SC0).

# eclipse geometry: shadow cones in kilometres, not fixed latitude cuts
# (a "grazing" latitude is not what separates total from partial)
EARTH_R_KM = 6378.1        # Earth mean radius
MOON_R_KM = 1737.4         # Moon mean radius
SUN_R_KM = 696340.0        # Sun mean radius
AU_KM = 149597870.7        # astronomical unit
OBLIQUITY_DEG = 23.4393    # obliquity of the ecliptic (J2000)
# Schlyter is arcminute-grade: a little honesty margin below the total/
# central gates, so a grazing central path still classifies as "likely"
ECLIPSE_TOL_KM = 900.0

# major meteor showers: (id, month, day, typical ZHR, radiant, ra, dec)
# radiant coordinates J2000, good enough for an altitude screen
_SHOWERS = (
    ("quadrantids", 1, 3, 110, "Bootes", 230.3, 49.5),
    ("lyrids", 4, 22, 18, "Lyra", 279.7, 33.9),
    ("eta_aquariids", 5, 5, 50, "Aquarius", 345.6, -13.6),
    ("perseids", 8, 12, 100, "Perseus", 35.0, 58.0),
    ("orionids", 10, 21, 20, "Orion", 92.5, 15.9),
    ("leonids", 11, 18, 15, "Leo", 152.4, 20.2),
    ("geminids", 12, 13, 150, "Gemini", 150.0, 33.0),
    ("ursids", 12, 22, 10, "Ursa Minor", 225.0, 76.0),
)


def _window(from_date=None, days=60):
    # @args: from_date - date/datetime (local today) or None (today UTC),
    #        days - horizon in days
    # @return: (jd start, jd end, start date)
    if from_date is None:
        d = datetime.datetime.now(datetime.timezone.utc).date()
    elif isinstance(from_date, datetime.datetime):
        d = from_date.date()
    else:
        d = from_date
    start = datetime.datetime(d.year, d.month, d.day,
                              tzinfo=datetime.timezone.utc)
    return (coords.jd_from_datetime(start),
            coords.jd_from_datetime(start + datetime.timedelta(days=days)),
            d)


def _ev(jd, kind, icon, objects, **extra):
    # Base event dict: the contract fields, None where a family has no value.
    # @return: event dict
    e = {"jd": jd,
         "date": coords.datetime_from_jd(jd),
         "kind": kind,
         "icon": icon,
         "objects": list(objects),
         "mag": None,
         "sep_deg": None,
         "alt_deg": None,
         "tonight": False}
    e.update(extra)
    return e


def _signed_to_target(jd, target):
    # Signed shortest distance (in moon-age days) from `target` to the
    # current moon age: negative before the crossing, positive after.
    w = (ephem_minor.moon(jd)["phase_age_days"] - target) % SYNODIC
    return w - SYNODIC if w > SYNODIC / 2 else w


def _bisect_crossing(jd_a, jd_b, sign_fn, iters=32):
    # Bisection root of `sign_fn` on (jd_a, jd_b) — it must change sign.
    # @return: crossing jd (sub-second precision)
    lo, hi = jd_a, jd_b
    glo = sign_fn(lo)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        gm = sign_fn(mid)
        if glo * gm <= 0.0:
            hi = mid
        else:
            lo, glo = mid, gm
    return 0.5 * (lo + hi)


def _phase_crossings(jds, ages, target):
    # Every jd where the moon age sweeps past `target` (0..29.53).
    # A 60-day window holds two or three of each phase — all of them count.
    # @return: [crossing jd]
    out = []
    for i in range(len(jds) - 1):
        w0 = (ages[i] - target) % SYNODIC
        w1 = (ages[i + 1] - target) % SYNODIC
        if w0 > SYNODIC - 1.0 and w1 < 1.0:  # the crossing sits inside
            out.append(_bisect_crossing(
                jds[i], jds[i + 1], lambda jd: _signed_to_target(jd, target)))
    return out


def _ecl_lon(ra_deg, dec_deg):
    # Geocentric ecliptic longitude from equatorial coordinates — the true
    # syzygy clock the mean moon age only approximates.
    # @return: 0..360 degrees
    eps = math.radians(OBLIQUITY_DEG)
    cd = math.cos(math.radians(dec_deg))
    x = cd * math.cos(math.radians(ra_deg))
    y = (cd * math.sin(math.radians(ra_deg)) * math.cos(eps)
         + math.sin(math.radians(dec_deg)) * math.sin(eps))
    return math.degrees(math.atan2(y, x)) % 360.0


def _syzygy_lambda(jd, target):
    # Signed circular distance (deg) from true syzygy: (moon - sun)
    # geocentric ecliptic longitude minus 0 (new) or 180 (full).
    m = ephem_minor.moon(jd)
    s = ephem_minor.sun_ra_dec(jd)
    w = (_ecl_lon(m["ra"], m["dec"]) - _ecl_lon(s[0], s[1]) - target) % 360.0
    return w - 360.0 if w > 180.0 else w


def _syzygy_crossings(jds, target):
    # True new (0) / full (180) Moon where the ecliptic longitudes meet or
    # oppose — bisection-refined. The mean moon age misses this by hours.
    # @return: [crossing jd]
    out = []
    for i in range(len(jds) - 1):
        w0 = _syzygy_lambda(jds[i], target) % 360.0
        w1 = _syzygy_lambda(jds[i + 1], target) % 360.0
        if w0 > 355.0 and w1 < 5.0:  # the sweep crosses inside the cell
            out.append(_bisect_crossing(
                jds[i], jds[i + 1], lambda jd: _syzygy_lambda(jd, target)))
    return out


def _lambda_minus_sun(jd, name, target):
    # Signed circular distance (deg) of the planet's geocentric ecliptic
    # longitude from the Sun's + `target` (180 = opposition, 0 =
    # conjunction). The one true clock for both families.
    # @return: degrees in (-180, 180]
    p = ephem_minor.planet(name, jd)
    s = ephem_minor.sun_ra_dec(jd)
    w = (_ecl_lon(p["ra"], p["dec"]) - _ecl_lon(s[0], s[1]) - target) % 360.0
    return w - 360.0 if w > 180.0 else w


def _lambda_crossings(jds, name, target):
    # Every jd where (lambda_planet - lambda_sun) sweeps past `target`,
    # bisection-refined. Direction-agnostic: near an opposition the outer
    # planets RETROGRADE (their longitude walks backwards), so the sweep
    # may cross from either side — a plain "wrap past 355/5" pattern only
    # catches the Moon's forward march.
    # @return: [crossing jd]
    out = []
    for i in range(len(jds) - 1):
        w0 = _lambda_minus_sun(jds[i], name, target)
        w1 = _lambda_minus_sun(jds[i + 1], name, target)
        if abs(w1 - w0) > 180.0:
            continue  # the far boundary (target ± 180) alias, not a cross
        if w0 == 0.0 or (w0 < 0.0) != (w1 < 0.0):
            out.append(_bisect_crossing(
                jds[i], jds[i + 1],
                lambda jd: _lambda_minus_sun(jd, name, target)))
    return out


def _parabolic(jd, h, f0, f1, f2):
    # Vertex of the parabola through 3 uniform samples — cheap refinement
    # of an extremum found on the grid.
    # @return: refined jd, clamped to the sample box
    denom = f0 - 2.0 * f1 + f2
    if abs(denom) < 1e-15:
        return jd
    off = h * (f0 - f2) / (2.0 * denom)
    return jd + max(-h, min(h, off))


def _altitude(ra, dec, lat_deg, lon_deg, when):
    # @args: when - utc datetime
    # @return: altitude in degrees
    jd = coords.jd_from_datetime(when)
    alt, _ = coords.altaz(ra, dec, lat_deg, coords.lst_degrees(jd, lon_deg))
    return alt


def _darkness(lat_deg, lon_deg, date):
    # @return: (start, end) UTC datetimes of astronomical darkness on
    #          `date`, or None when the site has no darkness that day
    return coords.tonight_window(lat_deg, lon_deg, date=date)


def _cleared_during(ra, dec, lat_deg, lon_deg, date):
    # Is (ra, dec) above 0 deg at some point during that date's darkness?
    # @return: bool
    w = _darkness(lat_deg, lon_deg, date)
    if w is None:  # polar day: sample the night hours blindly
        base = datetime.datetime(date.year, date.month, date.day,
                                 tzinfo=datetime.timezone.utc)
        return any(_altitude(ra, dec, lat_deg, lon_deg,
                             base + datetime.timedelta(hours=h)) > 0.0
                   for h in (0, 6, 12, 18))
    t, end = w
    while t <= end:
        if _altitude(ra, dec, lat_deg, lon_deg, t) > 0.0:
            return True
        t += datetime.timedelta(minutes=30)
    return False


def _alts_at_dusk(ra, dec, lat_deg, lon_deg, date):
    # Height of (ra, dec) at the start of that date's darkness.
    # @return: altitude in degrees, or None (no darkness at the site)
    w = _darkness(lat_deg, lon_deg, date)
    if w is None:
        return None
    return _altitude(ra, dec, lat_deg, lon_deg, w[0])


def _phases(jds, ages):
    # New / quarters / full: the moon age sweeping past its target.
    # @return: [event] with illum (0..1)
    out = []
    for target, kind, icon in _PHASES:
        for jd in _phase_crossings(jds, ages, target):
            m = ephem_minor.moon(jd)
            out.append(_ev(jd, kind, icon, ["moon"], illum=m["illum"]))
    return out


def _eclipse_shadow(at_km, r_sun_au):
    # Shadow cone cross-sections for a moon at `at_km` from the Earth/Sun
    # axis: rho is the Sun's angular radius (rad), core is the umbral
    # cross-section at Earth (km, negative = antumbra), reach is the
    # penumbral radius. Shared by the solar and lunar gates below.
    # @return: (rho, core, reach)
    rho = SUN_R_KM / (r_sun_au * AU_KM)
    return rho, MOON_R_KM - at_km * rho, MOON_R_KM + at_km * rho


def _lunar_eclipse(jd):
    # Full Moon in the Earth's shadow: umbra radius at the Moon is
    # R_Earth - d*rho, penumbra R_Earth + d*rho (Meeus 47-ish, small angles).
    # @return: event or None
    m = ephem_minor.moon(jd)
    d = m["dist_km"]
    beta = math.radians(abs(m["ecl_lat_deg"]))
    rho = SUN_R_KM / (ephem_minor.sun_ra_dec(jd)[2] * AU_KM)
    d_perp = d * math.sin(beta)  # axis offset of the Moon's centre
    r_umbra = EARTH_R_KM - d * rho
    r_penumbra = EARTH_R_KM + d * rho
    if d_perp > r_penumbra + MOON_R_KM:
        return None  # the disc never even grazes the penumbra
    total = d_perp <= r_umbra - MOON_R_KM + ECLIPSE_TOL_KM
    return _ev(jd, "lunar_eclipse", "🌘", ["moon"],
               detail="total" if total else "partial",
               ecl_lat_deg=round(abs(m["ecl_lat_deg"]), 2))


def _solar_eclipse(jd):
    # New Moon whose shadow cone (umbra or antumbra) reaches the Earth.
    # @return: event or None
    m = ephem_minor.moon(jd)
    d = m["dist_km"]
    beta = math.radians(abs(m["ecl_lat_deg"]))
    rho, core, reach = _eclipse_shadow(d, ephem_minor.sun_ra_dec(jd)[2])
    d_perp = d * math.sin(beta)  # axis offset of the cone at Earth
    if d_perp > reach + EARTH_R_KM:
        return None  # the penumbra never touches the Earth
    central = d_perp <= abs(core) + EARTH_R_KM + ECLIPSE_TOL_KM
    if central:
        detail = "total" if core > 0 else "annular"
    else:
        detail = "partial"
    return _ev(jd, "solar_eclipse", "🌘", ["sun", "moon"],
               detail=detail,
               ecl_lat_deg=round(abs(m["ecl_lat_deg"]), 2))


def _eclipses(jds):
    # Eclipses: every true syzygy in the window, gated on shadow geometry
    # in kilometres (the fixed latitude cuts mis-labelled grazing paths).
    # No contact times — the GUI labels them "likely".
    # @return: [event] with detail total/partial/annular, ecl_lat_deg
    out = []
    for jd in _syzygy_crossings(jds, 0.0):
        ev = _solar_eclipse(jd)
        if ev:
            out.append(ev)
    for jd in _syzygy_crossings(jds, 180.0):
        ev = _lunar_eclipse(jd)
        if ev:
            out.append(ev)
    return out


def _apsides(jds, moons):
    # Local extrema of the Moon's distance: min perigee, max apogee.
    # @return: [event] with dist_km
    out = []
    dists = [m["dist_km"] for m in moons]
    h = jds[1] - jds[0]
    for i in range(1, len(jds) - 1):
        d0, d1, d2 = dists[i - 1], dists[i], dists[i + 1]
        if d1 > d0 and d1 > d2:
            jd, kind, icon = _parabolic(jds[i], h, d0, d1, d2), "apogee", "🌕"
        elif d1 < d0 and d1 < d2:
            jd, kind, icon = _parabolic(jds[i], h, d0, d1, d2), "perigee", "🌕"
        else:
            continue
        m = ephem_minor.moon(jd)
        out.append(_ev(jd, kind, icon, ["moon"], dist_km=int(m["dist_km"])))
    return out


def _separation_series(a, b):
    # @args: a, b - lists of {ra, dec} samples
    # @return: the great-circle separation series, degrees
    return [coords.angular_separation(p["ra"], p["dec"], q["ra"], q["dec"])
            for p, q in zip(a, b)]


def _moon_conjunctions(jds, moons, planets, lat_deg, lon_deg):
    # The Moon passing a planet: local minimum separation < 4 deg.
    # @return: [event] with sep_deg, mag, alt_deg (at dusk), up_at_dusk
    out = []
    h = jds[1] - jds[0]
    for name in _ALL:
        seps = _separation_series(moons, planets[name])
        for i in range(1, len(seps) - 1):
            if seps[i] >= MOON_CONJ_DEG or seps[i] >= seps[i - 1] \
                    or seps[i] >= seps[i + 1]:
                continue
            jd = _parabolic(jds[i], h, seps[i - 1], seps[i], seps[i + 1])
            pl = ephem_minor.planet(name, jd)
            date = coords.datetime_from_jd(jd).date()
            alt = _alts_at_dusk(pl["ra"], pl["dec"], lat_deg, lon_deg, date)
            out.append(_ev(jd, "moon_conjunction", "🌙", ["moon", name],
                           sep_deg=round(seps[i], 2), mag=pl["mag"],
                           alt_deg=round(alt, 1) if alt is not None else None,
                           up_at_dusk=alt is not None and alt > 0.0))
    return out


def _pair_conjunctions(jds, planets):
    # Planet-planet: local minimum separation < 1.5 deg.
    # @return: [event] with sep_deg
    out = []
    h = jds[1] - jds[0]
    for a in range(len(_ALL)):
        for b in range(a + 1, len(_ALL)):
            na, nb = _ALL[a], _ALL[b]
            seps = _separation_series(planets[na], planets[nb])
            for i in range(1, len(seps) - 1):
                if seps[i] >= PAIR_CONJ_DEG or seps[i] >= seps[i - 1] \
                        or seps[i] >= seps[i + 1]:
                    continue
                jd = _parabolic(jds[i], h, seps[i - 1], seps[i], seps[i + 1])
                out.append(_ev(jd, "planet_conjunction", "✨", [na, nb],
                               sep_deg=round(seps[i], 2)))
    return out


def _elongation_series(suns, planets):
    # @return: {planet: [elongation degrees]} against the Sun, per sample
    return {name: _separation_series(suns, ps) for name, ps in planets.items()}


def _locals_max(series):
    # @return: indices of the local maxima of a sample series
    return [i for i in range(1, len(series) - 1)
            if series[i] > series[i - 1] and series[i] >= series[i + 1]]


def _locals_min(series):
    # @return: indices of the local minima of a sample series
    return [i for i in range(1, len(series) - 1)
            if series[i] < series[i - 1] and series[i] <= series[i + 1]]


def _oppositions(jds, planets):
    # Outer planets: the geocentric ECLIPTIC LONGITUDE crossing
    # lambda_planet - lambda_sun = 180 (bisection-refined). Elongation
    # peaks below 180 deg when the planet is off the ecliptic, so an
    # elongation gate loses real oppositions (Saturn 2026-10-04, peaked
    # at 177.28 deg with beta=-2.7 deg — lost by the old 178.5 deg gate).
    # The reported elong_deg is the TRUE elongation at the crossing —
    # real data, not a failure.
    # @return: [event] with elong_deg, dist_au, mag
    out = []
    for name in _OUTER:
        for jd in _lambda_crossings(jds, name, 180.0):
            p = ephem_minor.planet(name, jd)
            s = ephem_minor.sun_ra_dec(jd)
            elong = coords.angular_separation(p["ra"], p["dec"],
                                              s[0], s[1])
            out.append(_ev(jd, "opposition", "🔴", [name],
                           elong_deg=round(elong, 1),
                           dist_au=round(p["dist_au"], 2),
                           mag=p["mag"]))
    return out


def _east_west(planet_ra, sun_ra):
    # East of the Sun sets after it (evening); west rises before it (noon).
    # Mercury and Venus hug the ecliptic, so the RA side decides.
    # @return: "east" | "west"
    return "east" if (planet_ra - sun_ra) % 360.0 < 180.0 else "west"


def _max_elongations(el, jds, planets):
    # Mercury / Venus: local maximum elongation — the "best evening/morning"
    # of that synodic cycle.
    # @return: [event] with elong_deg, side, mag
    out = []
    h = jds[1] - jds[0]
    for name in _INNER:
        eln = el[name]
        for i in _locals_max(eln):
            if eln[i] < MAXEL_MIN_DEG:
                continue
            jd = _parabolic(jds[i], h, eln[i - 1], eln[i], eln[i + 1])
            p = ephem_minor.planet(name, jd)
            sra = ephem_minor.sun_ra_dec(jd)[0]
            icon = "☿" if name == "mercury" else "♀"
            out.append(_ev(jd, "max_elongation", icon, [name],
                           elong_deg=round(eln[i], 1),
                           side=_east_west(p["ra"], sra),
                           mag=p["mag"]))
    return out


def _sun_conjunctions(jds):
    # Sun-planet: the longitude crossing lambda_planet - lambda_sun = 0.
    # Same latitude trap as the oppositions (a high-beta planet's minimum
    # elongation stays above the old 2 deg gate — Saturn reaches ~3.4 deg).
    # Inner planets cross twice per synodic cycle: BETWEEN us and the Sun
    # (inferior, planet closer than the Sun) or BEHIND it (superior).
    # @return: [event] with detail ("inferior"|"superior"), elong_deg
    out = []
    for name in _ALL:
        for jd in _lambda_crossings(jds, name, 0.0):
            p = ephem_minor.planet(name, jd)
            s = ephem_minor.sun_ra_dec(jd)
            elong = coords.angular_separation(p["ra"], p["dec"],
                                              s[0], s[1])
            detail = ("inferior" if name in _INNER
                      and p["dist_au"] < s[2] else "superior")
            out.append(_ev(jd, "sun_conjunction", "☀️", [name],
                           detail=detail, elong_deg=round(elong, 1)))
    return out


def _meteor_showers(jd_from, jd_to, date0, lat_deg, lon_deg):
    # Annual peaks falling inside the horizon (this year or next).
    # @return: [event] with shower, zhr, radiant, alt_deg (max that day)
    out = []
    for (sid, month, day, zhr, radiant, ra, dec) in _SHOWERS:
        for year in (date0.year, date0.year + 1):
            try:
                t = datetime.datetime(year, month, day,
                                      tzinfo=datetime.timezone.utc)
            except ValueError:  # Feb 29
                continue
            jd = coords.jd_from_datetime(t)
            if not (jd_from <= jd <= jd_to):
                continue
            high = max(_altitude(ra, dec, lat_deg, lon_deg,
                       datetime.datetime(t.year, t.month, t.day, hour=h,
                        tzinfo=datetime.timezone.utc))
                       for h in (0, 6, 12, 18))
            out.append(_ev(jd, "meteor_shower", "☄️", [sid], shower=sid,
                           zhr=zhr, radiant=radiant, alt_deg=round(high, 1),
                           up_at_dusk=high > 0.0))
    return out


def _satellite_events(jd_from, jd_to, lat_deg, lon_deg):
    # TODO(phase SD): Galilean moon transits and shadow transits —
    # core/satellites.py (Meeus ch. 43) merges in here.
    # @return: [] until phase SD ships the math
    return []


def _tonight_flag(ev, lat_deg, lon_deg):
    # The "tonight" gate: the lead object clears 0 deg that date's darkness.
    # @args: ev - event dict
    # @return: bool
    date = ev["date"].date()
    kind = ev["kind"]
    if kind in ("new_moon", "first_quarter", "full_moon", "last_quarter",
                "lunar_eclipse", "solar_eclipse"):
        pos = ephem_minor.moon(ev["jd"])
        return _cleared_during(pos["ra"], pos["dec"], lat_deg, lon_deg, date)
    if kind == "moon_conjunction":
        if ev.get("up_at_dusk"):
            # the pair hangs in the twilight sky: it IS a tonight event
            return True
        name = [n for n in ev["objects"] if n != "moon"][0]
    elif kind in ("opposition", "max_elongation", "sun_conjunction",
                  "planet_conjunction"):
        name = ev["objects"][0]
    else:
        return ev.get("up_at_dusk", False)
    pos = ephem_minor.planet(name, ev["jd"])
    return _cleared_during(pos["ra"], pos["dec"], lat_deg, lon_deg, date)


def events(lat_deg, lon_deg, from_date=None, days=60):
    # The horizon of sky events for a site: Moon phases, apsides,
    # Moon/planet and planet/planet conjunctions, oppositions, maximum
    # elongations, Sun conjunctions, likely eclipses, meteor showers, and
    # (phase SD) Galilean satellite transits. Pure local math — no network.
    # @args: lat_deg, lon_deg - site (drives altitudes & "tonight"),
    #        from_date - date/datetime (local today) or None,
    #        days - horizon (default 60)
    # @return: [event dict] sorted by jd; base keys jd, date, kind, icon,
    #          objects, mag, sep_deg, alt_deg, tonight
    jd_from, jd_to, date0 = _window(from_date, days)
    n = int(round((jd_to - jd_from) / STEP))
    jds = [jd_from + i * STEP for i in range(n + 1)]

    moons = [ephem_minor.moon(j) for j in jds]
    ages = [m["phase_age_days"] for m in moons]
    suns = [{"ra": s[0], "dec": s[1]} for s in (ephem_minor.sun_ra_dec(j)
            for j in jds)]
    planets = {name: [ephem_minor.planet(name, j) for j in jds]
               for name in _ALL}
    el = _elongation_series(suns, planets)

    out = []
    out += _phases(jds, ages)
    out += _eclipses(jds)
    out += _apsides(jds, moons)
    out += _moon_conjunctions(jds, moons, planets, lat_deg, lon_deg)
    out += _pair_conjunctions(jds, planets)
    out += _oppositions(jds, planets)
    out += _max_elongations(el, jds, planets)
    out += _sun_conjunctions(jds)
    out += _meteor_showers(jd_from, jd_to, date0, lat_deg, lon_deg)
    out += _satellite_events(jd_from, jd_to, lat_deg, lon_deg)

    for ev in out:
        ev["tonight"] = _tonight_flag(ev, lat_deg, lon_deg)

    out.sort(key=lambda ev: ev["jd"])
    return out
