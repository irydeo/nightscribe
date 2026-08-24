############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Functional tests (online, end-to-end)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# Each test below verifies one NightScribe feature end-to-end against the
# live sources, so regressions are caught quickly (see CONTRIBUTING).
# Run with: .venv/bin/pytest tests/functional -v

import pytest

pytestmark = pytest.mark.network

from nightscribe.config import config
from nightscribe.core import enrich, planner, post, solar, suggest, transits
from nightscribe.core.db import db
from nightscribe.core.sources import (cad, cobs, esa_neo, exoclock,
                                      exoplanet_archive, horizons, neofixer,
                                      noaa, obscodes, pccp, rochester, sbdb,
                                      sdo, silso, simbad)

MPC = config.get("mpc_code", "Z41")


# ---------------- sources ----------------

def test_obscodes_resolves_site():
    info = obscodes.lookup(MPC)
    assert info and abs(info["lat"]) <= 90 and abs(info["lon"]) <= 180
    assert info["name"]


def test_neofixer_targets_for_site():
    tg = neofixer.targets(MPC, 5)
    assert tg and all("score" in t for t in tg)


def test_sbdb_asteroid_and_comet():
    a = sbdb.get("Apophis")
    assert a and a["orbit_class"] == "Aten"
    c = sbdb.get("29P")
    assert c and "Comet" in (c["orbit_class"] or "")


def test_horizons_site_ephemeris():
    rows = horizons.ephemeris("99942", center=MPC)
    assert rows and rows[0]["delta"] > 0


def test_horizons_periodic_comet_cap():
    rows = horizons.ephemeris("29P", center=MPC)
    assert rows, "periodic comets must resolve via the CAP fallback"


def test_cad_close_approach():
    na = cad.next_approach("99942")
    assert na and na["dist_ld"] > 0 and na["date"]


def test_simbad_transient_and_host():
    ident = simbad.query_id("SN2023ixf")
    assert ident and ident["ra"]
    host = simbad.query_around_galaxy("SN2023ixf")
    assert host and host.get("z")


def test_rochester_sne():
    sne = rochester.latest_sne(19.0)
    assert sne and sne[0]["mag"] < 19.0


def test_cobs_comets():
    comets = cobs.active_comets(18.0)
    assert comets and comets[0]["mag"] <= 18.0


def test_pccp_candidates():
    cands = pccp.candidates()
    assert isinstance(cands, list)
    if cands:  # the page may occasionally be empty
        assert cands[0]["desig"]


def test_esa_close_approaches():
    rows = esa_neo.close_approaches(20.0)
    assert rows and rows[0]["dist_ld"] <= 20.0


def test_exoclock_catalogue():
    pl = exoclock.planets()
    assert len(pl) > 100
    assert all("t0" in p and "period" in p for p in pl[:10])


def test_exoplanet_archive():
    p = exoplanet_archive.planet("HD 209458 b")
    assert p and p["pl_radj"] > 0.5


def test_noaa_and_silso():
    assert noaa.solar_indices() is not None
    assert noaa.kp_index() is not None
    assert silso.daily_series(7)


def test_sdo_image(tmp_path):
    img = sdo.latest_image("0193", 1024)
    assert img and img.exists() and img.stat().st_size > 10000


# ---------------- features end-to-end ----------------

def test_tonight_pipeline():
    targets = planner.build_tonight(config)
    assert len(targets) > 10
    top, all_scored = suggest.top_n(targets, config, db, 3)
    assert len(top) == 3
    for t, score, parts, phrase in top:
        assert 0 <= score <= 100
        assert phrase["es"] and phrase["en"]


def test_enrich_and_post_neo():
    e = enrich.enrich("2021EQ3", site=MPC)
    assert e and e["type"] in ("small_body", "comet")
    p = post.render_post(e, config)
    assert "#MPC" + MPC in p["es"]
    assert len(p["tweet"]) <= 280


def test_enrich_comet_outburst_fields():
    e = enrich.enrich("29P", site=MPC)
    assert e and e["type"] == "comet"
    assert e["data"].get("mag_expected") is not None


def test_enrich_transient():
    e = enrich.enrich("SN2023ixf", site=MPC)
    assert e and e["type"] == "transient"
    assert e["data"].get("dist_mly")


def test_solar_now():
    s = solar.solar_now()
    assert s.get("ssn") is not None or s.get("kp") is not None


def test_transits_tonight_real():
    pl = exoclock.planets()
    tt = transits.transits_tonight(pl, config.get("lat"), config.get("lon"))
    assert isinstance(tt, list)
    for t in tt[:5]:
        assert t["egress"] > t["ingress"]


