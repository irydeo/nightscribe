############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Target kind catalogue (wizard + settings)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import re

# The canonical list of target kinds the app can follow, in display order.
# The "Your targets" page of the update wizard (ADR-042) and the Settings
# dialog both read from here, so the checkbox list, the labels, the
# plain-language descriptions and the data source lines always agree.
#
# "since" is the application milestone the kind was introduced at. It is
# a version string (e.g. "0.0.3") used only to compare order with the
# user's last installed version, so the wizard can badge what a recent
# update brought ("nuevo"). A dev build like "0.0.1.dev1" compares as
# the release it is heading to (the dev tail is dropped), which keeps
# the comparison simple and needs no external parser.

KINDS = [
    {
        "id": "neo",
        "label": "Near-Earth objects (NEOs)",
        "blurb": ("Asteroids and comets on paths that pass close to Earth: "
                  "the confirmed ones with score, priority, apparent rate, "
                  "sky uncertainty and flags (NEOCP, impact risk, radar, "
                  "NHATS), plus the unconfirmed candidates with preliminary "
                  "orbits computed from the MPC astrometry."),
        "source": ("NEOfixer's site-specific list + NEOCP (MPC); positions "
                   "from NASA Horizons"),
        "since": "0.0.1",
    },
    {
        "id": "sn",
        "label": "Supernovae",
        "blurb": ("The newest discoveries, with the complete follow-up: a "
                  "confirmation blink of your FITS against a PanSTARRS "
                  "reference, the light curve drawn against the typical "
                  "templates of each type, an evolution animation, exports "
                  "and cadence reminders to know when to go back."),
        "source": ("Rochester Astronomy discovery list + a PanSTARRS (MAST) "
                   "reference for the blink"),
        "since": "0.0.1",
    },
    {
        "id": "comet",
        "label": "Comets",
        "blurb": ("Comets visible tonight with their live observed "
                  "magnitude, perihelion date and activity flags, so you "
                  "know how each one is doing now, not last month."),
        "source": "COBS (MPC) live magnitudes + NASA Horizons",
        "since": "0.0.1",
    },
    {
        "id": "pccp",
        "label": "Comet candidates (PCCP)",
        "blurb": ("Objects reported as asteroids that might actually be "
                  "comets, with their comet score: the MPC's Possible "
                  "Comet Confirmation Page. Getting there first matters."),
        "source": "MPC PCCP (minorplanetcenter.net) + NASA Horizons",
        "since": "0.0.1",
    },
    {
        "id": "transit",
        "label": "Exoplanet transits",
        "blurb": ("Exoplanets crossing their star tonight from your site, "
                  "with the transit time, how much the observed timing is "
                  "drifting from the prediction (O-C), whether the whole "
                  "transit fits in your night, the maximum trail-free "
                  "exposure and a pre-filled export for EXOTIC."),
        "source": ("ExoClock (ESA Ariel ephemeris programme) + NASA "
                   "Exoplanet Archive; times from NASA Horizons (HJD)"),
        "since": "0.0.1",
    },
    {
        "id": "alert",
        "label": "Close approaches and alerts",
        "blurb": ("Upcoming close approaches from ESA NEOCC (how the "
                  "visitor gets by, roughly how big, how bright at the "
                  "closest pass) to catch the week's fast mover, plus the "
                  "AAVSO editorial channel: community alerts and the "
                  "campaigns currently running."),
        "source": "ESA NEOCC + the AAVSO editorial channel (alerts and campaigns)",
        "since": "0.0.2",
    },
    {
        "id": "hads",
        "label": "HADS stars",
        "blurb": ("High-amplitude delta Scuti variables: they pulse so "
                  "fast and so strongly that you can watch them vary in a "
                  "single session; your run folds by phase into the "
                  "classic saw-tooth. Priorities are colour coded: period "
                  "changes, never-observed stars, coverage gaps."),
        "source": "The living HADS catalogue maintained by P. Wils",
        "since": "0.0.3",
    },
    {
        "id": "variable",
        "label": "Variable stars and duties",
        "blurb": ("Your campaign members that are due by cadence, stars "
                  "with an event in progress, stars nearing a predicted "
                  "extremum, and your standing vigils (the T CrB eruption, "
                  "the R CrB fade) checked day by day against the "
                  "observatories and the community."),
        "source": ("AAVSO VSX + AAVSO community photometry + a ZTF check "
                   "for the vigils"),
        "since": "0.0.4",
    },
]


def ids():
    # @return: the kind ids in display order (e.g. ["neo", "sn", ...])
    return [k["id"] for k in KINDS]


def by_id(kind_id):
    # @args: kind_id - e.g. "hads"
    # @return: the kind dict, or None when the id is not in the catalogue
    for k in KINDS:
        if k["id"] == kind_id:
            return k
    return None


def version_key(version):
    # "0.1.2.dev3+g12ab" -> (0, 1, 2) so a working build compares as the
    # release it is heading to (no external PEP 440 parser needed).
    # @args: version - a version string like "0.0.1.dev1" (or "" / None)
    # @return: an (int, int, int) tuple, or None when unrecognised
    if not version:
        return None
    m = re.match(r"^\s*v?(\d+)\.(\d+)\.(\d+)", str(version).split("+")[0])
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def is_new(kind_id, last_version):
    # The wizard badges a kind as "new" when it landed after the user's
    # last running version. A first install (empty last_version) knows
    # nothing yet, so nothing gets flagged there.
    # @args: kind_id - e.g. "hads"; last_version - e.g. "0.0.1.dev1" or ""
    # @return: True if this kind arrived after that version
    kind = by_id(kind_id)
    if kind is None:
        return False
    last = version_key(last_version)
    since = version_key(kind["since"])
    if last is None or since is None:
        return False
    return since > last
