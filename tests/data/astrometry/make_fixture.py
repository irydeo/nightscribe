############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Astrometry fixture builder (ADR-062)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Rebuild the astrometry regression fixture from the observer's frames.

The two real datasets (2025 UR and 2026 PY9, about 2.5 GB) live outside
the repository. This script cuts a run of frames down to a small window
around the object's track (they still carry the whole drift, so the
asteroid emerges when they are stacked) and writes, next to them, the
reference: the cropped WCS, the object's position in every frame and the
astrometry the MPC published for that night.

    NIGHTSCRIBE_ASTRO_DATASET=/path/to/dataset \
        python tests/data/astrometry/make_fixture.py

The object's position per frame comes from JPL Horizons at the station's
code (topocentric: for a close NEO the parallax is minutes of arc, not a
detail), so the fixture does not depend on how the frames were grouped
into observations. The frames carry no WCS, so the first one is solved
with the local ASTAP (ADR-051) and its CD matrix is reused for the rest,
with each frame's own pointing from its header.
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from astropy.io import fits                      # noqa: E402
from astropy.wcs import WCS                      # noqa: E402

from nightscribe.core import coords, ephemeris   # noqa: E402
from nightscribe.core.sources import astap, horizons  # noqa: E402

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "dataset.json"
# A frame belongs to the same run as the previous one unless the gap is
# bigger than this: the observer's cadence is 5-7 s, and the real gaps
# between runs are ~2-5 minutes.
BLOCK_GAP_S = 30.0


def _read_time(path):
    # @args: path - FITS frame
    # @return: (datetime aware UTC, header dict) or (None, {})
    header = fits.getheader(path)
    raw = header.get("DATE-OBS")
    if not raw:
        return None, dict(header)
    try:
        dt = datetime.datetime.fromisoformat(str(raw))
    except ValueError:
        return None, dict(header)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt, dict(header)


def _pick_frames(entries, anchor, n):
    # @args: entries - list[(datetime, path)], anchor - datetime, n - how many
    # @return: the n frames closest to the anchor, in time order
    chosen = sorted(entries, key=lambda e: abs((e[0] - anchor).total_seconds()))
    return sorted(chosen[:n], key=lambda e: e[0])


def _solve_cd(path):
    # @args: path - a frame with no WCS in its header
    # @return: (cd matrix as 2x2 list, header of that frame)
    # ASTAP writes a TAN solution; only the CD matrix is reused, because
    # every frame carries its own pointing in CRVAL.
    cards = astap.solve(path)
    if not cards:
        raise SystemExit(f"ASTAP could not solve {path}")
    cd = [[float(cards["CD1_1"]), float(cards["CD1_2"])],
          [float(cards["CD2_1"]), float(cards["CD2_2"])]]
    return cd, dict(fits.getheader(path))


def _frame_wcs(header, cd):
    # @args: header - a frame header, cd - the 2x2 matrix from the solve
    # @return: an astropy WCS for that frame
    # The frames have no WCS but they do carry CRVAL (the pointing), so a
    # dither between frames is handled without solving each one.
    naxis1 = int(header["NAXIS1"])
    naxis2 = int(header["NAXIS2"])
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [float(header["CRVAL1"]), float(header["CRVAL2"])]
    w.wcs.crpix = [(naxis1 + 1) / 2.0, (naxis2 + 1) / 2.0]
    w.wcs.cd = np.asarray(cd, dtype=float)
    w.wcs.radesys = "ICRS"
    w.wcs.equinox = 2000.0
    return w


def _object_pixels(paths, cd, name, site):
    # @args: paths - frame paths in time order, cd - CD matrix, name -
    #        Horizons designation, site - MPC code
    # @return: list[(ra_deg, dec_deg, x, y)] per frame
    times = [_read_time(p)[0] for p in paths]
    day = times[0].date()
    rows = horizons.ephemeris(name, center=site,
                              start=str(day),
                              stop=str(day + datetime.timedelta(days=1)),
                              step="1 m")
    motion = ephemeris.motion_interpolator(rows) if rows else None
    if motion is None:
        raise SystemExit(f"Horizons gave nothing for {name}")
    out = []
    for path, when in zip(paths, times):
        jd = coords.jd_from_datetime(when)
        ra, dec = motion(jd)
        header = dict(fits.getheader(path))
        w = _frame_wcs(header, cd)
        x, y = w.all_world2pix([[ra, dec]], 0)[0]
        out.append((ra, dec, float(x), float(y)))
    return out


def _crop_box(pixels, size, naxis1, naxis2):
    # @args: pixels - list[(ra, dec, x, y)], size - window side, naxis1/2 -
    #        the full frame size
    # @return: (x0, y0) of the window that holds the whole track
    xs = [p[2] for p in pixels]
    ys = [p[3] for p in pixels]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    x0 = int(round(cx - size / 2.0))
    y0 = int(round(cy - size / 2.0))
    x0 = max(0, min(x0, naxis1 - size))
    y0 = max(0, min(y0, naxis2 - size))
    return x0, y0


