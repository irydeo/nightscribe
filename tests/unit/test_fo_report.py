############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: MPC / Find_Orb orbit report (ADR-021)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import ephemeris, ephem_minor, orbits

# Sar2911, the reference orbit validated against
# docs/Sar2911-sample-ephemerids.txt (Find_Orb two-body solution).
EPOCH = 2461291.37919
ELEMENTS = {
    "a": 1.4624917, "e": 0.2881631, "i": 7.94982, "om": 169.16454,
    "w": 182.66687, "ma": 356.53233, "epoch": EPOCH, "P": 646.0,
    "n": 0.55726783, "q": 1.04105554, "Q": 1.88392780,
    "tp": 2461297.722631,
}

BODY = {
    "des": "Sar2911",
    "phys": {"H": 27.07, "albedo": 0.10},
    "moid": 0.0348,
    "moids": {
        "Mercury": 0.6705, "Venus": 0.3169, "Earth": 0.0348, "Mars": 0.1846,
        "Jupiter": 3.5406, "Saturn": 7.4074, "Uranus": 16.4036,
        "Neptune": 28.3056,
    },
    "n_resids": 20, "arc_days": 21.4 / 24.0, "rms_residual": 0.36,
    "sigmas": {"ma": 1, "a": 1},
    "elements": ELEMENTS,
}


def test_tisserand_sar2911():
    # Ground truth from the sample report: 2.97758.
    t = orbits.tisserand_earth(ELEMENTS["a"], ELEMENTS["e"], ELEMENTS["i"])
    assert abs(t - 2.97758) < 1e-4


def test_state_vector_sar2911():
    # Heliocentric state at the epoch, within arcminute-level tolerance
    # (the two-body engine, not a full N-body integrator).
    px, py, pz, vx, vy, vz = ephem_minor.state_vector_j2000(ELEMENTS, EPOCH)
    assert abs(px - 1.008506846153) < 1e-3
    assert abs(py - -0.246249758226) < 1e-3
    assert abs(pz - -0.096127752779) < 1e-3
    # velocity in mAU/day
    k = 1000.0
    assert abs(vx * k - 4.347021406325) < 0.05
    assert abs(vy * k - 17.954408927073) < 0.05
    assert abs(vz * k - 4.905507244961) < 0.05


def test_encounter_velocity_sar2911():
    # Barbee-style encounter speed, ground truth 5.5974 km/s.
    sv = ephem_minor.state_vector_j2000(ELEMENTS, EPOCH)
    v_earth = ephem_minor.earth_velocity_j2000(EPOCH)
    km_s = orbits.AU_KM / 86400.0
    venc = orbits.encounter_velocity(sv[3:], v_earth) * km_s
    assert abs(venc - 5.5974) < 0.05


def test_pq_vectors_sar2911():
    # P (toward perihelion) and Q (90 deg ahead, in-plane) as three
    # components each; validated against the sample report values.
    (px, py, pz), (qx, qy, qz) = ephem_minor.pq_vectors_j2000(ELEMENTS, EPOCH)
    assert abs(px - 0.98977021) < 1e-4
    assert abs(py - -0.12820475) < 1e-4
    assert abs(pz - -0.06259756) < 1e-4
    assert abs(qx - 0.14028155) < 1e-4
    assert abs(qy - 0.95447801) < 1e-4
    assert abs(qz - 0.26323525) < 1e-4


def test_topocentric_differs_from_geocentric():
    # A topocentric propagation must differ from the geocentric one (the
    # site offset is of order R_Earth/delta for a near-Earth object).
    g = ephem_minor.kepler_ra_dec(ELEMENTS, EPOCH)
    t = ephem_minor.kepler_ra_dec(ELEMENTS, EPOCH, lat_deg=40.55, lon_deg=-3.37,
                                  height_m=631.0)
    assert g is not None and t is not None
    assert abs(g[0] - t[0]) > 1e-6 or abs(g[1] - t[1]) > 1e-6


