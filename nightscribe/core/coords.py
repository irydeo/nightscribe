############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Coordinates and time module (pure math)
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

# Pure-math helpers: sidereal time, alt-az, Julian dates. No astropy
# (see ADR-004); arcminute accuracy is plenty for planning.


def jd_from_datetime(dt):
    # @args: dt - timezone-aware (UTC) datetime
    # @return: Julian date as float
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    t = dt.astimezone(datetime.timezone.utc)
    y, m = t.year, t.month
    if m <= 2:
        y, m = y - 1, m + 12
    day = t.day + (t.hour + (t.minute + (t.second + t.microsecond / 1e6) / 60) / 60) / 24
    a = y // 100
    b = 2 - a + a // 4
    return (int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + b - 1524.5)


def datetime_from_jd(jd):
    # @args: jd - Julian date
    # @return: timezone-aware UTC datetime
    # Meeus, Astronomical Algorithms ch. 7
    z = int(jd + 0.5)
    f = jd + 0.5 - z
    if z >= 2299161:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4
    else:
        a = z
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = b - d - int(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    d_int = int(day)
    frac = (day - d_int) * 24
    h = int(frac)
    m = int((frac - h) * 60)
    s = int(round((((frac - h) * 60) - m) * 60))
    if s >= 60:  # rounding may spill over
        s, m = 0, m + 1
    if m >= 60:
        m, h = 0, h + 1
    if h >= 24:
        h = 0
        d_int += 1
    return datetime.datetime(year, month, d_int, h, m, s,
                             tzinfo=datetime.timezone.utc)


def gmst_degrees(jd):
    # @args: jd - Julian date
    # @return: Greenwich mean sidereal time in degrees [0, 360)
    t = (jd - 2451545.0) / 36525.0
    gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0) \
        + 0.000387933 * t * t - t * t * t / 38710000.0
    return gmst % 360.0


def lst_degrees(jd, lon_deg):
    # @args: jd - Julian date, lon_deg - observer longitude, degrees east
    # @return: local sidereal time in degrees [0, 360)
    return (gmst_degrees(jd) + lon_deg) % 360.0


def altaz(ra_deg, dec_deg, lat_deg, lst_deg):
    # Horizontal coordinates from equatorial ones.
    # @args: ra_deg, dec_deg - object RA/Dec in degrees (J2000 is fine),
    #        lat_deg - observer latitude, lst_deg - local sidereal time
    # @return: (altitude, azimuth) in degrees, azimuth from north through east
    ha = math.radians(lst_deg - ra_deg)
    dec = math.radians(dec_deg)
    lat = math.radians(lat_deg)
    sin_alt = math.sin(dec) * math.sin(lat) \
        + math.cos(dec) * math.cos(lat) * math.cos(ha)
    alt = math.asin(max(-1.0, min(1.0, sin_alt)))
    cos_az = (math.sin(dec) - math.sin(alt) * math.sin(lat)) \
        / (math.cos(alt) * math.cos(lat) + 1e-12)
    az = math.acos(max(-1.0, min(1.0, cos_az)))
    if math.sin(ha) > 0:
        az = 2 * math.pi - az
    return math.degrees(alt), math.degrees(az)


def ra_hms_to_deg(ra_hms):
    # @args: ra_hms - "hh:mm:ss.sss" or "hh mm ss.sss"
    # @return: right ascension in degrees
    h, m, s = (float(x) for x in ra_hms.replace(":", " ").split())
    return 15.0 * (h + m / 60.0 + s / 3600.0)


def dec_dms_to_deg(dec_dms):
    # @args: dec_dms - "[+/-]dd:mm:ss.sss" or with spaces
    # @return: declination in degrees
    sign = -1.0 if dec_dms.strip().startswith("-") else 1.0
    d, m, s = (float(x) for x in dec_dms.replace(":", " ")
               .replace("+", "").replace("-", "").split())
    return sign * (d + m / 60.0 + s / 3600.0)