def _write_crop(src, out_path, box, wcs_cropped, x0, y0):
    # @args: src - full frame, out_path - where, box - (x0,y0,x1,y1),
    #        wcs_cropped - the cropped WCS, x0/y0 - crop origin
    # @return: None
    # Read the raw values (do_not_scale_image_data: astropy refuses to
    # memmap a frame with BZERO, D32) and write them back as the camera
    # wrote them, so the fixture still exercises the unsigned-16 path.
    with fits.open(src, memmap=True, do_not_scale_image_data=True) as hdul:
        hdu = next(h for h in hdul if h.header.get("NAXIS", 0) == 2)
        raw = np.asarray(hdu.section[box[1]:box[3], box[0]:box[2]])
        src_header = dict(hdu.header)
    out = fits.PrimaryHDU(raw)
    header = out.header
    for key in ("EXPTIME", "DATE-OBS", "FILTER", "INSTRUME", "GAIN",
                "CCD-TEMP", "XBINNING", "YBINNING", "OBJECT"):
        if key in src_header:
            header[key] = src_header[key]
    header["BSCALE"] = src_header.get("BSCALE", 1)
    header["BZERO"] = src_header.get("BZERO", 32768)
    header["CRPIX1"] = wcs_cropped.wcs.crpix[0] - x0
    header["CRPIX2"] = wcs_cropped.wcs.crpix[1] - y0
    # the WCS cards, written explicitly (astropy needs the exact names)
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRVAL1"] = wcs_cropped.wcs.crval[0]
    header["CRVAL2"] = wcs_cropped.wcs.crval[1]
    cd = wcs_cropped.wcs.cd
    header["CD1_1"], header["CD1_2"] = cd[0][0], cd[0][1]
    header["CD2_1"], header["CD2_2"] = cd[1][0], cd[1][1]
    header["RADESYS"] = "ICRS"
    header["EQUINOX"] = 2000.0
    header["HISTORY"] = "NightScribe astrometry fixture crop (ADR-062)"
    out.writeto(str(out_path), overwrite=True)


def build(cfg, dataset_root, out_root, n_frames, size):
    # @args: cfg - one object from the manifest, dataset_root - where the
    #        raw FITS live, out_root - the fixture dir, n_frames/size - crop
    # @return: the reference dict written next to the frames
    run = Path(dataset_root) / cfg["raw_path"].split("/")[-1] / cfg["run"]
    paths = sorted(run.glob("*.fits"))
    if not paths:
        raise SystemExit(f"no frames under {run}")
    stamped = [(_read_time(p)[0], p) for p in paths]
    stamped = [(t, p) for t, p in stamped if t is not None]
    anchor = datetime.datetime.fromisoformat(cfg["anchor"])
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=datetime.timezone.utc)
    # the frames closest to the anchor. A crop may span the multi-minute
    # gaps between runs: the object just moves a little more, and the
    # ephemeris carries it. The anchor keeps the crop centred on the
    # published observation instead of on the whole night.
    picked = _pick_frames(sorted(stamped), anchor, n_frames)
    print(f"{cfg['key']}: {len(paths)} frames, picked {len(picked)} "
          f"({picked[0][0].isoformat()} .. {picked[-1][0].isoformat()})")
    cd, _header = _solve_cd(str(picked[0][1]))
    pixels = _object_pixels([str(p) for _t, p in picked], cd,
                            cfg["horizons"], cfg["site_code"])
    naxis1, naxis2 = cfg["frame_size"]
    x0, y0 = _crop_box(pixels, size, naxis1, naxis2)
    box = (x0, y0, x0 + size, y0 + size)
    print(f"   crop {box} (track x {min(p[2] for p in pixels):.0f}-"
          f"{max(p[2] for p in pixels):.0f}, "
          f"y {min(p[3] for p in pixels):.0f}-{max(p[3] for p in pixels):.0f})")
    obj_dir = Path(out_root) / cfg["key"]
    obj_dir.mkdir(parents=True, exist_ok=True)
    frames_ref = []
    for index, ((when, path), (ra, dec, x, y)) in enumerate(zip(picked, pixels)):
        out_path = obj_dir / f"frame{index:03d}.fits"
        header = dict(fits.getheader(str(path)))
        w = _frame_wcs(header, cd)
        _write_crop(str(path), out_path, box, w, x0, y0)
        frames_ref.append({
            "file": out_path.name,
            "date_obs": when.isoformat(),
            "object_ra_deg": round(ra, 7), "object_dec_deg": round(dec, 7),
            "object_xy": [round(x - x0, 2), round(y - y0, 2)],
        })
    ref = {
        "object": cfg["key"],
        "horizons": cfg["horizons"],
        "mpec": cfg["mpec"],
        "exptime_s": cfg["exptime_s"],
        "filter": cfg["filter"],
        "n_frames": len(frames_ref),
        "crop": {"box": list(box), "size": size},
        "cd": cd,
        "published": cfg["published"],
        "tycho_png": cfg["tycho_png"],
        "grouping": cfg["grouping"],
        "frames": frames_ref,
    }
    (obj_dir / "reference.json").write_text(json.dumps(ref, indent=1),
                                            encoding="utf-8")
    print(f"   wrote {len(frames_ref)} frames + reference.json in {obj_dir}")
    return ref


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default=os.environ.get("NIGHTSCRIBE_ASTRO_DATASET"),
                    help="root that holds 2025UR/ and 2026PY9/ (or set "
                         "NIGHTSCRIBE_ASTRO_DATASET)")
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--frames", type=int, default=50)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--object", default=None, help="only this object key")
    args = ap.parse_args()
    if not args.dataset:
        raise SystemExit("pass --dataset or set NIGHTSCRIBE_ASTRO_DATASET")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    site = manifest["site"]["mpc_code"]
    for cfg in manifest["objects"]:
        if args.object and cfg["key"] != args.object:
            continue
        cfg = dict(cfg)
        cfg["site_code"] = site
        n = int(cfg.get("fixture_frames", args.frames))
        build(cfg, args.dataset, args.out, n, args.size)


if __name__ == "__main__":
    main()