def test_viz_png_exports(tmp_path):
    # every chart must render to a non-empty PNG (Agg, no display)
    import matplotlib
    matplotlib.use("Agg")
    from nightscribe.viz import (families_view, orbit_view, sky_view,
                                 sun_panel, transit_view)
    b = sbdb.get("Apophis")
    f1 = tmp_path / "orbit.png"
    orbit_view.draw_orbit(dict(b["elements"]), obj_name="Apophis",
                          approach=cad.next_approach("99942"), out=str(f1))
    assert f1.exists() and f1.stat().st_size > 20000
    f2 = tmp_path / "sky.png"
    sky_view.draw_sky(346.7, 16.26, config.get("lat"), config.get("lon"),
                      obj_name="test", out=str(f2))
    assert f2.exists() and f2.stat().st_size > 10000
    f3 = tmp_path / "families.png"
    families_view.draw_families("Aten", obj_name="Apophis", a=0.92, out=str(f3))
    assert f3.exists() and f3.stat().st_size > 10000
    f4 = tmp_path / "sun.png"
    sun_panel.draw_sun(sdo.latest_image("0193", 1024), solar.solar_now(),
                       out=str(f4))
    assert f4.exists() and f4.stat().st_size > 20000
    pl = exoclock.planets()
    tt = transits.transits_tonight(pl, config.get("lat"), config.get("lon"))
    if tt:
        f5 = tmp_path / "transit.png"
        transit_view.draw_transit(tt[0], out=str(f5))
        assert f5.exists() and f5.stat().st_size > 5000


def test_cli_runs():
    # the CLI entry point must at least parse and fail politely offline-free
    from nightscribe.__main__ import main
    assert main(["history"]) == 0


# ---------------- supernova blink (ADR-018) ----------------

def test_tns_resolves_fresh_transient():
    # TNS is the authoritative source for very fresh transients (ADR-018)
    from nightscribe.core.sources import tns
    info = tns.resolve("2026zji")
    assert info and info["ra"] == pytest.approx(301.1436, abs=1e-3)
    assert info["dec"] == pytest.approx(62.6441, abs=1e-3)


def test_blink_resolves_via_tns():
    # the blink resolver must reach TNS first for a brand-new transient
    from nightscribe.core import blink
    got = blink.resolve_sn("2026zji")
    assert got["name"] == "SN2026zji"
    assert got["ra"] == pytest.approx(301.1436, abs=1e-3)
    assert got["dec"] == pytest.approx(62.6441, abs=1e-3)


def test_blink_real_mirrored_frame():
    # Regression with the real 2026zji CDK17 frame: its solve is mirrored
    # (det CD > 0) — it must be flipped horizontally to align (ADR-018).
    from nightscribe.core import blink
    from nightscribe.viz import blink_view
    import matplotlib
    matplotlib.use("Agg")
    from pathlib import Path
    fixture = Path(__file__).parents[1] / "fixtures" / "sn2026zji_new_image.fits"
    pair = blink.prepare_pair(fixture, sn_name="2026zji")
    assert pair["flipped"] is True            # mirrored solve was corrected
    assert not pair["wcs"].is_mirrored()
    assert pair["ra"] == pytest.approx(301.1436, abs=1e-3)   # TNS position
    assert pair["dec"] == pytest.approx(62.6441, abs=1e-3)
    sx, sy = pair["sn_xy"]
    h, w = pair["obs"].shape
    assert 0 < sx < w and 0 < sy < h          # SN inside the frame
    assert pair["ref"].shape == pair["obs"].shape
    # the aligned pair must render (survey geometry matches by construction)
    ref8 = blink_view.to_uint8(blink_view.apply_stretch(
        pair["ref"], *blink_view.auto_limits(pair["ref"])))
    obs8 = blink_view.to_uint8(blink_view.apply_stretch(
        pair["obs"], *blink_view.auto_limits(pair["obs"])))
    assert ref8.shape == obs8.shape


@pytest.mark.skipif(not config.get("astrometry_key"),
                    reason="no astrometry.net API key configured")
def test_astrometry_solve_live(tmp_path):
    # blind-solve of a synthetic star field (only with a configured key)
    from nightscribe.core.sources import astrometry
    img = _solved_fits(tmp_path / "raw.fits", 210.9107, 54.3117,
                       width=200, height=150)
    cards = astrometry.solve(img)
    assert cards and "CRVAL1" in cards and "CD1_1" in cards



