############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: solve.solve accepts a plain cancel callable
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""solve.solve must accept the plain callable the GUI workers hand it.

The track & stack passes `cancel=lambda: self._cancel`, but the auto path's
fallback check called `cancel.is_set()` unconditionally and raised
AttributeError on a function, aborting the astrometry run right after the
velocity sweep, on every machine without a local ASTAP. The helper
is_cancelled() is the one place that knows both shapes (a SolveCancel with
is_set() and a plain callable); this pins solve.solve to it.
"""


def test_solve_accepts_a_plain_callable_cancel(monkeypatch):
    from nightscribe.core import solve as solve_mod
    from nightscribe.core.sources import astap, astrometry

    # No local solve, so the auto path reaches the fallback check.
    monkeypatch.setattr(astap, "solve", lambda *a, **k: None)
    sentinel = {"CRVAL1": 1.0}
    monkeypatch.setattr(astrometry, "solve", lambda *a, **k: sentinel)

    # Not cancelled: the nova fallback runs and returns its cards. Before the
    # fix this raised AttributeError instead of returning anything.
    assert solve_mod.solve("frame.fits", solver="auto",
                           astap_path="/nonexistent",
                           cancel=lambda: False) == sentinel

    # Cancelled: no fallback, and still no AttributeError.
    assert solve_mod.solve("frame.fits", solver="auto",
                           astap_path="/nonexistent",
                           cancel=lambda: True) is None


def test_is_cancelled_understands_both_shapes():
    from nightscribe.core import solve as solve_mod
    assert solve_mod.is_cancelled(None) is False
    assert solve_mod.is_cancelled(lambda: False) is False
    assert solve_mod.is_cancelled(lambda: True) is True

    class _Cancel:
        def __init__(self, flag):
            self._flag = flag

        def is_set(self):
            return self._flag

    assert solve_mod.is_cancelled(_Cancel(True)) is True
    assert solve_mod.is_cancelled(_Cancel(False)) is False
