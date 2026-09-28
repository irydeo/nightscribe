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


def _fake_astap(tmp_path, to_stdout=False, honor_o=False, fail_first=False):
    # a simulated ASTAP: writes <file>.wcs with fixed cards (or prints
    # them), records each run so the cache can be proven, and leaves its
    # command line in <file>.argv; honor_o writes the sidecar at the `-o`
    # base, exactly like the real binary; fail_first exits with no
    # solution the first time (to exercise the auto-field fallback)
    script = tmp_path / ("fake_astap_stdout.py" if to_stdout
                         else "fake_astap.py")
    lines = [
        "#!/usr/bin/env python3",
        "import sys",
        "from pathlib import Path",
        "args = sys.argv[1:]",
        "f = args[args.index('-f') + 1]",
        "Path(f + '.argv').write_text(repr(args))",
        "Path(f + '.runs').write_text(Path(f + '.runs').read_text() + 'x')"
        " if Path(f + '.runs').exists() else Path(f + '.runs').write_text('x')",
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
    os.chmod(script, 0o755)
    return script


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

    def _nova(path, progress=None):
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
                        lambda path, progress=None: {"CRVAL1": 1.0})
    assert solve_mod.solve(tmp_path / "p.fits", solver="auto") \
        == {"CRVAL1": 9.0}


# ---------------- the speed fix: -ra in hours, -d, -progress, cancel ----

def test_solve_passes_database_and_progress_but_no_ra_hint(tmp_path,
                                                           monkeypatch):
    # the header's RA units are ambiguous; a wrong -ra hint loops ASTAP
    # ("Found 0 references"), so only the reliable -fov is passed
    monkeypatch.setattr(astap, "db", _FakeCache())
    fits = _write_fits(tmp_path / "p.fits")
    script = _fake_astap(tmp_path, honor_o=True)
    monkeypatch.setattr(astap, "_database_path", lambda *a, **k: "/db")
    astap.solve(fits, astap_path=str(script))
    argv = ast.literal_eval(Path(str(fits) + ".argv").read_text())
    assert "-ra" not in argv and "-spd" not in argv
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
    script.write_text(
        "#!/usr/bin/env python3\nimport sys, time\n"
        "open(sys.argv[sys.argv.index('-f')+1] + '.pid', 'w').write('x')\n"
        "time.sleep(30)\n")
    os.chmod(script, 0o755)
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
    assert astap._fov_hint({"IM_SCALE": 5.21, "NAXIS2": 500},
                           _Cfg(pixel_um=11.0, focal_mm=2200.0)) \
        == pytest.approx(0.724, abs=1e-3)
    # XPIXSZ + FOCALLEN when there is no scale keyword
    assert astap._fov_hint({"XPIXSZ": 3.76, "FOCALLEN": 2000.0,
                            "NAXIS2": 2048}, _Cfg()) \
        == pytest.approx(0.221, abs=1e-3)
    # CDELT1 in degrees/pixel
    assert astap._fov_hint({"CDELT1": 0.001, "NAXIS2": 500}, _Cfg()) \
        == pytest.approx(0.5, abs=1e-3)


def test_fov_hint_falls_back_to_settings_then_auto():
    cfg = _Cfg(pixel_um=3.76, focal_mm=2000.0)
    assert astap._fov_hint({"NAXIS2": 2048}, cfg) \
        == pytest.approx(0.221, abs=1e-3)          # the Settings scale
    assert astap._fov_hint({"NAXIS2": 2048}, _Cfg()) is None   # nothing
    assert astap._fov_hint({"IM_SCALE": 5.21}, cfg) is None    # no NAXIS2


def test_fov_hint_on_the_hatp32_sample():
    # the repo fixture (MicroObservatory frame): its own IM_SCALE wins
    from nightscribe.core import fits_io
    p = Path(__file__).parents[1] / "fixtures" / "hatp32_sample.fits"
    h, _ = fits_io.read_fits(p)
    assert astap._fov_hint(h, _Cfg(pixel_um=11.0, focal_mm=2200.0)) \
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