def test_report_structure(tmp_path):
    out = ephemeris.export_fo_report("Sar2911", tmp_path / "r.txt", data=BODY)
    text = open(out, encoding="utf-8").read()

    # core derived quantities present and correct
    assert "Perihelion 2026 Sep 14.222631" in text
    assert "(JD 2461297.722631)" in text
    assert "Epoch 2026 Sep 7.879190" in text
    assert "Tisserand relative to Earth: 2.97758" in text
    assert "Barbee-style encounter velocity:" in text
    assert "State vector (heliocentric equatorial J2000):" in text

    # all eight MOIDs, in the two Find_Orb lines
    for code in ("Me", "Ve", "Ea", "Ma", "Ju", "Sa", "Ur", "Ne"):
        assert code in text

    # perihelion, P/Q, diameter and sigmas footer
    assert "# Sigmas avail: 2" in text
    assert "$T=2461297.722631" in text


def test_report_mpc_footer(tmp_path):
    out = ephemeris.export_fo_report("Sar2911", tmp_path / "r.txt", data=BODY)
    text = open(out, encoding="utf-8").read()
    assert "$Name=Sar2911" in text
    assert "$Eqnx=2000." in text
    assert "$Peri=182.66687" in text
    assert "$Node=169.16454" in text
    assert "$Incl=7.94982" in text
    assert "$a=1.4624917" in text
    assert "$q=1.04105554" in text
    assert "$H=27.1" in text


def test_export_dispatcher_fo(tmp_path, monkeypatch):
    # export(fmt="fo") routes to the orbit report, ignoring `rows`.
    monkeypatch.setattr(ephemeris, "export_fo_report",
                        lambda **kw: "MARKER")
    assert ephemeris.export(None, tmp_path / "r.txt", fmt="fo",
                            obj_name="Sar2911") == "MARKER"


# --------------------------------------------------------------------------
# MPC MPOrbit element line (universal handover) — ADR-021 addendum
# --------------------------------------------------------------------------

# Golden line: byte-identical to the Find_Orb element line in
# docs/Sar2911-sample-ephemerids.txt (epoch is 2026 Sep 8.0 -> "K2698").
GOLDEN_MPC = (
    "Sar2911 27.07  0.15 K2698 356.53233  182.66687  169.16454    7.94982  "
    "0.2881631  0.55726783   1.4624917    FO 260907    20   1 21.4 hrs  0.36"
    "         Find_Orb   0000 Sar2911                     20260907")

GOLDEN_MPC_BODY = {
    "fullname": "Sar2911", "des": "Sar2911",
    "phys": {"H": 27.07, "G": 0.15},
    "preliminary": True,
    "n_resids": 20, "rms_residual": 0.36, "arc_days": 21.4 / 24.0,
    "last_obs": "2026-09-07",
    "elements": {"a": 1.4624917, "e": 0.2881631, "i": 7.94982,
                 "om": 169.16454, "w": 182.66687, "ma": 356.53233,
                 "epoch": 2461291.5, "n": 0.55726783},
}


def test_mpc_line_golden_sar2911():
    # Byte-for-byte vs the reference Find_Orb element line. The only
    # intentional difference from production is the "Find_Orb" computer tag
    # (nightly exports sign "NightScr"); the goal is layout compatibility.
    line = ephemeris._mpc_elements_line(GOLDEN_MPC_BODY, computer="Find_Orb")
    assert len(line) == 202
    assert line == GOLDEN_MPC


def test_mpc_line_column_layout():
    # The documented MPC column layout, sliced from the golden line.
    line = ephemeris._mpc_elements_line(GOLDEN_MPC_BODY, computer="Find_Orb")
    assert line[0:7] == "Sar2911"
    assert line[8:13] == "27.07"            # H
    assert line[14:19].strip() == "0.15"    # G
    assert line[20:25] == "K2698"           # packed epoch
    assert line[26:35].strip() == "356.53233"    # mean anomaly
    assert line[37:46].strip() == "182.66687"    # perihelion
    assert line[48:57].strip() == "169.16454"    # ascending node
    assert line[59:68].strip() == "7.94982"      # inclination
    assert line[70:79] == "0.2881631"            # eccentricity
    assert line[80:91].strip() == "0.55726783"   # mean motion
    assert line[92:103].strip() == "1.4624917"   # semi-major axis
    assert line[107:116] == "FO 260907"          # reference + last obs
    assert line[117:122].strip() == "20"         # observations
    assert line[123:126].strip() == "1"          # oppositions
    assert line[127:136] == "21.4 hrs "          # arc
    assert line[137:141].strip() == "0.36"       # RMS
    assert line[150:160] == "Find_Orb  "         # computer (left-justified)
    assert line[161:165] == "0000"               # flags
    assert line[166:194].replace(" ", "") == "Sar2911"   # readable name
    assert line[194:202] == "20260907"                 # last obs YYYYMMDD


