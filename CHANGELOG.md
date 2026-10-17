# Changelog

All notable changes to NightScribe are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-15

The first public release. NightScribe covers the whole life cycle of an
observatory project: **plan the night, understand the object, capture and
reduce, and tell it**.

### Added

- **Plan the night**: a ranked, explained list of what is worth observing
  tonight from your site and with your equipment, across eight kinds of
  targets (NEOs and NEOCP candidates, supernovae, comets, PCCP candidates,
  exoplanet transits, HADS stars, variable stars and duties, close approaches
  and alerts), with a 0-100 score, a "why tonight" sentence, the sky calendar
  and the Sun and Moon context.
- **Understand the object**: an object card that translates orbital and
  physical parameters into plain language, with charts (orbit, sky, survey
  field, light curve) and capture chips (magnitude, rate, maximum trail-free
  exposure, window, copyable coordinates).
- **Capture and reduce**: it drives CCDciel or NINA/PINS, and its unified
  FITS editor calibrates (library of masters), stacks (track & stack, with
  registration and the manual weak-object mode), measures photometry
  (comparison sequences, series, periods, transit fit) and astrometry
  (sub-pixel centroids, MPC-ready reports in ADES or 80 columns, the check
  against other stations with Find_Orb, the ExoClock handoff).
- **Tell it**: bilingual (ES/EN) post and tweet drafts with the night's
  charts.
- **Projects, visits and campaigns**: every target becomes a project with its
  own folder and a Card, Capture, Analysis, Publishing flow; each night is a
  visit; campaigns and variable-star vigils carry their own cadence.
- **A command-line interface** for planning and publishing, bilingual.
- **The assistant** (optional, off by default): it answers from the app's own
  guide and ADRs, offline, through a model you configure.
- **An OpenCL GPU path** (on by default, falls back to the processor) for the
  warp and the combine.

### Notes

- This is the first public release, so it is a **beta**: expect rough edges.
  Report them at <https://github.com/irydeo/nightscribe/issues>, attaching the
  log (**Help → Open the log**).
- Find_Orb travels inside the Windows installer and the Linux packages;
  EXOTIC (the transit reduction) is the one external tool you install by hand.
- The **NINA/PINS** integration is **not finished**: it is there to be tried
  and to report what is missing or broken, and the rest is planned for
  **0.2**. CCDciel is the complete one today (chapter 05 lists what NINA/PINS
  does not do yet).
