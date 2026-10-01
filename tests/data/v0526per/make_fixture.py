############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - V0526 Per fixture builder (quality plan, phase D)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Rebuild the V0526 Per regression fixture from the observer's frames.

The real series lives outside the repository (about 1 GB). This script
cuts eight frames down to 512 x 512 around the target (they still carry
the whole 134 arcsec drift), writes the reference WCS, the comparison
sequence and the observer's own report, so the unit tests can hold the
alignment to real data without the whole folder.

    python tests/data/v0526per/make_fixture.py <series folder>

The folder must hold v526per-001Rcal.fit ... v526per-244Rcal.fit and,
one level up, INFORMES/informe fotodfi v526per.txt.
"""

import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from nightscribe.core import fits_io, photometry, register  # noqa: E402
from nightscribe.core import wcs as wcs_mod  # noqa: E402

HERE = Path(__file__).resolve().parent

# The ASTAP solution of the reference plate (frame 1), solved for this
# documentation and reproduced here so the fixture needs no solver.
FULL_WCS = {
    "crval1": 49.99264085174, "crval2": 49.77952159051,
    "crpix1": 832.0, "crpix2": 626.5,
    "cd": [[4.276374824421e-4, 4.955628662279e-5],
           [-4.945730932057e-5, 4.277697071812e-4]],
    "naxis1": 1663, "naxis2": 1252,
}
TARGET_FULL = (804.2478974709531, 830.9527603479363)
# the sequence the project used (Gaia EDR3, V derived): the east and
# north ones leave the field with the drift, which the report says
FULL_ENTRIES = json.loads(
    (HERE / "series_entries.json").read_text(encoding="utf-8"))

# the crop: 512 x 512 around the target, drift included
CROP = 550
SIZE = 512
FRAMES = (1, 40, 80, 120, 160, 200, 230, 244)


def _card(key, value=None, comment=""):
    s = key.ljust(8) if value is None else f"{key.ljust(8)}= {value}"
    return (s + (f" / {comment}" if comment else ""))[:80].ljust(80)


def _write(path, data, header_in):
    cards = [
        _card("SIMPLE", "T"), _card("BITPIX", "16"), _card("NAXIS", "2"),
        _card("NAXIS1", str(data.shape[1])), _card("NAXIS2", str(data.shape[0])),
        _card("BSCALE", "1.0"), _card("BZERO", "32768.0"),
        # the cropped WCS: only CRPIX moves
        _card("CTYPE1", "'RA---TAN'"), _card("CTYPE2", "'DEC--TAN'"),
        _card("CRVAL1", repr(FULL_WCS["crval1"])),
        _card("CRVAL2", repr(FULL_WCS["crval2"])),
        _card("CRPIX1", repr(FULL_WCS["crpix1"] - CROP)),
        _card("CRPIX2", repr(FULL_WCS["crpix2"] - CROP)),
        _card("CD1_1", repr(FULL_WCS["cd"][0][0])),
        _card("CD1_2", repr(FULL_WCS["cd"][0][1])),
        _card("CD2_1", repr(FULL_WCS["cd"][1][0])),
        _card("CD2_2", repr(FULL_WCS["cd"][1][1])),
        _card("EXPTIME", str(header_in.get("EXPTIME", 40.0))),
        _card("JD", repr(float(header_in.get("JD", 0.0)))),
        _card("DATE-OBS", "'{}'".format(header_in.get("DATE-OBS", ""))),
        _card("INSTRUME", "'SXV-H18'"), _card("XBINNING", "2"),
        _card("SOLVED", "T"),
    ]
    raw = "".join(cards + [_card("END")]).encode("latin-1")
    raw += b" " * ((2880 - len(raw) % 2880) % 2880)
    # 16-bit unsigned, like the camera wrote them (BZERO=32768)
    body = np.clip(np.rint(np.asarray(data, dtype=np.float64) - 32768.0),
                   -32768.0, 32767.0).astype(">i2").tobytes()
    body += b"\0" * ((2880 - len(body) % 2880) % 2880)
    path.write_bytes(raw + body)


def main(series_dir):
    series = Path(series_dir)
    wcs = wcs_mod.Wcs(FULL_WCS["crval1"], FULL_WCS["crval2"],
                      FULL_WCS["crpix1"], FULL_WCS["crpix2"],
                      FULL_WCS["cd"], FULL_WCS["naxis1"],
                      FULL_WCS["naxis2"])
    # 1. the cropped frames
    head = None
    for n in FRAMES:
        src = series / f"v526per-{n:03d}Rcal.fit"
        hdr, data = fits_io.read_fits(src)
        data = np.asarray(data, dtype=np.float64)
        if n == 1:
            head = hdr
        cut = data[CROP:CROP + SIZE, CROP:CROP + SIZE]
        _write(HERE / f"frame{n:03d}.fits", cut, hdr)
        print("wrote", f"frame{n:03d}.fits", cut.shape)
    # 2. the target: the full-frame position minus the crop
    tx, ty = TARGET_FULL[0] - CROP, TARGET_FULL[1] - CROP
    # 3. comparison stars inside the crop that survive the drift
    import numpy as _np  # noqa: F401  (readability of the section)

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from nightscribe.core import fits_io as _fio
    _h, ref = _fio.read_fits(HERE / "frame001.fits")
    ref = np.asarray(ref, dtype=np.float64)
    stars = register.detect_stars(register.source_image(ref), nmax=60,
                                  sat=None)
    # the region that stays in frame, apertures included, for the whole
    # drift (measured: +85 in x, -21 in y over the series)
    inside = [(x, y, p) for x, y, p in stars
              if 21.0 <= x <= SIZE - 106.0 and 42.0 <= y <= SIZE - 21.0
              and p < 55000.0]
    # comparison stars must be NEAR the target in brightness: the app's
    # own rule is "never the brightest of the field, they saturate"
    t_peak = photometry.measure_point(ref, tx, ty, r_ap=6.0, r_ann_in=10.0,
                                      r_ann_out=15.0)["peak"]
    inside.sort(key=lambda s: abs(math.log10(max(s[2], 1.0) / t_peak)))
    picked = []
    for x, y, p in inside:
        if p < 1500.0:
            continue
        if math.hypot(x - tx, y - ty) < 35.0:
            continue
        if any(math.hypot(x - a, y - b) < 30.0 for a, b, _c in picked):
            continue
        picked.append((x, y, p))
        if len(picked) == 6:
            break
    if len(picked) < 5:
        raise SystemExit("not enough comparison stars inside the crop")
    cw = wcs_mod.Wcs(FULL_WCS["crval1"], FULL_WCS["crval2"],
                     FULL_WCS["crpix1"] - CROP, FULL_WCS["crpix2"] - CROP,
                     FULL_WCS["cd"], SIZE, SIZE)
    entries = []
    for j, (x, y, p) in enumerate(picked):
        r = photometry.measure_point(ref, x, y, r_ap=6.0, r_ann_in=10.0,
                                    r_ann_out=15.0)
        inst = -2.5 * math.log10(r["flux"])
        ra, dec = cw.pixel_to_sky(x, y)
        entries.append({
            "name": "Check" if j == len(picked) - 1 else f"C{j + 1}",
            "kind": "check" if j == len(picked) - 1 else "comp",
            "star": {"ra": ra, "dec": dec, "band": "Rc",
                     "bands": [{"label": "Rc", "value": inst + 22.0,
                                "err": 0.02, "derived": False}],
                     "bv": 1.2},
            "xy_full": [x + CROP, y + CROP]})
        print("comp", entries[-1]["name"], "at", round(x, 1), round(y, 1),
              "V~", round(inst + 22.0, 2))
    # 4. the reference block
    out = {
        "series": {
            "wcs": FULL_WCS, "target_xy": list(TARGET_FULL), "band": "V",
            "entries": FULL_ENTRIES,
            "drift_px": [85.0, -21.0], "n_frames": 244,
        },
        "crop": {
            "box": [CROP, CROP, SIZE, SIZE], "frames": list(FRAMES),
            "wcs": {"crval1": FULL_WCS["crval1"], "crval2": FULL_WCS["crval2"],
                    "crpix1": FULL_WCS["crpix1"] - CROP,
                    "crpix2": FULL_WCS["crpix2"] - CROP,
                    "cd": FULL_WCS["cd"], "naxis1": SIZE, "naxis2": SIZE},
            "target_xy": [tx, ty], "band": "Rc",
            "expected_drift_px": [85.0, -21.0],
            "entries": entries,
        },
    }
    (HERE / "reference.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    report = series.parent / "INFORMES" / "informe fotodfi v526per.txt"
    if report.exists():
        shutil.copyfile(report, HERE / "reference_report.txt")
        print("copied the report")
    print("fixture ready in", HERE)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
