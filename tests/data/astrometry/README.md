# Astrometry fixture (ADR-062)

Real data for the minor-planet track & stack work: two nights the observer
actually measured and reported to the MPC, plus Tycho-Tracker's own
results for the same nights.

## What is here

| Item | What it is |
|---|---|
| `dataset.json` | The manifest: the objects, the site and equipment, the frame counts and blocks, the astrometry the MPC published for each night, and Tycho's own numbers (rate, PA, stack recipe). |
| `reference/2025UR.png`, `reference/2026PY9.png` | Tycho-Tracker's track & stack results. They carry the reference astrometry, the measured rate/PA and the stack recipe, so they are the ground truth for this work. |
| `2025UR/`, `2026PY9/` | The cropped fixture: 60 frames of 256 x 256 around the object's track, plus a `reference.json` with the cropped WCS, the object's position in every frame and the published positions. |
| `make_fixture.py` | Rebuilds the cropped fixture from the raw frames. |

The raw FITS (about 2.5 GB: 140 frames of 2025 UR and 247 of 2026 PY9,
2048 x 2048, 8.4 MB each) **live outside the repository**. They are used
by the functional test when `NIGHTSCRIBE_ASTRO_DATASET` points at them.

## The nights

Both were taken with the same rig: QHY42PRO camera on a CDK17 (0.43-m
f/4.9), gain 6, Clear filter, 1.066 arcsec/px, 13.7 arcmin field. The
frames are unsigned 16-bit stored as int16 with `BZERO=32768`, which is
the case astropy refuses to memory-map (D32), so the fixture keeps it on
purpose.

- **2025 UR** (MPEC 2025-U52): 2025-10-18, 140 frames of 3 s. Published:
  3 observations from Z41 at 21:40, 21:43 and 21:46, mag 18.0 G.
- **2026 PY9** (MPEC 2026-Q24): 2026-08-16, 247 frames of 5 s in five
  blocks. Published: 2 observations from Z41 at 22:34 and 22:51, mag
  19.2-19.3 G.

Tycho's PNGs give the recipe for the first published observation of each:
76 x 3 s for 2025 UR and 130 x 5 s for 2026 PY9.

## How the grouping was decided

It was not: the observer does not remember it and the block structure
does not map onto the published observations (2025 UR has two runs but
three published points; 2026 PY9 has five blocks but two points). The
manifest records the published positions as they are and marks the
grouping as pending, to be recovered empirically once the engine runs:
try the candidate splits and keep the one that reproduces the published
positions.

## What the fixture shows, and what it does not

- **2025 UR**: the asteroid emerges from the crop when the frames are
  stacked along its motion (SNR about 15 with a sigma-clipped mean of the
  60 frames). This is the fixture that demonstrates a detection.
- **2026 PY9**: the object does **not** emerge from a crude stack of the
  crop. It is 1.2 mag fainter and the sky is about 2.5 times brighter
  (~12000 ADU), so a plain mean or median stays at SNR about 3. It is
  kept as a mechanics fixture (the faint, bright-sky case); the real
  detection test is the whole night through the functional test.

The fixture is for the engine's mechanics first: unsigned 16-bit reading,
WCS with a crop, a moving object, real star fields and real trails.

## Rebuilding

```bash
NIGHTSCRIBE_ASTRO_DATASET=/path/to/dataset \
    python tests/data/astrometry/make_fixture.py
```

The script cuts each object's run down to the frames closest to its
published observation, solves the first one with the local ASTAP
(ADR-051) for the CD matrix, asks JPL Horizons for the object's position
in every frame (topocentric at Z41: for a close NEO the parallax is
minutes of arc), and writes the crop plus the reference. It needs ASTAP
and network for Horizons; the frames themselves are not modified.
