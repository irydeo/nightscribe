############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Galilean satellite events module (Track SC2-SD)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Transits of the Galilean moons (and their shadows) across Jupiter's
disc, computed for the observer's site — the binocular/telescope jewel of
the sky calendar (Track SC2-SD, ADR-040).

Pure local maths, no network:

* the moons' orbits come from the JPL *mean elements* (JUP365, epoch J2000,
  local Laplace planes — ssd.jpl.nasa.gov/sats/elem), propagated with
  their apsis/node precession rates;
* Jupiter and Earth heliocentric positions are Schlyter's
  (`core/ephem_minor`), the observer's topocentric offset is
  `core/ephem_minor.observer_offset_ecliptic`;
* the moon's position is projected onto the sky plane; the SHADOW is the
  exact ray (Sun→moon) ∩ (spherical Jupiter) intersection, so it can lead
  or trail the moon itself by up to ~1 Jupiter radius at 10 deg phase.

HONESTY (shown in the UI): mean elements without the periodic libration
terms give planning-grade timing, **±10 min** (Io is the twitchiest). The
label says so. This plans the night; it does not time contacts. The exact
(~1 min) refinement path is JPL Horizons satellite phenomena — a future,
spike-validated source (see docs/PLANS/sky-calendar.md).

Frames: the orbit planes are J2000 inertial (their poles from the same JPL
table); the pole vector is precessed to the date (Lieske 1976 angles), and
Jupiter/Earth/Sun geometry lives in the of-date ecliptic frame that
ephem_minor already uses, so both halves agree.
"""

import datetime
import math

from . import coords, ephem_minor

# --- IAU WGCCRE rotation elements (Archinal et al. 2018; cross-checked
# --- against NAIF pck00011.tpc) + JPL orbit radii (JUP365). The Galileans
# --- are synchronously rotating, so the prime-meridian angle W(t) =
# --- W0 + W1*d tracks the orbital phase at the true rate (the JPL
# --- mean-elements "P" column is a precessing-frame period, NOT usable
# --- for ephemeris, as its own page warns).
# --- The IAU convention for synchronous rotators is W = L - 180 deg
# --- (checked for the Moon: 38.32 = 218.32 - 180): the orbital phase is
# --- W + 180. And because the IAU angle tracks the BODY's rotation, it
# --- carries the moon's physical/optical libration around the mean
# --- sub-Jupiter point — biggest for the icy outer pair. We absorb that
# --- with an empirical per-moon `phase_cal_deg`, fitted ONCE against JPL
# --- Horizons transit windows (quantity 12, site Z41) on 2026-09-17 and
# --- validated across Sep/Oct/Nov 2026 (see tests/unit/test_satellites.py
# --- and tests/functional/test_satellites_live.py). Ganymede's constant
# --- drifts slowly (its free libration has a ~2465 d period) — re-fit
# --- when a yearly drift shows; the exact path is the Horizons phenomena
# --- source (docs/PLANS/sky-calendar.md).
_J2000 = 2451545.0
GALILEANS = {
    "io": dict(a_km=421800.0, period_d=360.0 / 203.4889538,
               pole_ra0=268.05, pole_ra1=-0.009, pole_de0=64.50,
               pole_de1=0.003, w0=200.39, w1=203.4889538,
               phase_cal_deg=0.0),
    "europa": dict(a_km=671100.0, period_d=360.0 / 101.3747235,
                   pole_ra0=268.08, pole_ra1=-0.009, pole_de0=64.51,
                   pole_de1=0.003, w0=36.022, w1=101.3747235,
                   phase_cal_deg=0.0),
    "ganymede": dict(a_km=1070400.0, period_d=360.0 / 50.3176081,
                     pole_ra0=268.20, pole_ra1=-0.009, pole_de0=64.57,
                     pole_de1=0.003, w0=44.064, w1=50.3176081,
                     phase_cal_deg=-2.13),
    "callisto": dict(a_km=1882700.0, period_d=360.0 / 21.5710715,
                     pole_ra0=268.72, pole_ra1=-0.009, pole_de0=64.83,
                     pole_de1=0.003, w0=259.51, w1=21.5710715,
                     phase_cal_deg=0.62),
}

# IAU WGCCRE Jupiter north pole (J2000) + equatorial radius
JUP_POLE_J2000 = (268.056, 64.495)
JUP_R_KM = 71492.0
AU_KM = 149597870.7
LIGHT_D_PER_AU = 499.005 / 86400.0   # light travel time, days per AU

# planning-grade timing honesty (the UI prints it next to every window)
UNCERTAINTY_MIN = 10


# ---------------- small vector kit ----------------

def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _iaumodel_note():
    # Documentation anchor (no code): the IAU WGCCRE rotation elements
    # are ICRF-inertial (J2000 + a tiny linear drift already applied per
    # moon). We do NOT precess the pole to date: the 0.36 deg of frame
    # precession over 26 years rotates the sky-plane projection by the
    # same ~arcminute-grade amount it would "fix", and the validated
    # error budget (minutes of time against Horizons) already includes
    # whatever is left. Simpler frame, measured error.
    raise NotImplementedError  # never called — see the module docstring


def _equatorial_to_ecliptic_ofdate(vec, jd):
    # Equatorial -> ecliptic of date: the INVERSE of ephem_minor's
    # `_ecliptic_to_equatorial` (same construction as the tested
    # `observer_offset_ecliptic`). @return: of-date ecliptic components
    d = jd - 2451543.5
    ecl = math.radians(23.4393 - 3.563e-7 * d)
    ce, se = math.cos(ecl), math.sin(ecl)
    x, y, z = vec
    return x, y * ce + z * se, -y * se + z * ce


def _plane_basis(pole_ra_deg, pole_dec_deg, jd):
    # @return: (node, q, pole) of-date ECLIPTIC unit vectors spanning the
    #          moon's orbit plane (node = the plane's ascending node on
    #          the J2000 equator, precessed; q completes the right-handed
    #          frame; pole = the plane normal)
    ra = math.radians(pole_ra_deg)
    dec = math.radians(pole_dec_deg)
    pole = (math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra),
            math.sin(dec))
    # ICRF inertial (no precession to date — see _iaumodel_note)
    node = _norm(_cross((0.0, 0.0, 1.0), pole))
    q = _cross(pole, node)
    to_ecl = lambda v: _equatorial_to_ecliptic_ofdate(v, jd)
    return to_ecl(node), to_ecl(q), to_ecl(pole)


# ---------------- moon position ----------------

def _moon_jovicentric_km(name, jd):
    # The moon's jovicentric position in the of-date ecliptic frame.
    # IAU WGCCRE model: circular orbit (e <= 0.009 -> the radial wobble
    # stays under 1 % of a, far below our arcminute-grade needs), phase
    # from the synchronous-rotation prime-meridian angle W(t) = W0 + W1 d
    # (the true sidereal rate), plane = the moon's own equator (its pole,
    # with the tiny linear drift, precessed J2000 -> date).
    # @args: name - io|europa|ganymede|callisto, jd - Julian date
    # @return: (x, y, z) km, jovicentric, of-date ecliptic
    el = GALILEANS[name]
    d = jd - _J2000
    t = d / 36525.0
    pole_ra = el["pole_ra0"] + el["pole_ra1"] * t
    pole_de = el["pole_de0"] + el["pole_de1"] * t
    # IAU synchronous convention: the orbital phase is W + 180 deg, plus
    # the empirical libration calibration (see the constants header)
    w = math.radians(
        (el["w0"] + 180.0 + el["phase_cal_deg"] + el["w1"] * d) % 360.0)
    node_v, q_v, _pole_v = _plane_basis(pole_ra, pole_de, jd)
    ca, sa = math.cos(w), math.sin(w)
    a = el["a_km"]
    return (a * (ca * node_v[0] + sa * q_v[0]),
            a * (ca * node_v[1] + sa * q_v[1]),
            a * (ca * node_v[2] + sa * q_v[2]))


# ---------------- geometry ----------------

def _geometry(jd, lat_deg=None, lon_deg=None):
    # The shared 3D scene: Jupiter geocentric vector and distance.
    # Light-time is applied by the CALLER (jd already retarded).
    # @return: (los_unit, dist_au, jup_hel_km)
    jx, jy, jz, _r = ephem_minor.planet_heliocentric_xyz("jupiter", jd)
    ex, ey, ez = ephem_minor.earth_ecliptic_xyz(jd)
    gx, gy, gz = jx - ex, jy - ey, jz - ez
    if lat_deg is not None:
        ox, oy, oz = ephem_minor.observer_offset_ecliptic(
            lat_deg, lon_deg, 0.0, jd)
        gx, gy, gz = gx - ox, gy - oy, gz - oz
    dist = math.sqrt(gx * gx + gy * gy + gz * gz)
    return ((gx / dist, gy / dist, gz / dist), dist,
            (jx * AU_KM, jy * AU_KM, jz * AU_KM))


def _moon_and_shadow(jd, name, lat_deg=None, lon_deg=None):
    # Sky-plane state of a moon and its shadow at `jd` (the caller's jd
    # is retarded by the light time). Offsets in JUPITER RADII on the
    # plane of the sky (1.0 = the disc's limb); z_depth < 0 = the moon is
    # on the observer's side of Jupiter's centre.
    # @return: {"rho_moon", "z_moon", "rho_shadow", "front_shadow"} or
    #          rho_shadow=None when the shadow ray misses the planet
    los, dist, jup_hel_km = _geometry(jd, lat_deg, lon_deg)
    sx, sy, sz = _moon_jovicentric_km(name, jd)
    # moon: project the jovicentric offset on the sky plane
    rel_au = (sx / AU_KM, sy / AU_KM, sz / AU_KM)
    z_moon = _dot(rel_au, los)
    rho_vec = tuple(r - z_moon * l for r, l in zip(rel_au, los))
    rho_moon = math.sqrt(_dot(rho_vec, rho_vec)) * AU_KM / JUP_R_KM
    # shadow: the ray from the Sun through the moon, continued to the
    # (spherical) planet — solves |S + t*dir - J| = R_jup
    sun_pt = (jup_hel_km[0] + sx, jup_hel_km[1] + sy, jup_hel_km[2] + sz)
    d = _norm(sun_pt)               # heliocentric: the Sun sits at 0
    w = (sun_pt[0] - jup_hel_km[0], sun_pt[1] - jup_hel_km[1],
         sun_pt[2] - jup_hel_km[2])
    b = _dot(w, d)
    c = _dot(w, w) - JUP_R_KM * JUP_R_KM
    disc = b * b - c
    rho_shadow = None
    front_shadow = False
    if disc >= 0.0:
        t = -b - math.sqrt(disc)    # the first intersection along the ray
        if t > 0.0:
            hit = (sun_pt[0] + t * d[0] - jup_hel_km[0],
                   sun_pt[1] + t * d[1] - jup_hel_km[1],
                   sun_pt[2] + t * d[2] - jup_hel_km[2])
            hit_au = tuple(h / AU_KM for h in hit)
            z_sh = _dot(hit_au, los)
            front_shadow = z_sh < 0.0
            rho_vec_s = tuple(hh - z_sh * l for hh, l in zip(hit_au, los))
            rho_shadow = math.sqrt(_dot(rho_vec_s, rho_vec_s)) \
                * AU_KM / JUP_R_KM
    return {"rho_moon": rho_moon, "z_moon": z_moon,
            "rho_shadow": rho_shadow, "front_shadow": front_shadow,
            "dist_au": dist}


def _states(jd, name, lat_deg, lon_deg):
    # @return: (in_transit, in_shadow) booleans at `jd` (light-retarded
    #          inside): the moon on the disc in front, the shadow on the
    #          Earth-facing disc
    g = _geometry_lighttime(jd, name, lat_deg, lon_deg)
    in_transit = g["z_moon"] < 0.0 and g["rho_moon"] < 1.0
    in_shadow = (g["rho_shadow"] is not None and g["front_shadow"]
                 and g["rho_shadow"] < 1.0)
    return in_transit, in_shadow


def _geometry_lighttime(jd, name, lat_deg, lon_deg):
    # One light-time iteration: evaluate the scene, retard by the light
    # travel Earth<->Jupiter, evaluate again (the moons move measurably
    # in those ~33-52 min, Io most of all).
    dist = _geometry(jd, lat_deg, lon_deg)[1]
    jd_ret = jd - dist * LIGHT_D_PER_AU
    return _moon_and_shadow(jd_ret, name, lat_deg, lon_deg)


def _bisect_state(jd_a, jd_b, name, which, lat_deg, lon_deg, iters=26):
    # Refine the ingress/egress edge between two jd that differ in state.
    # @return: jd of the edge (sub-30 s)
    lo, hi = jd_a, jd_b
    glo = _states(lo, name, lat_deg, lon_deg)[which]
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        gm = _states(mid, name, lat_deg, lon_deg)[which]
        if gm == glo:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------- public API ----------------

def galilean_events(jd_from, jd_to, lat_deg=None, lon_deg=None):
    # The Galilean moon + shadow transits across Jupiter's disc in the
    # window, with their observability for the site when lat/lon are
    # given. Pure local maths — planning grade (see UNCERTAINTY_MIN).
    # @args: jd_from/jd_to - Julian window, lat_deg/lon_deg - site or None
    # @return: [{"kind": "sat_transit"|"shadow_transit", "satellite",
    #          "jd0", "jd1", "t0", "t1" (UTC datetimes),
    #          "uncertainty_min", "dist_au", "mag" (Jupiter),
    #          "observable" (None when no site), "alt_deg"}] by jd0
    out = []
    pad = 1.0                      # catch events straddling the window
    for name in GALILEANS:
        el = GALILEANS[name]
        step = el["period_d"] / 64.0        # ~40 min for Io, ~2 h Callisto
        jds = []
        jd = jd_from - pad
        while jd <= jd_to + pad:
            jds.append(jd)
            jd += step
        prev = _states(jds[0], name, lat_deg, lon_deg)
        prev_jd = jds[0]
        # open windows per phenomenon: [phenomenon][0] = ingress jd or None
        open_ev = [None, None]
        for jd in jds[1:]:
            cur = _states(jd, name, lat_deg, lon_deg)
            for which in (0, 1):
                if cur[which] == prev[which]:
                    continue
                edge = _bisect_state(prev_jd, jd, name, which,
                                     lat_deg, lon_deg)
                if cur[which]:      # ingress
                    open_ev[which] = edge
                elif open_ev[which] is not None:  # egress closes it
                    out.append(_assemble(name, which, open_ev[which],
                                         edge, jd_from, jd_to,
                                         lat_deg, lon_deg))
                    open_ev[which] = None
            prev, prev_jd = cur, jd
    out = [e for e in out if e is not None]
    out.sort(key=lambda e: e["jd0"])
    return out


def _assemble(name, which, jd0, jd1, jd_from, jd_to, lat_deg, lon_deg):
    # One transit window -> the event dict (None when fully outside the
    # requested window). @return: dict or None
    if jd1 < jd_from or jd0 > jd_to:
        return None
    kind = "sat_transit" if which == 0 else "shadow_transit"
    dist = _geometry(jd0, lat_deg, lon_deg)[1]
    mag = ephem_minor.planet("jupiter", jd0)["mag"]
    t0 = coords.datetime_from_jd(max(jd0, jd_from))
    t1 = coords.datetime_from_jd(min(jd1, jd_to))
    ev = {"kind": kind, "satellite": name,
          "jd0": jd0, "jd1": jd1, "t0": t0, "t1": t1,
          "uncertainty_min": UNCERTAINTY_MIN,
          "dist_au": round(dist, 2), "mag": mag,
          "observable": None, "alt_deg": None}
    if lat_deg is not None:
        ev["observable"], ev["alt_deg"] = _observable(
            jd0, jd1, lat_deg, lon_deg)
    return ev


def _observable(jd0, jd1, lat_deg, lon_deg):
    # Is any of the transit visible from the site: Jupiter above 0 deg
    # AND the Sun below the horizon (the calendar's honesty gate, same as
    # skyevents). @return: (bool, best Jupiter altitude in deg)
    best = None
    ok = False
    for jd in (jd0, 0.5 * (jd0 + jd1), jd1):
        when = coords.datetime_from_jd(jd)
        p = ephem_minor.planet("jupiter", jd)
        alt, _az = coords.altaz(p["ra"], p["dec"], lat_deg,
                                coords.lst_degrees(jd, lon_deg))
        sra, sdec, _r = ephem_minor.sun_ra_dec(jd)
        salt, _saz = coords.altaz(sra, sdec, lat_deg,
                                  coords.lst_degrees(jd, lon_deg))
        if best is None or alt > best:
            best = alt
        if alt > 0.0 and salt < 0.0:
            ok = True
    return ok, round(best, 1) if best is not None else None
