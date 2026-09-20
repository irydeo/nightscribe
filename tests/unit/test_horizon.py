############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: local horizon (ADR-020)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime

from nightscribe.core import horizon


# --- TheSkyX .hrz parser ---

def _thesky_file(tmp_path, header="0.00|  0.00", cardinality=360,
                 n_lines=360, alt=20.0):
    # Build a synthetic .hrz file and return its path.
    lines = [header, str(cardinality)]
    lines += [" %.2f" % alt for _ in range(n_lines)]
    p = tmp_path / "sample.hrz"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def test_parse_thesky_hrz(tmp_path):
    # A 12-point file: alts 0,10,...,110 deg → clamped to 90 after parsing.
    h = horizon.load(_thesky_file(
        tmp_path, cardinality=12, n_lines=12, alt=45.0))
    assert h is not None
    assert len(h.points) == 12
    assert h.alt_at(0.0) == 45.0


def test_parse_thesky_rejects_short_body():
    # cardinality says 10 but only 3 lines present → the thesky parser
    # must reject the structure (the pairs fallback is not what we test here)
    lines = ["0.00|  0.00", "10", " 10.0", " 20.0", " 30.0"]
    assert horizon._parse_thesky(lines) is None


def test_parse_thesky_rejects_multi_number_lines():
    # a body line with two numbers is not a valid altitude entry
    lines = ["0.00|  0.00", "4", " 10.0  20.0", " 20.0", " 30.0", " 40.0"]
    assert horizon._parse_thesky(lines) is None


def test_parse_thesky_rejects_bad_cardinality():
    lines = ["0.00|  0.00", "999", " 10.0"]
    assert horizon._parse_thesky(lines) is None


def test_parse_thesky_real_sample():
    # The canonical docs/limits-sample.hrz should parse to 360 points.
    h = horizon.load("docs/limits-sample.hrz")
    assert h is not None
    assert len(h.points) == 360
    s = h.stats()
    assert s["min_alt"] >= 0.0 and s["max_alt"] <= 90.0


# --- safe_spans / best_span ---

def _samples(start, n, step_s=300):
    # n samples at 5-min intervals from a UTC datetime
    t0 = datetime.datetime(2026, 8, 21, 20, 0, tzinfo=datetime.timezone.utc)
    return [(start + datetime.timedelta(seconds=i * step_s), 40.0, 90.0)
            for i in range(n)]


def test_safe_spans_single_run():
    f = horizon.FlatHorizon(30.0)
    s = _samples(datetime.datetime(2026, 8, 21, 20, 0,
                                   tzinfo=datetime.timezone.utc), 20)
    spans = f.safe_spans(s)
    assert len(spans) == 1
    assert spans[0][0] == s[0][0] and spans[0][1] == s[-1][0]


def test_safe_spans_breaks_on_gap():
    # Two groups of consecutive samples (10-min step, below the 20-min
    # span gap) separated by a 10-hour gap → two distinct spans
    f = horizon.FlatHorizon(30.0)
    t0 = datetime.datetime(2026, 8, 21, 20, 0, tzinfo=datetime.timezone.utc)
    dt = datetime.timedelta(minutes=10)
    group1 = [(t0 + i * dt, 40.0, 90.0) for i in range(3)]
    group2 = [(t0 + datetime.timedelta(hours=10) + i * dt, 40.0, 90.0)
              for i in range(3)]
    spans = f.safe_spans(group1 + group2)
    assert len(spans) == 2
    # each span covers 2 × 10 min
    assert (spans[0][1] - spans[0][0]).total_seconds() == 1200


def test_safe_spans_duration_filter():
    # 10-min spread; 2h duration filter → nothing survives
    f = horizon.FlatHorizon(30.0)
    t0 = datetime.datetime(2026, 8, 21, 20, 0, tzinfo=datetime.timezone.utc)
    s = [(t0, 40.0, 90.0), (t0 + datetime.timedelta(minutes=10), 40.0, 90.0)]
    spans = f.safe_spans(s, duration_s=7200)
    assert spans == []


def test_best_span_single():
    f = horizon.FlatHorizon(30.0)
    t0 = datetime.datetime(2026, 8, 21, 20, 0, tzinfo=datetime.timezone.utc)
    s = [(t0, 40.0, 90.0), (t0 + datetime.timedelta(minutes=30), 40.0, 90.0),
         (t0 + datetime.timedelta(minutes=60), 40.0, 90.0)]
    best = f.best_span(s)
    assert best[0] == t0
    assert best[2] == t0  # no duration → rec = span start


