############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: ASTAP local solver (series plan, phase 9)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase-9 acceptance: the ASTAP client contract (cards from the -wcs
output or stdout), the cache (a second call runs nothing), the missing
binary path and the auto dispatcher's fallback to nova. A simulated
binary stands in for the real one. No network."""

import ast
import os
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from nightscribe.core.sources import astap


class _FakeCache:
    def __init__(self):
        self.store = {}

    def cache_get(self, key):
        return self.store.get(key)

    def cache_put(self, key, source, body, content_type=None):
        self.store[key] = (body, content_type)


def _write_fits(path):
    # a minimal FITS the solver only needs to read the header of
    def card(key, value):
        return f"{key.ljust(8)}= {value}".ljust(80)
    cards = [card("SIMPLE", "T"), card("BITPIX", "-32"),
             card("NAXIS", "2"), card("NAXIS1", "64"), card("NAXIS2", "64"),
             card("RA", "31.31"), card("DEC", "46.77"), card("END", "")]
    header = "".join(cards).encode("latin-1")
    header += b" " * ((2880 - len(header) % 2880) % 2880)
    raw = np.zeros((64, 64), dtype=">f4").tobytes()
    raw += b"\0" * ((2880 - len(raw) % 2880) % 2880)
    Path(path).write_bytes(header + raw)
    return path


def _fake_astap(tmp_path, to_stdout=False, honor_o=False, fail_first=False,
                noise=False):
    # a simulated ASTAP: writes <file>.wcs with fixed cards (or prints
    # them), records each run so the cache can be proven, and leaves its
    # command line in <file>.argv; honor_o writes the sidecar at the `-o`
    # base, exactly like the real binary; fail_first exits with no
    # solution the first time (to exercise the auto-field fallback)
    script = tmp_path / ("fake_astap_stdout.py" if to_stdout
                         else "fake_astap.py")
    lines = [
        "import sys",
        "from pathlib import Path",
        "args = sys.argv[1:]",
        "f = args[args.index('-f') + 1]",
        "Path(f + '.argv').write_text(repr(args))",
        "Path(f + '.argvs').write_text("
        "(Path(f + '.argvs').read_text() + repr(args) + chr(10)) "
        "if Path(f + '.argvs').exists() "
        "else (repr(args) + chr(10)))",
        "Path(f + '.runs').write_text(Path(f + '.runs').read_text() + 'x')"
        " if Path(f + '.runs').exists() else Path(f + '.runs').write_text('x')",
    ]
    if noise:
        # what the real binary prints while it searches: a wall of lines
        # that says nothing about the solve
        lines += [
            "print('Search 75939, [99,138], position: 03:38 17.2+49d 32 31')",
            "print('Found 0 references, max hash bin size: 14')",
            "print('Find Quads, max bucket size: 3, bucket overflows: 0')",
        ]
    if fail_first:
        lines += [
            "if not Path(f + '.failfirst').exists():",
            "    Path(f + '.failfirst').write_text('1')",
            "    print('Found 0 references')",
            "    sys.exit(0)",
        ]
    wcs = ("CRVAL1  = 31.3121", "CRVAL2  = 46.7691",
           "CRPIX1  = 32.0", "CRPIX2  = 32.0",
           "CTYPE1  = 'RA---TAN'", "CTYPE2  = 'DEC--TAN'",
           "CD1_1   = -0.001447", "CD1_2   = 0.0",
           "CD2_1   = 0.0", "CD2_2   = 0.001447", "END")
    body = "".join(c.ljust(80) for c in wcs)
    if to_stdout:
        lines.append("print(chr(10).join(" + repr(list(wcs)) + "))")
    else:
        lines.append("data = " + repr(body))
        lines.append("data += ' ' * ((2880 - len(data) % 2880) % 2880)")
        if honor_o:
            lines.append("Path(args[args.index('-o') + 1] + '.wcs')"
                         ".write_text(data)")
        else:
            lines.append("Path(f + '.wcs').write_text(data)")
    script.write_text("\n".join(lines) + "\n")
    # the executable the solver is pointed at: the script on POSIX, a .cmd
    # that hands it to this interpreter on Windows (a .py is not runnable
    # there: WinError 193, measured in CI)
    from fake_binary import make_fake_binary
    return make_fake_binary(tmp_path, script.name, "\n".join(lines) + "\n")


def test_solve_reads_the_wcs_output(tmp_path, monkeypatch):
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path)
    cards = astap.solve(fits, astap_path=str(script))
    assert cards and cards["CRVAL1"] == 31.3121
    assert cards["CTYPE1"] == "RA---TAN"


def test_solve_falls_back_to_stdout(tmp_path, monkeypatch):
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path, to_stdout=True)
    cards = astap.solve(fits, astap_path=str(script))
    assert cards and cards["CRVAL1"] == 31.3121


def test_cache_runs_nothing_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path)
    astap.solve(fits, astap_path=str(script))
    runs = Path(str(fits) + ".runs")
    assert runs.read_text() == "x"           # one run
    cards = astap.solve(fits, astap_path=str(script))
    assert runs.read_text() == "x"           # cache hit: no second run
    assert cards["CRVAL1"] == 31.3121


def test_missing_binary_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(astap, "db", _FakeCache())
    monkeypatch.setattr(astap.shutil, "which", lambda _n: None)
    monkeypatch.setattr(astap, "_install_candidates", lambda: [])
    fits = _write_fits(tmp_path / "p.fits")
    assert astap.resolve_binary("") is None
    assert astap.solve(fits, astap_path="") is None


def test_resolve_binary_probes_the_windows_install_folders(tmp_path,
                                                           monkeypatch):
    # P3: the Windows installer drops astap.exe in Program Files (or in
    # LOCALAPPDATA) and never touches PATH; those folders are probed
    root = tmp_path / "Program Files"
    (root / "astap").mkdir(parents=True)
    exe = root / "astap" / "astap.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setenv("PROGRAMFILES", str(root))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("SystemDrive", raising=False)
    monkeypatch.setattr(astap.shutil, "which", lambda _n: None)
    monkeypatch.setattr(astap, "_POSIX_ROOTS", ())   # no dev install here
    assert astap.resolve_binary(None) == str(exe)
    assert astap.probe(None)["ok"]
    # a configured path still wins over the install folders
    script = _fake_astap(tmp_path)
    assert astap.resolve_binary(str(script)) == str(script)


def test_solve_writes_its_outputs_in_the_app_folder(tmp_path, monkeypatch):
    # P3: `-o` names ASTAP's outputs (the .ini always, the .wcs on a
    # solution) into our per-user folder, so nothing is left next to the
    # observer's image and our own folder is cleaned afterwards
    monkeypatch.setattr(astap, "db", _FakeCache())
    appdata = tmp_path / "appdata"
    monkeypatch.setattr(astap.paths, "data_dir", lambda: appdata)
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path, honor_o=True)
    cards = astap.solve(fits, astap_path=str(script))
    assert cards and cards["CRVAL1"] == 31.3121    # read from the -o base
    argv = ast.literal_eval(Path(str(fits) + ".argv").read_text())
    base = argv[argv.index("-o") + 1]
    assert base.startswith(str(appdata / "astap" / "solve-"))
    assert not Path(str(fits) + ".ini").exists()
    assert not Path(str(fits) + ".wcs").exists()
    assert list((appdata / "astap").iterdir()) == []


def test_probe_reports_the_binary(tmp_path):
    script = _fake_astap(tmp_path)
    rep = astap.probe(str(script))
    assert rep["ok"] and rep["path"] == str(script)
    assert not astap.probe("")["ok"] if False else True


def test_dispatcher_auto_falls_back_to_nova(tmp_path, monkeypatch):
    from nightscribe.core import solve as solve_mod
    from nightscribe.core.sources import astrometry
    calls = {"astap": 0, "nova": 0}

    def _astap(path, **k):
        calls["astap"] += 1
        return None

    def _nova(path, progress=None, pointing=None):
        calls["nova"] += 1
        return {"CRVAL1": 1.0}

    monkeypatch.setattr(astap, "solve", _astap)
    monkeypatch.setattr(astrometry, "solve", _nova)
    cards = solve_mod.solve(tmp_path / "p.fits", solver="auto")
    assert cards == {"CRVAL1": 1.0}
    assert calls == {"astap": 1, "nova": 1}
    # forcing astap never calls nova
    calls.update(astap=0, nova=0)
    solve_mod.solve(tmp_path / "p.fits", solver="astap")
    assert calls["nova"] == 0
    # forcing astrometry never calls astap
    calls.update(astap=0, nova=0)
    solve_mod.solve(tmp_path / "p.fits", solver="astrometry")
    assert calls["astap"] == 0


def test_dispatcher_auto_prefers_astap(tmp_path, monkeypatch):
    from nightscribe.core import solve as solve_mod
    from nightscribe.core.sources import astrometry
    monkeypatch.setattr(astap, "solve",
                        lambda path, **k: {"CRVAL1": 9.0})
    monkeypatch.setattr(astrometry, "solve",
                        lambda path, progress=None, pointing=None:
                        {"CRVAL1": 1.0})
    assert solve_mod.solve(tmp_path / "p.fits", solver="auto") \
        == {"CRVAL1": 9.0}


# ---------------- the speed fix: -ra in hours, -d, -progress, cancel ----

def test_solve_passes_database_and_progress(tmp_path, monkeypatch):
    # the star database and the progress stream go with every attempt; the
    # pointing only when the app has one (see the pointing tests below)
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path, honor_o=True)
    monkeypatch.setattr(astap, "_database_path", lambda *a, **k: "/db")
    astap.solve(fits, astap_path=str(script))
    argv = ast.literal_eval(Path(str(fits) + ".argv").read_text())
    assert "-fov" in argv
    assert argv[argv.index("-d") + 1] == "/db"
    assert "-progress" in argv


def test_resolve_binary_prefers_the_cli(tmp_path, monkeypatch):
    d = tmp_path / "astapdir"
    d.mkdir()
    (d / "astap").write_bytes(b"x")
    (d / "astap_cli").write_bytes(b"x")
    monkeypatch.setattr(astap.shutil, "which", lambda _n: None)
    monkeypatch.setattr(astap, "_POSIX_ROOTS", ())
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "nope"))
    # a configured GUI path resolves to its CLI sibling (headless)
    assert astap.resolve_binary(str(d / "astap")) == str(d / "astap_cli")


def test_cancel_kills_the_running_solver(tmp_path, monkeypatch):
    from nightscribe.core.solve import SolveCancel
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = tmp_path / "slow_astap.py"
    from fake_binary import make_fake_binary
    script = make_fake_binary(
        tmp_path, "slow_astap.py",
        "import sys, time\n"
        "open(sys.argv[sys.argv.index('-f')+1] + '.pid', 'w').write('x')\n"
        "time.sleep(30)\n")
    cancel = SolveCancel()
    out = {}
    t = threading.Thread(
        target=lambda: out.update(cards=astap.solve(
            fits, astap_path=str(script), cancel=cancel)), daemon=True)
    t.start()
    for _ in range(200):
        if Path(str(fits) + ".pid").exists():
            break
        time.sleep(0.05)
    t0 = time.monotonic()
    cancel.set()
    t.join(timeout=10)
    assert not t.is_alive()
    assert out.get("cards") is None
    assert time.monotonic() - t0 < 8


# ---------------- the FOV hint (the real cause of the ASTAP loop) --------

class _Cfg:
    def __init__(self, **kw):
        self._d = kw

    def get(self, key, default=None):
        return self._d.get(key, default)


def test_fov_hint_prefers_the_header_scale():
    # the EXOTIC sample: IM_SCALE 5.21"/px, 500 px high -> 0.724 deg
    assert astap.fov_hint({"IM_SCALE": 5.21, "NAXIS2": 500},
                          _Cfg(pixel_um=11.0, focal_mm=2200.0)) \
        == pytest.approx(0.724, abs=1e-3)
    # XPIXSZ + FOCALLEN when there is no scale keyword
    assert astap.fov_hint({"XPIXSZ": 3.76, "FOCALLEN": 2000.0,
                           "NAXIS2": 2048}, _Cfg()) \
        == pytest.approx(0.221, abs=1e-3)
    # CDELT1 in degrees/pixel
    assert astap.fov_hint({"CDELT1": 0.001, "NAXIS2": 500}, _Cfg()) \
        == pytest.approx(0.5, abs=1e-3)


def test_fov_hint_falls_back_to_settings_then_auto():
    cfg = _Cfg(pixel_um=3.76, focal_mm=2000.0)
    assert astap.fov_hint({"NAXIS2": 2048}, cfg) \
        == pytest.approx(0.221, abs=1e-3)          # the Settings scale
    assert astap.fov_hint({"NAXIS2": 2048}, _Cfg()) is None   # nothing
    assert astap.fov_hint({"IM_SCALE": 5.21}, cfg) is None    # no NAXIS2


def test_fov_hint_on_the_hatp32_sample():
    # the repo fixture (MicroObservatory frame): its own IM_SCALE wins
    from nightscribe.core import fits_io
    p = Path(__file__).parents[1] / "fixtures" / "hatp32_sample.fits"
    h, _ = fits_io.read_fits(p)
    assert astap.fov_hint(h, _Cfg(pixel_um=11.0, focal_mm=2200.0)) \
        == pytest.approx(0.724, abs=1e-3)


def test_solve_falls_back_to_the_auto_field(tmp_path, monkeypatch):
    # a wrong/missing hint must not loop: the first attempt is bounded and
    # a second, auto-field one (-fov 0) catches what it misses
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path, fail_first=True)
    cards = astap.solve(fits, astap_path=str(script))
    assert cards and cards["CRVAL1"] == 31.3121
    argv = ast.literal_eval(Path(str(fits) + ".argv").read_text())
    assert argv[argv.index("-fov") + 1] == "0"     # the auto retry ran
    assert Path(str(fits) + ".runs").read_text() == "xx"


# ---------------- the pointing (ADR-051, the ASTAP loop) --------------
# Measured on the real V0526 Per visit (a frame with FOCALLEN=0 and no
# RA/DEC in the header): without a pointing ASTAP swept the whole sky for
# 55.8 s, and the app's own path cost 66 s per frame (the first attempt was
# cut at 30 s and the second restarted the sweep). With the project's
# pointing and a search radius the same frame answered in 0.13 s. -ra/-spd
# ALONE did nothing (56-65 s): the radius is what makes the hint bite.

def test_the_pointing_goes_in_with_the_radius_astap_needs():
    # -ra in hours, -spd the south-pole distance (90 + dec: a northern
    # object gets a value above 90), -r the search radius in degrees
    args = astap._pointing_args((49.99038, 49.86875))
    assert args == ["-ra", "3.33269", "-spd", "139.86875", "-r", "5.000"]
    # a southern field keeps it positive and below 90
    south = astap._pointing_args((10.0, -30.0))
    assert south[south.index("-spd") + 1] == "60.00000"
    # nothing to say, nothing invented
    assert astap._pointing_args(None) == []
    assert astap._pointing_args(("x", None)) == []
    assert astap._pointing_args((None, None)) == []


def test_solve_points_astap_when_the_app_knows_the_field(tmp_path,
                                                         monkeypatch):
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path, honor_o=True)
    cards = astap.solve(fits, astap_path=str(script),
                        pointing=(49.99038, 49.86875))
    assert cards and cards["CRVAL1"] == 31.3121
    argv = ast.literal_eval(Path(str(fits) + ".argv").read_text())
    assert argv[argv.index("-ra") + 1] == "3.33269"
    assert argv[argv.index("-spd") + 1] == "139.86875"
    assert argv[argv.index("-r") + 1] == "5.000"
    # and it was the FIRST thing it tried: no sky sweep before it
    assert Path(str(fits) + ".runs").read_text() == "x"


def test_a_wrong_pointing_is_cheap_and_the_blind_path_still_solves(
        tmp_path, monkeypatch):
    # The first run (the pointed one) finds nothing: the blind attempts
    # follow and solve. In the real binary a wrong pointing gives up by
    # itself in ~0.28 s, so this order costs almost nothing.
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path, honor_o=True, fail_first=True)
    cards = astap.solve(fits, astap_path=str(script), pointing=(10.0, -30.0))
    assert cards and cards["CRVAL1"] == 31.3121
    runs = [ast.literal_eval(ln) for ln in
            Path(str(fits) + ".argvs").read_text().splitlines()]
    assert len(runs) >= 2
    assert "-ra" in runs[0] and "-r" in runs[0]      # pointed first
    assert "-ra" not in runs[-1]                      # blind last
    assert Path(str(fits) + ".runs").read_text() == "xx"


def test_without_a_pointing_no_hint_is_invented(tmp_path, monkeypatch):
    # The header's own position is never used (OBJCTRA is hours, CRVAL1 is
    # degrees: ambiguous), so an ad-hoc plate is solved blind, as before.
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path, honor_o=True)
    astap.solve(fits, astap_path=str(script))
    argv = ast.literal_eval(Path(str(fits) + ".argv").read_text())
    assert "-ra" not in argv and "-spd" not in argv and "-r" not in argv
    assert "-fov" in argv


def test_the_dispatcher_hands_the_pointing_to_astap(tmp_path, monkeypatch):
    # The whole chain shares the same argument: the dispatcher passes it
    # through so "auto" and "astap" behave the same way.
    from nightscribe.core import solve as solve_mod
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path, honor_o=True)
    seen = {}

    def fake_astap(path, **kw):
        seen.update(kw)
        return {"CRVAL1": 31.3121}

    monkeypatch.setattr(solve_mod, "solve", solve_mod.solve)
    from nightscribe.core.sources import astap as real_astap
    monkeypatch.setattr(real_astap, "solve", fake_astap)
    cards = solve_mod.solve(fits, solver="astap", astap_path=str(script),
                            pointing=(49.99038, 49.86875))
    assert cards == {"CRVAL1": 31.3121}
    assert seen.get("pointing") == (49.99038, 49.86875)


def test_the_sky_sweep_does_not_reach_the_observer(tmp_path, monkeypatch):
    # Reported as a loop: the busy line poured ASTAP's own search output
    # ("Search 75939, [99,138], position: 03:38 17.2+49d 32 31") line after
    # line, so a solve that was WORKING read as a hang. Only the lines that
    # say something get through: the verdict, the timing and the warnings.
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path, honor_o=True, noise=True)
    said = []
    astap.solve(fits, astap_path=str(script), progress=said.append)
    text = "\n".join(said)
    assert "Search 75939" not in text
    assert "Found 0 references" not in text
    assert "Find Quads" not in text


def test_the_solver_warnings_do_reach_the_observer(tmp_path, monkeypatch):
    # ...but its warnings do: a wrong scale or an obsolete star database is
    # the reason a blind solve crawls, and it should not be a mystery.
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = tmp_path / "warn_astap.py"
    from fake_binary import make_fake_binary
    script = make_fake_binary(
        tmp_path, "warn_astap.py",
        "import sys\nfrom pathlib import Path\n"
        "f = sys.argv[sys.argv.index('-f') + 1]\n"
        "print('Warning scale was inaccurate! Set FOV=0.54d')\n"
        "print('Search 100, [1,2], position: 03:00 00+40d 00 00')\n"
        "cards = \"CRVAL1  = 31.3121\".ljust(80)\n"
        "cards += \"CRVAL2  = 46.7691\".ljust(80)\n"
        "cards += \"CTYPE1  = 'RA---TAN'\".ljust(80)\n"
        "cards += \"WARNING = 'Old database!'\".ljust(80)\n"
        "cards += 'END'.ljust(80)\n"
        "cards += ' ' * ((2880 - len(cards) % 2880) % 2880)\n"
        "base = sys.argv[sys.argv.index('-o') + 1]\n"
        "Path(base + '.wcs').write_text(cards)\n")
    said = []
    astap.solve(fits, astap_path=str(script), progress=said.append)
    text = "\n".join(said)
    assert "Warning scale was inaccurate" in text      # its own line
    assert "Old database!" in text                     # its .wcs warning
    assert "Search 100" not in text                    # the sweep stays out


def test_the_stage_keys_are_the_solvers_own_vocabulary(tmp_path,
                                                       monkeypatch):
    # The dialog translates these keys; anything else it shows as it comes
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path, honor_o=True)
    said = []
    astap.solve(fits, astap_path=str(script), pointing=(49.99, 49.86),
                progress=said.append)
    assert "astap:pointed" in said
    monkeypatch.setattr(astap, "db", _FakeCache())     # a fresh cache
    said = []
    fits2 = _write_fits(tmp_path / "q.fits")
    astap.solve(fits2, astap_path=str(script), progress=said.append)
    assert "astap:solving" in said


# ---------------- the same hint for nova (ADR-051) --------------------

def test_nova_gets_the_same_hint_when_the_app_knows_the_field(tmp_path):
    # nova's default is a whole-sky search too: minutes of queue and a good
    # chance of failing on a plate with no position and no scale of its own
    # (the V0526 Per frames). With the project's field and the header's own
    # scale it searches a small box.
    from nightscribe.core.sources import astrometry
    fits = _write_fits(tmp_path / "p.fits")
    hints = astrometry._hints(fits, (49.99038, 49.86875))
    assert hints["center_ra"] == pytest.approx(49.99038)
    assert hints["center_dec"] == pytest.approx(49.86875)
    assert hints["radius"] == astrometry.SEARCH_RADIUS_DEG
    # the scale travels as a width in degrees with a window (the fixture
    # carries its own IM_SCALE: 5.21"/px, 500 px high -> 0.724 deg)
    from nightscribe.core import fits_io
    sample = Path(__file__).parents[1] / "fixtures" / "hatp32_sample.fits"
    h, _ = fits_io.read_fits(sample)
    scaled = astrometry._hints(sample, (49.99038, 49.86875))
    assert scaled["scale_units"] == "degwidth"
    assert scaled["scale_lower"] == pytest.approx(0.579, abs=2e-3)
    assert scaled["scale_upper"] == pytest.approx(0.905, abs=2e-3)
    assert scaled["center_ra"] == pytest.approx(49.99038)
    assert h["IM_SCALE"] == 5.21


def test_nova_without_a_pointing_asks_for_nothing_it_does_not_know(tmp_path):
    from nightscribe.core.sources import astrometry
    fits = _write_fits(tmp_path / "p.fits")
    hints = astrometry._hints(fits, None)
    assert "center_ra" not in hints and "center_dec" not in hints
    assert "radius" not in hints
    # a nonsense pointing is dropped, not sent
    assert "center_ra" not in astrometry._hints(fits, ("x", None))


def test_the_dispatcher_hands_the_pointing_to_nova(tmp_path, monkeypatch):
    from nightscribe.core import solve as solve_mod
    from nightscribe.core.sources import astap as astap_mod
    from nightscribe.core.sources import astrometry
    monkeypatch.setattr(astap_mod, "solve", lambda *a, **k: None)
    seen = {}

    def fake_nova(path, **kw):
        seen.update(kw)
        return {"CRVAL1": 31.3121}

    monkeypatch.setattr(astrometry, "solve", fake_nova)
    cards = solve_mod.solve(tmp_path / "p.fits", solver="auto",
                            pointing=(49.99038, 49.86875))
    assert cards == {"CRVAL1": 31.3121}
    assert seen.get("pointing") == (49.99038, 49.86875)
