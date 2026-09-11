############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Long-period variable stars module (ADR-035)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Long-period variable stars: cycle maths, heliocentric dates and the
brightness-event advisor.

The molde is the multi-night follow-up (Track B): one point per night and
filter, folded later by the catalog period. All functions are pure and
local — no network, no db. Times are MJD inside the module; the VSX Epoch
arrives as JD and is converted by the VSX parser (MJD = JD - 2400000.5).
"""

import logging
import math
import statistics
import time

logger = logging.getLogger(__name__)

MJD0 = 2400000.5          # MJD = JD - MJD0

# VSX convention (V-e): for eclipsing binaries the Epoch marks the MINIMUM
# (primary eclipse); for pulsating/eruptive stars it marks the MAXIMUM.
# The FIRST component of a composite type decides: "E-DO" eclipses,
# "NR+ELL" does not (there ELL is the orbital ellipsoidal modulation).
_EPOCH_MIN_PREFIXES = ("EA", "EB", "EW", "E/", "E-")


def _epoch_is_minimum(var_type):
    # @args: var_type - VSX variability type, e.g. "M", "NR+ELL", "E-DO"
    # @return: True when the VSX Epoch marks the light minimum
    first = (var_type or "").split("+")[0].strip().upper()
    return first == "E" or first.startswith(_EPOCH_MIN_PREFIXES)


def _now_mjd():
    # @return: current MJD (UTC)
    return time.time() / 86400.0 + 2440587.5 - MJD0


def phase_at(mjd, period_d, epoch_mjd):
    # @args: mjd - instant, period_d - period in days, epoch_mjd - cycle
    #        epoch (phase 0)
    # @return: phase in [0, 1), or None when the ephemeris is incomplete
    if not period_d or epoch_mjd is None:
        return None
    return ((mjd - epoch_mjd) / period_d) % 1.0


def next_extremum(period_d, epoch_mjd, now_mjd=None, var_type=""):
    # The next extremum of the cycle from now — maximum for pulsating
    # stars, minimum for eclipsing ones (V-e) — whichever comes FIRST,
    # labelled, so Tonight can say "maximum expected in ~N days".
    # @return: {"kind": "max"|"min", "mjd": float, "days": float} or None
    if not period_d or epoch_mjd is None:
        return None
    now = now_mjd if now_mjd is not None else _now_mjd()
    if _epoch_is_minimum(var_type):
        min_ep, max_ep = epoch_mjd, epoch_mjd + period_d / 2.0
    else:
        max_ep, min_ep = epoch_mjd, epoch_mjd + period_d / 2.0

    def _next(ep):
        # @return: mjd of the first occurrence of epoch `ep` at/after now
        n = math.ceil((now - ep) / period_d - 1e-9)
        return ep + n * period_d

    nmax, nmin = _next(max_ep), _next(min_ep)
    if nmax <= nmin:
        return {"kind": "max", "mjd": nmax, "days": round(nmax - now, 1)}
    return {"kind": "min", "mjd": nmin, "days": round(nmin - now, 1)}


# ---------------- heliocentric Julian date ----------------

_LIGHT_TIME_S_PER_AU = 499.004784   # 1 AU / c, in seconds


def jd_to_hjd(jd, ra_deg, dec_deg):
    # Heliocentric Julian Date: the geocentric JD corrected for the light
    # travel time between Earth and Sun (at most +/-499 s). AAVSO reports
    # are filed in HJD. The Sun position is Schlyter's (ephem_minor,
    # ADR-009), good to ~1 arcmin -> <0.2 s here, far below photometric
    # needs. Convention (checked): a star in the Sun's direction is seen
    # EARLIER from Earth, so HJD = JD + (n . s) * r * tau.
    # @args: jd - Julian date (UTC), ra_deg/dec_deg - target (degrees)
    # @return: HJD (float)
    from . import ephem_minor
    sra, sdec, r = ephem_minor.sun_ra_dec(jd)
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    sra, sdec = math.radians(sra), math.radians(sdec)
    dot = (math.cos(dec) * math.cos(ra) * math.cos(sdec) * math.cos(sra)
           + math.cos(dec) * math.sin(ra) * math.cos(sdec) * math.sin(sra)
           + math.sin(dec) * math.sin(sdec))
    return jd + dot * r * _LIGHT_TIME_S_PER_AU / 86400.0
