############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Remembered system gain module (ADR-072 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The gain the app measured on the observer's own frames, remembered.

A supernova observer usually hands in ONE image, and one image cannot
measure the conversion gain: the photon-transfer recipe (core/gain.py)
needs a PAIR of frames at the same exposure. So the app measures the gain
whenever it can (a series, the track & stack, the one-time action) and
keeps the result here, keyed by the camera's own name and its gain
setting, so a single plate reuses it instead of trusting a header card
that may carry the camera's setting or a placeholder (ADR-072).

The key is (INSTRUME, GAIN, XBINNING): the camera with its serial, the
camera's gain setting, the binning. A plate that does not say its setting
(a stack carries no GAIN) falls back to the camera's most recent
measurement, and `matched` says whether it was the exact key or that
fallback.

All SQL goes through the shared Database (core/db.py): no Qt, no network.
"""

import logging
import time

logger = logging.getLogger(__name__)

# A setting nobody wrote is stored as this sentinel, not NULL: SQLite's
# UNIQUE treats two NULLs as different, so a NULL key would let the same
# camera pile up rows that never collide.
NO_SETTING = -1.0

_COLS = ("camera", "gain_setting", "binning", "gain_e_per_adu", "ron_e",
         "measured_at", "n_boxes", "n_kept")
_SELECT = ("SELECT camera, gain_setting, binning, gain_e_per_adu, ron_e,"
           " measured_at, n_boxes, n_kept FROM gains")


def key_of(header):
    # The store's key for a plate, straight out of its header.
    # @args: header - a FITS header dict (or None)
    # @return: {"camera", "gain_setting", "binning"} or None when the
    #          camera cannot be named (the store cannot be keyed)
    if not header:
        return None
    up = {str(k).upper(): v for k, v in header.items()}
    camera = str(up.get("INSTRUME") or "").strip()
    if not camera:
        return None
    setting = up.get("GAIN")
    try:
        setting = float(setting) if setting is not None else None
    except (TypeError, ValueError):
        setting = None
    try:
        binning = int(float(up.get("XBINNING") or 1))
    except (TypeError, ValueError):
        binning = 1
    return {"camera": camera, "gain_setting": setting, "binning": binning}


def _block(values, matched):
    # @args: values - a gains row (tuple, in _COLS order), matched - True
    #        on the exact key
    # @return: the store's own dict, or None
    if values is None:
        return None
    r = dict(zip(_COLS, values))
    setting = r["gain_setting"]
    return {"gain": r["gain_e_per_adu"], "ron": r["ron_e"],
            "source": "remembered", "camera": r["camera"],
            "gain_setting": (None if setting == NO_SETTING else setting),
            "binning": r["binning"], "measured_at": r["measured_at"],
            "matched": bool(matched), "n_boxes": r["n_boxes"],
            "n_kept": r["n_kept"]}


def recall(db, header):
    # The gain remembered for this plate's camera, or None.
    # @args: db - the Database, header - the plate's header
    # @return: {"gain", "ron", "source": "remembered", "camera",
    #           "gain_setting", "binning", "measured_at", "matched"} or None
    key = key_of(header)
    if key is None:
        return None
    setting = key["gain_setting"] if key["gain_setting"] is not None \
        else NO_SETTING
    row = db.execute(_SELECT + " WHERE camera=? AND gain_setting=? AND"
                     " binning=?", (key["camera"], setting,
                                    key["binning"])).fetchone()
    if row is not None:
        return _block(row, True)
    # no exact key: a plate that does not say its setting (a stack) still
    # gets the camera's most recent measurement, and `matched` says so
    row = db.execute(_SELECT + " WHERE camera=? ORDER BY measured_at DESC"
                     " LIMIT 1", (key["camera"],)).fetchone()
    return _block(row, False)


def remember(db, header, resolved):
    # Store the gain the app has just measured on the observer's frames.
    # @args: db - the Database, header - the header of the frames the gain
    #        was measured on (its INSTRUME and GAIN key the entry),
    #        resolved - a gain.resolve block carrying a gain
    # @return: the stored block (as recall returns it), or None when there
    #          is nothing to store (no camera, no gain)
    key = key_of(header)
    gain = (resolved or {}).get("gain")
    if key is None or gain is None or float(gain) <= 0.0:
        return None
    setting = key["gain_setting"] if key["gain_setting"] is not None \
        else NO_SETTING
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    ron = (resolved or {}).get("ron")
    row = db.execute("SELECT id FROM gains WHERE camera=? AND gain_setting=?"
                     " AND binning=?",
                     (key["camera"], setting, key["binning"])).fetchone()
    if row is not None:
        db.execute("UPDATE gains SET gain_e_per_adu=?, ron_e=?, source=?,"
                   " measured_at=?, n_boxes=?, n_kept=? WHERE id=?",
                   (float(gain), ron, "frames", now,
                    resolved.get("n_boxes"), resolved.get("n_kept"), row[0]))
    else:
        db.execute("INSERT INTO gains(camera, gain_setting, binning,"
                   " gain_e_per_adu, ron_e, source, measured_at, n_boxes,"
                   " n_kept) VALUES(?,?,?,?,?,?,?,?,?)",
                   (key["camera"], setting, key["binning"], float(gain), ron,
                    "frames", now, resolved.get("n_boxes"),
                    resolved.get("n_kept")))
    db.commit()
    logger.info("gain remembered: %s at setting %s -> %.4g e-/ADU",
                key["camera"], key["gain_setting"], float(gain))
    return recall(db, header)


def summary(record, lang="es"):
    # The remembered gain as one plain sentence, with the caveat when it is
    # the camera's most recent measurement and not this plate's exact key.
    # @args: record - a recall/remember block, lang - ui language
    # @return: {"es", "en"}, or None when there is no record
    if not record or record.get("gain") is None:
        return None
    setting = record.get("gain_setting")
    stxt = "{:.3g}".format(setting) if setting is not None else "?"
    when = str(record.get("measured_at") or "")[:10]
    es = ("Recordada de tu cámara (ajuste {}, medida el {})"
          .format(stxt, when or "?"))
    en = ("Remembered from your camera (setting {}, measured on {})"
          .format(stxt, when or "?"))
    if not record.get("matched"):
        es += (". Esta placa no dice su ajuste: es la última medida de esa "
               "cámara")
        en += (". This plate does not say its setting: it is that camera's "
               "most recent measurement")
    return {"es": es, "en": en}