def _solved_fits(path, ra, dec, width=600, height=400, pixscale=1.5,
                 rot_deg=10.0):
    # Writes a synthetic plate-solved FITS (noise + a bright "SN" at centre).
    import math
    import numpy as np
    rng = np.random.default_rng(3)
    data = rng.normal(900, 15, (height, width))
    data[height // 2, width // 2] += 9000
    scale = pixscale / 3600.0
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    cards = [
        "SIMPLE  =                    T", "BITPIX  =                  -32",
        "NAXIS   =                    2", f"NAXIS1  ={width:21d}",
        f"NAXIS2  ={height:21d}", "CTYPE1  = 'RA---TAN'",
        "CTYPE2  = 'DEC--TAN'", f"CRVAL1  ={ra:21.7f}", f"CRVAL2  ={dec:21.7f}",
        f"CRPIX1  ={width / 2:21.1f}", f"CRPIX2  ={height / 2:21.1f}",
        f"CD1_1   ={-scale * c:21.10f}", f"CD1_2   ={-scale * s:21.10f}",
        f"CD2_1   ={-scale * s:21.10f}", f"CD2_2   ={scale * c:21.10f}",
    ]
    blob = "".join(c.ljust(80) for c in cards + ["END"]).encode("ascii")
    blob += b" " * ((-len(blob)) % 2880)
    payload = data.astype(">f4").tobytes()
    payload += b"\0" * ((-len(payload)) % 2880)
    path.write_bytes(blob + payload)
    return path


def test_ps1g_matched_cutout_live():
    # CDS hips2fits must serve a PanSTARRS DR1 g cutout matching our geometry
    from nightscribe.core import fits_io, wcs as wcs_mod
    from nightscribe.core.sources import cutouts
    path, label = cutouts.ps1g_matched(187.705, 12.391, 128, 96, 1.8, 25.0)
    assert path and label == "PanSTARRS DR1 g"
    header, data = fits_io.read_fits(path)
    assert data.shape == (96, 128)
    w = wcs_mod.Wcs.from_header(header)
    assert w.pixel_scale() == pytest.approx(1.8, rel=0.01)
    assert w.rotation() == pytest.approx(25.0, abs=0.2)


def test_blink_end_to_end(tmp_path):
    # Full pipeline: real SIMBAD resolution + real PS1 g survey + exports.
    import matplotlib
    matplotlib.use("Agg")
    from nightscribe.core import blink
    from nightscribe.viz import blink_view
    # SN2023ixf: RA 14 03 38.6, Dec +54 18 42 -> centre the frame there
    img = _solved_fits(tmp_path / "sn2023ixf.fits", 210.9107, 54.3117)
    pair = blink.prepare_pair(img, sn_name="2023ixf")
    assert pair["name"] == "SN2023ixf"
    assert pair["ref_label"] == "PanSTARRS DR1 g"
    assert pair["ref"].shape == pair["obs"].shape == (400, 600)
    sx, sy = pair["sn_xy"]
    assert abs(sx - 300) < 20 and abs(sy - 200) < 20
    ref8 = blink_view.to_uint8(blink_view.apply_stretch(
        pair["ref"], *blink_view.auto_limits(pair["ref"])))
    obs8 = blink_view.to_uint8(blink_view.apply_stretch(
        pair["obs"], *blink_view.auto_limits(pair["obs"])))
    gif = tmp_path / "sn_blink.gif"
    png = tmp_path / "sn_pair.png"
    blink_view.make_blink_gif(ref8, obs8, pair["sn_xy"], gif, effect="fade",
                              name=pair["name"], ref_label=pair["ref_label"])
    blink_view.draw_pair(ref8, obs8, pair["sn_xy"], name=pair["name"],
                         ref_label=pair["ref_label"], out=str(png))
    assert gif.exists() and gif.stat().st_size > 10000
    assert png.exists() and png.stat().st_size > 10000


def test_blink_tab_offscreen(tmp_path):
    # The Blink tab must drive the whole flow without crashing the GUI.
    import os
    import time
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui.main_window import MainWindow
    w = MainWindow()
    img = _solved_fits(tmp_path / "u.fits", 187.705, 12.391,
                       width=320, height=240)
    w.blink.edt_fits.setText(str(img))
    w.blink.chk_manual.setChecked(True)
    # comma decimal separator must work too (locale-proof fields)
    w.blink.edt_ra.setText("187,705")
    w.blink.edt_dec.setText("12.391")
    w.on_blink_prepare()
    t0 = time.time()
    while w._blink_pair is None and time.time() - t0 < 60:
        QCoreApplication.processEvents()
        time.sleep(0.05)
    assert w._blink_pair is not None, "blink worker never delivered a pair"
    pix = w.blink.lbl_blink.pixmap()
    assert pix is not None and not pix.isNull()
    # exercise the interactive controls: nudge, gamma, fade, marker toggle
    w._blink_nudge_move(0.5, -0.5)
    assert w._blink_nudge == [0.5, -0.5]
    w.blink.sld_gamma.setValue(60)
    w.blink.chk_blink_live.setChecked(False)
    w.blink.sld_fade.setValue(30)
    w.blink.chk_marker.setChecked(False)
    w._blink_render()
    assert w._blink_ref8 is not None and w._blink_obs8 is not None
    w.close()


def test_gui_boots_offscreen():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QTabWidget
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui.main_window import MainWindow
    w = MainWindow()
    tabs = w.centralWidget().findChild(QTabWidget, "tabs")
    assert tabs.count() == 4  # UX v3: Tonight · Projects · Solar · History (ADR-019)
    assert tabs.tabText(0) == "Tonight"
    assert tabs.tabText(1) == "Projects"
    # suggestion grid container exists
    assert w.tonight.scroll_suggestions is not None
    # table starts collapsed (progressive disclosure)
    assert not w.tonight.grp_list.isVisible()
    # projects step tabs exist (5 clickable tabs)
    assert w.projects.tabs_steps.count() == 5
    # menu bar with ad-hoc tools
    menu_texts = [a.text() for a in w.menuBar().actions()]
    assert "File" in menu_texts and "Tools" in menu_texts
    # tables must be sortable
    assert w.tonight.tbl_targets.isSortingEnabled()
    assert w.history.tbl_history.isSortingEnabled()
    w.close()
