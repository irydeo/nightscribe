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
from the editor's Solve button). ASTAP's own outputs are named with `-o`
into our per-user folder, so the solver never leaves its .ini/.wcs next
to the observer's images. Results are cached by content hash and backend,
so the same plate is never solved twice. No network.
"""

import hashlib
import json
import logging
import os
import subprocess
import shutil
import time
from pathlib import Path

from ..db import db
from ... import paths
from .astrometry import _WCS_KEYS

logger = logging.getLogger(__name__)

# The ASTAP command-line switch set we use: hints (fov/ra/spd), the -wcs
# output file and the optional -update of the FITS header.
TIMEOUT_S = 180.0


def _install_candidates():
    # The install folders PATH usually misses: the Windows installer drops
    # astap.exe under Program Files (or in the user's LOCALAPPDATA for a
    # per-user install) and never touches PATH; a portable zip often lives
    # in <drive>:\astap. Where those environment folders do not exist
    # (Linux, macOS) the list is empty: there the package manager puts the
    # binary in PATH and shutil.which finds it.
    # @return: list of candidate Paths (they may not exist)
    out = []
    env = os.environ
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = env.get(key)
        if root:
            out.append(Path(root) / "astap" / "astap.exe")
    drive = env.get("SystemDrive")
    if drive:
        out.append(Path(drive + "\\") / "astap" / "astap.exe")
    return out


def resolve_binary(astap_path=None):
    # @args: astap_path - a configured path or None
    # @return: the executable to run, or None when ASTAP is not found
    if astap_path:
        p = Path(astap_path)
        if p.is_file():
            return str(p)
    found = shutil.which("astap") or shutil.which("astap.exe")
    if found:
        return found
    for cand in _install_candidates():
        if cand.is_file():
            return str(cand)
    return None


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


def _take_wcs(wcs_path):
    # Reads one .wcs sidecar ASTAP wrote and removes it right away.
    # @args: wcs_path - the candidate sidecar
    # @return: dict of WCS cards, or None when there is no such file
    p = Path(wcs_path)
    if not p.is_file():
        return None
    cards = _cards_from_wcs_file(p)
    try:
        p.unlink()
    except OSError:
        pass
    return cards


def _out_base(digest):
    # ASTAP names its outputs from `-o` (base path and file name) and,
    # without it, writes them next to the image: the .ini report always,
    # the .wcs on a solution. Pointing the base at our own per-user folder
    # keeps the solver out of the observer's image folders; the digest
    # keeps two concurrent solves (live mode plus a manual Solve) apart.
    # @args: digest - the plate's content hash (the cache key)
    # @return: Path base for this plate's ASTAP outputs
    return paths.astap_dir() / f"solve-{digest[:16]}"


def _drop_outputs(base):
    # @args: base - the `-o` base inside our own folder
    # @return: None; removes what ASTAP left there (.ini always, .log with
    #          -log), so the app folder does not fill up with scratch
    for ext in (".ini", ".log"):
        p = Path(str(base) + ext)
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass


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
    out_base = _out_base(digest)
    cmd = [binary, "-f", str(path), "-wcs", "-o", str(out_base)]
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
    cards = _take_wcs(str(out_base) + ".wcs")
    if cards is None:
        # an ASTAP that ignores -o still writes the sidecar next to the
        # image, which is where the previous versions looked for it
        cards = _take_wcs(str(path) + ".wcs")
    _drop_outputs(out_base)
    if cards is None:
        cards = _cards_from_stdout(proc.stdout)
    if not cards:
        logger.info("ASTAP returned no usable WCS (rc=%s)", proc.returncode)
        return None
    db.cache_put(key, "astap", json.dumps(cards).encode("utf-8"),
                 "application/json")
    return cards
