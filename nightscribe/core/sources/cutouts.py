############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Reference field cutouts source (DESI LS / CDS)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging

import io

import requests

from ... import paths
from ..db import db

logger = logging.getLogger(__name__)

LS_URL = "https://www.legacysurvey.org/viewer/jpeg-cutout"
HIPS_URL = "https://alasky.cds.unistra.fr/hips-image-services/hips2fits"

# HiPS used for blink reference images (ADR-018): PanSTARRS DR1 g-band first,
# DSS2-red as the southern-sky fallback (PS1 3pi stops at dec ~ -30)
PS1G_HIPS = "CDS/P/PanSTARRS/DR1/g"
DSS_RED_HIPS = "CDS/P/DSS2/red"
PS1_DEC_LIMIT = -30.0


def _save(body, name):
    # @args: body - image bytes, name - local file name
    # @return: local Path or None
    out = paths.image_cache_dir() / name
    try:
        out.write_bytes(body)
        return out
    except OSError as err:
        logger.error("Could not write %s: %s", out, err)
        return None


def _flat_image(body):
    # A "no coverage" answer is a valid 200 JPEG, just flat (Legacy Survey
    # fills with uniform gray 32): detect it by the luminance spread of a
    # small thumbnail, no numpy needed. Undecodable bodies count as flat.
    # @args: body - JPEG bytes
    # @return: True when the image carries no structure
    try:
        from PIL import Image
        lo, hi = Image.open(io.BytesIO(body)).convert("L") \
            .resize((128, 128)).getextrema()
        return hi - lo < 8
    except Exception:
        return True


def reference_cutout(ra, dec, size=512, pixscale=2.0):
    # Colour reference image of a sky field (public services, see ADR-016).
    # Tries DESI Legacy Survey first, falls back to DSS colour via
    # hips2fits; a flat "no coverage" tile falls through to the next source
    # so the caller never shows an empty pane believing it is the sky.
    # @args: ra, dec - degrees, size - pixels, pixscale - arcsec/pixel
    # @return: (local Path to the JPEG, source label) or (None, None)
    ra, dec = float(ra), float(dec)

    def fetch_ls():
        r = requests.get(LS_URL, params={
            "ra": ra, "dec": dec, "size": size, "layer": "ls-dr10",
            "pixscale": pixscale}, timeout=60)
        r.raise_for_status()
        return r.content, "image/jpeg"
    try:
        body, _ = db.http_get(f"cutouts:ls:{ra}:{dec}:{size}", "cutouts",
                              fetch_ls)
        if _flat_image(body):
            logger.info("Legacy Survey cutout is a flat tile at %.4f,%+.4f"
                        " (no coverage?); trying DSS", ra, dec)
        else:
            out = _save(body, f"cutout_{ra:.4f}_{dec:.4f}_{size}.jpg")
            if out is not None:
                return out, "Legacy Survey DR10"
    except requests.RequestException:
        logger.info("Legacy Survey cutout failed, trying DSS")

    def fetch_dss():
        fov = size * pixscale / 3600.0
        r = requests.get(HIPS_URL, params={
            "hips": "CDS/P/DSS2/color", "width": size, "height": size,
            "fov": fov, "projection": "TAN", "coordsys": "icrs",
            "ra": ra, "dec": dec, "format": "jpg"}, timeout=60)
        r.raise_for_status()
        return r.content, "image/jpeg"
    try:
        body, _ = db.http_get(f"cutouts:dss:{ra}:{dec}:{size}", "cutouts",
                              fetch_dss)
        if _flat_image(body):
            logger.warning("DSS cutout is a flat tile too at %.4f,%+.4f",
                           ra, dec)
        else:
            out = _save(body, f"cutout_dss_{ra:.4f}_{dec:.4f}_{size}.jpg")
            if out is not None:
                return out, "DSS2 color (CDS)"
    except requests.RequestException as err:
        logger.warning("DSS cutout failed: %s", err)
    return None, None


def _hips_fits(hips, ra, dec, width, height, pixscale, rotation, tag):
    # Single hips2fits FITS request with cache and local save.
    # Note: hips2fits reads `fov` along the largest dimension (verified).
    # @return: local Path to the FITS cutout
    fov = max(width, height) * pixscale / 3600.0

    def fetch():
        r = requests.get(HIPS_URL, params={
            "hips": hips, "width": width, "height": height, "fov": fov,
            "projection": "TAN", "coordsys": "icrs", "ra": ra, "dec": dec,
            "rotation_angle": f"{rotation:.2f}", "format": "fits"},
            timeout=120)
        r.raise_for_status()
        return r.content, "application/fits"
    key = (f"cutouts:{tag}:{ra:.5f}:{dec:.5f}:{width}x{height}"
           f":{pixscale:.3f}:{rotation:.1f}")
    body, _ = db.http_get(key, "cutouts", fetch)
    return _save(body, f"{tag}_{ra:.4f}_{dec:.4f}_{width}x{height}"
                       f"_{rotation:.1f}.fits")


def ps1g_matched(ra, dec, width, height, pixscale, rotation):
    # PanSTARRS DR1 g-band cutout matching the user's image geometry, so the
    # pair comes out aligned by construction (ADR-018): same celestial
    # centre, pixel scale and rotation; the user's pixels are never resampled.
    # @args: ra, dec - degrees (image centre), width, height - pixels,
    #        pixscale - arcsec/pixel, rotation - hips2fits rotation_angle deg
    # @return: (local FITS Path, survey label) or (None, None)
    ra, dec = float(ra), float(dec)
    if dec >= PS1_DEC_LIMIT:
        try:
            path = _hips_fits(PS1G_HIPS, ra, dec, width, height, pixscale,
                              rotation, "ps1g")
            if path:
                return path, "PanSTARRS DR1 g"
        except requests.RequestException as err:
            logger.info("PanSTARRS g cutout failed, trying DSS2-red: %s", err)
    try:
        path = _hips_fits(DSS_RED_HIPS, ra, dec, width, height, pixscale,
                          rotation, "dssred")
        if path:
            return path, "DSS2-red"
    except requests.RequestException as err:
        logger.warning("DSS2-red cutout failed: %s", err)
    return None, None
