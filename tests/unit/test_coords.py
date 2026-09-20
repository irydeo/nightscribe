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


def test_window_above_flat():
    # a meridian object clears a flat 30 deg horizon; a far-south one never
    date = datetime.date(2026, 8, 21)
    up = coords.window_above(100.0, 40.5, 40.55, -3.37,
                             lambda az: 30.0, date)
    assert up is not None
    start, end = up
    assert end >= start
    never = coords.window_above(100.0, -80.0, 40.55, -3.37,
                                lambda az: 30.0, date)
    assert never is None


def test_hours_above_h_matches_scalar():
    # the horizon-aware helper must equal the scalar one for a flat floor
    date = datetime.date(2026, 8, 21)
    flat = lambda az: 30.0
    h1 = coords.hours_above(100.0, 40.5, 40.55, -3.37, 30, date)
    h2 = coords.hours_above_h(100.0, 40.5, 40.55, -3.37, flat, date)
    assert abs(h1 - h2) < 1e-6


def test_angular_separation():
    # opposite points on the equator are 180 deg apart
    sep = coords.angular_separation(0.0, 0.0, 180.0, 0.0)
    assert abs(sep - 180.0) < 1e-6
    # same point -> 0
    assert abs(coords.angular_separation(100.0, 40.0, 100.0, 40.0)) < 1e-6


def test_neptune_arc_2026_09_18():
    # The two outer planets must now be first-class in the almanac.
    # On the night of 18/09/2026 Neptune is up the whole time from the Irydeo
    # site (culminating just past midnight); with the 48 h search it now
    # also hands over the *previous* rise (before dusk) and the *next* set
    # (after dawn) instead of a bare "—".
    arc = coords.planet_rise_set_max_alt("neptune", 40.55, -3.37,
                                         datetime.date(2026, 9, 18))
    assert arc["up_all_night"] is True
    assert arc["down_all_night"] is False
    assert arc["above_at_dusk"] is True
    assert arc["open_earlier"] is False and arc["open_later"] is False
    assert arc["below_band"] is False
    w = coords.tonight_window(40.55, -3.37, datetime.date(2026, 9, 18))
    assert arc["rise_utc"] is not None and arc["set_utc"] is not None
    assert arc["rise_utc"] < w[0] < arc["set_utc"]
    # culmination is ~49 deg, right around 00:35 UTC
    assert 48.0 < arc["max_alt"] < 51.0
    assert arc["max_utc"].hour == 0
    assert 25 <= arc["max_utc"].minute <= 45


def test_uranus_arc_2026_09_18():
    # Uranus rises late in the evening and is still climbing at dawn. With
    # the 48 h rise/set search it now has an honest *set* time too: the
    # following forenoon, ~14 h after rise (its dec is ~+15).
    arc = coords.planet_rise_set_max_alt("uranus", 40.55, -3.37,
                                         datetime.date(2026, 9, 18))
    assert arc["up_all_night"] is False and arc["down_all_night"] is False
    assert arc["rise_utc"] is not None and arc["set_utc"] is not None
    # rises around 21:20 UTC
    assert arc["rise_utc"].hour in (21, 22)
    assert arc["set_utc"] > arc["rise_utc"]
    span = (arc["set_utc"] - arc["rise_utc"]).total_seconds() / 3600
    assert 10.5 < span < 15.5
    # best moment near the dawn edge, high in the sky
    assert 68.0 < arc["max_alt"] < 72.5
    assert arc["max_utc"] > arc["rise_utc"]


def test_mars_arc_2026_09_18():
    # Mars also rises late (after 00:00 UTC); with the 48 h search its *set*
    # now falls the following afternoon, ~13 h after rise.
    arc = coords.planet_rise_set_max_alt("mars", 40.55, -3.37,
                                         datetime.date(2026, 9, 18))
    assert arc["rise_utc"] is not None and arc["set_utc"] is not None
    assert 36.0 < arc["max_alt"] < 42.0
    # rise happens well after dusk (after 00:00 UTC)
    assert arc["rise_utc"].hour in (0, 1)
    assert arc["set_utc"] > arc["rise_utc"]
    span = (arc["set_utc"] - arc["rise_utc"]).total_seconds() / 3600
    assert 10.5 < span < 15.0


