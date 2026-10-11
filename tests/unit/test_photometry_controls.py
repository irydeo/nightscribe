############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: photometry follow-up (comps, re-measure)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The photometry follow-up: the reasons a comparison star was dropped ride
the run's summary, and the brightness can be re-measured on the SAVED stacks
with the recipe the Photometry tab holds now, without re-stacking."""

import numpy as np

from nightscribe.gui import workers


def test_stack_remeasure_worker_summarises(monkeypatch):
    # The worker reads the saved object + star stacks, runs the plate recipe
    # and reports the magnitude, how many COMPS held the zero point (the
    # check star is not a comp) and why the others were dropped.
    from nightscribe.core import fits_io, photometry, wcs as wcs_mod

    monkeypatch.setattr(
        fits_io, "read_fits",
        lambda p: ({"NAXIS1": 8, "NAXIS2": 8},
                   np.zeros((8, 8), dtype="float32")))
    monkeypatch.setattr(wcs_mod.Wcs, "from_header",
                        classmethod(lambda cls, h: None))

    class _Res:
        ok = True
        mag = 19.10
        err_total = 0.12
        band = "G"
        used = [({"kind": "comp", "star": {}}, {"ok": True}),
                ({"kind": "check", "star": {}}, {"ok": True})]
        skipped = {"sat": 2}
        check = {"ok": True}
        matched_used = True

    monkeypatch.setattr(photometry, "measure_plate", lambda img, cfg: _Res())

    seen = {}
    worker = workers.StackRemeasureWorker(
        [{"index": 0, "stack": "/tmp/o.fits", "star": "/tmp/s.fits",
          "target_xy": (4.0, 4.0), "fwhm": 3.0}],
        [{"kind": "comp", "star": {"ra": 1.0, "dec": 2.0}}], "G",
        recipe={"rap": 3.0, "rin": 6.0, "rout": 10.0}, cfg={})
    worker.finished.connect(lambda payload: seen.update(payload))
    worker.run()
    res = seen["results"][0]
    assert res["mag"] == 19.10
    assert res["err"] == 0.12
    assert res["n_comps"] == 1          # the check star is not a comp
    assert res["comps_skipped"] == {"sat": 2}
    assert res["check_ok"] is True
    assert res["matched_used"] is True


def test_stack_remeasure_worker_reports_a_failure(monkeypatch):
    # A plate that cannot be calibrated says so instead of crashing: the run
    # keeps its own numbers and the observer reads why.
    from nightscribe.core import fits_io, photometry, wcs as wcs_mod

    monkeypatch.setattr(
        fits_io, "read_fits",
        lambda p: ({"NAXIS1": 8, "NAXIS2": 8},
                   np.zeros((8, 8), dtype="float32")))
    monkeypatch.setattr(wcs_mod.Wcs, "from_header",
                        classmethod(lambda cls, h: None))

    class _Res:
        ok = False
        mag = None
        reason = "no comps"

    monkeypatch.setattr(photometry, "measure_plate", lambda img, cfg: _Res())

    seen = {}
    worker = workers.StackRemeasureWorker(
        [{"index": 0, "stack": "/tmp/o.fits", "star": None,
          "target_xy": (4.0, 4.0), "fwhm": None}], [], "G", cfg={})
    worker.finished.connect(lambda payload: seen.update(payload))
    worker.run()
    assert "error" in seen["results"][0]


def test_stack_remeasure_worker_does_the_whole_series(monkeypatch):
    # The recipe is the same for every observation, so the worker re-measures
    # the WHOLE series of a run, not only the one on stage.
    from nightscribe.core import fits_io, photometry, wcs as wcs_mod

    monkeypatch.setattr(
        fits_io, "read_fits",
        lambda p: ({"NAXIS1": 8, "NAXIS2": 8},
                   np.zeros((8, 8), dtype="float32")))
    monkeypatch.setattr(wcs_mod.Wcs, "from_header",
                        classmethod(lambda cls, h: None))

    class _Res:
        ok = True
        mag = 18.5
        err_total = 0.05
        band = "G"
        used = [({"kind": "comp", "star": {}}, {"ok": True})]
        skipped = {}
        check = None
        matched_used = False

    monkeypatch.setattr(photometry, "measure_plate", lambda img, cfg: _Res())

    seen = {}
    worker = workers.StackRemeasureWorker(
        [{"index": 0, "stack": "/tmp/a.fits", "star": "/tmp/a_star.fits",
          "target_xy": (1.0, 1.0), "fwhm": 3.0},
         {"index": 1, "stack": "/tmp/b.fits", "star": "/tmp/b_star.fits",
          "target_xy": (2.0, 2.0), "fwhm": 3.0}],
        [{"kind": "comp", "star": {"ra": 1.0, "dec": 2.0}}], "G", cfg={})
    worker.finished.connect(lambda payload: seen.update(payload))
    worker.run()
    assert [r["index"] for r in seen["results"]] == [0, 1]
    assert all(r["mag"] == 18.5 for r in seen["results"])


def test_motion_from_trail_offers_both_signs():
    # The object's trail on a stack is the RESIDUAL between the real motion
    # and the one the stack was tracked with. motion_from_trail adds it back
    # (both signs, because a trail is a line) and returns two candidates.
    from nightscribe.core import track_stack

    class _Wcs:
        # a trivial pixel<->sky: 1 px = 1 arcsec, origin at 0
        def pixel_to_sky(self, x, y):
            return x / 3600.0, y / 3600.0

    # a 5 px trail along +x (image PA 0) over 10 min, tracked at 1"/min
    # towards north (PA 0): the residual is 0.5"/min along east, PERPENDICULAR
    # to the motion, so both signs give the same speed (added in quadrature)
    # and two different headings.
    import math
    cands = track_stack.motion_from_trail(
        _Wcs(), (0.0, 0.0), 5.0, 0.0, 10.0, 1.0, 0.0)
    assert len(cands) == 2
    assert all(abs(c[0] - math.hypot(1.0, 0.5)) < 1e-6 for c in cands)
    pas = sorted(c[1] for c in cands)
    assert abs(pas[0] - 26.565051177078) < 1e-3
    assert abs(pas[1] - 333.434948822922) < 1e-3


def test_motion_from_trail_needs_a_span_and_a_wcs():
    from nightscribe.core import track_stack
    assert track_stack.motion_from_trail(None, (0, 0), 5, 0, 10, 1, 0) == []
    assert track_stack.motion_from_trail(object(), (0, 0), 5, 0, 0, 1, 0) == []
