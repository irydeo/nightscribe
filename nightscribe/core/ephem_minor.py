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
    # Solves Kepler's equation by Newton's method (works up to e < 1).
    # @args: m_deg - mean anomaly (degrees), e - eccentricity
    # @return: eccentric anomaly in degrees
    m = math.radians(m_deg)
    ea = m if e < 0.8 else m + e * math.sin(m)
    for _ in range(30):
        f = ea - e * math.sin(ea) - m
        fp = 1.0 - e * math.cos(ea)
        delta = f / fp
        ea -= delta
        if abs(delta) < 1e-12:
            break
    return math.degrees(ea)


def _open_orbit_ecliptic(n, i, w, q, e, nu_deg):
    # Open orbit (parabolic e=1 / hyperbolic e>1) position from true anomaly.
    # r = q(1+e) / (1 + e*cos(nu))
    # @args: n - node, i - inclination, w - arg perihelion,
    #        q - perihelion distance (AU), e - eccentricity (>=1),
    #        nu_deg - true anomaly (degrees)
    # @return: (x, y, z, r) in AU
    nu = math.radians(nu_deg)
    r = q * (1 + e) / (1 + e * math.cos(nu))
    ns, iw = math.radians(n), math.radians(i)
    ww = math.radians(w)
    x = r * (math.cos(ns) * math.cos(nu + ww)
             - math.sin(ns) * math.sin(nu + ww) * math.cos(iw))
    y = r * (math.sin(ns) * math.cos(nu + ww)
             + math.cos(ns) * math.sin(nu + ww) * math.cos(iw))
    z = r * math.sin(nu + ww) * math.sin(iw)
    return x, y, z, r


def _barker_true_anomaly(q, dt_days):
    # Barker's equation for parabolic orbits: D + D³/3 = B*(t-T),
    # D = tan(nu/2), B = k / (2*q^1.5), k = 0.01720209895
    # @args: q - perihelion distance (AU), dt_days - days since perihelion
    # @return: true anomaly in degrees
    B = 0.01720209895 / (2 * q ** 1.5)
    M = B * dt_days
    D = M if abs(M) < 1 else math.copysign(1.0, M)
    for _ in range(20):
        f = D + D ** 3 / 3 - M
        fp = 1 + D ** 2
        delta = f / fp
        D -= delta
        if abs(delta) < 1e-12:
            break
    return 2 * math.degrees(math.atan(D))


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


def _ecliptic_to_equatorial(x, y, z, jd):
    # Ecliptic -> equatorial J2000 rotation (same obliquity as _ecliptic_to_ra_dec).
    # @return: (xe, ye, ze)
    ecl = math.radians(23.4393 - 3.563e-7 * (jd - 2451543.5))
    return x, y * math.cos(ecl) - z * math.sin(ecl), y * math.sin(ecl) + z * math.cos(ecl)


def _ecliptic_to_ra_dec(x, y, z, jd):
    # Ecliptic rectangular -> equatorial RA/Dec (degrees).
    xe, ye, ze = _ecliptic_to_equatorial(x, y, z, jd)
    ra = _rev(math.degrees(math.atan2(ye, xe)))
    dec = math.degrees(math.atan2(ze, math.sqrt(xe * xe + ye * ye)))
    return ra, dec


_KM_AU_DAY = AU_KM / 86400.0  # 1 AU/day in km/s


def _mean_anomaly(elements, jd):
    # Resolves the mean anomaly at jd from either ma+epoch or tp.
    # @args: elements - dict with a, e, (ma or tp), (epoch), jd - Julian date
    # @return: mean anomaly (degrees) in [0, 360), or None
    a = elements.get("a")
    if a is None or a <= 0:
        return None
    if elements.get("ma") is not None:
        m0 = elements["ma"]
        epoch = elements.get("epoch", jd)
    elif elements.get("tp") is not None:
        m0 = 0.0
        epoch = elements["tp"]
    else:
        return None
    n_deg_day = 0.9856076686 / (a ** 1.5)
    return _rev(m0 + n_deg_day * (jd - epoch))


