############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Low-precision ephemeris module (Schlyter)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import math

# Paul Schlyter's classic low-precision algorithms (stjarnhimlen.se/comp/ppcomp.html)
# for the Sun, Moon and planets, plus Kepler propagation for minor bodies.
# Arcminute accuracy, offline, pure math (see ADR-009). Angles in degrees,
# distances in AU (Moon in Earth radii), epochs referred to J2000 (d = days
# since 2000 Jan 0.0 TT, close enough to UT for us).

AU_KM = 149597870.7
EARTH_RADII_KM = 6378.14


def _rev(x):
    # @return: angle normalised to [0, 360)
    return x % 360.0


def _kepler_e(m_deg, e):
    # Solves Kepler's equation by simple iteration (e < 0.8 always here).
    # @args: m_deg - mean anomaly (degrees), e - eccentricity
    # @return: eccentric anomaly in degrees
    m = math.radians(m_deg)
    ea = m + e * math.sin(m) * (1.0 + e * math.cos(m))
    for _ in range(10):
        ea = m + e * math.sin(ea)
    return math.degrees(ea)


def _elements_to_ecliptic(n, i, w, a, e, m_deg):
    # Orbital elements -> heliocentric ecliptic rectangular position.
    # @args: n - ascending node, i - inclination, w - argument of perihelion,
    #        a - semi-major axis (AU), e - eccentricity, m_deg - mean anomaly
    # @return: (x, y, z, r) in AU
    ea = _kepler_e(m_deg, e)
    xv = a * (math.cos(math.radians(ea)) - e)
    yv = a * math.sqrt(1 - e * e) * math.sin(math.radians(ea))
    v = math.atan2(yv, xv)
    r = math.sqrt(xv * xv + yv * yv)
    ns, iw = math.radians(n), math.radians(i)
    ww = math.radians(w)
    x = r * (math.cos(ns) * math.cos(v + ww) - math.sin(ns) * math.sin(v + ww) * math.cos(iw))
    y = r * (math.sin(ns) * math.cos(v + ww) + math.cos(ns) * math.sin(v + ww) * math.cos(iw))
    z = r * math.sin(v + ww) * math.sin(iw)
    return x, y, z, r


def _ecliptic_to_ra_dec(x, y, z, jd):
    # Ecliptic rectangular -> equatorial RA/Dec (degrees).
    ecl = math.radians(23.4393 - 3.563e-7 * (jd - 2451543.5))
    xe = x
    ye = y * math.cos(ecl) - z * math.sin(ecl)
    ze = y * math.sin(ecl) + z * math.cos(ecl)
    ra = _rev(math.degrees(math.atan2(ye, xe)))
    dec = math.degrees(math.atan2(ze, math.sqrt(xe * xe + ye * ye)))
    return ra, dec


# ---------------- Sun ----------------

def sun_ra_dec(jd):
    # @args: jd - Julian date
    # @return: (ra_deg, dec_deg, distance_au) geocentric
    d = jd - 2451543.5
    w = 282.9404 + 4.70935e-5 * d
    e = 0.016709 - 1.151e-9 * d
    m = _rev(356.0470 + 0.9856002585 * d)
    ea = _kepler_e(m, e)
    xv = math.cos(math.radians(ea)) - e
    yv = math.sqrt(1 - e * e) * math.sin(math.radians(ea))
    v = math.degrees(math.atan2(yv, xv))
    r = math.sqrt(xv * xv + yv * yv)
    lon = _rev(v + w)
    xs = r * math.cos(math.radians(lon))
    ys = r * math.sin(math.radians(lon))
    ra, dec = _ecliptic_to_ra_dec(xs, ys, 0.0, jd)
    return ra, dec, r


def earth_ecliptic_xyz(jd):
    # @args: jd - Julian date
    # @return: (x, y, z) heliocentric ecliptic position of Earth in AU
    ra, dec, r = sun_ra_dec(jd)  # Sun geocentric = -Earth heliocentric
    ecl = math.radians(23.4393 - 3.563e-7 * (jd - 2451543.5))
    xs = r * math.cos(math.radians(dec)) * math.cos(math.radians(ra))
    ys = r * math.cos(math.radians(dec)) * math.sin(math.radians(ra))
    zs = r * math.sin(math.radians(dec))
    # back to ecliptic frame and flip sign
    xe = xs
    ye = ys * math.cos(ecl) + zs * math.sin(ecl)
    ze = -ys * math.sin(ecl) + zs * math.cos(ecl)
    return -xe, -ye, -ze


