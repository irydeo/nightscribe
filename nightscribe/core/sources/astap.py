############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - ASTAP local plate solver source (ADR-051, series plan 9)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Local plate solving with ASTAP (ADR-051).

Same contract as the Astrometry.net client: `solve(path, progress) ->
cards|None`, with the WCS read into memory from the `-wcs` output (the
user's FITS is only rewritten with `-update`, which is opt-in and driven
from the editor's Solve button). Results are cached by content hash and
backend, so the same plate is never solved twice. No network.
"""

import hashlib
import json
import logging
import subprocess
import shutil
import time
from pathlib import Path

from ..db import db
from .astrometry import _WCS_KEYS

logger = logging.getLogger(__name__)

# The ASTAP command-line switch set we use: hints (fov/ra/spd), the -wcs
# output file and the optional -update of the FITS header.
TIMEOUT_S = 180.0


def resolve_binary(astap_path=None):
    # @args: astap_path - a configured path or None
    # @return: the executable to run, or None when ASTAP is not found
    if astap_path:
        p = Path(astap_path)
        if p.is_file():
            return str(p)
    found = shutil.which("astap") or shutil.which("astap.exe")
    return found


def probe(astap_path=None):
    # @args: astap_path - a configured path or None
    # @return: {"ok": bool, "path": str|None, "message": str} - a quick
    #          existence check for the Settings "Test" button
    binary = resolve_binary(astap_path)
    if binary is None:
        return {"ok": False, "path": None,
                "message": "ASTAP not found"}
    return {"ok": True, "path": binary,
            "message": f"ASTAP at {binary}"}


def _cards_from_wcs_file(wcs_path):
    # Reads the .wcs header ASTAP wrote and keeps the cards we understand.
    # @return: dict of WCS cards or None
    from .. import fits_io
    try:
        header = fits_io.read_header(wcs_path)
    except Exception as err:
        logger.warning("ASTAP .wcs unreadable: %s", err)
        return None
    cards = {k: header[k] for k in _WCS_KEYS if k in header}
    return cards or None


def _cards_from_stdout(text):
    # Fallback: parse 80-char "KEY = value" cards from ASTAP's output.
    # @return: dict of WCS cards or None
    cards = {}
    for line in (text or "").splitlines():
        if "=" not in line:
            continue
        key, _, rest = line.partition("=")
        key = key.strip()
        if key not in _WCS_KEYS:
            continue
        val = rest.split("/")[0].strip().strip("'").strip()
        try:
            cards[key] = float(val)
        except ValueError:
            cards[key] = val
    return cards or None


def _fov_hint(header, config):
    # The field of view in degrees, from the camera pixel size and the
    # telescope focal length (a strong hint that makes ASTAP much faster).
    # @return: fov in degrees, or None
    try:
        from ...config import config as _cfg
        cfg = config or _cfg
        pix_um = float(cfg.get("pixel_um") or 0.0)
        focal_mm = float(cfg.get("focal_mm") or 0.0)
        nx = float(header.get("NAXIS1") or 0.0)
        ny = float(header.get("NAXIS2") or 0.0)
        if pix_um <= 0 or focal_mm <= 0 or nx <= 0 or ny <= 0:
            return None
        scale_deg = (pix_um / 1000.0) / focal_mm * 57.2957795
        return round(max(nx, ny) * scale_deg, 3)
    except Exception:
        return None


def solve(path, progress=None, astap_path=None, update=False, config=None):
    # Solves a FITS image locally with ASTAP.
    # @args: path - FITS Path, progress - optional callable(stage_text),
    #        astap_path - configured binary or None (PATH lookup),
    #        update - write the solution back into the FITS (opt-in)
    # @return: dict of WCS header cards, or None (missing/failed)
    binary = resolve_binary(astap_path)
    if binary is None:
        logger.info("ASTAP not found; cannot solve locally")
        return None
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    key = f"astap:wcs:{digest}"
    cached = db.cache_get(key)
    if cached:
        logger.info("ASTAP cache hit for %s", path.name)
        return json.loads(cached[0].decode("utf-8"))
    from .. import fits_io
    try:
        header, _data = fits_io.read_fits(path)
    except fits_io.FitsError:
        header = {}
    cmd = [binary, "-f", str(path), "-wcs", "-o", str(path) + ".ini"]
    fov = _fov_hint(header, config)
    if fov:
        cmd += ["-fov", str(fov)]
    object_ra = header.get("RA")
    object_dec = header.get("DEC")
    if object_ra is not None and object_dec is not None:
        try:
            cmd += ["-ra", str(float(object_ra)),
                    "-spd", str(90.0 + float(object_dec))]
        except (TypeError, ValueError):
            pass
    if update:
        cmd.append("-update")
    if progress:
        progress("astap: solving locally")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as err:
        logger.warning("ASTAP run failed: %s", err)
        return None
    wcs_path = Path(str(path) + ".wcs")
    cards = None
    if wcs_path.is_file():
        cards = _cards_from_wcs_file(wcs_path)
        try:
            wcs_path.unlink()
        except OSError:
            pass
    if cards is None:
        cards = _cards_from_stdout(proc.stdout)
    if not cards:
        logger.info("ASTAP returned no usable WCS (rc=%s)", proc.returncode)
        return None
    db.cache_put(key, "astap", json.dumps(cards).encode("utf-8"),
                 "application/json")
    return cards
