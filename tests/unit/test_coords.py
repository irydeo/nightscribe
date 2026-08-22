############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: coords (pure math)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime

from nightscribe.core import coords


def test_jd_roundtrip():
    # jd -> datetime -> jd must come back to the same instant
    dt = datetime.datetime(2026, 8, 21, 22, 15, tzinfo=datetime.timezone.utc)
    jd = coords.jd_from_datetime(dt)
    back = coords.datetime_from_jd(jd)
    assert abs((back - dt).total_seconds()) < 60


def test_jd_known_epoch():
    # 2000-01-01 12:00 UTC is JD 2451545.0 by definition
    dt = datetime.datetime(2000, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
    assert abs(coords.jd_from_datetime(dt) - 2451545.0) < 1e-6


def test_altaz_zenith():
    # an object with RA = LST and dec = lat sits at the zenith
    alt, az = coords.altaz(ra_deg=100.0, dec_deg=40.5, lat_deg=40.5,
                           lst_deg=100.0)
    assert abs(alt - 90.0) < 0.01


def test_altaz_below_horizon():
    # a far-south object on the meridian is below the horizon from Madrid
    alt, az = coords.altaz(ra_deg=100.0, dec_deg=-80.0, lat_deg=40.5,
                           lst_deg=100.0)
    assert alt < 0


def test_sexagesimal_helpers():
    assert abs(coords.ra_hms_to_deg("10:00:00") - 150.0) < 1e-6
    assert abs(coords.dec_dms_to_deg("-30:00:00") + 30.0) < 1e-6
    assert abs(coords.dec_dms_to_deg("+30:30:00") - 30.5) < 1e-6


def test_tonight_window_z41():
    # Madrid in August: darkness must exist and last several hours
    w = coords.tonight_window(40.55, -3.37, datetime.date(2026, 8, 21))
    assert w is not None
    start, end = w
    assert (end - start).total_seconds() > 5 * 3600
    assert start.hour in (19, 20, 21, 22)


def test_current_altaz():
    # an object at RA=LST, dec=lat sits at the zenith *right now*
    import datetime as dt
    when = dt.datetime(2026, 8, 21, 22, 0, tzinfo=dt.timezone.utc)
    jd = coords.jd_from_datetime(when)
    lst = coords.lst_degrees(jd, -3.37)
    alt, az = coords.current_altaz(lst, 40.55, 40.55, -3.37, when)
    assert alt > 89.9


def test_hours_above_never_up():
    # a circumpolar-south object is never up from Madrid
    h = coords.hours_above(ra_deg=0, dec_deg=-80, lat_deg=40.5, lon_deg=-3.37,
                           min_alt=30, date=datetime.date(2026, 8, 21))
    assert h == 0.0
