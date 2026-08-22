############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Minimal FITS reader module (ADR-018)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging

import numpy as np

logger = logging.getLogger(__name__)

# Just enough FITS for the blink feature: header cards + the first image HDU,
# BSCALE/BZERO applied, RGB/cubes collapsed to luminance. No astropy (ADR-004).

_CARD = 80
_BLOCK = 2880

# BITPIX -> big-endian numpy dtype (FITS is always big-endian)
_DTYPES = {8: ">u1", 16: ">i2", 32: ">i4", 64: ">i8", -32: ">f4", -64: ">f8"}


class FitsError(Exception):
    # Unreadable or unsupported FITS file. Message in English; callers
    # (GUI/CLI) translate or wrap it for the user.
    pass


def _parse_card_value(card):
    # Parses the value of a "KEY     = value / comment" card.
    # @args: card - 80-char string with "= " at columns 9-10
    # @return: str | int | float | bool
    body = card[10:]
    stripped = body.lstrip()
    if stripped.startswith("'"):
        # string: ends at the next unpaired quote ('' inside means a quote)
        out = []
        i = body.index("'") + 1
        while i < len(body):
            ch = body[i]
            if ch == "'":
                if i + 1 < len(body) and body[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                break
            out.append(ch)
            i += 1
        return "".join(out).rstrip()
    token = body.split("/", 1)[0].strip()
    if token in ("T", "F"):
        return token == "T"
    try:
        return int(token)
    except ValueError:
        pass
    try:
        # FITS may write exponents with a Fortran D
        return float(token.replace("D", "E").replace("d", "e"))
    except ValueError:
        return token


def _read_header(fh):
    # Reads one FITS header (2880-byte blocks of 80-char cards).
    # @args: fh - binary file object positioned at a header start
    # @return: dict of keyword -> value, or None at clean EOF
    header = {}
    seen_any = False
    while True:
        block = fh.read(_BLOCK)
        if not block and not seen_any:
            return None
        if len(block) < _BLOCK:
            raise FitsError("Truncated FITS header block")
        seen_any = True
        text = block.decode("ascii", "replace")
        for i in range(0, _BLOCK, _CARD):
            card = text[i:i + _CARD]
            key = card[:8].strip()
            if key == "END":
                return header
            if card[8:10] == "= ":
                header[key] = _parse_card_value(card)


def _data_size(header):
    # Size in bytes of the data block described by a header (unpadded).
    # @args: header - header dict
    # @return: int
    bitpix = int(header.get("BITPIX", 8))
    naxis = int(header.get("NAXIS", 0))
    if naxis == 0:
        return 0  # no data array at all (e.g. grouping primary HDU)
    npix = 1
    for i in range(1, naxis + 1):
        npix *= int(header.get(f"NAXIS{i}", 0))
    gcount = int(header.get("GCOUNT", 1))
    pcount = int(header.get("PCOUNT", 0))
    return abs(bitpix) // 8 * (gcount * npix + pcount)


def _skip_data(fh, header):
    # Jumps over the data block (padded to a 2880-byte boundary).
    size = _data_size(header)
    fh.seek((size + _BLOCK - 1) // _BLOCK * _BLOCK, 1)


def _read_data(fh, header):
    # Reads the data block of an image HDU into a numpy array.
    # @args: fh - positioned right after the header, header - header dict
    # @return: numpy array with FITS axis order (NAXIS1 fastest -> last index)
    bitpix = int(header.get("BITPIX", 8))
    if bitpix not in _DTYPES:
        raise FitsError(f"Unsupported BITPIX {bitpix}")
    naxis = int(header.get("NAXIS", 0))
    shape = [int(header.get(f"NAXIS{i}", 0)) for i in range(1, naxis + 1)]
    raw = fh.read(_data_size(header))
    if len(raw) < _data_size(header):
        raise FitsError("Truncated FITS data block")
    data = np.frombuffer(raw, dtype=np.dtype(_DTYPES[bitpix]))
    data = data.reshape(tuple(reversed(shape))) if shape else data
    # BLANK marks invalid pixels in integer arrays (floats use NaN already)
    if bitpix > 0 and "BLANK" in header:
        data = np.where(data == int(header["BLANK"]), np.nan, data)
    # Physical values: BZERO + BSCALE * raw (uint16 cameras use BZERO=32768)
    bscale = float(header.get("BSCALE", 1.0))
    bzero = float(header.get("BZERO", 0.0))
    return np.ascontiguousarray(data * bscale + bzero, dtype=np.float32)


def to_luminance(data):
    # Collapses RGB frames and data cubes to a single 2D plane.
    # @args: data - numpy array (2D, 3D or more)
    # @return: 2D numpy array
    while data.ndim > 3:
        data = data[0]
    if data.ndim == 3:
        # axis 0 is NAXIS3: 2-4 planes mean colour, more mean a data cube
        if data.shape[0] in (2, 3, 4):
            return np.nanmean(data, axis=0).astype(np.float32)
        return data[0]
    return data


def read_fits(path):
    # Reads the first image HDU of a FITS file.
    # @args: path - FITS file path
    # @return: (header dict, 2D float32 numpy array)
    try:
        with open(path, "rb") as fh:
            while True:
                header = _read_header(fh)
                if header is None:
                    raise FitsError("No image HDU found in the file")
                if int(header.get("NAXIS", 0)) >= 2 and \
                        int(header.get("NAXIS1", 0)) > 0 and \
                        int(header.get("NAXIS2", 0)) > 0:
                    return header, to_luminance(_read_data(fh, header))
                _skip_data(fh, header)
    except OSError as err:
        raise FitsError(f"Cannot read FITS file: {err}") from err


def read_header(source):
    # Reads only the first header (e.g. an astrometry.net wcs.fits, which
    # carries the solution as cards with no image data).
    # @args: source - FITS file path or binary file object
    # @return: header dict
    try:
        if hasattr(source, "read"):
            header = _read_header(source)
        else:
            with open(source, "rb") as fh:
                header = _read_header(fh)
    except OSError as err:
        raise FitsError(f"Cannot read FITS header: {err}") from err
    if header is None:
        raise FitsError("Empty FITS file")
    return header
