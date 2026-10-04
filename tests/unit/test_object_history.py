############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: object history and centred sequence
# (ADR-062, 5.4 and 5.5)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The card's observation history (how many observatories, when it was last
seen) and the centred sequence of the observations. Offline."""

import numpy as np

from nightscribe.core import orbits
from nightscribe.core.sources import sbdb
from nightscribe.core.viz import sequence_view


def _row(rows, param_es):
    for row in rows:
        if row["param"]["es"] == param_es:
            return row
    return None


def test_explain_elements_shows_the_history():
    rows = orbits.explain_elements({"a": 2.2, "e": 0.6}, n_resids=108,
                                   arc_days=3.0, n_stations=42,
                                   last_obs="2025-10-18")
    row = _row(rows, "Observatorios y última vez")
    assert row is not None
    assert "42" in row["value"] and "2025-10-18" in row["value"]
    assert row["level"] == "basic"
    assert "perderse" in row["es"] and "lost" in row["en"]


def test_explain_elements_without_history_has_no_row():
    rows = orbits.explain_elements({"a": 2.2, "e": 0.6})
    assert _row(rows, "Observatorios y última vez") is None


def test_parse_sbdb_carries_the_history():
    reply = {
        "object": {"fullname": "2025 UR", "des": "2025 UR", "kind": "an",
                   "neo": True, "orbit_class": {"name": "Apollo", "code": "APO"}},
        "orbit": {"elements": [{"name": "a", "value": "2.24"},
                               {"name": "e", "value": "0.6"}],
                  "n_obs_used": 108, "last_obs": "2025-10-18",
                  "data_arc": 3.0, "first_obs": "2025-10-15"},
    }
    out = sbdb.parse_sbdb(reply)
    assert out["n_obs_used"] == 108
    assert out["last_obs"] == "2025-10-18"
    assert out["data_arc"] == 3.0


# ------------------------------------------------------- centred sequence

def _field(size=80, x=40.0, y=40.0, seed=0):
    rng = np.random.default_rng(seed)
    img = rng.normal(1000.0, 5.0, (size, size)).astype(np.float32)
    yy, xx = np.mgrid[0:size, 0:size]
    img += 3000.0 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.5 ** 2))
    return img


def test_centred_sequence_writes_a_gif(tmp_path):
    images = [_field(x=40.0 + 2 * i) for i in range(4)]
    centers = [(40.0 + 2 * i, 40.0) for i in range(4)]
    out = sequence_view.centered_sequence(images, centers,
                                          tmp_path / "seq.gif",
                                          size=48, duration_ms=200)
    from pathlib import Path
    assert Path(out).exists() and Path(out).stat().st_size > 0
    assert out.endswith(".gif")


def test_centred_sequence_montage(tmp_path):
    images = [_field() for _ in range(3)]
    centers = [(40.0, 40.0)] * 3
    out = sequence_view.centered_sequence(images, centers,
                                          tmp_path / "montage.png",
                                          size=32, fmt="png")
    from PIL import Image
    assert Image.open(out).size == (3 * 32, 32)