def state_vector_j2000(elements, jd):
    # Heliocentric state vector in the equatorial J2000 frame (two-body Kepler).
    # @args: elements - dict like kepler_ra_dec (a, e, i, om, w, ma or tp),
    #        jd - Julian date
    # @return: (px, py, pz, vx, vy, vz) in (AU, AU/day), or None if invalid
    m = _mean_anomaly(elements, jd)
    if m is None:
        return None
    a = elements["a"]
    e = elements.get("e", 0.0)
    om = elements.get("om", 0.0)
    inc = elements.get("i", 0.0)
    w = elements.get("w", 0.0)
    ea = math.radians(_kepler_e(m, e))
    xv = a * (math.cos(ea) - e)
    yv = a * math.sqrt(1 - e * e) * math.sin(ea)
    r = math.sqrt(xv * xv + yv * yv)
    if r <= 0:
        return None
    nu = math.atan2(yv, xv)
    # velocity components in the orbital plane (AU/day): mu/h * (e*sin nu, 1+e*cos nu)
    # where h = sqrt(mu * a * (1 - e^2)) is the specific angular momentum.
    GAUSS = 0.01720209895  # sqrt(GM_sun) in AU^1.5/day^0.5
    # specific angular momentum h = GAUSS * sqrt(a*(1-e^2));  mu/h = GAUSS/sqrt(a*(1-e^2))
    mu_over_h = GAUSS / math.sqrt(a * (1.0 - e * e))
    vr = mu_over_h * e * math.sin(nu)
    vt = mu_over_h * (1.0 + e * math.cos(nu))
    cos_nu, sin_nu = math.cos(nu), math.sin(nu)
    px_o, py_o = r * cos_nu, r * sin_nu
    vx_o, vy_o = (vr * cos_nu - vt * sin_nu, vr * sin_nu + vt * cos_nu)
    # perifocal -> ecliptic
    Cn, Sn = math.cos(math.radians(om)), math.sin(math.radians(om))
    Ci, Si = math.cos(math.radians(inc)), math.sin(math.radians(inc))
    Cw, Sw = math.cos(math.radians(w)), math.sin(math.radians(w))

    def rot(xp, yp):
        x = (Cn * Cw - Sn * Sw * Ci) * xp + (-Cn * Sw - Sn * Cw * Ci) * yp
        y = (Sn * Cw + Cn * Sw * Ci) * xp + (-Sn * Sw + Cn * Cw * Ci) * yp
        z = (Sw * Si * xp + Cw * Si * yp)
        return x, y, z

    px, py, pz = rot(px_o, py_o)
    vx, vy, vz = rot(vx_o, vy_o)
    # ecliptic -> equatorial J2000 (same obliquity as the RA/Dec path)
    ecl = math.radians(23.4393 - 3.563e-7 * (jd - 2451543.5))
    ce, se = math.cos(ecl), math.sin(ecl)

    def to_eq(x, y, z):
        return x, y * ce - z * se, y * se + z * ce

    return to_eq(px, py, pz) + to_eq(vx, vy, vz)


def _rotation_matrix_pq(om_deg, inc_deg, w_deg):
    # The first two columns of the perifocal->ecliptic Euler rotation:
    # P (toward perihelion) and Q (90 deg ahead, in the orbital plane).
    # @return: (P, Q) as (x, y, z) triples, unit length, ecliptic frame
    om = math.radians(om_deg)
    i = math.radians(inc_deg)
    w = math.radians(w_deg)
    Cn, Sn = math.cos(om), math.sin(om)
    Ci, Si = math.cos(i), math.sin(i)
    Cw, Sw = math.cos(w), math.sin(w)
    p = (Cn * Cw - Sn * Sw * Ci,
         Sn * Cw + Cn * Sw * Ci,
         Sw * Si)
    q = (-Cn * Sw - Sn * Cw * Ci,
         -Sn * Sw + Cn * Cw * Ci,
         Cw * Si)
    return p, q


def pq_vectors_j2000(elements, jd):
    # P and Q unit vectors of the orbit in the equatorial J2000 frame.
    # @args: elements - dict with i, om, w, jd - Julian date (only fixes obliquity)
    # @return: (P, Q) as (x,y,z) triples, or None if the orientation is missing
    if elements.get("w") is None or elements.get("om") is None or elements.get("i") is None:
        return None
    p, q = _rotation_matrix_pq(elements.get("om", 0.0),
                               elements.get("i", 0.0), elements.get("w", 0.0))
    return (_ecliptic_to_equatorial(*p, jd), _ecliptic_to_equatorial(*q, jd))


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


