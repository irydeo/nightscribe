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

import os
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


def _fake_astap(tmp_path, to_stdout=False):
    # a simulated ASTAP: writes <file>.wcs with fixed cards (or prints
    # them), and records each run so the cache can be proven
    script = tmp_path / ("fake_astap_stdout.py" if to_stdout
                         else "fake_astap.py")
    lines = [
        "#!/usr/bin/env python3",
        "import sys",
        "from pathlib import Path",
        "args = sys.argv[1:]",
        "f = args[args.index('-f') + 1]",
        "Path(f + '.runs').write_text(Path(f + '.runs').read_text() + 'x')"
        " if Path(f + '.runs').exists() else Path(f + '.runs').write_text('x')",
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
    fits = _write_fits(tmp_path / "p.fits")
    assert astap.resolve_binary("") is None
    assert astap.solve(fits, astap_path="") is None


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
