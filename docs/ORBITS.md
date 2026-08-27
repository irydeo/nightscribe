# NightScribe — Orbital Explorer ("Explora")

*[Versión en español](ORBITS.es.md)*

The orbital explorer (`core/orbits.py`) translates raw orbital and physical
parameters into explanations that are **accurate, engaging and deep** — the feature
that sets NightScribe apart from raw ephemeris tables.

## Orbital families

Classification from SBDB elements (a, q, e) and orbit class code. Each family ships
with a short bilingual explanation (built by `core/orbits.py`):

| Family | Rule of thumb | One-liner |
|---|---|---|
| Atira | a < 1 AU, Q < 0.983 AU | lives entirely inside Earth's orbit |
| Aten | a < 1 AU, Q > 0.983 AU | crosses Earth's orbit from inside |
| Apollo | a > 1 AU, q < 1.017 AU | crosses Earth's orbit from outside |
| Amor | 1.017 < q < 1.3 AU | approaches but does not cross Earth |
| Main belt | 2.06 < a < 3.28 AU (approx.) | the rocky donut between Mars and Jupiter |
| Hungaria, Hilda, ... | resonances | notable sub-families |
| Trojan | a ≈ 5.2 AU, near L4/L5 | shares Jupiter's orbit, leading or trailing |
| Centaur | 5.5 < a < 30 AU | wandering between the giant planets |
| Trans-Neptunian | a > 30 AU | the frozen outskirts |
| Comets: JFc / HTc / CTc / LPC | SBDB class | Jupiter-family (returns every few years), Halley-type, long-period ("from the Oort cloud; will not return for millennia"), dynamically new |

## Translated parameters

Every parameter gets a value, an analogy and a "why it matters", in ES and EN, at two
depth levels:

- **a (semi-major axis)** → average distance; via Kepler's third law, "its year lasts
  X Earth years".
- **e (eccentricity)** → 0 = perfect circle; with e = 0.5 "it dives from beyond Mars
  to inside Venus' orbit" — crossing narratives from q and Q.
- **i (inclination)** → tilt over the solar system's "landing strip".
- **q / Q (perihelion / aphelion)** → closest and farthest points, with planetary context.
- **MOID** → minimum theoretical distance to Earth's orbit; honest risk scale:
  PHA = MOID < 0.05 AU and H ≤ 22, explained without alarmism; Torino scale when known.
- **H (absolute magnitude)** → size estimate: diameter from H with an assumed albedo
  per spectral class (C≈0.057, S≈0.20, M≈0.14; cometary nuclei ≈0.04), compared to
  everyday objects (see narrative size ladder).
- **U (orbit uncertainty 0–9)** → "how well we know its orbit" — links to planning:
  *"that is why your observation tonight matters"*.
- **period, perihelion velocity** → human-scale comparisons.
- **Next close approach** (CAD) → date, distance in lunar distances, relative velocity.
- **Comets: M1/K1** → expected magnitude `m = M1 + 5·log10(Δ) + K1·log10(r)`;
  comparing with COBS observed magnitude detects outbursts.
- **Supernovae**: redshift/distance of the host → light travel time, typical peak
  luminosity by type (Ia ≈ "5 billion Suns").
- **Exoplanets**: planet class from radius/mass (hot Jupiter, Neptune-like...),
  "its year lasts X days", equilibrium temperature, transit depth in mmag → "it dims
  its star by Y%".

## "Hooks that sell"

`orbits.py` ranks the object's 2–3 most outreach-worthy facts; `suggest.py` and
`post.py` consume them. Rules are explicit and tested (see SCORING.md).

## Formulas used (all documented in code)

- Visual magnitude estimate: `m ≈ H + 5·log10(r·Δ)` (phase neglected for outreach).
- Comet magnitude: `m = M1 + 5·log10(Δ) + K1·log10(r)`.
- Diameter from H: `D(km) = 1329 / sqrt(albedo) · 10^(-H/5)`.
- Kinetic energy (only when PHA, always with a reassuring note):
  `E = ½·ρ(4/3)π(D/2)³·v²`, ρ per spectral class (C 1300, S 2700, M 5000 kg/m³).
- Redshift → distance: `d ≈ z·c/H0`, H0 = 70 km/s/Mpc (small z).
- Lunar distance: 384 400 km. 1 AU = 149 597 870.7 km.
