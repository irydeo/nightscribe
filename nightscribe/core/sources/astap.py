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
cards|None`, with the WCS read into memory from the `-wcs` output, and the
`astap_cli` barebone preferred so no window or modal hangs the call. No
`-ra`/`-spd` hint is passed (the header's RA units are ambiguous and a
wrong hint loops ASTAP); `-fov` is the reliable speed-up, `-d` points at
the star database when found and `-progress` feeds the busy dialog; the
run can be killed through a `core.solve.SolveCancel`. ASTAP's own outputs
are named with `-o` into our per-user folder, so the solver never leaves
its .ini/.wcs next to the observer's images. Results are cached by content
hash and backend, so the same plate is never solved twice. The solution is
returned as cards; the caller merges them in memory and writes them into
the FITS (ADR-051 rev.), never `-update`. No network.
"""

import hashlib
import json
import logging
import os
import subprocess
import shutil
import threading
import time
from pathlib import Path

from ..db import db
from ... import paths
from .astrometry import _WCS_KEYS

logger = logging.getLogger(__name__)

# The ASTAP command-line switch set we use: hints (fov/ra/spd), the -wcs
# output file, -progress for the busy dialog and the optional -update of
# the FITS header.
TIMEOUT_S = 180.0


def _install_candidates():
    # The install folders PATH usually misses: the Windows installer drops
    # astap.exe under Program Files (or in the user's LOCALAPPDATA for a
    # per-user install) and never touches PATH; a portable zip often lives
    # in <drive>:\astap; on Linux/macOS the package or a manual unpack puts
    # it under /opt or /usr/local. Both the GUI and the barebone CLI names
    # are listed: the CLI is preferred (no window, no pop-up).
    # @return: list of candidate Paths (they may not exist)
    names = ("astap_cli", "astap", "astap_cli.exe", "astap.exe")
    out = []
    env = os.environ
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = env.get(key)
        if root:
            out += [Path(root) / "astap" / n for n in names]
    drive = env.get("SystemDrive")
    if drive:
        out += [Path(drive + "\\") / "astap" / n for n in names]
    for root in _POSIX_ROOTS:
        out += [Path(root) / n for n in names]
    return out


# the common Linux/macOS unpack folders (the tests blank this to isolate
# the Windows probes from the developer's own install)
_POSIX_ROOTS = ("/opt/astap", "/usr/share/astap", "/usr/local/opt/astap",
                "/usr/local/lib/astap")


def _sibling_cli(binary):
    # The barebone CLI sits next to the GUI binary (astap_cli beside
    # astap). A symlink like /usr/local/bin/astap -> /opt/astap/astap must
    # resolve first, or the sibling is looked for in the wrong folder.
    # @args: binary - the found astap path
    # @return: the astap_cli path, or None
    p = Path(binary)
    parents = []
    try:
        parents.append(p.resolve().parent)
    except OSError:
        pass
    parents.append(p.parent)
    for parent in parents:
        for name in ("astap_cli", "astap_cli.exe"):
            cand = parent / name
            if cand.is_file():
                return str(cand)
    return None


def resolve_binary(astap_path=None):
    # @args: astap_path - a configured path or None
    # @return: the executable to run, or None when ASTAP is not found. A
    #          configured path wins outright; otherwise a CLI variant wins
    #          over the GUI binary (headless: no window, no modal
    #          "Solution found" that would hang the call).
    if astap_path:
        p = Path(astap_path)
        if p.is_file():
            if p.stem.lower() == "astap_cli":
                return str(p)
            return _sibling_cli(str(p)) or str(p)
    seeds = []
    for name in ("astap_cli", "astap_cli.exe", "astap", "astap.exe"):
        found = shutil.which(name)
        if found:
            seeds.append(Path(found))
    seeds.extend(_install_candidates())
    gui = None
    for seed in seeds:
        if not seed.is_file():
            continue
        if seed.stem.lower() == "astap_cli":
            return str(seed)
        cli = _sibling_cli(str(seed))
        if cli:
            return cli
        if gui is None:
            gui = str(seed)
    return gui


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


def _database_path(binary, config=None):
    # ASTAP should be told where its star database lives: without -d it can
    # sit on a modal "No star database found!" dialog on a machine where
    # the DB is not next to the binary. Probe the usual places.
    # @return: the database folder, or None (ASTAP's own search wins)
    from ...config import config as _cfg
    cfg = config or _cfg
    explicit = str(cfg.get("astap_db") or "").strip()
    if explicit and Path(explicit).is_dir():
        return explicit
    roots = []
    try:
        roots.append(Path(binary).resolve().parent)
    except OSError:
        pass
    roots += [Path("/opt/astap"), Path("/opt/astap/data"),
              Path("/usr/share/astap/data"), Path("/usr/share/astap"),
              Path("/usr/local/opt/astap")]
    for root in roots:
        try:
            if root.is_dir() and next(root.glob("*.1476"), None) is not None:
                return str(root)
        except OSError:
            continue
    return None


def _terminate(proc):
    # Kills a running ASTAP (the dialog's Cancel): terminate, then kill if
    # it does not answer. Windows TerminateProcess is enough here (ASTAP
    # spawns no children).
    # @args: proc - the subprocess.Popen
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


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


def solve(path, progress=None, astap_path=None, update=False, config=None,
          cancel=None):
    # Solves a FITS image locally with ASTAP.
    # @args: path - FITS Path, progress - optional callable(stage_text),
    #        astap_path - configured binary or None (PATH lookup),
    #        update - write the solution back into the FITS (opt-in),
    #        cancel - a core.solve.SolveCancel (the dialog's Cancel) or None
    # @return: dict of WCS header cards, or None (missing/failed/cancelled)
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
    # -progress streams stage lines for the busy dialog. No -ra/-spd hint:
    # the header's RA units are ambiguous (degrees vs hours) and a wrong
    # hint sends ASTAP to the wrong sky and loops ("Found 0 references");
    # -fov is the reliable speed-up and ASTAP reads the header's own
    # position safely.
    cmd = [binary, "-f", str(path), "-wcs", "-progress",
           "-o", str(out_base)]
    db_path = _database_path(binary, config)
    if db_path:
        cmd += ["-d", db_path]
    fov = _fov_hint(header, config)
    if fov:
        cmd += ["-fov", str(fov)]
    if update:
        cmd.append("-update")
    if progress:
        progress("astap: solving locally")
    logger.info("ASTAP: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
    except OSError as err:
        logger.warning("ASTAP run failed: %s", err)
        return None
    if cancel is not None:
        cancel.attach(proc)
    lines = []
    deadline = time.monotonic() + TIMEOUT_S

    def _pump():
        # Reading off-thread keeps the Cancel responsive while ASTAP runs.
        for line in proc.stdout or ():
            lines.append(line)
            if progress and line.strip():
                progress(line.strip())

    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()
    timed_out = False
    while proc.poll() is None:
        if cancel is not None and cancel.is_set():
            _terminate(proc)
            break
        if time.monotonic() > deadline:
            timed_out = True
            _terminate(proc)
            break
        time.sleep(0.05)
    reader.join(timeout=2.0)
    if cancel is not None and cancel.is_set():
        logger.info("ASTAP cancelled for %s", path.name)
        return None
    if timed_out:
        logger.warning("ASTAP timed out after %ss", TIMEOUT_S)
        return None
    cards = _take_wcs(str(out_base) + ".wcs")
    if cards is None:
        # an ASTAP that ignores -o still writes the sidecar next to the
        # image, which is where the previous versions looked for it
        cards = _take_wcs(str(path) + ".wcs")
    _drop_outputs(out_base)
    if cards is None:
        cards = _cards_from_stdout("".join(lines))
    if not cards:
        logger.info("ASTAP returned no usable WCS (rc=%s)", proc.returncode)
        return None
    db.cache_put(key, "astap", json.dumps(cards).encode("utf-8"),
                 "application/json")
    return cards
