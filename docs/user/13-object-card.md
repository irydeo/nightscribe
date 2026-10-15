# 13. Understanding an object

Planning tells you *what* to observe. This chapter is the other half: *what
you are looking at*. NightScribe has one door for every object it knows, and
the card behind it is the same wherever you open it from.

## Three ways to open it

- the box in the top bar: **Explore an object…** (type a name and press
  Enter);
- **Tools → Explore object…**;
- double-click any row of the **Tonight** list, or the button on the row.

The name is looked up in VSX, SIMBAD, JPL SBDB, Horizons, CAD, TNS and the
NASA Exoplanet Archive, so it works for an asteroid, a comet, a supernova, a
variable star or an exoplanet host. If the object is in no catalogue, the
**Tonight** view still lets you create it by hand.

## The card

The card is a calling card, not a data dump:

- a **hook line** and a few outreach bullets, in Spanish and English: the
  sentence you would say out loud to explain why this object is interesting;
- a **parameter table where every row is explained**: the orbital family,
  the MOID (the minimum distance the orbit ever gets to the Earth's, in
  lunar distances), the size estimated from the absolute magnitude, the next
  close approach, the discovery date. It is multiline and nothing is
  truncated;
- the **charts**: the orbit (animated by date, with hover readouts), the
  night sky with *your* horizon silhouette and the safe window shaded, the
  survey field and the light curve when there is one. In the app they are
  live vector graphics (zoom, pan, hover); the same engines render the PNGs;
- the **capture chips**: current magnitude, apparent rate, the maximum
  trail-free exposure with your camera, the window and the hours above the
  horizon, plus copyable coordinates in decimal and sexagesimal with their
  epoch.

> **Why does every row come explained?** Because "MOID 0.03 AU" means
> nothing to most people, and "it can come within twelve lunar distances"
> means everything. The figures are the same; only the reader changes. The
> explanations live in one place (`core/explain.py`), so a type, a spectral
> class or a discovery method is described the same way wherever it appears.

## From the card to a project

The card is a starting point, not a dead end: **Create project** turns the
object into a project and drops you on its card, with the coordinates,
window and magnitude already filled in (chapter 03). From there the flow is
the usual one: capture, analyse, publish.

Next: [14. When something goes wrong](14-troubleshooting.md).
