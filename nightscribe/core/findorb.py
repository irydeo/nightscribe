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
- `fo` writes its JSON (total.json, with the residuals) to its CONFIGURATION
  directory (~/.find_orb on Linux), NOT the current directory, and only when
  the JSON_*_NAME settings say so. It is run in a temporary one and the
  private `-D` environment points every output at that directory, so the
  parser finds total.json where it ran (and two runs cannot collide). It
  also creates ~/.find_orb on first use, which is the other reason for `-D`.
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
import time
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
    no_fit: bool = False                    # Find_Orb could not fit an orbit
    our_residual: tuple | None = None      # (dra, ddec) arcsec
    scatter: tuple | None = None           # (dra, ddec) arcsec, robust
    z: tuple | None = None
    n_others: int = 0
    n_stations: int = 0
    note: str = ""
    # The whole published list, ours included, so the GUI can show the
    # table the observer asked for (Find_Orb's own Num/Date/Stn/RA/Dec/
    # dRA/dDec). Each row is a dict; `ours` marks our own observations.
    residuals: list = field(default_factory=list)
    # The identity facts: where the reference came from, the designation
    # it really lives under (a NEOCP object confirmed since the visit) and
    # the MPEC that published it. The GUI shows them as the rename notice.
    reference: str = ""                     # "MPC" | "NEOCP" | ""
    resolved_desig: str = ""                # the confirmed designation, if any
    mpec: str = ""
    mpec_url: str = ""
    confirmed_at: str = ""
    ours_published: bool = False            # our station already in the list
    n_obs: int = 0


def auto_find():
    # @return: (path or None, why) the `fo` the app finds on its own and a
    #          short plain-language reason, for the Settings screen to fill
    #          the field with and for the check to use. Nothing configured:
    #          this is what "out of the box" means.
    #
    # The order answers the most work first: the copy the app SHIPS (the
    # packaged installs), then the two folders the APP ITSELF tells the
    # observer to use, then PATH.
    #
    # Those two folders are here because following the app's own instructions
    # has to work: `~/findorb` is the command the install dialog prints, and
    # `<data dir>/findorb` is where the guided install puts its private
    # environment by default. Until 2026-10-17 only the bundled copy and PATH
    # were searched, so an observer who did exactly what the dialog said (or
    # who runs from a source tree or a pip install, which ship no copy) read
    # "Find_Orb is not configured" with the program sitting right there
    # (reported 2026-10-17).
    from .. import paths
    from .findorb_install import bundled_fo, find_fo, find_on_path
    bundle = paths.findorb_bundle_dir()
    found = bundled_fo()
    if found:
        return found, "bundled with NightScribe"
    if bundle is not None and not os.access(bundle, os.R_OK | os.X_OK):
        # There IS a copy and this user cannot read it: say THAT instead of
        # "not configured", which sends the observer looking for what is
        # already installed. Measured 2026-10-17: the Linux packages shipped
        # the tree as drwx------ root root, so the app could not even enter
        # the folder and Find_Orb "was not there" with its 63 files on disk.
        return None, (f"the copy that ships with NightScribe is at {bundle} "
                      f"but this user cannot read it: check its permissions")
    for folder, why in ((Path.home() / "findorb", "in your home folder"),
                        (paths.data_dir() / "findorb",
                         "in NightScribe's folder")):
        found = find_fo(folder)
        if found:
            return found, why
    found = find_on_path()
    if found:
        return found, "on your PATH"
    return None, ""


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
        # A configured path that is GONE is not the end of it: the copy the
        # app ships (or the one it can find on its own) is still a Find_Orb,
        # and saying "not found" while one sits there is the same lie as
        # before. It is said that the old one moved.
        found, why = auto_find()
        if found:
            return found, (f"the configured Find_Orb is gone ({candidate}); "
                           f"using {found} ({why})")
        return None, (f"not found: {candidate}" + (f". {why}" if why else ""))
    # No configured path: the copy NightScribe SHIPS, then the folders the
    # app's own instructions use, then PATH.
    found, why = auto_find()
    if found:
        return found, f"Find_Orb at {found} ({why})"
    return None, why or "Find_Orb is not configured (Settings > Measurement)"