# ---------------- Moon ----------------

def moon(jd):
    # Moon position, distance and phase (main perturbations included).
    # @args: jd - Julian date
    # @return: dict with ra, dec (deg), dist_km, illum (0-1), phase_age_days
    d = jd - 2451543.5
    n = _rev(125.1228 - 0.0529538083 * d)
    i = 5.1454
    w = _rev(318.0634 + 0.1643573223 * d)
    a = 60.2666
    e = 0.054900
    m = _rev(115.3654 + 13.0649929509 * d)

    x, y, z, r = _elements_to_ecliptic(n, i, w, a, e, m)
    lon = _rev(math.degrees(math.atan2(y, x)))
    lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))

    # Sun mean elements, needed by the perturbation terms
    ms = _rev(356.0470 + 0.9856002585 * d)
    ws = 282.9404 + 4.70935e-5 * d
    ls = _rev(ms + ws)
    lm = _rev(n + w + m)
    dd = _rev(lm - ls)
    f = _rev(lm - n)

    # The big perturbation terms (Schlyter); degrees and Earth radii
    plon = (-1.274 * math.sin(math.radians(m - 2 * dd))
            + 0.658 * math.sin(math.radians(2 * dd))
            - 0.186 * math.sin(math.radians(ms))
            - 0.059 * math.sin(math.radians(2 * m - 2 * dd))
            - 0.057 * math.sin(math.radians(m - 2 * dd + ms))
            + 0.053 * math.sin(math.radians(m + 2 * dd))
            + 0.046 * math.sin(math.radians(2 * dd - ms))
            + 0.041 * math.sin(math.radians(m - ms))
            - 0.035 * math.sin(math.radians(dd))
            - 0.031 * math.sin(math.radians(m + ms))
            - 0.015 * math.sin(math.radians(2 * f - 2 * dd))
            + 0.011 * math.sin(math.radians(m - 4 * dd)))
    plat = (-0.173 * math.sin(math.radians(f - 2 * dd))
            - 0.055 * math.sin(math.radians(m - f - 2 * dd))
            - 0.046 * math.sin(math.radians(m + f - 2 * dd))
            + 0.033 * math.sin(math.radians(f + 2 * dd))
            + 0.017 * math.sin(math.radians(2 * m + f)))
    pdist = -0.58 * math.cos(math.radians(m - 2 * dd)) - 0.46 * math.cos(math.radians(2 * dd))

    lon = _rev(lon + plon)
    lat += plat
    r += pdist

    xe = r * math.cos(math.radians(lon)) * math.cos(math.radians(lat))
    ye = r * math.sin(math.radians(lon)) * math.cos(math.radians(lat))
    ze = r * math.sin(math.radians(lat))
    ra, dec = _ecliptic_to_ra_dec(xe, ye, ze, jd)

    elong = _rev(lon - ls)
    if elong > 180:
        elong -= 360
    illum = (1 + math.cos(math.radians(180 - abs(elong)))) / 2
    age = (abs(elong) / 360.0) * 29.53059
    if elong < 0:
        age = 29.53059 - age

    return {
        "ra": ra, "dec": dec,
        "dist_km": r * EARTH_RADII_KM,
        "illum": illum,
        "phase_age_days": age,
        "elong_deg": elong,
    }


# ---------------- Planets ----------------

