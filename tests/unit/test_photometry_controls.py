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
        "/tmp/o.fits", "/tmp/s.fits", (4.0, 4.0),
        [{"kind": "comp", "star": {"ra": 1.0, "dec": 2.0}}], "G",
        recipe={"rap": 3.0, "rin": 6.0, "rout": 10.0}, fwhm=3.0, cfg={})
    worker.finished.connect(lambda payload: seen.update(payload))
    worker.run()
    assert seen["mag"] == 19.10
    assert seen["err"] == 0.12
    assert seen["n_comps"] == 1          # the check star is not a comp
    assert seen["comps_skipped"] == {"sat": 2}
    assert seen["check_ok"] is True
    assert seen["matched_used"] is True


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
        "/tmp/o.fits", None, (4.0, 4.0), [], "G", cfg={})
    worker.finished.connect(lambda payload: seen.update(payload))
    worker.run()
    assert "error" in seen