def test_best_span_with_duration():
    # 7 samples at 10-min steps → one contiguous 60-min span that holds a
    # 1-hour session; the recommended start is end − duration
    f = horizon.FlatHorizon(30.0)
    t0 = datetime.datetime(2026, 8, 21, 20, 0, tzinfo=datetime.timezone.utc)
    dt = datetime.timedelta(minutes=10)
    s = [(t0 + i * dt, 40.0, 90.0) for i in range(7)]
    best = f.best_span(s, duration_s=3600)
    start, end, rec = best
    assert start == t0 and end == t0 + 6 * dt
    assert rec == end - datetime.timedelta(seconds=3600)


def test_best_span_none_when_too_short():
    f = horizon.FlatHorizon(30.0)
    t0 = datetime.datetime(2026, 8, 21, 20, 0, tzinfo=datetime.timezone.utc)
    s = [(t0, 40.0, 90.0)]
    assert f.best_span(s, duration_s=7200) is None


def test_stats_and_peak():
    f = horizon.FlatHorizon(30.0)
    assert f.stats()["min_alt"] == 30.0
    assert f.stats()["max_alt"] == 30.0
    assert f.peak()[1] == 30.0


# --- open_reference ---

def test_open_reference_file_wins(fake_cfg, tmp_path):
    p = _thesky_file(tmp_path)
    fake_cfg._v["horizon_file"] = p
    h, notes = horizon.open_reference(fake_cfg)
    assert isinstance(h, horizon.Horizon)
    assert len(h.points) == 360
    assert notes == []


def test_open_reference_fallback_notes(fake_cfg, tmp_path):
    fake_cfg._v["horizon_file"] = str(tmp_path / "no_such_file.txt")
    h, notes = horizon.open_reference(fake_cfg)
    assert h.is_flat
    assert any(n[0] == "warn" for n in notes)


def test_open_reference_none_cfg():
    h, notes = horizon.open_reference(None)
    assert h.is_flat
    assert notes == []


def test_parse_sample_fixture(fixture_path):
    h = horizon.load(fixture_path / "horizon_sample.txt")
    assert h is not None
    pts = h.points
    assert len(pts) == 36
    # sorted by azimuth
    assert pts[0][0] == 0.0 and pts[-1][0] == 350.0


def test_wall_and_gap_interpolation(fixture_path):
    h = horizon.load(fixture_path / "horizon_sample.txt")
    # NE wall: az 60 -> 60 deg
    assert abs(h.alt_at(60.0) - 60.0) < 1e-6
    # uniform floor: az 120 -> 30 deg
    assert abs(h.alt_at(120.0) - 30.0) < 1e-6
    # southern gap: az 180 -> 20 deg
    assert abs(h.alt_at(180.0) - 20.0) < 1e-6
    # interpolation between 30 (az 30) and 60 (az 40): az 35 -> 45 deg
    assert abs(h.alt_at(35.0) - 45.0) < 1e-6


def test_wrap_across_seam(fixture_path):
    h = horizon.load(fixture_path / "horizon_sample.txt")
    # across the 0/360 seam: between az 350 (30) and az 0 (30) -> 30
    assert abs(h.alt_at(355.0) - 30.0) < 1e-6
    assert abs(h.alt_at(5.0) - 30.0) < 1e-6
    # az slightly negative wraps to ~360
    assert abs(h.alt_at(-5.0) - 30.0) < 1e-6


def test_flat_horizon_constant():
    f = horizon.FlatHorizon(30.0)
    assert f.is_flat
    assert f.alt_at(0.0) == 30.0
    assert f.alt_at(123.4) == 30.0


def test_from_config_falls_back_to_flat(fake_cfg):
    # fake_cfg has no horizon_file -> flat min_alt (30)
    h = horizon.from_config(fake_cfg)
    assert h.is_flat
    assert h.alt_at(0.0) == 30.0


def test_from_config_uses_file(fake_cfg, fixture_path):
    fake_cfg._v["horizon_file"] = str(fixture_path / "horizon_sample.txt")
    h = horizon.from_config(fake_cfg)
    assert not h.is_flat
    assert abs(h.alt_at(60.0) - 60.0) < 1e-6


def test_from_config_missing_file_falls_back(fake_cfg, tmp_path):
    fake_cfg._v["horizon_file"] = str(tmp_path / "does_not_exist.txt")
    h = horizon.from_config(fake_cfg)
    assert h.is_flat
    assert h.alt_at(0.0) == 30.0


def test_load_rejects_garbage(tmp_path):
    p = tmp_path / "bad.txt"
    p.write_text("# only comments\n\n", encoding="utf-8")
    assert horizon.load(p) is None