# Schlyter elements: (N0, Ndot, i0, idot, w0, wdot, a0, adot, e0, edot, M0, Mdot)
_PLANETS = {
    "mercury": (48.3313, 3.24587e-5, 7.0047, 5.00e-8, 29.1241, 1.01444e-5,
                0.387098, 0.0, 0.205635, 5.59e-10, 168.6562, 4.0923344368),
    "venus": (76.6799, 2.46590e-5, 3.3946, 2.75e-8, 54.8910, 1.38374e-5,
              0.723330, 0.0, 0.006773, -1.302e-9, 48.0052, 1.6021302244),
    "mars": (49.5574, 2.11081e-5, 1.8497, -1.78e-8, 286.5016, 2.92961e-5,
             1.523688, 0.0, 0.093405, 2.516e-9, 18.6021, 0.5240207766),
    "jupiter": (100.4542, 2.76854e-5, 1.3030, -1.557e-7, 273.8777, 1.64505e-5,
                5.20256, 0.0, 0.048498, 4.469e-9, 19.8950, 0.0830853001),
    "saturn": (113.6634, 2.38980e-5, 2.4886, -1.081e-7, 339.3939, 2.97661e-5,
               9.55475, 0.0, 0.055546, -9.499e-9, 316.9670, 0.0334442282),
    "uranus": (74.0005, 1.3978e-5, 0.7733, 1.9e-8, 96.6612, 3.0565e-5,
               19.18171, -1.55e-8, 0.047318, 7.45e-9, 142.5905, 0.011725806),
    "neptune": (131.7806, 3.0173e-5, 1.7700, -2.55e-7, 272.8461, -6.027e-6,
                30.05826, 3.313e-8, 0.008606, 2.15e-9, 260.2471, 0.005995147),
}

# Rough magnitude recipe: mag0 + 5*log10(r*R) + phase coefficient
_PLANET_MAG0 = {"mercury": -0.36, "venus": -4.34, "mars": -1.51,
                "jupiter": -9.25, "saturn": -8.88, "uranus": -7.19,
                "neptune": -6.87}


def planet(name, jd):
    # Geocentric position and rough magnitude of a planet.
    # @args: name - planet name (lowercase, no Earth), jd - Julian date
    # @return: dict with ra, dec (deg), dist_au (geocentric), mag
    p = _PLANETS[name.lower()]
    d = jd - 2451543.5
    n = _rev(p[0] + p[1] * d)
    i = p[2] + p[3] * d
    w = _rev(p[4] + p[5] * d)
    a = p[6] + p[7] * d
    e = p[8] + p[9] * d
    m = _rev(p[10] + p[11] * d)
    xh, yh, zh, r = _elements_to_ecliptic(n, i, w, a, e, m)

    xe, ye, ze = earth_ecliptic_xyz(jd)
    xg, yg, zg = xh + xe, yh + ye, zh + ze
    dist = math.sqrt(xg * xg + yg * yg + zg * zg)
    ra, dec = _ecliptic_to_ra_dec(xg, yg, zg, jd)
    mag = _PLANET_MAG0[name.lower()] + 5 * math.log10(max(r * dist, 1e-9))
    return {"ra": ra, "dec": dec, "dist_au": dist, "mag": round(mag, 1)}


# ---------------- Minor bodies ----------------

def kepler_ra_dec(elements, jd):
    # Geocentric RA/Dec of a minor body from its orbital elements.
    # @args: elements - dict with a (AU), e, i, om (node), w (arg. peri.),
    #        ma (mean anomaly at epoch), epoch (JD); or tp instead of ma,
    #        jd - Julian date of interest
    # @return: (ra_deg, dec_deg, r_au, delta_au) or None if hyperbolic/invalid
    a = elements.get("a")
    e = elements.get("e")
    if a is None or e is None or e >= 0.99:
        return None
    epoch = elements.get("epoch", jd)
    if elements.get("ma") is not None:
        m0 = elements["ma"]
    elif elements.get("tp") is not None:
        n_deg_day = 0.9856076686 / (a ** 1.5)  # Gauss constant in deg/day
        m0 = _rev(n_deg_day * (epoch - elements["tp"]))
    else:
        return None
    n_deg_day = 0.9856076686 / (a ** 1.5)
    m = _rev(m0 + n_deg_day * (jd - epoch))

    xo, yo, zo, r = _elements_to_ecliptic(
        elements.get("om", 0.0), elements.get("i", 0.0), elements.get("w", 0.0),
        a, e, m)
    xe, ye, ze = earth_ecliptic_xyz(jd)
    xg, yg, zg = xo + xe, yo + ye, zo + ze
    delta = math.sqrt(xg * xg + yg * yg + zg * zg)
    ra, dec = _ecliptic_to_ra_dec(xg, yg, zg, jd)
    return ra, dec, r, delta
