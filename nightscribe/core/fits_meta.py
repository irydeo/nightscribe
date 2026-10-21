############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - FITS metadata extractor (Track B, B1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Extracts observation metadata from a FITS header.

The follow-up panel (B2) and the series engine (B5) need the observation
date, filter and exposure from the stacked image. fits_io preserves the
full header dict (ADR-018); this module is a thin, tolerant wrapper that
pulls the relevant cards and computes MJD.
"""

import datetime
import logging
import re

from . import coords, fits_io

logger = logging.getLogger(__name__)

# FITS date keywords tried in order — DATE-OBS is the classic, but some
# pipelines write DATE or UTC-OBS instead.
_DATE_KEYS = ("DATE-OBS", "DATE", "UTC-OBS")
_MJD_KEYS = ("MJD-OBS", "MJD")          # numeric UTC, when the header has it
_FILTER_KEYS = ("FILTER", "FILTERS", "FILT")
_EXPTIME_KEYS = ("EXPTIME", "EXPOSURE", "ELAPSED")

# THE PLATE'S OWN SITE AND AIRMASS, when it declares them.
#
# Why this matters, measured 2026-10-21 on a Las Cumbres plate (1 m at
# McDonald, Texas) measured from a site in Spain: the engine was computing
# the target's altitude from the OBSERVER's Settings, so the airmass came
# out rising to 5.2 through the night while the plate's own header said
# 1.16 -> 1.03. That airmass feeds the scintillation term of the error
# (Young), and the error went from 0.05 to 0.39 mag over the night, which
# the chart reads as green -> orange -> red. With the plate's own airmass
# the same errors are flat at 0.03. The plate knows where it was taken; the
# observer's Settings are for the observer's own plates.
#
# Same rule astap.py already applies to the plate scale ("the image's own
# scale beats the observer's Settings: a foreign plate carries IM_SCALE").
_SITE_KEYS = (("SITELAT", "SITELONG"), ("LATITUDE", "LONGITUD"),
              ("LAT-OBS", "LONG-OBS"), ("OBSLAT", "OBSLONG"),
              ("LATITUDE", "LONGITUDE"))
_AIRMASS_KEYS = ("AIRMASS", "SECZ")     # SECZ is sec(z), the same number

# The telescope's diameter, when the plate's own name says it.
#
# Las Cumbres writes the aperture into the telescope's id: 0m4a is a 0.4 m,
# 1m0a is a 1 m, 2m0a is a 2 m, and TELESCOP carries the same prefix
# ('0m4-63'). It is the ONE convention in these headers that states the
# diameter instead of leaving it to be guessed, and guessing is exactly what
# this module refuses to do: 'Cecilia' (MicroObservatory) and 'CDK17' (a
# model) say nothing about the size, and inventing a number from them would
# be worse than falling back to the observer's Settings, which for the
# observer's OWN telescope is the right answer anyway.
_APERTURE_RE = re.compile(r"^(\d)m(\d)(?!\d)")
_APERTURE_KEYS = ("TELID", "TELESCOP")
_APERTURE_RANGE_M = (0.05, 30.0)        # a finder to a large amateur


def _parse_fits_date(raw):
    # @args: raw - string from a FITS DATE-OBS card
    # @return: timezone-aware UTC datetime, or None if unparseable
    # Tolerates both "2026-09-09" and "2026-09-09T22:30:00.123" (ISO 8601),
    # plus the legacy "09/09/26" dd/mm/yy format some cameras still write.
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d", "%d/%m/%y"):
        try:
            dt = datetime.datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except ValueError:
            continue
    logger.debug("unparseable FITS date: %s", raw)
    return None


def aperture_from_header(header):
    # The telescope's diameter, in METRES, as the plate itself declares it.
    #
    # It feeds the scintillation term of the error (Young), which goes with
    # the diameter: on a Las Cumbres 1 m measured with the observer's 10"
    # that term comes out 2.5 times too big (0.032 mag against the honest
    # 0.013), and it is the term that dominates an otherwise quiet night.
    # @args: header - dict from fits_io.read_header / read_fits
    # @return: the diameter in metres, or None when the plate does not say.
    #          None is a real answer here (see _APERTURE_RE): a name that
    #          says nothing must not become a number.
    for key in _APERTURE_KEYS:
        raw = header.get(key)
        if raw is None:
            continue
        m = _APERTURE_RE.match(str(raw).strip())
        if not m:
            continue
        metres = int(m.group(1)) + int(m.group(2)) / 10.0
        if _APERTURE_RANGE_M[0] <= metres <= _APERTURE_RANGE_M[1]:
            return metres
    return None


def _num(raw):
    # @args: raw - a header value
    # @return: it as a float, or None when it is not a number
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def site_from_header(header):
    # The site the PLATE was taken from, as the plate declares it.
    #
    # The observer's Settings describe the observer's own observatory: on a
    # plate from another one they are simply wrong, and the airmass they
    # produce is wrong with them (measured 2026-10-21: 5.2 instead of 1.03
    # on a Las Cumbres frame, which inflated the error from 0.03 to 0.39 mag
    # through the night). The plate knows where it was taken.
    # @args: header - dict from fits_io.read_header / read_fits
    # @return: (lat_deg, lon_deg), or (None, None) when the plate does not
    #          say. Longitude is positive east, which is how every one of
    #          these cards writes it.
    for lat_key, lon_key in _SITE_KEYS:
        lat = _num(header.get(lat_key))
        lon = _num(header.get(lon_key))
        if lat is not None and lon is not None \
                and -90.0 <= lat <= 90.0 and -360.0 <= lon <= 360.0:
            return lat, lon
    return None, None


def airmass_from_header(header):
    # The airmass the PLATE declares, which beats any geometry computed for
    # a site that is not the plate's.
    # @args: header - dict from fits_io.read_header / read_fits
    # @return: the airmass, or None when the plate does not say (1.0 is the
    #          zenith, so anything below it is not an airmass)
    for key in _AIRMASS_KEYS:
        v = _num(header.get(key))
        if v is not None and v >= 1.0:
            return v
    return None


def read_meta(path):
    # @args: path - FITS file path
    # @return: dict {date_obs, mjd, filter, exptime_s, object} — missing
    #         fields are None; never raises on a readable FITS (tolerant)
    header = fits_io.read_header(path)
    return meta_from_header(header)


def meta_from_header(header):
    # @args: header - dict from fits_io.read_header / read_fits
    # @return: dict {date_obs, mjd, filter, exptime_s, object}
    date_raw = None
    for key in _DATE_KEYS:
        if key in header:
            date_raw = header[key]
            break
    dt = _parse_fits_date(date_raw) if date_raw else None
    mjd = None
    if dt is not None:
        jd = coords.jd_from_datetime(dt)
        mjd = jd - 2400000.5
    if mjd is None:
        # some headers (MicroObservatory, several amateur rigs) carry the
        # numeric UTC MJD instead of a parseable DATE-OBS
        for key in _MJD_KEYS:
            if key in header:
                try:
                    mjd = float(header[key])
                    break
                except (TypeError, ValueError):
                    continue

    filt = None
    for key in _FILTER_KEYS:
        if key in header:
            filt = str(header[key]).strip()
            break

    exptime = None
    for key in _EXPTIME_KEYS:
        if key in header:
            try:
                exptime = float(header[key])
            except (ValueError, TypeError):
                pass
            break

    obj = header.get("OBJECT")
    lat, lon = site_from_header(header)
    return {"date_obs": date_raw,
            "mjd": mjd,
            "filter": filt,
            "exptime_s": exptime,
            "object": str(obj).strip() if obj else None,
            "site_lat": lat, "site_lon": lon,
            "airmass": airmass_from_header(header),
            "aperture_m": aperture_from_header(header)}
