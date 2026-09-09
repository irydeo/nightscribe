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

from . import coords, fits_io

logger = logging.getLogger(__name__)

# FITS date keywords tried in order — DATE-OBS is the classic, but some
# pipelines write DATE or UTC-OBS instead.
_DATE_KEYS = ("DATE-OBS", "DATE", "UTC-OBS")
_FILTER_KEYS = ("FILTER", "FILTERS", "FILT")
_EXPTIME_KEYS = ("EXPTIME", "EXPOSURE", "ELAPSED")


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
    return {"date_obs": date_raw,
            "mjd": mjd,
            "filter": filt,
            "exptime_s": exptime,
            "object": str(obj).strip() if obj else None}
