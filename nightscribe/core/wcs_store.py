############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Solved WCS store module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Persist a solved astrometry solution into the FITS header (ADR-051 rev.).

The editor used to keep the solution in memory only. That leaves the file
unsolved for every other program, so now a solve (manual or automatic) writes
the WCS cards into the plate. The write is atomic: the header is rebuilt from
the original cards (stale WCS dropped), the pixel data and any extensions are
copied verbatim, and the result replaces the file through a temporary sibling
and `os.replace`, so a crash mid-write never truncates the observer's image.
"""

import logging
import os
import tempfile
from pathlib import Path

from . import fits_annotate

logger = logging.getLogger(__name__)


def _atomic_replace(path, data):
    # Writes bytes to a temp file in the same folder and swaps it in.
    # @args: path - destination Path, data - full file bytes
    # @return: None; the original is only gone once the new bytes are down
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                               prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        # A temp file is created 0600; the observer's FITS should keep its own
        # mode (a solved frame that quietly becomes owner-only is a surprise,
        # and another account or tool may need to read it).
        try:
            os.chmod(tmp, os.stat(path).st_mode)
        except OSError:
            pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _rebuild(raw, cards):
    # Rebuilds the first HDU header with the solved WCS cards in place,
    # keeping the data (and extensions) verbatim.
    # @args: raw - the whole file bytes, cards - solved WCS card dict
    # @return: the new whole-file bytes
    from .blink import _STALE_WCS
    new_keys = {k.upper() for k in cards}
    old, data_start = fits_annotate._split_header(raw)

    def _drop(card):
        key = card[:8].strip().upper()
        return key in new_keys or any(key.startswith(p)
                                      for p in _STALE_WCS)

    kept = [c for c in old if not _drop(c)]
    tail = [fits_annotate._format_card(k, v) for k, v in cards.items()]
    header = "".join(kept + tail + ["END".ljust(fits_annotate._CARD)])
    try:
        header_bytes = header.encode("latin-1")
    except UnicodeEncodeError:
        header_bytes = header.encode("latin-1", "replace")
    pad = (-len(header_bytes)) % fits_annotate._BLOCK
    return header_bytes + b" " * pad + raw[data_start:]


def write_solved_wcs(path, cards):
    # Merges a solved WCS into the plate's header, in place and atomic.
    # @args: path - FITS file, cards - solved WCS cards (non-empty dict)
    # @return: True when the file was rewritten; raises OSError on a write
    #          problem (read-only file, permissions) for the caller to tell
    if not cards:
        return False
    path = Path(path)
    raw = path.read_bytes()
    _atomic_replace(path, _rebuild(raw, cards))
    logger.info("solved WCS written into %s", path.name)
    return True


def copy_with_solved_wcs(src, dest, cards):
    # Writes a COPY of a plate with a solved WCS merged into its header, so
    # an export can carry an astrometry solved this session (which may not
    # be on disk yet when "save the solved WCS" is off) without touching
    # the observer's original. Same header surgery as write_solved_wcs;
    # only the destination changes, and the pixel data plus any extensions
    # are copied verbatim. With no cards it is a plain byte copy (the
    # file's own WCS, if it has one, is preserved untouched).
    # @args: src - source FITS, dest - the copy to write, cards - solved
    #        WCS cards ({} copies as-is)
    # @return: the destination Path; raises OSError on a write problem
    src = Path(src)
    dest = Path(dest)
    raw = src.read_bytes()
    data = _rebuild(raw, cards) if cards else raw
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    logger.info("FITS copy with solved WCS written to %s", dest.name)
    return dest


def persist_solution(path, cards):
    # The policy door the GUI uses: writes the solution only when the
    # observer keeps the option on (default: on, ADR-051 rev).
    # @args: path - FITS file, cards - solved WCS cards
    # @return: (done, error) - error is "" or a short message; never raises
    try:
        from ..config import config
        enabled = bool(config.get("solve_save", True))
    except Exception:
        enabled = True
    if not enabled or not cards:
        return False, ""
    try:
        write_solved_wcs(path, cards)
        return True, ""
    except Exception as err:
        logger.warning("could not write the solved WCS into %s: %s",
                       Path(path).name, err)
        return False, str(err)