def _seed_findorb_home(home):
    # @args: home - the private HOME (paths.findorb_home_dir)
    # @return: None. On the first run, copy the data NightScribe ships into
    #          `<home>/.find_orb`, which is where Find_Orb looks for it, and
    #          place the JPL ephemeris if the bundle carries one.
    # This is the piece that makes a RELOCATED `fo` work. The `fo` we ship
    # was built with its package manager's prefix baked into the binary and
    # copies `share/findorb/data` to `$HOME/.find_orb` on the first run; on a
    # machine where that prefix does not exist the copy throws and the run
    # dies before reading a single observation (measured 2026-10-11). Seeding
    # the folder first means the copy is a no-op and `fo` starts.
    # Two layouts: the conda one (share/findorb/data) and the Project Pluto
    # zip, which unpacks its data files flat next to the executable.
    cfg = Path(home) / ".find_orb"
    from .. import paths
    bundle = paths.findorb_bundle_dir()
    if bundle is None:
        return
    data = bundle / "share" / "findorb" / "data"
    flat = not data.is_dir()
    if flat and (bundle / "ObsCodes.htm").is_file():
        data = bundle
    if data.is_dir() and not (cfg / "ObsCodes.htm").exists():
        cfg.mkdir(parents=True, exist_ok=True)
        for item in data.iterdir():
            if not item.is_file():
                continue
            if flat and item.suffix.lower() in (".exe", ".dll", ".zip"):
                continue      # the zip's programs stay where they are
            dest = cfg / item.name
            if not dest.exists():
                try:
                    shutil.copy2(item, dest)
                except OSError:
                    pass
    # The JPL ephemeris (DE430t) is optional and large: it may come with the
    # package or be downloaded from Settings. Find_Orb reads it from
    # `.find_orb` too, so a bundled one is linked (or copied on Windows).
    for eph in (bundle / "share" / "findorb" / "jpl_eph", bundle):
        if not eph.is_dir():
            continue
        for item in eph.iterdir():
            if item.suffix.lower() != ".430t":
                continue
            cfg.mkdir(parents=True, exist_ok=True)
            dest = cfg / item.name
            if dest.exists():
                continue
            try:
                dest.symlink_to(item)
            except OSError:
                try:
                    shutil.copy2(item, dest)
                except OSError:
                    pass


def _private_env():
    # @return: os.environ with HOME (and USERPROFILE, for Windows) pointed at
    #          the private Find_Orb home, seeded on the way.
    from .. import paths
    home = paths.findorb_home_dir()
    _seed_findorb_home(home)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return env


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
    # Run in a temporary directory and tell fo to write EVERYTHING there.
    # On Linux fo drops its JSON in its configuration directory (~/.find_orb)
    # unless OUTPUT_DIR and the JSON_*_NAME settings say otherwise, and it
    # only writes total.json when the names are set: without this the parser
    # looked for a file that was never written ("produced no residuals").
    workdir = tempfile.mkdtemp(prefix="nightscribe-fo-")
    local_input = Path(workdir) / "obs.txt"
    shutil.copyfile(input_path, local_input)
    base = ""
    if env_file and Path(env_file).exists():
        base = Path(env_file).read_text(encoding="utf-8", errors="replace")
    local_env = Path(workdir) / "environ.dat"
    local_env.write_text(base.rstrip() + "\n" + "\n".join([
        f"OUTPUT_DIR={workdir}",
        f"JSON_COMBINED_NAME={Path(workdir) / 'total.json'}",
        f"JSON_ELEMENTS_NAME={Path(workdir) / 'elements.json'}",
        f"JSON_SHORT_ELEMENTS={Path(workdir) / 'short.json'}",
    ]) + "\n", encoding="utf-8")
    args = [binary, str(local_input), "-D", str(local_env)]
    if cpu_limit:
        args += ["-r", cpu_limit]
    try:
        # A PRIVATE home (paths.findorb_home_dir) keeps Find_Orb's own
        # `~/.find_orb` inside NightScribe's data folder and, seeded with the
        # shipped data, is what lets the `fo` we ship run at all (see
        # _seed_findorb_home).
        proc = subprocess.Popen(args, cwd=workdir, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                env=_private_env())
    except OSError as err:
        return False, workdir, f"Find_Orb failed: {err}"
    # Poll instead of subprocess.run: a run can last up to the CPU limit or
    # the wall timeout, and the observer's Cancel has to be able to stop it.
    # subprocess.run(timeout=...) cannot be interrupted, so the button used
    # to do nothing until `fo` finished on its own (QA-07).
    deadline = time.monotonic() + float(timeout) if timeout else None
    while True:
        try:
            out, err = proc.communicate(timeout=0.2)
            break
        except subprocess.TimeoutExpired:
            pass
        if cancel is not None and cancel():
            _terminate(proc)
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            return False, workdir, "Find-Orb cancelled"
        if deadline is not None and time.monotonic() >= deadline:
            _terminate(proc)
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            return False, workdir, f"Find_Orb failed: timeout after {timeout}s"
    log = (out or "") + (err or "")
    return True, workdir, log


