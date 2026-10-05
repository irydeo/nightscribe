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
`astap_cli` barebone preferred so no window or modal hangs the call.

WHERE THE PLATE LOOKS is the hint that decides everything. A `pointing`
(ra/dec in degrees, from the project the editor was opened from) goes in
as `-ra`/`-spd` PLUS `-r`, the search radius; without `-r` ASTAP ignores
the position and sweeps the sky: measured on a real frame of the V0526 Per
visit, the same hint took 56-65 s with no radius and 0.13 s with `-r 5`,
and a WRONG pointing fails in 0.28 s, so a bad hint is cheap and the blind
path below still saves it. The header's own position is never used (its RA
units are ambiguous: hours in OBJCTRA, degrees in CRVAL1).

The `-fov` is the image HEIGHT in degrees from the header's own scale
(IM_SCALE/SECPIX/CDELT/XPIXSZ+FOCALLEN) or the Settings, and the hinted
attempt is bounded before a fallback to the auto field (`-fov 0`), so a
wrong scale can never loop ASTAP either. `-d` points at the star database
when found and `-progress` feeds the busy dialog; the run can be killed
through a `core.solve.SolveCancel`. ASTAP's own outputs are named with `-o`
into our per-user folder, so the solver never leaves its .ini/.wcs next to
the observer's images. Results are cached by content hash and backend, so
the same plate is never solved twice. The solution is returned as cards;
the caller merges them in memory and writes them into the FITS (ADR-051
rev.), never `-update`. No network.
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
from .astrometry import WCS_KEYS

logger = logging.getLogger(__name__)

# The ASTAP command-line switch set we use: hints (fov/ra/spd), the -wcs
# output file, -progress for the busy dialog and the optional -update of
# the FITS header.
TIMEOUT_S = 180.0
# the hinted attempt must not loop: a wrong/missing -fov can make ASTAP
# sweep the whole sky, so give it a short budget before falling back to
# the auto field (-fov 0)
ATTEMPT_S = 30.0
# The pointed attempt (a known field) gets room: when the pointing is right
# ASTAP answers in a tenth of a second, and when it is WRONG it gives up by
# itself in ~0.3 s (measured: it tries radii 1-5 and stops), so this budget
# is only spent on a plate that is really being solved.
POINTED_S = 60.0
# The search radius that goes with a pointing (-r): the offset between the
# project's target and the plate centre is arcminutes (5.3' in the real
# V0526 Per visit) and another night's framing stays under a degree, so 5
# degrees covers it with room to spare, and it costs nothing: measured, the
# same pointed solve took 0.13 s with -r 1, 3, 5 and 10.
SEARCH_RADIUS_DEG = 5.0


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
    # @return: (cards, warning): the WCS cards and ASTAP's own WARNING card
    #          (it writes one when its star database is obsolete, which is
    #          the reason a blind solve crawls), or (None, None)
    from .. import fits_io
    try:
        header = fits_io.read_header(wcs_path)
    except Exception as err:
        logger.warning("ASTAP .wcs unreadable: %s", err)
        return None, None
    cards = {k: header[k] for k in WCS_KEYS if k in header}
    warning = str(header.get("WARNING") or "").strip() or None
    return (cards or None), warning


def _take_wcs(wcs_path):
    # Reads one .wcs sidecar ASTAP wrote and removes it right away.
    # @args: wcs_path - the candidate sidecar
    # @return: (cards, warning), or (None, None) when there is no such file
    p = Path(wcs_path)
    if not p.is_file():
        return None, None
    cards, warning = _cards_from_wcs_file(p)
    try:
        p.unlink()
    except OSError:
        pass
    return cards, warning


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
        if key not in WCS_KEYS:
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


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _scale_arcsec(header, config):
    # Arcseconds per pixel. The image's own scale beats the observer's
    # Settings (a foreign plate, e.g. a MicroObservatory frame, carries
    # IM_SCALE and a very different setup).
    # @return: arcsec/pixel, or None when nothing gives a scale
    for key in ("IM_SCALE", "PIXSCALE", "SECPIX", "SECPIX1"):
        v = _num(header.get(key))
        if v and v > 0:
            return v
    cd = _num(header.get("CDELT1"))
    if cd:
        return abs(cd) * 3600.0
    px = _num(header.get("XPIXSZ")) or _num(header.get("PIXSIZE"))
    fl = _num(header.get("FOCALLEN"))
    if px and fl and fl > 0:
        return (px / 1000.0) / fl * 206264.806
    from ...config import config as _cfg
    cfg = config or _cfg
    ux = _num(cfg.get("pixel_um"))
    fl = _num(cfg.get("focal_mm"))
    if ux and fl and fl > 0:
        return (ux / 1000.0) / fl * 206264.806
    return None


