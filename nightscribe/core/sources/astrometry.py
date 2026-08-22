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
TIMEOUT_S = 300.0     # give up on a solve after this

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


def _upload(session, path):
    # @args: session - login session, path - FITS file to upload
    # @return: submission id; raises on network error
    req = {"session": session, "publicly_visible": "n",
           "allow_modifications": "n", "allow_commercial_use": "n"}
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


def solve(path, progress=None):
    # Blind-solves a FITS image with Astrometry.net and returns the WCS cards.
    # Results are cached by content hash: the same file never gets re-solved.
    # @args: path - FITS Path, progress - optional callable(stage_text)
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
        subid = _upload(session, path)
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
