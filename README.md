# NightScribe

*[Versión en español](README.es.md)*

**Plan your night, understand every object, tell your science.**

NightScribe is a desktop application (Qt6 GUI + CLI) for amateur astronomical
observatories:

- **Tonight** — the best NEOs, comets, possible comets (PCCP), supernovae and
  exoplanet transits visible from your observatory, ranked by a unified score with
  one-line "why tonight" explanations.
- **Explore** — orbital and physical parameters translated into accurate, engaging
  explanations (families, MOID, sizes, origins...).
- **Post** — bilingual (ES/EN) social-media drafts + tweet + ready-to-attach PNG
  charts (orbit, night sky, Sun, supernova before/after).
- **Solar system now** — live Sun (NASA SDO), Moon, and tonight's visible planets.
- **Settings** — first-run wizard; your MPC observatory code resolves your
  coordinates automatically.

Data sources include NEOfixer, MPC (PCCP, ObsCodes), JPL SBDB/Horizons/CAD, COBS,
Rochester Astronomy, SIMBAD, ExoClock, NASA Exoplanet Archive, NOAA SWPC, SILSO and
NASA SDO.

## Quickstart

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nightscribe gui        # desktop app
.venv/bin/python -m nightscribe tonight    # best targets tonight (CLI)
```

See [INSTALL.md](INSTALL.md) for full per-OS instructions and the standalone
installer, and [CONTRIBUTING.md](CONTRIBUTING.md) to hack on it.

## Documentation

Design, architecture, data sources, scoring and all decisions (ADRs) live in
[`docs/`](docs/) (bilingual ES/EN).

## Licence

GPL v3 — (c) 2026 Francisco José Calvo Fernández (Irydeo Observatory, MPC Z41).
