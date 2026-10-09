############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Find_Orb handoff and the check against others
# (ADR-062, phase 5.2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Asking Find_Orb whether our measurement is any good.

The check is a leave-one-out test: fit the orbit WITHOUT our observations
and see what residual ours have. Find_Orb already does that, with
perturbations and weighting, and it is what the community uses, so
NightScribe does not reimplement orbit fitting (ADR-062). It writes a file
with our lines and the others', runs the NON-interactive `fo` excluding
ours from the fit, and reads the residuals back.

Three details that are easy to get wrong and are handled here:

- `fo` is the non-interactive binary; the interactive `find_orb` is a
  different program and cannot be driven this way. `probe` refuses it.
- `fo` writes its output (total.json, elements.txt) into the CURRENT
  directory, so it is run in a temporary one; and it creates ~/.find_orb
  on first use, which is why a private `-D` environment file is passed.
- `-r 60,65` gives a soft and a hard CPU limit, so a stuck fit cannot hang
  the app.

The verdict is relative: our residual is compared with the ROBUST scatter
of the others, not with zero. With a bad orbit every residual is large, and
what matters is whether we fall outside the cloud. Without anyone to
compare with (a discovery), the check does not block: the MPC itself warns
that on a short arc a wrong observation fits just as well.
"""

import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# The binary is `fo` (Linux/macOS) or `fo64.exe` (Windows); the interactive
# one is `find_orb` and must be refused.
FO_NAMES = ("fo", "fo64.exe", "fo.exe")
INTERACTIVE_NAMES = ("find_orb", "find_orb.exe", "find_o64.exe")
DEFAULT_CPU_LIMIT = "60,65"


@dataclass
class CheckReport:
    available: bool = True
    blocked: bool = False
    outlier: bool = False
    no_reference: bool = False
    our_residual: tuple | None = None      # (dra, ddec) arcsec
    scatter: tuple | None = None           # (dra, ddec) arcsec, robust
    z: tuple | None = None
    n_others: int = 0
    n_stations: int = 0
    note: str = ""


def probe(findorb_path=None):
    # @args: findorb_path - the configured path (cfg "findorb_path")
    # @return: (path or None, message)
    # A path that points at the interactive program is refused with a plain
    # message: it is the mistake everybody makes once.
    candidate = findorb_path or ""
    if candidate:
        name = Path(candidate).name.lower()
        if name in INTERACTIVE_NAMES:
            return None, ("that is the interactive Find_Orb; NightScribe "
                          "needs the non-interactive `fo` (fo64.exe)")
        if Path(candidate).exists():
            return candidate, f"Find_Orb at {candidate}"
        return None, f"not found: {candidate}"
    for name in FO_NAMES:
        found = shutil.which(name)
        if found:
            return found, f"Find_Orb at {found}"
    return None, "Find_Orb is not configured (Settings > Measurement)"


def _lines(value):
    # @args: value - a string of 80-column lines, or an iterable of lines
    # @return: the non-empty lines, as a list of strings
    # The caller may hand us either shape. Normalising HERE is what keeps a
    # type slip from taking the whole run down: the track & stack once passed
    # a list to a function that called `.splitlines()` on it, and the
    # AttributeError bubbled up as a failed run instead of a check verdict.
    if isinstance(value, str):
        return [ln for ln in value.splitlines() if ln.strip()]
    return [str(ln) for ln in (value or []) if str(ln).strip()]


def write_input(ours, others, path):
    # @args: ours - our MPC 80-column lines (core/mpc_astrometry), others -
    #        the published lines (mpc_obs.observations_80), path - where.
    #        Each may be a string or a list of lines.
    # @return: the path
    # `fo` reads 80-column and ADES, mixed, in one file. Ours go first so
    # the residual report is easy to read.
    text = "\n".join(_lines(ours) + _lines(others))
    Path(path).write_text(text.rstrip() + "\n", encoding="ascii",
                          errors="replace")
    return str(path)


def write_environment(path, extra=None):
    # @args: path - where to write the private environ file, extra - extra
    #        KEY=VALUE lines
    # @return: the path
    # A private environment keeps the result independent from whatever the
    # user has in ~/.find_orb.
    lines = ["# NightScribe's private Find_Orb environment (ADR-062)",
             "PERTURBERS=7fe"]
    if extra:
        lines.extend(extra)
    Path(path).write_text("\n".join(lines) + "\n", encoding="ascii")
    return str(path)


def run(input_path, binary, env_file=None, cpu_limit=DEFAULT_CPU_LIMIT,
        cancel=None, timeout=180):
    # @args: input_path - the observation file, binary - the `fo` path,
    #        env_file - the private environment, cpu_limit - the -r value,
    #        cancel - callable() -> True, timeout - wall-clock seconds
    # @return: (ok, workdir, log) with workdir holding total.json
    # Run in a temporary directory: fo writes its outputs in the CWD, and
    # the app must not litter the user's project with them.
    workdir = tempfile.mkdtemp(prefix="nightscribe-fo-")
    local_input = Path(workdir) / "obs.txt"
    shutil.copyfile(input_path, local_input)
    args = [binary, str(local_input)]
    if env_file:
        args += ["-D", env_file]
    if cpu_limit:
        args += ["-r", cpu_limit]
    try:
        proc = subprocess.run(args, cwd=workdir, capture_output=True,
                              text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as err:
        return False, workdir, f"Find_Orb failed: {err}"
    log = (proc.stdout or "") + (proc.stderr or "")
    return True, workdir, log


def parse_output(workdir):
    # @args: workdir - where `fo` ran
    # @return: dict {residuals: [...], elements: ..., ok: bool}
    # `fo` writes total.json with the elements, the observations and their
    # residuals. The exact schema is fixed in the phase-0 checklist, so the
    # parser is defensive: it walks the structure looking for the residual
    # records instead of trusting one shape.
    path = Path(workdir) / "total.json"
    if not path.exists():
        return {"residuals": [], "ok": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as err:
        logger.warning("cannot read Find_Orb's total.json: %s", err)
        return {"residuals": [], "ok": False}
    residuals = _find_residuals(data)
    return {"residuals": residuals, "ok": True, "raw": data}


def _find_residuals(node, out=None):
    # @args: node - a decoded JSON fragment, out - accumulator
    # @return: list of dicts {stn, time, dra, ddec}
    if out is None:
        out = []
    if isinstance(node, dict):
        keys = {k.lower() for k in node}
        if "dra" in keys or "resid" in keys or "residual" in keys:
            out.append(_as_residual(node))
        else:
            for value in node.values():
                _find_residuals(value, out)
    elif isinstance(node, list):
        for item in node:
            _find_residuals(item, out)
    return out


def _as_residual(node):
    # @args: node - one residual record
    # @return: {stn, time, dra, ddec} with whatever the record carries
    low = {k.lower(): v for k, v in node.items()}
    return {
        "stn": low.get("stn") or low.get("code") or low.get("station"),
        "time": low.get("time") or low.get("obstime") or low.get("jd"),
        "dra": _num(low.get("dra") or low.get("resid_ra")),
        "ddec": _num(low.get("ddec") or low.get("resid_dec")),
    }


def _num(value):
    # @args: value - a number or a string
    # @return: float or None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def robust_scatter(values):
    # @args: values - a list of numbers (arcsec)
    # @return: (median, mad_sigma) or (None, None)
    # The MAD is used, not the standard deviation: a single bad observer
    # must not raise the bar for everyone else.
    clean = [v for v in values if v is not None]
    if not clean:
        return None, None
    import numpy as np
    from . import outliers
    arr = np.asarray(clean, dtype=float)
    med = float(np.median(arr))
    mad = float(outliers.scaled_mad(arr, centre=med))
    return med, mad


def decide(our_dra, our_ddec, others, our_rms_arcsec=0.0, cfg=None):
    # @args: our_dra/our_ddec - our residual (arcsec), others - the list of
    #        the others' residuals {dra, ddec, stn}, our_rms_arcsec - our
    #        own uncertainty, cfg - Config
    # @return: CheckReport
    # z = residual / sqrt(our rms^2 + scatter^2): the residual is compared
    # with the cloud, not with zero. Without anyone to compare with, the
    # check does not block (D29).
    if not others:
        return CheckReport(no_reference=True, n_others=0,
                           our_residual=(our_dra, our_ddec),
                           note="no other observations to compare with")
    med_ra, mad_ra = robust_scatter([o.get("dra") for o in others])
    med_dec, mad_dec = robust_scatter([o.get("ddec") for o in others])
    if mad_ra is None or mad_dec is None:
        return CheckReport(no_reference=True, n_others=len(others),
                           note="the others' residuals could not be read")
    sigma = float(cfg.get("astrometry_check_sigma", 3.0)) if cfg else 3.0
    floor = float(cfg.get("astrometry_check_floor_arcsec", 1.0)) if cfg \
        else 1.0
    z_ra = (our_dra - med_ra) / math.hypot(mad_ra, our_rms_arcsec)
    z_dec = (our_ddec - med_dec) / math.hypot(mad_dec, our_rms_arcsec)
    sep = math.hypot(our_dra - med_ra, our_ddec - med_dec)
    outlier = (abs(z_ra) > sigma or abs(z_dec) > sigma) and sep > floor
    stations = {o.get("stn") for o in others if o.get("stn")}
    report = CheckReport(
        outlier=outlier, blocked=outlier,
        our_residual=(our_dra, our_ddec),
        scatter=(mad_ra, mad_dec), z=(z_ra, z_dec),
        n_others=len(others), n_stations=len(stations))
    if outlier:
        report.note = (f"our residual is {sep:.2f}\" from the others' "
                       f"cloud: check the measurement before sending")
    return report


def check(ours_lines, desig, cfg=None, others_lines=None, findorb_path=None,
          cancel=None, timeout=180):
    # @args: ours_lines - our 80-column lines, desig - the object, cfg -
    #        Config, others_lines - the published lines (when the caller
    #        already fetched them), findorb_path - override, cancel, timeout
    # @return: CheckReport
    # The whole handoff, in order: fetch the others (unless given), write
    # the file, run `fo`, parse the residuals, decide. Without Find_Orb the
    # check is NOT available and says so: it never fakes a verdict.
    binary, message = probe(findorb_path or
                            (cfg.get("findorb_path") if cfg else None))
    if not binary:
        return CheckReport(available=False, note=message)
    if others_lines is None:
        from .sources import mpc_obs
        others_lines = mpc_obs.observations_80(desig)
    workdir = None
    try:
        workdir = tempfile.mkdtemp(prefix="nightscribe-fo-in-")
        input_path = write_input(ours_lines, others_lines,
                                 Path(workdir) / "obs.txt")
        env_file = write_environment(Path(workdir) / "environ.dat")
        ok, run_dir, log = run(input_path, binary, env_file=env_file,
                               cancel=cancel, timeout=timeout)
        if not ok:
            return CheckReport(available=False, note=log)
        parsed = parse_output(run_dir)
        if not parsed["ok"] or not parsed["residuals"]:
            return CheckReport(available=False,
                               note="Find_Orb produced no residuals")
        return _decide_from_residuals(parsed["residuals"], cfg)
    finally:
        for path in (workdir,):
            if path:
                shutil.rmtree(path, ignore_errors=True)


def _decide_from_residuals(residuals, cfg):
    # @args: residuals - the parsed records, cfg - Config
    # @return: CheckReport
    # Split ours from the others: ours are the ones Find_Orb fitted OUT (a
    # zero weight) and reported as check observations; without that
    # distinction the caller would compare us with ourselves.
    ours = [r for r in residuals if r.get("check")]
    others = [r for r in residuals if not r.get("check")]
    if not ours:
        ours = residuals[:1]
        others = residuals[1:]
    if not ours:
        return CheckReport(no_reference=True, note="no residual for ours")
    our = ours[0]
    return decide(our.get("dra"), our.get("ddec"), others, cfg=cfg)