def fov_hint(header, config=None):
    # ASTAP's -fov is the field diameter, taken as the image HEIGHT in
    # degrees (the ADR fixes it so). The old max(nx,ny) over-estimated
    # landscape plates and sent ASTAP to the wrong star database: the
    # "Found 0 references" loop (~19 s+ instead of 0.3 s).
    # It is public because the nova client wants the same number (its
    # scale_units=degwidth hints), and one plate has one field.
    # @args: header - the FITS header cards, config - override or None
    # @return: fov in degrees, or None (the caller passes -fov 0 = auto)
    ny = _num(header.get("NAXIS2"))
    if not ny or ny <= 0:
        return None
    scale = _scale_arcsec(header, config)
    if not scale:
        return None
    return round(ny * scale / 3600.0, 3)


def _pointing_args(pointing, radius_deg=None):
    # The argv tokens that tell ASTAP where the plate looks. The three
    # conventions are the binary's own (help + official docs) and the
    # ADR-051 measurements: -ra in HOURS, -spd the south-pole distance
    # (90 + dec, so it is 0 at the south pole and 180 at the north: a
    # northern object gets a value ABOVE 90, which is what tripped the
    # first attempt at this), and -r the search radius in degrees.
    #
    # The radius is what makes the hint DO something: -ra/-spd alone left
    # ASTAP sweeping the sky (56-65 s measured on the real frame), while
    # the same call with -r 5 answered in 0.13 s.
    # @args: pointing - (ra_deg, dec_deg) or None, radius_deg - override
    # @return: list of argv tokens (empty when there is no usable pointing)
    if not pointing:
        return []
    try:
        ra_deg = float(pointing[0])
        dec_deg = float(pointing[1])
    except (TypeError, ValueError, IndexError):
        logger.info("ASTAP: unusable pointing %r; solving blind", pointing)
        return []
    radius = SEARCH_RADIUS_DEG if radius_deg is None else float(radius_deg)
    return ["-ra", "%.5f" % (ra_deg / 15.0),
            "-spd", "%.5f" % (90.0 + dec_deg),
            "-r", "%.3f" % radius]


def solve(path, progress=None, astap_path=None, update=False, config=None,
          cancel=None, pointing=None):
    # Solves a FITS image locally with ASTAP.
    # @args: path - FITS Path, progress - optional callable(stage_text),
    #        astap_path - configured binary or None (PATH lookup),
    #        update - write the solution back into the FITS (opt-in),
    #        cancel - a core.solve.SolveCancel (the dialog's Cancel) or None,
    #        pointing - (ra_deg, dec_deg) of the field when the app knows it
    #        (the project's target), or None to solve blind
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
    base = _out_base(digest)

    # The attempts, in the order that answers for the least time: WITH the
    # pointing when the app knows where the plate looks (0.13 s against a
    # minute), then the scale hint alone (bounded: a wrong -fov sweeps the
    # sky, which is what ATTEMPT_S is for), and last the auto field (-fov 0),
    # which reads the scale off the image itself. A wrong pointing falls
    # through to the blind ones on its own, in 0.28 s.
    fov = fov_hint(header, config)
    extra = []
    db_path = _database_path(binary, config)
    if db_path:
        extra += ["-d", db_path]
    if update:
        extra.append("-update")
    hint = _pointing_args(pointing)
    attempts = []
    if hint:
        attempts.append((hint, fov, POINTED_S))
    if fov:
        attempts.append(([], fov, ATTEMPT_S))
    attempts.append(([], None, None))     # None: whatever the budget has left
    overall = time.monotonic() + TIMEOUT_S
    cards = None
    for i, (hint_args, target, budget) in enumerate(attempts):
        tail = max(overall - time.monotonic(), 1.0)
        last = i == len(attempts) - 1
        slot = tail if (budget is None or last) else min(budget, tail)
        out_base = Path(f"{base}-a{i}")
        cmd = [binary, "-f", str(path), "-wcs", "-progress",
               "-o", str(out_base)] + extra + hint_args \
            + ["-fov", str(target) if target else "0"]
        if progress:
            if hint_args:
                progress("astap:pointed")
            elif target:
                progress("astap:solving")
            else:
                # the honest reason the observer may be in for a minute of
                # waiting: nothing told ASTAP where the plate looks (see
                # _pointing_args)
                progress("astap:blind")
        logger.info("ASTAP: %s", " ".join(cmd))
        lines, cancelled, _timed_out, rc = _run_astap(
            cmd, progress, cancel, slot)
        if cancelled:
            logger.info("ASTAP cancelled for %s", path.name)
            return None
        cards, warning = _take_wcs(str(out_base) + ".wcs")
        if cards is None:
            # an ASTAP that ignores -o still writes the sidecar next to
            # the image, which is where the older versions looked for it
            cards, warning = _take_wcs(str(path) + ".wcs")
        _drop_outputs(out_base)
        if warning:
            # ASTAP's own caveat about the solve (an obsolete star database
            # is the classic one). It goes to the log and to the busy line:
            # a solve that took a minute because of it should not look like
            # a mystery.
            logger.warning("ASTAP warns for %s: %s", path.name, warning)
            if progress:
                progress("ASTAP: %s" % warning)
        if cards is None:
            cards = _cards_from_stdout("".join(lines))
        if cards:
            break
        if time.monotonic() >= overall:
            logger.warning("ASTAP timed out after %ss", TIMEOUT_S)
            break
        logger.info("ASTAP attempt %s failed (rc=%s); retrying", i + 1, rc)
    if not cards:
        logger.info("ASTAP returned no usable WCS")
        return None
    db.cache_put(key, "astap", json.dumps(cards).encode("utf-8"),
                 "application/json")
    return cards


