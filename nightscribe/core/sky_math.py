############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - night sky sampling math (pure, no matplotlib)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Pure night-sky sampling shared by the matplotlib chart layer
(`viz/sky_view.py`) and the PySide6 GUI widget layer (`gui/widgets/
sky_widget.py`).

Like `core/orbit_math`, this module deliberately does NOT import matplotlib
(ADR-029) — it only depends on `core.coords` + `core.ephem_minor`, so it is
import-safe from the QGraphicsView widgets. A single `sample_night()` call is
the one source of the target, Moon and local-horizon altitude series, so the
two renderers can never drift apart (the widget must match the PNG exports).
"""

import datetime

from . import coords, ephem_minor


def _utc(dt):
    # @args: dt - datetime (aware or naive)
    # @return: the aware-UTC equivalent (naive inputs assumed to be UTC).
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def sample_night(ra_deg, dec_deg, lat_deg, lon_deg, date,
                 horizon=None, margin=0.0, step_min=10):
    # Altitude series for one night, at `step_min` resolution, one hour either
    # side of the dark window. `horizon` is the optional `alt_at(az)` callable
    # (ADR-020); when absent the local limit flat at 30°.
    # @args: ra_deg, dec_deg - target; lat_deg, lon_deg - site; date - datetime.date;
    #        horizon - optional alt_at(az) callable; margin - safety margin (deg);
    #        step_min - sampling interval in minutes (default 10, as draw_sky)
    # @return: dict {"start", "end", "rel", "alt", "moon", "horizon", "time"}
    #          or None when there is no astronomical night that night.
    window = coords.tonight_window(lat_deg, lon_deg, date)
    if not window:
        return None
    start, end = window

    def _pos(dt):
        # @return: hours from `start`, keeping across-midnight times positive
        return (_utc(dt) - start).total_seconds() / 3600.0

    rel, alt, azim, moon, hor, times = [], [], [], [], [], []
    t = start - datetime.timedelta(hours=1)
    t_end = end + datetime.timedelta(hours=1)
    while t <= t_end:
        jd = coords.jd_from_datetime(t)
        lst = coords.lst_degrees(jd, lon_deg)
        a, az = coords.altaz(ra_deg, dec_deg, lat_deg, lst)
        m = ephem_minor.moon(jd)
        ma, _mz = coords.altaz(m["ra"], m["dec"], lat_deg, lst)
        rel.append(_pos(t))
        alt.append(a)
        azim.append(az)
        moon.append(ma)
        hor.append(horizon(az) + margin if horizon else 30.0)
        times.append(t)
        t += datetime.timedelta(minutes=step_min)

    return {
        "start": start,
        "end": end,
        "rel": rel,        # hours from dusk (0 = astronomical dusk)
        "alt": alt,        # target altitude, deg
        "azim": azim,      # target azimuth, deg (hover)
        "moon": moon,      # Moon altitude, deg
        "horizon": hor,    # local limit, deg (per azimuth)
        "time": times,     # the instants sampled (aware-UTC)
    }
