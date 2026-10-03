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

# QT_TRANSLATE_NOOP marks the user-visible strings so lupdate picks them up
# from this file (the wizard and the settings dialog build their labels at
# runtime, so a plain QObject.tr() would stay invisible to the translator).
# The CLI never imports this module, but the fallback keeps it Qt-free anyway.
try:
    from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication
except ImportError:
    QCoreApplication = None

    def QT_TRANSLATE_NOOP(context, string):
        # @args: context - unused; string - the source text
        # @return: the source text unchanged
        return string

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

_K = "NSKinds"

KINDS = [
    {
        "id": "neo",
        "label": QT_TRANSLATE_NOOP("NSKinds", "Near-Earth objects (NEOs)"),
        "blurb": QT_TRANSLATE_NOOP("NSKinds",
            "Asteroids and comets on paths that pass close to Earth: "
            "the confirmed ones with score, priority, apparent rate, "
            "sky uncertainty and flags (NEOCP, impact risk, radar, "
            "NHATS), plus the unconfirmed candidates with preliminary "
            "orbits computed from the MPC astrometry." ),
        "source": QT_TRANSLATE_NOOP("NSKinds",
            "NEOfixer's site-specific list + NEOCP (MPC); positions "
            "from NASA Horizons" ),
        "since": "0.0.1",
    },
    {
        "id": "sn",
        "label": QT_TRANSLATE_NOOP("NSKinds", "Supernovae"),
        "blurb": QT_TRANSLATE_NOOP("NSKinds",
            "The newest discoveries, with the complete follow-up: a "
            "confirmation blink of your FITS against a PanSTARRS "
            "reference, the light curve drawn against the typical "
            "templates of each type, an evolution animation, exports "
            "and cadence reminders to know when to go back." ),
        "source": QT_TRANSLATE_NOOP("NSKinds",
            "Rochester Astronomy discovery list + a PanSTARRS (MAST) "
            "reference for the blink" ),
        "since": "0.0.1",
    },
    {
        "id": "comet",
        "label": QT_TRANSLATE_NOOP("NSKinds", "Comets"),
        "blurb": QT_TRANSLATE_NOOP("NSKinds",
            "Comets visible tonight with their live observed "
            "magnitude, perihelion date and activity flags, so you "
            "know how each one is doing now, not last month." ),
        "source": QT_TRANSLATE_NOOP("NSKinds", "COBS (MPC) live magnitudes + NASA Horizons"),
        "since": "0.0.1",
    },
    {
        "id": "pccp",
        "label": QT_TRANSLATE_NOOP("NSKinds", "Comet candidates (PCCP)"),
        "blurb": QT_TRANSLATE_NOOP("NSKinds",
            "Objects reported as asteroids that might actually be "
            "comets, with their comet score: the MPC's Possible "
            "Comet Confirmation Page. Getting there first matters." ),
        "source": QT_TRANSLATE_NOOP("NSKinds",
            "MPC PCCP (minorplanetcenter.net) + NASA Horizons" ),
        "since": "0.0.1",
    },
    {
        "id": "transit",
        "label": QT_TRANSLATE_NOOP("NSKinds", "Exoplanet transits"),
        "blurb": QT_TRANSLATE_NOOP("NSKinds",
            "Exoplanets crossing their star tonight from your site, "
            "with the transit time, how much the observed timing is "
            "drifting from the prediction (O-C), whether the whole "
            "transit fits in your night, the maximum trail-free "
            "exposure and a pre-filled export for EXOTIC." ),
        "source": QT_TRANSLATE_NOOP("NSKinds",
            "ExoClock (ESA Ariel ephemeris programme) + NASA "
            "Exoplanet Archive; times from NASA Horizons (HJD)" ),
        "since": "0.0.1",
    },
    {
        "id": "alert",
        "label": QT_TRANSLATE_NOOP("NSKinds", "Close approaches and alerts"),
        "blurb": QT_TRANSLATE_NOOP("NSKinds",
            "Upcoming close approaches from ESA NEOCC (how the "
            "visitor gets by, roughly how big, how bright at the "
            "closest pass) to catch the week's fast mover, plus the "
            "AAVSO editorial channel: community alerts and the "
            "campaigns currently running." ),
        "source": QT_TRANSLATE_NOOP("NSKinds",
            "ESA NEOCC + the AAVSO editorial channel "
            "(alerts and campaigns)" ),
        "since": "0.0.2",
    },
    {
        "id": "hads",
        "label": QT_TRANSLATE_NOOP("NSKinds", "HADS stars"),
        "blurb": QT_TRANSLATE_NOOP("NSKinds",
            "High-amplitude delta Scuti variables: they pulse so "
            "fast and so strongly that you can watch them vary in a "
            "single session; your run folds by phase into the "
            "classic saw-tooth. Priorities are colour coded: period "
            "changes, never-observed stars, coverage gaps." ),
        "source": QT_TRANSLATE_NOOP("NSKinds",
            "The living HADS catalogue maintained by P. Wils" ),
        "since": "0.0.3",
    },
    {
        "id": "variable",
        "label": QT_TRANSLATE_NOOP("NSKinds", "Variable stars and duties"),
        "blurb": QT_TRANSLATE_NOOP("NSKinds",
            "Your campaign members that are due by cadence, stars "
            "with an event in progress, stars nearing a predicted "
            "extremum, and your standing vigils (the T CrB eruption, "
            "the R CrB fade) checked day by day against the "
            "observatories and the community." ),
        "source": QT_TRANSLATE_NOOP("NSKinds",
            "AAVSO VSX + AAVSO community photometry + a ZTF check "
            "for the vigils" ),
        "since": "0.0.4",
    },
]


