############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Annotated FITS export (Track B, B10)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Annotated FITS export for the SN follow-up.

The observer keeps "la imagen anotada, resuelta astrometricamente": AIJ
stores annotation data in the FITS header and renders it on load. An AIJ
annotation is a repeated ANNOTATE card whose value is "x,y,size,...,color"
and whose comment is the label, e.g.

    ANNOTATE= '876.74,868.43,30,1,0,1,1,orange' / NGC 7325

NightScribe produces a **copy** of the stacked FITS: it rewrites the first
header with an ANNOTATE card (position + SN name) and a short tail of
NS_* cards (RA/DEC, plate scale, north PA, night notes). Everything else
is copied verbatim, including every other header card (NAXIS, BSCALE/BZERO,
WCS, ...), the image data bytes, and any extension HDUs after it. The
observer's original file is never modified.

Writing is pure Python (ADR-004: no astropy). The whole header is rebuilt
block by block (headers span several 2880-byte blocks; a single-block edit
would shred the rest of it) with a latin-1 decode/encode round trip, so
accented comments the observer (or AIJ) wrote survive byte for byte.
Savings are idempotent: cards we own are stripped before the new ones go
in, so annotating twice leaves one clean set.
"""

import logging
from pathlib import Path

from . import fits_io

logger = logging.getLogger(__name__)

_CARD = 80      # FITS header card, chars
_BLOCK = 2880   # FITS header block, bytes

# Keys NightScribe owns in the header. On a re-save they are dropped
# (even if left by an earlier run) and re-emitted, so the file never
# accumulates stale annotations.
_OWNED = {"ANNOTATE", "NS_RA", "NS_DEC", "NS_SCALE", "NS_NORTH", "NS_NOTES"}

# AIJ annotation flags after the size: marker on, no background, label on,
# "highlight" flag, orange. NightScribe follows the same convention.
_AIJ_FLAGS = "30,1,0,1,1,orange"


def _num(value):
    # Compact number for a FITS card: a bare number (never a string), with
    # no trailing ".0" when it is whole.
    # @args: value - int or float
    # @return: int when whole, float otherwise
    f = float(value)
    if f == int(f) and abs(f) < 1e15:
        return int(f)
    return float(f"{f:.6g}")


def _format_card(key, value, comment=""):
    # One 80-column card the way AIJ writes one: "KEY     = value / comment".
    # Strings are quoted; the value (then the comment) is trimmed to fit.
    # @args: key - FITS keyword (<= 8 chars), value - str or number,
    #        comment - trailing comment after " / "
    # @return: the card, exactly 80 chars
    key = (key or "KEYWORD").upper()[:8]
    val = str(value).strip()
    comment = (comment or "").strip()
    is_str = isinstance(value, str)
    overhead = 10                               # "KEY     = " ("=" in col. 9)
    if is_str:
        overhead += 2                           # the quotes
    if comment:
        overhead += 3 + len(comment)            # " / comment"
    max_val = max(_CARD - overhead, 1)
    if len(val) > max_val:
        val = val[:max_val]
    # The "=" always sits in column 9, even for 8-character keywords:
    # "ANNOTATE= '…'" the way AIJ writes it, "NS_RA    = 1" otherwise.
    card = f"{key.ljust(8)}= " + (f"'{val}'" if is_str else val)
    if comment:
        card += f" / {comment}"
    return card[:_CARD].ljust(_CARD)


def _split_header(raw):
    # Walks the first HDU header (consecutive 2880-byte blocks up to its END
    # card) and returns it as a list of 80-char card strings, decoded
    # latin-1 so accented comments survive a byte-exact round trip.
    # @args: raw - the whole file as bytes
    # @return: (cards_before_end, data_offset) - byte offset of the data
    cards = []
    off = 0
    while True:
        block = raw[off:off + _BLOCK]
        if len(block) < _BLOCK:
            raise fits_io.FitsError("Truncated FITS header")
        off += _BLOCK
        text = block.decode("latin-1")
        for c in range(0, _BLOCK, _CARD):
            card = text[c:c + _CARD]
            if card[:8].strip() == "END":
                return cards, off
            cards.append(card)


def write_annotated_fits(input_path, output_path, sn_xy=None, scale=None,
                         north_pa=None, obj_name=None, ra_deg=None,
                         dec_deg=None, notes=""):
    # Writes an annotated **copy** of the FITS (module doc for the format).
    # With nothing to annotate it copies the bytes verbatim. The input
    # file is never modified.
    # @args: input_path - original stacked FITS, output_path - annotated copy,
    #        sn_xy - (x, y) 0-based pixel of the SN (drives the ANNOTATE
    #        card), scale - arcsec/pixel, north_pa - degrees east of north,
    #        obj_name - SN name (ANNOTATE label), ra_deg/dec_deg - J2000,
    #        notes - free-text night notes
    # @return: output Path
    input_path = Path(input_path)
    output_path = Path(output_path)
    raw = input_path.read_bytes()

    # Nothing to annotate: keep the existing contract, a verbatim copy.
    if (sn_xy is None and scale is None and north_pa is None
            and not str(obj_name or "").strip()
            and ra_deg is None and dec_deg is None
            and not str(notes or "").strip()):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(raw)
        return output_path

    cards, data_start = _split_header(raw)
    # Drop our own cards from a previous pass (or any the observer left)
    # so a re-save of the annotated copy stays clean; keep all the rest.
    kept = [c for c in cards if c[:8].strip() not in _OWNED]

    tail = []
    if sn_xy is not None:
        x, y = sn_xy
        tail.append(_format_card(
            "ANNOTATE", f"{float(x):.2f},{float(y):.2f},{_AIJ_FLAGS}",
            str(obj_name or "").strip()))
    if ra_deg is not None:
        tail.append(_format_card("NS_RA", _num(ra_deg)))
    if dec_deg is not None:
        tail.append(_format_card("NS_DEC", _num(dec_deg)))
    if scale is not None:
        tail.append(_format_card("NS_SCALE", _num(scale), "arcsec per pixel"))
    if north_pa is not None:
        tail.append(_format_card("NS_NORTH", _num(north_pa),
                                 "deg east of north"))
    notes_s = str(notes or "").strip()
    if notes_s:
        tail.append(_format_card("NS_NOTES", notes_s))

    # Rebuild: kept cards + new tail + END, padded to a whole number of
    # blocks; the data (and any extensions after it) are copied verbatim.
    header = "".join(kept + tail + ["END".ljust(_CARD)])
    try:
        header_bytes = header.encode("latin-1")
    except UnicodeEncodeError:
        header_bytes = header.encode("latin-1", "replace")
    header_bytes += b" " * ((_BLOCK - len(header_bytes) % _BLOCK) % _BLOCK)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(header_bytes + raw[data_start:])
    logger.info("annotated FITS written to %s", output_path)
    return output_path
