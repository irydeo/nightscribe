############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Dependency policy guard tests (ADR-060)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# ADR-060 reopened ADR-004: astropy, scipy and photutils are allowed for the
# astrometry/calibration modules, but the rest of the app must keep working
# without them (the astrometry plan is opt-in). So these tests SKIP when the
# libraries are absent instead of failing, and only assert the exact pieces the
# plan relies on, so a broken install is caught here and not in the middle of a
# night's reduction.

import pytest


def test_astropy_pieces():
    # astropy is used for FITS with extensions, WCS with SIP, units and time.
    # @return: None
    astropy = pytest.importorskip("astropy")
    from astropy.io import fits          # noqa: F401
    from astropy.wcs import WCS          # noqa: F401
    from astropy import units as u       # noqa: F401
    from astropy.time import Time        # noqa: F401
    assert astropy.__version__


def test_scipy_pieces():
    # scipy is used for subpixel resampling (ndimage), fitting (optimize) and
    # robust statistics (stats).
    # @return: None
    scipy = pytest.importorskip("scipy")
    from scipy import ndimage, optimize, stats   # noqa: F401
    assert scipy.__version__


def test_photutils_pieces():
    # photutils is used for the subpixel centroids shared by the stack and the
    # per-frame measurement (D7).
    # @return: None
    photutils = pytest.importorskip("photutils")
    from photutils.centroids import centroid_2dg, centroid_com   # noqa: F401
    assert photutils.__version__


def test_wcs_reads_sip_without_crashing():
    # The plan reads SIP with astropy.wcs when the solver provides it; the own
    # TAN WCS (ADR-051) ignores it. This only checks the API is present.
    # @return: None
    pytest.importorskip("astropy")
    from astropy.wcs import WCS
    assert hasattr(WCS, "all_pix2world")