def _dusk_lst(date, lat, lon):
    # Local sidereal time at the start of tonight's darkness, for building
    # synthetic RA targets relative to what is up at dusk.
    window = coords.tonight_window(lat, lon, date)
    jd = coords.jd_from_datetime(window[0])
    return coords.lst_degrees(jd, lon), window


def test_night_arc_up_at_dusk_synth():
    # A fixed object on the celestial equator, HA -45 at dusk (south-east,
    # still below its culmination) must be reported *above at dusk*, with a
    # rise found a few hours back (before dusk) and a set the same night,
    # both inside the search band.
    date = datetime.date(2026, 9, 18)
    lst, window = _dusk_lst(date, 40.5, -3.37)
    ra_target = (lst + 45.0) % 360.0
    fixed = lambda jd: (ra_target, 0.0)
    arc = coords.night_arc(fixed, 40.5, -3.37, date)
    assert arc["above_at_dusk"] is True
    assert arc["down_all_night"] is False
    assert arc["rise_utc"] is not None and arc["set_utc"] is not None
    assert arc["rise_utc"] < window[0] < arc["set_utc"]
    assert arc["open_earlier"] is False and arc["open_later"] is False


def test_night_arc_down_at_dusk_rises_later_synth():
    # The mirror case: fixed on the equator, HA +135 at dusk (morning side,
    # below the horizon at dusk). It must rise later that same night —
    # just after dawn — and set the following afternoon; both times found,
    # neither edge open.
    date = datetime.date(2026, 9, 18)
    lst, window = _dusk_lst(date, 40.5, -3.37)
    ra_target = (lst - 135.0) % 360.0
    fixed = lambda jd: (ra_target, 0.0)
    arc = coords.night_arc(fixed, 40.5, -3.37, date)
    assert arc["above_at_dusk"] is False
    assert arc["down_all_night"] is True   # below across tonight's darkness
    assert arc["rise_utc"] is not None and arc["set_utc"] is not None
    assert arc["rise_utc"] > window[0]
    assert arc["set_utc"] > arc["rise_utc"]
    assert arc["open_earlier"] is False and arc["open_later"] is False


def test_night_arc_circumpolar_synth():
    # dec +70 from 40.5 N never sets: min altitude ~20.5 deg, so the arc
    # must flag the open edges on *both* sides and no crossing at all.
    date = datetime.date(2026, 9, 18)
    fixed = lambda jd: (120.0, 70.0)
    arc = coords.night_arc(fixed, 40.5, -3.37, date)
    assert arc["up_all_night"] is True and arc["down_all_night"] is False
    assert arc["above_at_dusk"] is True
    assert arc["rise_utc"] is None and arc["set_utc"] is None
    assert arc["open_earlier"] is True and arc["open_later"] is True
    assert arc["below_band"] is False
    assert arc["max_alt"] > 20.0


def test_night_arc_down_all_night_synth():
    # A synthetic object fixed at dec -60 never clears the horizon from
    # 40.5 N: the generic arc must report the down-all-night case cleanly,
    # and the 48 h band stays below too (below_band).
    fixed = lambda jd: (120.0, -60.0)
    arc = coords.night_arc(fixed, 40.5, -3.37, datetime.date(2026, 9, 18))
    assert arc["down_all_night"] is True
    assert arc["up_all_night"] is False
    assert arc["above_at_dusk"] is False
    assert arc["below_band"] is True
    assert arc["open_earlier"] is False and arc["open_later"] is False
    assert arc["rise_utc"] is None and arc["set_utc"] is None
    # it is below the geometric horizon at its best
    assert arc["max_alt"] < 0.0
