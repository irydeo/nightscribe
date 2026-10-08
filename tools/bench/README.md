# tools/bench, the photometry and stacking bench

Bench code. **The app never imports it and it is not shipped** (see the
PyInstaller spec): it exists to answer questions with numbers, and it is kept
so the answers can be re-checked when the regime changes (another camera,
another sky, another library version).

Each script prints a table and writes a JSON into `$NIGHTSCRIBE_BENCH_OUT`
(default `/tmp/opencode/nsbench`).

| script | the question it answers | the report |
|---|---|---|
| `bench_inject.py` | Would another photometry engine measure a single star better? Injects a star of a known flux into copies of real frames and measures it back, at a fixed SNR against the plate's own noise floor. | `inject.json` |
| `bench_centroid.py` | What does a centroid cost and what does it buy? Synthetic truth, deterministic clicks, fresh noise per trial. | printed |
| `bench_series.py` | Does another engine give a flatter light curve? Runs the real series twice with the same frames, comps, apertures and alignment; only the measurement changes. | `series.json` |
| `bench_defences.py` | What do the centroid's deblending defences buy, in the case they were built for (a faint target next to a bright neighbour)? | printed |
| `bench_depth.py` | How deep does a stack really go? Injection and recovery on a stack, with the flux measured without the engine's positivity cut. | `depth.json` |
| `bench_order.py` | Does the interpolation order buy depth, or only looks? Builds the same stack at orders 1, 3 and 5 and injects into each. | `order.json` |
| `bench_combine.py` | How much depth is lost by combining with the median instead of the sigma-clipped mean? Four stacks, one test, one verdict. | `combine.json` |
| `bench_frames.py` | Should the frames the registration refused be stacked anyway? The seeing is the reason, not the alignment. | `frames.json` |
| `engines.py`, `harness.py` | The engines and the shared helpers (datasets, injection, metrics). |, |

## The two rules this bench learned the hard way

1. **Measure the flux without the engine's guards.** `photometry.measure_point`
   refuses a non-positive flux (it is right to), so measuring with it keeps
   only the positive half of a distribution centred on zero: the first version
   of `bench_depth.py` reported a +222 % bias at 40 ADU that was nothing but
   that cut.
2. **Share the injection positions, with an absolute criterion.** Choosing the
   spots from each stack's own noise test moved the answer by more than the
   effect being measured (three runs gave "Tycho +0.19 mag", "ours +0.29" and
   "Tycho +0.24"). The criterion is in ADU above the sky, the same ruler for
   every image, and every image must be clean at those spots.

The results are recorded in **ADR-067** (the engine) and **ADR-068** (the
combination and the depth).
