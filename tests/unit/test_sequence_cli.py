############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: sequence CLI command (ADR-042)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from pathlib import Path

import pytest

from nightscribe import __main__ as cli
from nightscribe.core import compstars

FIX = Path(__file__).resolve().parent.parent / "fixtures"
CENTER = (291.366, 42.784)


class _Args:
    objeto = "V0001 Cyg"
    ra = CENTER[0]
    dec = CENTER[1]
    catalog = "gaia"
    fov = 18.0
    comps = 4
    mag = 13.5
    fits = None
    sin_imagen = True     # no background fetch in unit tests
    salida = None


def _fake_field(*_args, **_kwargs):
    from nightscribe.core.sources import vizier
    text = (FIX / "vizier_gaia.tsv").read_bytes().decode("utf-8")
    spec = vizier.CATALOGS["gaia"]
    rows = vizier.parse_tsv(text, spec["required"], spec["ra"],
                            spec["dec"])[1]
    stars = compstars.build_stars(rows, CENTER, 18.0 / 60.0, "gaia")
    return {"stars": stars, "variables": [], "catalog": "gaia",
            "catalog_name": "Gaia EDR3", "band": "G", "center": CENTER,
            "fov_arcmin": 18.0, "vsx_warning": False}


def test_cmd_sequence_writes_csv_and_png(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(compstars, "load_field", _fake_field)
    args = _Args()
    args.salida = str(tmp_path)
    rc = cli.cmd_sequence(args)
    assert rc is None
    csvs = list(tmp_path.glob("*_secuencia.csv"))
    pngs = list(tmp_path.glob("*_carta.png"))
    assert len(csvs) == 1 and len(pngs) == 1
    text = csvs[0].read_text(encoding="utf-8")
    assert "# target: V0001 Cyg" in text
    assert "Comp1" in text and "Check" in text
    out = capsys.readouterr().out
    assert "V0001 Cyg" in out and "CSV ->" in out


def test_cmd_sequence_unknown_target_is_honest(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_resolve_target", lambda name: None)
    args = _Args()
    args.ra = None
    args.dec = None
    rc = cli.cmd_sequence(args)
    assert rc == 1
    assert "could not resolve" in capsys.readouterr().out


def test_cmd_sequence_missing_target_is_honest(capsys):
    args = _Args()
    args.objeto = None
    args.ra = None
    args.dec = None
    assert cli.cmd_sequence(args) == 1
    assert "missing target" in capsys.readouterr().out


def test_cmd_sequence_vizier_down_is_honest(monkeypatch, capsys):
    monkeypatch.setattr(compstars, "load_field",
                        lambda *a, **k: None)
    args = _Args()
    args.salida = None
    rc = cli.cmd_sequence(args)
    assert rc == 1
    assert "VizieR" in capsys.readouterr().out
