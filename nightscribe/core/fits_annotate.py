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

The observer keeps "la imagen anotada, resuelta astrométricamente": AIJ
stores annotation data in the FITS header and renders it on load. NightScribe
produces a **copy** of the stacked FITS with annotation keywords (crosshair
at the SN, scale bar, north arrow, labels) so the user's original is never
modified, and the annotated copy can be opened in AIJ (if our keywords match
AIJ's format — investigation flagged as a risk in the plan) or any FITS viewer.

Writing is pure Python (ADR-004: no astropy): we copy the input file
and inject annotation cards into the header by manipulating the raw 2880-byte
blocks. This is enough for simple TAN headers (the format the blink pipeline
already handles); no checksum is needed for image HDUs (FITS headers
carry no mandatory checksum in practice).
"""

import logging
from pathlib import Path

from . import fits_io

logger = logging.getLogger(__name__)

# Annotation keywords written into the header. AIJ-compatible where
# feasible (AIJ stores aperture/annotation info in custom keywords); otherwise
# NightScribe's own documented keywords.
_KEYWORDS = {
    "NS_SN_X": "pixel x of the SN on the reference frame",
    "NS_SN_Y": "pixel y of the SN on the reference frame",
    "NS_SCALE": "plate scale in arcsec/pixel",
    "NS_NORTH": "north arrow PA in degrees (East of North)",
    "NS_OBJ": "object name (SN designation)",
    "NS_RA": "SN right ascension (degrees, J2000)",
    "NS_DEC": "SN declination (degrees, J2000)",
    "NS_NOTES": "free-text night notes (seeing, clouds…)",
}


def _inject_cards(header_bytes, cards):
    # @args: header_bytes - raw 2880-byte header block (bytes),
    #        cards - list of (key, value) strings to inject before END
    # @return: new header bytes (2880, padded) with the cards inserted
    text = header_bytes.decode("ascii", "replace")
    # find the END card and build the new card section
    new_cards = []
    for key, value in cards:
        card = f"{key:<8}= "
        if isinstance(value, (int, float)):
            card += str(value)
        else:
            s = str(value)
            if len(s) > 68:
                s = s[:68]
            card += f"'{s}'"
        card = card.ljust(80)
        new_cards.append(card)
    # insert before END
    end_pos = text.find("END")
    if end_pos < 0:
        return header_bytes   # no END? leave as-is
    pre = text[:end_pos]
    post = text[end_pos:]
    new_text = pre + "".join(new_cards) + post
    # pad/truncate to 2880
    new_bytes = new_text.encode("ascii", "replace")
    if len(new_bytes) < 2880:
        new_bytes += b" " * (2880 - len(new_bytes))
    else:
        new_bytes = new_bytes[:2880]
    return new_bytes


def write_annotated_fits(input_path, output_path, sn_xy=None, scale=None,
                           north_pa=None, obj_name=None, ra_deg=None, dec_deg=None,
                           notes=""):
    # Copies the input FITS to output_path with annotation keywords injected
    # into the header. The input file is never modified.
    # @args: input_path - original stacked FITS, output_path - annotated copy,
    #        sn_xy - (x, y) pixel of the SN, scale - arcsec/pixel,
    #        north_pa - north arrow PA in degrees, obj_name - SN name,
    #        ra_deg/dec_deg - SN position, notes - free-text night notes
    # @return: output Path
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # read the raw bytes
    raw = input_path.read_bytes()
    # parse the first header to find END and the data offset
    with open(input_path, "rb") as fh:
        header = fits_io._read_header(fh)
    if header is None:
        raise fits_io.FitsError("Cannot read FITS header")
    # build the annotation cards
    cards = []
    if sn_xy is not None:
        cards.append(("NS_SN_X", sn_xy[0]))
        cards.append(("NS_SN_Y", sn_xy[1]))
    if scale is not None:
        cards.append(("NS_SCALE", scale))
    if north_pa is not None:
        cards.append(("NS_NORTH", north_pa))
    if obj_name:
        cards.append(("NS_OBJ", obj_name))
    if ra_deg is not None:
        cards.append(("NS_RA", ra_deg))
    if dec_deg is not None:
        cards.append(("NS_DEC", dec_deg))
    if notes:
        cards.append(("NS_NOTES", notes))
    if not cards:
        # nothing to annotate: just copy
        output_path.write_bytes(raw)
        return output_path
    # inject into the first 2880-byte block
    first_block = raw[:2880]
    new_block = _inject_cards(first_block, cards)
    output_path.write_bytes(new_block + raw[2880:])
    logger.info("annotated FITS written to %s", output_path)
    return output_path