def ids():
    # @return: the kind ids in display order (e.g. ["neo", "sn", ...])
    return [k["id"] for k in KINDS]


# The enriched object type (core/enrich.py "type") -> project kind. Used
# when an object is explored ad-hoc (Tools > Explore) and no planner
# target carries its kind: the enriched panel already knows the class.
_ENRICHED_KIND = {
    "exoplanet": "transit",
    "transient": "sn",
    "hads": "hads",
    "variable": "variable",
    "small_body": "neo",
    "comet": "comet",
    "neo": "neo",
    "pccp": "pccp",
    "sn": "sn",
    "transit": "transit",
}


def project_kind(enriched):
    # @args: enriched - an enrich result dict ({"type": ...}), a planner
    #        target, or a plain kind string
    # @return: the project kind, or None when it cannot be told
    if isinstance(enriched, str):
        return enriched if enriched in _ENRICHED_KIND else None
    t = (enriched or {}).get("type") or (enriched or {}).get("kind")
    return _ENRICHED_KIND.get(t)


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


def tr_text(text):
    # Translates one of the catalogue strings above (label, blurb,
    # source) for display in the wizard or the Settings dialog.
    # @args: text - one of the QT_TRANSLATE_NOOP values in KINDS
    # @return: the text in the current language, or the source when Qt
    #          is not installed
    if QCoreApplication is None:
        return text
    return QCoreApplication.translate(_K, text)


# ---- the one-glance summary of a project's context -------------------
#
# A project row has room for two or three numbers, and WHICH numbers make
# a project recognisable depends on what it is: a supernova is its
# magnitude and its host, a NEO is how fast it moves and how close it
# comes. The keys are the ones the manual object form and the enrichers
# write (gui/widgets/manual_object_panel.py), so nothing here invents a
# field name.
_CTX_MAG = QT_TRANSLATE_NOOP("NSKinds", "mag {value}")
_CTX_RATE = QT_TRANSLATE_NOOP("NSKinds", "{value}″/min")
_CTX_MOID = QT_TRANSLATE_NOOP("NSKinds", "MOID {value} au")
_CTX_H = QT_TRANSLATE_NOOP("NSKinds", "H {value}")
_CTX_PERIOD = QT_TRANSLATE_NOOP("NSKinds", "period {value} d")
_CTX_DEPTH = QT_TRANSLATE_NOOP("NSKinds", "depth {value} mmag")
_CTX_AMP = QT_TRANSLATE_NOOP("NSKinds", "amp {value} mag")
_CTX_PERIHELION = QT_TRANSLATE_NOOP("NSKinds", "perihelion {value}")

# kind id -> the fields worth showing, in order of importance
_CONTEXT_FIELDS = {
    "sn": ("mag", "sn_type", "host"),
    "neo": ("mag", "rate_arcsec_min", "moid"),
    "pccp": ("mag", "rate_arcsec_min", "moid"),
    "comet": ("mag", "perihelion_date"),
    "transit": ("period_d", "depth_mmag"),
    "variable": ("period_d", "amplitude"),
    "hads": ("period_d", "amplitude"),
    "alert": ("mag",),
}


def _ctx_number(value, short=False):
    # @args: value - a float-ish; short - True for periods, which can be
    #        tiny (a HADS star pulsates in 0.13 days)
    # @return: the number as text, without a trailing ".0"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if short and abs(number) < 1.0:
        return ("%.4f" % number).rstrip("0").rstrip(".")
    if short:
        return ("%.2f" % number).rstrip("0").rstrip(".")
    return ("%.1f" % number).rstrip("0").rstrip(".")


def context_line(kind_id, ctx, limit=3):
    # @args: kind_id - a KINDS id; ctx - a project's context dict;
    #        limit - how many numbers to keep (a list row has no room for
    #        more; the object card shows them all)
    # @return: "mag 15.2 · Ia · NGC 4414", or "" when there is nothing to
    #          say. Never raises: a project with a half-written context is
    #          normal, not exceptional.
    if not ctx:
        return ""
    fields = _CONTEXT_FIELDS.get(kind_id)
    if not fields:
        return ""
    parts = []
    for key in fields:
        value = ctx.get(key)
        if value in (None, "", []):
            continue
        if key == "mag":
            parts.append(tr_text(_CTX_MAG).format(value=_ctx_number(value)))
        elif key == "rate_arcsec_min":
            parts.append(tr_text(_CTX_RATE).format(value=_ctx_number(value)))
        elif key == "moid":
            parts.append(tr_text(_CTX_MOID).format(value="%.3f" % float(value)))
        elif key == "h":
            parts.append(tr_text(_CTX_H).format(value=_ctx_number(value)))
        elif key == "period_d":
            parts.append(tr_text(_CTX_PERIOD).format(
                value=_ctx_number(value, short=True)))
        elif key == "depth_mmag":
            parts.append(tr_text(_CTX_DEPTH).format(value=_ctx_number(value)))
        elif key == "amplitude":
            parts.append(tr_text(_CTX_AMP).format(value=_ctx_number(value)))
        elif key == "perihelion_date":
            parts.append(tr_text(_CTX_PERIHELION).format(value=str(value)))
        else:
            # a short free-text field (the SN type, the host galaxy): its
            # own value is the whole message
            parts.append(str(value))
        if len(parts) == limit:
            break
    return " · ".join(parts)
