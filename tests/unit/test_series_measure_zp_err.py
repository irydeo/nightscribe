############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: series zero-point error honesty
# (series-photometry review, P1 #9)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The ensemble zero-point error must never beat the data it hangs
from: with a known comp scatter the error is ~ scatter/sqrt(N) (the
classical standard error of the mean), and catalogue errors set a
floor. Anchors are statistical (known injected sigma), never the
implementation's own formula.
"""

import math

import numpy as np
import pytest

from nightscribe.core import series_measure


def test_zp_err_tracks_the_known_comp_scatter():
    # 8 comps whose residuals carry an injected Gaussian sigma of
    # 0.05 mag; the standard error of their mean is sigma/sqrt(8)
    # ~ 0.0177 mag. Formal errors are tiny on purpose: a bare 1/sqrt(N)
    # of them would claim ~0.0004 mag (the x100 underestimate of the
    # review).
    rng = np.random.default_rng(42)
    residuals = list(rng.normal(0.0, 0.05, 8))
    errors = [0.001] * 8
    zp, zp_err, n_used, _rej = series_measure._ensemble_zp(residuals,
                                                           errors)
    assert n_used == 8
    want = 0.05 / math.sqrt(8)
    assert zp_err == pytest.approx(want, rel=0.5)
    assert zp_err > 0.01  # never the x100 underestimate


def test_zp_err_never_beats_the_catalogue_errors():
    # 6 comps with zero scatter but a catalogue error of 0.02 mag each:
    # the ZP cannot be known better than 0.02/sqrt(6) ~ 0.0082 mag.
    residuals = [0.0] * 6
    errors = [0.02] * 6
    zp, zp_err, n_used, _rej = series_measure._ensemble_zp(residuals,
                                                           errors)
    assert n_used == 6
    assert zp_err >= 0.02 / math.sqrt(6) * 0.99