# The lines of ASTAP's own output worth showing the observer: its verdict,
# its timing and its warnings. Everything else is the search itself, which
# is noise (and looked like a loop).
_NOTABLE = ("warning", "error", "no solution", "solution found", "solved in",
            "not solved", "failed")


def _notable(line):
    # @args: line - one line of ASTAP's output
    # @return: True when the observer should see it: ASTAP's verdict, its
    #          timing and its warnings (a wrong scale, an obsolete star
    #          database). The rest of its output is the SEARCH itself.
    low = (line or "").lower()
    return any(marker in low for marker in _NOTABLE)


def _cancelled(cancel):
    # @args: cancel - a core.solve.SolveCancel, a plain callable, or None
    # @return: True when the run was asked to stop
    # Both shapes are accepted on purpose: the GUI worker has always handed
    # the engines a callable (lambda: self._cancel), while the solve dialog
    # uses a SolveCancel with attach()/is_set(). Asking for .is_set()
    # unconditionally is what made a plain callable blow up with
    # "'function' object has no attribute 'attach'" the first time the
    # track & stack solve ran. The knowledge lives in core.solve.
    from .. import solve
    return solve.is_cancelled(cancel)


def _run_astap(cmd, progress, cancel, budget):
    # One ASTAP attempt: streams stdout to progress, honours the Cancel
    # flag and the time budget (a kill on either).
    # @return: (lines, cancelled, timed_out, returncode)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
    except OSError as err:
        logger.warning("ASTAP run failed: %s", err)
        return [], False, False, None
    attach = getattr(cancel, "attach", None)
    if callable(attach):
        # only a SolveCancel can kill the live process; a plain callable
        # is polled below and stops the run at the next tick
        attach(proc)
    lines = []
    deadline = time.monotonic() + max(budget, 1.0)

    def _pump():
        # Reading off-thread keeps the Cancel responsive while ASTAP runs.
        # ONLY the lines that say something reach the observer: ASTAP's own
        # progress is a wall of "Search 75939, [99,138], position: 03:38
        # 17.2+49d 32 31 ..." that scrolled through the busy dialog and made
        # a solve that was WORKING look like a loop (reported). The full
        # output is still kept for the stdout fallback below.
        for line in proc.stdout or ():
            lines.append(line)
            if progress and _notable(line):
                progress(line.strip())

    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()
    timed_out = False
    while proc.poll() is None:
        if _cancelled(cancel):
            _terminate(proc)
            break
        if time.monotonic() > deadline:
            timed_out = True
            _terminate(proc)
            break
        time.sleep(0.05)
    reader.join(timeout=2.0)
    return lines, _cancelled(cancel), timed_out, proc.returncode
