############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Astrometry.net (nova) source: blind plate solving
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import hashlib
import io
import json
import logging
import time

import requests

from ..db import db

logger = logging.getLogger(__name__)

# nova.astrometry.net web API: login with the user's API key (free account),
# upload, poll the job, and fetch the resulting WCS header. Solved WCS cards
# are cached by file hash: re-solving the same image is free (ADR-018).
API = "https://nova.astrometry.net/api"
WCS_URL = "https://nova.astrometry.net/wcs_file"

POLL_S = 3.0          # seconds between job status checks
# A live solve queues on the server and can take a few minutes (measured ~4 min,
# seen longer under load). Re-solving the same file is a cache hit and instant,
# so the budget can be generous without any cost (ADR-018).
TIMEOUT_S = 900.0     # give up on a solve after this
# The radius that goes with a pointing hint (center_ra/center_dec/radius in
# degrees): the same 5 degrees ASTAP gets (see astap.SEARCH_RADIUS_DEG).
# Without it nova searches the whole sky.
SEARCH_RADIUS_DEG = 5.0

# WCS cards we keep from the solved wcs.fits (NAXIS stays from the user image;
# SIP polynomial cards A_*/B_* are dropped on purpose: our WCS is plain TAN)
_WCS_KEYS = ("CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CTYPE1", "CTYPE2",
             "CUNIT1", "CUNIT2", "CD1_1", "CD1_2", "CD2_1", "CD2_2",
             "CDELT1", "CDELT2", "CROTA2", "PC1_1", "PC1_2", "PC2_1",
             "PC2_2", "IMAGEW", "IMAGEH", "EQUINOX", "RADESYS")


def _login(api_key):
    # @args: api_key - nova.astrometry.net API key from the user profile
    # @return: session string; raises on network error
    r = requests.post(f"{API}/login",
                      data={"request-json": json.dumps({"apikey": api_key})},
                      timeout=40)
    r.raise_for_status()
    out = r.json()
    if out.get("status") != "success":
        logger.warning("astrometry login failed: %s", out.get("errormessage"))
        return None
    return out["session"]


def _hints(path, pointing=None):
    # What the upload tells nova about the plate: where it looks and how big
    # it is. Nova's default is a blind solve over the whole sky, which takes
    # minutes and fails often on a plate like the V0526 Per frames (no
    # position and no scale of their own: FOCALLEN=0, no RA/DEC); with the
    # project's field it searches a small box instead (ADR-051: the same
    # hint took ASTAP from 66 s to 0.13 s, and nova follows the same
    # physics).
    #
    # The scale goes as a width in degrees with a 25 % window: the header's
    # own scale is a good number, the observer's Settings are a guess, and
    # nova only needs to be told the neighbourhood.
    # @args: path - FITS Path, pointing - (ra_deg, dec_deg) or None
    # @return: dict of request-json fields ({} when nothing is known)
    out = {}
    if pointing:
        try:
            out["center_ra"] = float(pointing[0])
            out["center_dec"] = float(pointing[1])
            out["radius"] = SEARCH_RADIUS_DEG
        except (TypeError, ValueError, IndexError):
            logger.info("astrometry: unusable pointing %r", pointing)
            out = {}
    try:
        from .. import fits_io
        from .astap import fov_hint
        header, _data = fits_io.read_fits(path)
        fov = fov_hint(header)
    except Exception as err:        # a header we cannot read: no scale hint
        logger.warning("astrometry: no scale hint (%s)", err)
        fov = None
    if fov and fov > 0:
        out["scale_units"] = "degwidth"
        out["scale_lower"] = round(fov * 0.8, 4)
        out["scale_upper"] = round(fov * 1.25, 4)
    return out


def _upload(session, path, hints=None):
    # @args: session - login session, path - FITS file to upload,
    #        hints - the request-json fields from _hints (or None)
    # @return: submission id; raises on network error
    req = {"session": session, "publicly_visible": "n",
           "allow_modifications": "n", "allow_commercial_use": "n"}
    req.update(hints or {})
    with open(path, "rb") as fh:
        r = requests.post(f"{API}/upload", data={"request-json": json.dumps(req)},
                          files={"file": (path.name, fh)}, timeout=180)
    r.raise_for_status()
    out = r.json()
    if out.get("status") != "success":
        logger.warning("astrometry upload failed: %s", out.get("errormessage"))
        return None
    return out["subid"]


def _wait_job(subid, progress=None):
    # Polls the submission until a job finishes or TIMEOUT_S elapses.
    # @args: subid - submission id, progress - optional callable(stage_text)
    # @return: job id on success, None on failure/timeout
    deadline = time.time() + TIMEOUT_S
    job_id = None
    while time.time() < deadline:
        r = requests.get(f"{API}/submissions/{subid}", timeout=40)
        r.raise_for_status()
        jobs = [j for j in r.json().get("jobs", []) if j is not None]
        if jobs:
            job_id = jobs[0]
            break
        time.sleep(POLL_S)
    if job_id is None:
        logger.warning("astrometry: submission %s never got a job", subid)
        return None
    while time.time() < deadline:
        r = requests.get(f"{API}/jobs/{job_id}", timeout=40)
        r.raise_for_status()
        status = r.json().get("status")
        if status in ("success", "failure"):
            logger.info("astrometry job %s: %s", job_id, status)
            return job_id if status == "success" else None
        if progress:
            progress(f"job {job_id}: {status}")
        time.sleep(POLL_S)
    logger.warning("astrometry: job timed out")
    return None


def _fetch_wcs(job_id):
    # Downloads the solved WCS header and keeps the cards we understand.
    # @args: job_id - successful job id
    # @return: dict of WCS cards or None
    from .. import fits_io
    r = requests.get(f"{WCS_URL}/{job_id}", timeout=60)
    r.raise_for_status()
    header = fits_io.read_header(io.BytesIO(r.content))
    cards = {k: header[k] for k in _WCS_KEYS if k in header}
    return cards or None


def solve(path, progress=None, pointing=None):
    # Blind-solves a FITS image with Astrometry.net and returns the WCS cards.
    # Results are cached by content hash: the same file never gets re-solved.
    # @args: path - FITS Path, progress - optional callable(stage_text),
    #        pointing - (ra_deg, dec_deg) of the field when the app knows it
    #        (the project's target): it turns the whole-sky search into a
    #        small one
    # @return: dict of WCS header cards, or None (offline / failed / no key)
    from ...config import config
    api_key = (config.get("astrometry_key") or "").strip()
    if not api_key:
        logger.info("no astrometry_key configured; cannot blind-solve")
        return None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    key = f"astrometry:wcs:{digest}"
    cached = db.cache_get(key)
    if cached:
        logger.info("astrometry cache hit for %s", path.name)
        return json.loads(cached[0].decode("utf-8"))
    try:
        if progress:
            progress("login")
        session = _login(api_key)
        if not session:
            return None
        if progress:
            progress("upload")
        subid = _upload(session, path, _hints(path, pointing))
        if subid is None:
            return None
        if progress:
            progress("solving")
        job_id = _wait_job(subid, progress)
        if job_id is None:
            return None
        cards = _fetch_wcs(job_id)
    except requests.RequestException as err:
        logger.warning("astrometry solve failed: %s", err)
        return None
    if cards:
        db.cache_put(key, "astrometry", json.dumps(cards).encode("utf-8"),
                     "application/json")
    return cards
