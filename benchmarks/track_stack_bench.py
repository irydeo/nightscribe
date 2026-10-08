############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Track & stack benchmark (speed plan, F0)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The instrument of the speed plan: where the seconds of a track & stack
run actually go.

Why a separate script and not a test: a benchmark is a NUMBER, not a gate.
A test that asserts "under N seconds" fails on a slow machine for no reason,
and one that asserts nothing is a test that does not test. This prints a
table, a human reads it, and the numbers go in the code's comments and in
the plan.

It synthesizes a star field with an object walking at a known rate, writes
the frames once, and times each stage with the SAME functions the pipeline
calls. Usage:

    python benchmarks/track_stack_bench.py
    python benchmarks/track_stack_bench.py --frames 140 --size 2048
    python benchmarks/track_stack_bench.py --method sigma --final-size 0
"""

import argparse
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nightscribe.core import register, track_stack  # noqa: E402


def _star_field(size, seed=1):
    rng = np.random.default_rng(seed)
    img = rng.normal(1000.0, 4.0, (size, size))
    yy, xx = np.mgrid[0:size, 0:size]
    for _ in range(80):
        x, y = rng.uniform(8, size - 8), rng.uniform(8, size - 8)
        img += rng.uniform(1500.0, 4000.0) * np.exp(
            -((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.5 ** 2))
    return img


def _make_frames(folder, n, size, rate_px):
    from astropy.io import fits
    base = _star_field(size)
    yy, xx = np.mgrid[0:size, 0:size]
    frames = []
    x0 = size * 0.35
    for i in range(n):
        img = base.copy()
        x, y = x0 + rate_px * i, size * 0.5
        img += 2500.0 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2)
                               / (2 * 1.5 ** 2))
        path = folder / f"f{i:04d}.fits"
        fits.PrimaryHDU(img.astype(np.int16)).writeto(str(path),
                                                      overwrite=True)
        frame = track_stack.Frame(path=str(path),
                                  header={"NAXIS1": size, "NAXIS2": size})
        frame.transform = {"angle": 0.0, "dx": 0.0, "dy": 0.0,
                           "quality": 100.0, "rms_px": 0.0}
        frame.object_xy = (x, y)
        frame.t_mid_jd = 2460000.5 + i / 1440.0
        frames.append(frame)
    return frames


def _time(label, fn, repeat=1):
    best = float("inf")
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    print(f"  {label:<46} {best * 1000:10.1f} ms")
    return best


def main():
    ap = argparse.ArgumentParser(description="Track & stack benchmark")
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--rate", type=float, default=1.0, help="px/min of the object")
    ap.add_argument("--method", default="sigma")
    ap.add_argument("--final-size", type=int, default=0,
                    help="0 = whole frame")
    ap.add_argument("--sweep-steps", type=int, default=5)
    ap.add_argument("--threads", type=int, default=0,
                    help="0 = automatic (cores and memory)")
    args = ap.parse_args()
    cfg = {"astrometry_threads": args.threads}

    from nightscribe.core import parallel
    print(f"machine: {parallel.cpu_cores()} logical cores, "
          f"auto workers {parallel.worker_count()}, "
          f"free RAM {parallel.available_memory_bytes()}")
    print(f"sequence: {args.frames} x {args.size}^2, rate {args.rate} px/min, "
          f"method {args.method}, final {args.final_size or 'whole frame'}\n")

    folder = Path(tempfile.mkdtemp(prefix="nsbench_"))
    frames = _make_frames(folder, args.frames, args.size, args.rate)
    ref = frames[0]
    from nightscribe.core import calibration
    ref_data, _ = calibration.read_image(ref.path)

    print("registration (per frame):")
    ref_src = register.source_image(ref_data)
    ref_stars = register.detect_stars(ref_src)
    src_data, _ = calibration.read_image(frames[1].path)
    _time("source_image (one 2048^2-style frame)",
          lambda: register.source_image(src_data), repeat=3)
    _time("detect_stars",
          lambda: register.detect_stars(register.source_image(src_data)),
          repeat=3)
    _time("estimate_transform (full, ref_src cached)",
          lambda: register.estimate_transform(ref_data, src_data,
                                              ref_stars=ref_stars,
                                              ref_src=ref_src), repeat=3)

    print("\nstacking:")
    box = track_stack.cutout_box(frames, (0, len(frames)), frames[0].object_xy,
                                 margin_px=64, shape=(args.size, args.size))
    _time("sweep (full grid)",
          lambda: track_stack.sweep(frames, frames[0].object_xy, args.rate,
                                    90.0, box, (args.size, args.size),
                                    steps=args.sweep_steps, method="median",
                                    cfg=cfg),
          repeat=1)
    final_box = track_stack.box_around(frames[0].object_xy, args.final_size,
                                       (args.size, args.size))
    _time(f"stack_group ({args.method}, final box)",
          lambda: track_stack.stack_group(frames, (0, len(frames)),
                                          frames[0].object_xy, args.method,
                                          final_box, (args.size, args.size),
                                          cfg=cfg),
          repeat=1)
    strip = np.random.default_rng(0).normal(0, 1, (args.frames,
                                                   min(args.size, 512),
                                                   min(args.size, 512)))
    strip = strip.astype(np.float32)
    _time(f"combine alone ({args.method}, {strip.shape})",
          lambda: track_stack.combine(strip, args.method, cfg=cfg), repeat=1)
    _time("combine alone (mean, same cube)",
          lambda: track_stack.combine(strip, "mean", cfg=cfg), repeat=1)


if __name__ == "__main__":
    main()