def test_mpc_packed_epoch():
    from datetime import datetime, timezone
    jd = ephemeris.coords.jd_from_datetime
    assert ephemeris._pack_epoch(jd(datetime(2026, 9, 8, 0, 0,
                                             tzinfo=timezone.utc))) == "K2698"
    # month letter rollover: Oct -> A, Dec -> C; day 10 -> A
    assert ephemeris._pack_epoch(jd(datetime(2026, 10, 3,
                                             tzinfo=timezone.utc))) == "K26A3"
    assert ephemeris._pack_epoch(jd(datetime(2026, 12, 10,
                                             tzinfo=timezone.utc))) == "K26CA"
    # 20th century -> J; 20xx -> K
    assert ephemeris._pack_epoch(jd(datetime(1999, 5, 7,
                                             tzinfo=timezone.utc))) == "J9957"


def test_mpc_packed_provisional():
    assert ephemeris._pack_provisional("2021 EQ3") == "K21E03Q"
    assert ephemeris._pack_provisional("2023 AB12") == "K23A12B"
    # outside the 2000-2099 classic scheme: fall back to the raw name
    assert ephemeris._pack_provisional("1998 SQ13") is None
    assert ephemeris._pack_provisional(None) is None


def test_mpc_desig_numbered():
    # numbered minor planets: zero-padded 5 digits; letter+4 digits above
    assert ephemeris._mpc_desig({"des": "3202"}, "?") == "03202"
    assert ephemeris._mpc_desig({"des": "203289"}, "?") == "K3289"
    # provisional and NEOCP-style codes pass through
    assert ephemeris._mpc_desig({"des": "2021 EQ3"}, "?") == "K21E03Q"
    assert ephemeris._mpc_desig({"des": "Sar2911"}, "?") == "Sar2911"
    assert ephemeris._mpc_desig({}, "") == "       "


def test_mpc_line_derivations_and_gaps():
    # G defaults to 0.15; mean anomaly derives from tp when missing.
    body = {"des": "K21E03Q", "phys": {"H": 25.0}, "preliminary": True,
            "elements": {"a": 1.0, "e": 0.3, "i": 2.0, "om": 3.0, "w": 4.0,
                         "tp": 2461291.5, "epoch": 2461291.5}}
    line = ephemeris._mpc_elements_line(body)
    assert line[14:19].strip() == "0.15"            # G default
    assert line[26:35].strip() == "0.00000"         # M from tp (t==epoch)
    assert line[80:91].strip() == "0.98562628"      # n = 360/(365.25*a^1.5)
    # no last observation: blank arc field, left-justified reference,
    # blank last-obs columns
    assert line[107:116] == "FO       "
    assert line[127:136] == " " * 9
    assert line[194:202] == " " * 8


def test_export_mpc_elements_file(tmp_path):
    out = ephemeris.export_mpc_elements("Sar2911", tmp_path / "e.txt",
                                        data=GOLDEN_MPC_BODY)
    text = open(out, encoding="ascii").read().splitlines()
    # Find_Orb-style header: <jd> 1.000000 1 0,1,1 <site>
    assert len(text) == 2
    assert len(text[1]) == 202
    head = text[0].split()
    assert float(head[0]) > 2460000.0
    assert head[1:4] == ["1.000000", "1", "0,1,1"]
    # without a resolved orbit the export is a no-op
    assert ephemeris.export_mpc_elements("?", tmp_path / "e2.txt") is None


def test_export_dispatcher_mpx(tmp_path, monkeypatch):
    monkeypatch.setattr(ephemeris, "export_mpc_elements",
                        lambda **kw: "MARKER")
    assert ephemeris.export(None, tmp_path / "e.txt", fmt="mpx",
                            obj_name="Sar2911") == "MARKER"
