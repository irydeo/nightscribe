############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the minimal FITS reader (ADR-018)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The app's own reader (numpy, no astropy) and the SAMPLED read the frame
previews of a visit live on.

read_fits reads a whole HDU; read_sample reads one row out of every `step`
and keeps one column out of every `step` of it, which is what makes a
thumbnail of a 2048² frame cost ~1 MB instead of the 16 MB the frame takes.
Both apply BSCALE/BZERO/BLANK, so the numbers a preview shows are the
frame's own.
"""

import numpy as np
import pytest

from nightscribe.core import fits_io


def _write(path, data, **cards):
    # @args: path - where to write, data - the 2D array, cards - extra header
    # @return: the path as a string (FITS axis order: NAXIS1 is the width)
    from astropy.io import fits
    hdu = fits.PrimaryHDU(np.asarray(data))
    for key, value in cards.items():
        hdu.header[key.replace("__", "-")] = value
    hdu.writeto(str(path), overwrite=True)
    return str(path)


def test_read_sample_is_the_frame_small_and_cheap(tmp_path):
    # The thumbnail path cannot read a whole visit: 200 frames of 2048²
    # float32 are 3.2 GB. read_sample walks the file and reads one row out
    # of every `step` (measured on a real 2048² frame: ~1 MB instead of
    # 16 MB), with the same BSCALE/BZERO/BLANK handling as read_fits.
    data = np.arange(400, dtype=np.float32).reshape(20, 20)
    path = _write(tmp_path / "frame.fits", data)
    header, sample = fits_io.read_sample(path, max_px=10)
    assert header["NAXIS1"] == 20
    assert sample.shape == (10, 10)          # 20 px sampled every 2
    assert sample[0, 0] == data[0, 0]
    assert sample[1, 1] == data[2, 2]
    # the sample IS the frame: same values, and the scaling is applied
    scaled = _write(tmp_path / "scaled.fits",
                    np.full((20, 20), 100, dtype=np.int16),
                    BZERO=32768.0, BSCALE=1.0)
    _h, s2 = fits_io.read_sample(scaled, max_px=5)
    assert float(np.median(s2)) == 32868.0
    # a small frame is not padded up to max_px: it comes back whole
    _h, whole = fits_io.read_sample(path, max_px=64)
    assert whole.shape == (20, 20)
    # and a frame that cannot be read says so (the caller marks it broken)
    empty = tmp_path / "empty.fits"
    empty.write_bytes(b"")
    with pytest.raises(fits_io.FitsError):
        fits_io.read_sample(str(empty))