def earth_velocity_j2000(jd):
    # Heliocentric velocity of Earth in the equatorial J2000 frame.
    # Numerical derivative of earth_ecliptic_xyz (arcminute-level, matches the
    # position propagator).
    # @args: jd - Julian date
    # @return: (vx, vy, vz) in AU/day
    dt = 0.01  # 14.4 min — small enough for a 6-sig-fig derivative
    x0, y0, z0 = earth_ecliptic_xyz(jd - dt)
    x1, y1, z1 = earth_ecliptic_xyz(jd + dt)
    vx = (x1 - x0) / (2 * dt)
    vy = (y1 - y0) / (2 * dt)
    vz = (z1 - z0) / (2 * dt)
    # ecliptic -> equatorial J2000
    return _ecliptic_to_equatorial(vx, vy, vz, jd)


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
        "ecl_lat_deg": lat,  # ecliptic latitude (deg): the eclipse gate
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
    xg, yg, zg = xh - xe, yh - ye, zh - ze
    dist = math.sqrt(xg * xg + yg * yg + zg * zg)
    ra, dec = _ecliptic_to_ra_dec(xg, yg, zg, jd)
    mag = _PLANET_MAG0[name.lower()] + 5 * math.log10(max(r * dist, 1e-9))
    return {"ra": ra, "dec": dec, "dist_au": dist, "mag": round(mag, 1)}


# ---------------- Minor bodies ----------------

def observer_offset_ecliptic(lat_deg, lon_deg, height_m, jd):
    # Geocentric vector of the observer in the ecliptic J2000 frame.
    # @args: lat_deg - geodetic latitude, lon_deg - geodetic longitude (east+),
    #        height_m - height above sea level, jd - Julian date (TT, ~UT)
    # @return: (x, y, z) in AU
    d = jd - 2451543.5
    gast = _rev(280.46061837 + 360.98564736629 * d)  # GMST, deg
    phi = math.radians(lat_deg)
    r_au = (6378.14 + height_m) / AU_KM
    th = math.radians(gast + lon_deg)
    xe = r_au * math.cos(phi) * math.cos(th)
    ye = r_au * math.cos(phi) * math.sin(th)
    ze = r_au * math.sin(phi)
    # equatorial -> ecliptic (inverse of the _ecliptic_to_ra_dec rotation)
    ecl = math.radians(23.4393 - 3.563e-7 * d)
    ce, se = math.cos(ecl), math.sin(ecl)
    return xe, ye * ce + ze * se, -ye * se + ze * ce


def kepler_ra_dec(elements, jd, lat_deg=None, lon_deg=None, height_m=0.0):
    # Geocentric (or topocentric) RA/Dec of a minor body from its elements.
    # @args: elements - dict with a (AU), e, i, om (node), w (arg. peri.),
    #        ma (mean anomaly at epoch), epoch (JD); or tp instead of ma,
    #        jd - Julian date of interest,
    #        lat_deg/lon_deg - observer site (when given, a topocentric
    #        correction of order R_Earth/delta (~86" at delta = 0.1 AU) is
    #        applied), height_m - site height, default 0
    # @return: (ra_deg, dec_deg, r_au, delta_au) or None if invalid
    topo = lat_deg is not None

    def apply_topocentric(xg, yg, zg):
        # object as seen from the observer = geocentric - observer offset
        if not topo:
            return xg, yg, zg
        ox, oy, oz = observer_offset_ecliptic(lat_deg, lon_deg, height_m, jd)
        return xg - ox, yg - oy, zg - oz

    e = elements.get("e")
    if e is None:
        return None
    # parabolic orbit (e = 1.0): use Barker's equation
    if e >= 1.0:
        q = elements.get("q")
        tp = elements.get("tp")
        if q is None or tp is None or q <= 0:
            return None
        nu = _barker_true_anomaly(q, jd - tp)
        xo, yo, zo, r = _open_orbit_ecliptic(
            elements.get("om", 0.0), elements.get("i", 0.0),
            elements.get("w", 0.0), q, e, nu)
        xe, ye, ze = earth_ecliptic_xyz(jd)
        xg, yg, zg = apply_topocentric(xo - xe, yo - ye, zo - ze)
        delta = math.sqrt(xg * xg + yg * yg + zg * zg)
        ra, dec = _ecliptic_to_ra_dec(xg, yg, zg, jd)
        return ra, dec, r, delta
    # bound orbit: Kepler
    a = elements.get("a")
    if a is None or a <= 0:
        return None
    m = _mean_anomaly(elements, jd)
    if m is None:
        return None
    xo, yo, zo, r = _elements_to_ecliptic(
        elements.get("om", 0.0), elements.get("i", 0.0), elements.get("w", 0.0),
        a, e, m)
    xe, ye, ze = earth_ecliptic_xyz(jd)
    xg, yg, zg = apply_topocentric(xo - xe, yo - ye, zo - ze)
    delta = math.sqrt(xg * xg + yg * yg + zg * zg)
    ra, dec = _ecliptic_to_ra_dec(xg, yg, zg, jd)
    return ra, dec, r, delta