def _terminate(proc):
    # @args: proc - the subprocess.Popen running `fo`
    # @return: None. Terminate, then kill if it does not answer.
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


def parse_output(workdir):
    # @args: workdir - where `fo` ran
    # @return: dict {residuals: [...], ok: bool, incomplete: bool}
    # `fo` writes total.json with the elements, the observations and their
    # residuals. The exact schema is fixed in the phase-0 checklist, so the
    # parser is defensive: it walks the structure looking for the residual
    # records instead of trusting one shape.
    #
    # Two very different failures are told apart here. No file at all means
    # Find_Orb never wrote its answer (ok=False). A file that exists but is
    # empty or truncated is the signature of a fit that produced ZERO
    # objects: with nothing to fit, `fo` writes the header and stops
    # ("objects": { and no closing brace), which is NOT valid JSON. That is
    # "it ran but could not fit", not "it failed", so it is reported as
    # ok=True with no residuals and `incomplete=True`; the caller then says
    # the honest thing instead of "produced no residuals".
    path = Path(workdir) / "total.json"
    if not path.exists():
        return {"residuals": [], "ok": False, "incomplete": False}
    raw = path.read_text(encoding="utf-8", errors="replace")
    if not raw.strip():
        return {"residuals": [], "ok": True, "incomplete": True}
    try:
        data = json.loads(raw)
    except ValueError:
        # a truncated file: Find_Orb fitted no object (see above)
        logger.warning("Find_Orb's total.json is truncated: no object fitted")
        return {"residuals": [], "ok": True, "incomplete": True}
    residuals = _find_residuals(data)
    return {"residuals": residuals, "ok": True, "incomplete": False,
            "raw": data}


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


def _first(node, *keys):
    # @args: node - a dict with lowercased keys, keys - candidate key names
    # @return: the first present, non-None value (None when none is)
    # `value or fallback` is WRONG for numbers: a residual of exactly 0.0
    # is a perfect fit, not "missing", and would fall through to the next
    # key (or to None). This picks the first key that is PRESENT.
    for key in keys:
        if key in node and node[key] is not None:
            return node[key]
    return None