def ra_deg_to_hms(ra_deg):
    # @args: ra_deg - right ascension in degrees
    # @return: "hh mm ss.s" string (inverse of ra_hms_to_deg)
    ra_deg = ra_deg % 360.0
    total_s = ra_deg / 15.0 * 3600.0
    h = int(total_s // 3600)
    m = int((total_s - h * 3600) // 60)
    s = total_s - h * 3600 - m * 60
    return f"{h:02d} {m:02d} {s:04.1f}"


def dec_deg_to_dms(dec_deg):
    # @args: dec_deg - declination in degrees
    # @return: "+dd mm ss.s" string (inverse of dec_dms_to_deg)
    sign = "-" if dec_deg < 0 else "+"
    total_s = abs(dec_deg) * 3600.0
    d = int(total_s // 3600)
    m = int((total_s - d * 3600) // 60)
    s = total_s - d * 3600 - m * 60
    return f"{sign}{d:02d} {m:02d} {s:04.1f}"


def tonight_window(lat_deg, lon_deg, date=None, sun_alt_limit=-18.0):
    # Start and end of the astronomical night for a site.
    # Samples the Sun altitude every 10 minutes; arcminute ephemeris is fine here.
    # @args: lat_deg, lon_deg - site, date - datetime.date (UTC, tonight),
    #        sun_alt_limit - twilight definition (-18 astronomical)
    # @return: (start_utc, end_utc) as datetimes; None if no darkness found
    from . import ephem_minor

    date = date or datetime.datetime.now(datetime.timezone.utc).date()
    t0 = datetime.datetime(date.year, date.month, date.day, 12, 0,
                           tzinfo=datetime.timezone.utc)
    samples = []
    for i in range(24 * 6):  # 24 h at 10-min steps, from noon to noon
        t = t0 + datetime.timedelta(minutes=10 * i)
        jd = jd_from_datetime(t)
        ra, dec, _r = ephem_minor.sun_ra_dec(jd)
        alt, _ = altaz(ra, dec, lat_deg, lst_degrees(jd, lon_deg))
        samples.append((t, alt))
    dark = [t for (t, alt) in samples if alt < sun_alt_limit]
    if not dark:
        return None
    return dark[0], dark[-1]


def max_altitude_tonight(ra_deg, dec_deg, lat_deg, lon_deg, date=None):
    # Best altitude of a fixed object (RA/Dec) during tonight's darkness.
    # @args: ra_deg, dec_deg - object, lat_deg, lon_deg - site,
    #        date - datetime.date (UTC)
    # @return: (max_alt_deg, datetime of max) or (None, None) if never dark/up
    window = tonight_window(lat_deg, lon_deg, date)
    if not window:
        return None, None
    start, end = window
    best_alt, best_t = -90.0, None
    t = start
    while t <= end:
        jd = jd_from_datetime(t)
        alt, _ = altaz(ra_deg, dec_deg, lat_deg, lst_degrees(jd, lon_deg))
        if alt > best_alt:
            best_alt, best_t = alt, t
        t += datetime.timedelta(minutes=10)
    if best_t is None:
        return None, None
    return best_alt, best_t


def current_altaz(ra_deg, dec_deg, lat_deg, lon_deg, when=None):
    # Altitude and azimuth of an object right now (or at a given instant).
    # @args: ra_deg, dec_deg - object, lat_deg, lon_deg - site,
    #        when - UTC datetime (now)
    # @return: (altitude, azimuth) in degrees
    when = when or datetime.datetime.now(datetime.timezone.utc)
    jd = jd_from_datetime(when)
    return altaz(ra_deg, dec_deg, lat_deg, lst_degrees(jd, lon_deg))


def hours_above(ra_deg, dec_deg, lat_deg, lon_deg, min_alt, date=None):
    # Time an object spends above a given altitude during tonight's darkness.
    # @args: ra_deg, dec_deg - object, lat_deg, lon_deg - site,
    #        min_alt - altitude threshold in degrees, date - datetime.date
    # @return: hours as float (0 if none)
    window = tonight_window(lat_deg, lon_deg, date)
    if not window:
        return 0.0
    start, end = window
    n = 0
    t = start
    while t <= end:
        jd = jd_from_datetime(t)
        alt, _ = altaz(ra_deg, dec_deg, lat_deg, lst_degrees(jd, lon_deg))
        if alt >= min_alt:
            n += 1
        t += datetime.timedelta(minutes=10)
    return n / 6.0


def _tonight_samples(ra_deg, dec_deg, lat_deg, lon_deg, date, step_min=10):
    # @return: list of (datetime, alt, az) sampled across tonight's darkness
    window = tonight_window(lat_deg, lon_deg, date)
    if not window:
        return []
    start, end = window
    out = []
    t = start
    while t <= end:
        jd = jd_from_datetime(t)
        alt, az = altaz(ra_deg, dec_deg, lat_deg, lst_degrees(jd, lon_deg))
        out.append((t, alt, az))
        t += datetime.timedelta(minutes=step_min)
    return out


def window_above(ra_deg, dec_deg, lat_deg, lon_deg, threshold_fn,
                 date=None, margin=0.0):
    # First and last instants an object is above the local horizon during
    # tonight's darkness. threshold_fn(az)->alt is a Horizon/FlatHorizon
    # alt_at callable (ADR-020); margin is the safety margin in degrees.
    # @return: (start_utc, end_utc) or None when it never clears the horizon
    samples = _tonight_samples(ra_deg, dec_deg, lat_deg, lon_deg, date)
    above = [t for (t, alt, az) in samples
             if alt >= threshold_fn(az) + margin]
    if not above:
        return None
    return above[0], above[-1]


def hours_above_h(ra_deg, dec_deg, lat_deg, lon_deg, threshold_fn,
                  date=None, margin=0.0):
    # Hours above the local horizon (threshold_fn + margin) during tonight.
    # @return: hours as float (0 if none)
    samples = _tonight_samples(ra_deg, dec_deg, lat_deg, lon_deg, date)
    n = sum(1 for (_t, alt, az) in samples
            if alt >= threshold_fn(az) + margin)
    return n / 6.0


def angular_separation(ra1_deg, dec1_deg, ra2_deg, dec2_deg):
    # Great-circle separation between two equatorial points (haversine).
    # @return: separation in degrees
    ra1, dec1, ra2, dec2 = (math.radians(x) for x in
                            (ra1_deg, dec1_deg, ra2_deg, dec2_deg))
    dra = ra2 - ra1
    a = math.sin((dec2 - dec1) / 2) ** 2 \
        + math.cos(dec1) * math.cos(dec2) * math.sin(dra / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(a))))