def _as_residual(node):
    # @args: node - one residual record
    # @return: a normalised dict with whatever the record carries
    # The record is exactly what the listing needs: the instant, the
    # station, the observed direction, the residual in RA and Dec and the
    # magnitude. Find_Orb's total.json names the station "obscode" and the
    # fields "dRA"/"dDec"/"RA"/"Dec"; the others are tolerated so a schema
    # change does not silently empty a column.
    low = {k.lower(): v for k, v in node.items()}
    return {
        "stn": (_first(low, "obscode", "stn", "code", "station") or ""),
        "time": _first(low, "jd", "time", "obstime"),
        "iso": _first(low, "iso date", "iso_date", "iso") or "",
        "ra": _num(_first(low, "ra", "resid_ra")),
        "dec": _num(_first(low, "dec", "resid_dec")),
        "dra": _num(_first(low, "dra", "resid_ra")),
        "ddec": _num(_first(low, "ddec", "resid_dec")),
        "mag": _num(_first(low, "magobs", "mag")),
        "band": _first(low, "magband", "band") or "",
        "note": (_first(low, "note1", "note") or "").strip(),
        "ours": False,
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


def _our_code(cfg, obs_code=None):
    # @args: cfg - Config or None, obs_code - an explicit station code
    # @return: our MPC station code, upper-cased ("" when unknown)
    code = obs_code
    if not code and cfg is not None:
        code = cfg.get("mpc_code") if hasattr(cfg, "get") else None
    return str(code or "").strip().upper()


def _our_jds(ours_lines):
    # @args: ours_lines - our 80-column lines (string or list)
    # @return: the Julian dates we submitted, as floats
    # The instant is what identifies OUR residuals when the MPC already
    # holds other observations from our own station (a visit is not the
    # first time a code appears): matching by station alone would pick the
    # older published point and compare us with ourselves. The date is
    # columns 15-31 ("YYYY MM DD.DDDDDDD", UTC), so the same clock the app
    # wrote it with converts it back (core/coords).
    from .coords import jd_from_datetime
    import datetime as _dt
    out = []
    for line in _lines(ours_lines):
        if len(line) < 32:
            continue
        try:
            year = int(line[15:19])
            month = int(line[20:22])
            day = float(line[23:32])
        except (ValueError, IndexError):
            continue
        base = _dt.datetime(year, month, 1, tzinfo=_dt.timezone.utc)
        out.append(jd_from_datetime(base + _dt.timedelta(days=day - 1)))
    return out


def _match_ours(residuals, our_jds, want_code):
    # @args: residuals - the parsed records, our_jds - our submitted JDs,
    #        want_code - our station code
    # @return: (ours, others) with EVERY record that is ours flagged
    # Four identities, strongest first, because the same station can appear
    # more than once and our line can be MERGED by Find_Orb into an already
    # published near-duplicate (same station, seconds apart):
    #   1. the exact instants we submitted AND our station (the real answer);
    #   2. the exact instants, any station (our line accepted, station blank);
    #   3. our station, the record nearest our instant (Find_Orb merged our
    #      near-duplicate into a published point: our data is already there);
    #   4. the first line, which is ours because write_input puts ours first.
    # ALL of ours are flagged (ADR-086 rev): a combined run submits several
    # observations, and the check must see each one, not just the first.
    tol = 1e-6   # ~0.09 s: the 80-column time carries ~0.9 ms
    for r in residuals:      # every row carries the flag the table reads
        r["ours"] = False

    def time_ok(r):
        jd = r.get("time")
        return (jd is not None
                and any(abs(float(jd) - o) <= tol for o in our_jds))

    def stn_ok(r):
        return bool(want_code) and \
            str(r.get("stn") or "").strip().upper() == want_code

    ours = [r for r in residuals if time_ok(r) and (not want_code or stn_ok(r))]
    if not ours:
        ours = [r for r in residuals if time_ok(r)]
    if not ours and want_code:
        near = [r for r in residuals if stn_ok(r)]
        if near:
            ours = [min(near, key=lambda r: min(
                (abs(float(r["time"]) - o) for o in our_jds), default=0.0)
                if r.get("time") is not None else 0.0)]
    if not ours and residuals:
        ours = [residuals[0]]
    if not ours:
        return [], []
    for r in ours:
        r["ours"] = True
    ids = {id(r) for r in ours}
    others = [r for r in residuals if id(r) not in ids]
    return ours, others


def check(ours_lines, desig, cfg=None, others_lines=None, findorb_path=None,
          cancel=None, timeout=180, obs_code=None):
    # @args: ours_lines - our 80-column lines, desig - the object, cfg -
    #        Config, others_lines - the published lines (when the caller
    #        already fetched them), findorb_path - override, cancel, timeout,
    #        obs_code - our MPC station code (to flag our own rows)
    # @return: CheckReport
    # The whole handoff, in order: fetch the others (unless given), write
    # the file, run `fo`, parse the residuals, decide. Without Find_Orb the
    # check is NOT available and says so: it never fakes a verdict.
    binary, message = probe(findorb_path or
                            (cfg.get("findorb_path") if cfg else None))
    if not binary:
        return CheckReport(available=False, note=message)
    ref = None
    if others_lines is None:
        from .sources import mpc_obs
        ref = mpc_obs.reference_80(desig, obs_code=_our_code(cfg, obs_code))
        others_lines = ref.lines
    if not _lines(others_lines):
        # No published observations means nothing to fit an orbit from, so
        # there is nothing to compare with. That is NOT a Find_Orb failure
        # and must not be dressed up as one: an object known only by its
        # NEOCP name used to answer "Find_Orb produced no residuals" when
        # the real cause was an empty reference. Say it plainly, and carry
        # the identity facts (it may have been confirmed since).
        note = (ref.note if ref else "") or (
            f"no published observations found for {desig}")
        return CheckReport(
            no_reference=True, note=note,
            reference=(ref.source if ref else ""),
            resolved_desig=(ref.designation if ref else ""),
            mpec=(ref.mpec if ref else ""),
            mpec_url=(ref.mpec_url if ref else ""),
            confirmed_at=(ref.confirmed_at if ref else ""),
            ours_published=(ref.ours_present if ref else False))
    workdir = None
    run_dir = None
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
        if not parsed["ok"]:
            return CheckReport(available=False,
                               note="Find_Orb produced no output")
        if not parsed["residuals"]:
            # It ran, but fitted no object: too few or too short a set of
            # reference observations. Honest wording, not "no residuals".
            report = CheckReport(
                no_fit=True,
                note="Find_Orb could not fit an orbit from the published "
                     "observations (too few or too short an arc)")
            _attach_reference(report, ref)
            return report
        report = _decide_from_residuals(parsed["residuals"], cfg,
                                        _our_code(cfg, obs_code),
                                        ours_lines=ours_lines)
        _attach_reference(report, ref)
        return report
    finally:
        # BOTH the input folder and the one `run` made for itself: the
        # latter was left behind, one `nightscribe-fo-*` per check
        # (reported 2026-10-15).
        for path in (workdir, run_dir):
            if path:
                shutil.rmtree(path, ignore_errors=True)


def _attach_reference(report, ref):
    # @args: report - a CheckReport, ref - a mpc_obs.Reference or None
    # @return: None. Copies the identity facts onto the report so the GUI
    #          can show the rename notice without another network call.
    if ref is None:
        return
    report.reference = ref.source
    report.resolved_desig = ref.designation
    report.mpec = ref.mpec
    report.mpec_url = ref.mpec_url
    report.confirmed_at = ref.confirmed_at
    report.ours_published = ref.ours_present


def _decide_from_residuals(residuals, cfg, obs_code="", ours_lines=None):
    # @args: residuals - the parsed records, cfg - Config, obs_code - our
    #        station, ours_lines - our 80-column lines (to match by instant)
    # @return: CheckReport
    # Split ours from the others. Find_Orb's total.json has no "check" flag,
    # so ours are found by the instant we submitted, then by our station.
    # Without that distinction the caller would compare us with ourselves.
    our_jds = _our_jds(ours_lines) if ours_lines is not None else []
    ours, others = _match_ours(residuals, our_jds, obs_code)
    if not ours:
        return CheckReport(no_reference=True, note="no residual for ours")
    # The verdict is about the WORST of ours, not the first one (ADR-086
    # rev): a combined run submits several observations, and reporting the
    # first one hid a spurious point behind a good one (measured 2026-10-13:
    # a combined check blocked at 255" because ours[0] was the bad one).
    if len(ours) > 1 and others:
        med_ra, _ = robust_scatter([o.get("dra") for o in others])
        med_dec, _ = robust_scatter([o.get("ddec") for o in others])

        def _sep(r):
            return math.hypot((r.get("dra") or 0.0) - (med_ra or 0.0),
                              (r.get("ddec") or 0.0) - (med_dec or 0.0))

        our = max(ours, key=_sep)
    else:
        our = ours[0]
    report = decide(our.get("dra"), our.get("ddec"), others, cfg=cfg)
    report.residuals = residuals
    report.n_obs = len(residuals)
    return report
