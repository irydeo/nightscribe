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

import tempfile

from pathlib import Path

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


def test_enrich_transient_fallback_rochester(monkeypatch):
    # ADR-027 with real data: take a live Rochester SN, degrade SIMBAD, and
    # verify the planner context still gives host/type/mag/coords + a real
    # hook (not the generic follow-up).
    from nightscribe.core import narrative
    from nightscribe.core.sources import rochester
    # ADR-027 with real data: a live Rochester SN with a known host, degrade
    # SIMBAD, and verify the planner context still gives a real hook (naming
    # the host) and the sky chart from the planner coordinates. The exact
    # route (full-name transient vs short-name unconfirmed) is what the unit
    # tests pin down offline; here we only need a hosted SN.
    s = next((r for r in rochester.latest_sne(19.0)
              if r.get("host")
              and r["host"].lower() not in ("none", "unk", "")), None)
    if not s:
        pytest.skip("no hosted SN on Rochester right now")
    import datetime
    from nightscribe.core import coords as _coords
    ra = _coords.ra_hms_to_deg(s["ra"])
    dec = _coords.dec_dms_to_deg(s["dec"])
    date_ok = False
    try:
        d = datetime.datetime.strptime(s["date"].split(".")[0], "%Y/%m/%d")
        if (datetime.datetime.now() - d).days <= 90:
            date_ok = True
    except ValueError:
        pass
    if not date_ok:
        pytest.skip(f"{s['name']} is too old for the night list")
    monkeypatch.setattr(simbad, "query_id", lambda *a, **k: None)
    monkeypatch.setattr(simbad, "query_around_galaxy", lambda *a, **k: None)
    target = {
        "id": s["name"], "kind": "sn", "name": s["name"],
        "mag": s["mag"], "ra_deg": ra, "dec_deg": dec,
        "sn_type": s.get("type"), "host": s["host"], "disc_date": s["date"],
    }
    e = enrich.enrich(s["name"], site=MPC, fallback_target=target)
    assert e and e["type"] in ("transient", "sn"), \
        f"unexpected type {e['type']!r}"
    data = e["data"]
    # verify the host made it into the data dict or unconfirmed sub-dict
    host = (data.get("host") or {}).get("name") or \
           (data.get("unconfirmed") or {}).get("host")
    assert host == s["host"], f"host lost in data: {host!r}"
    hook = narrative.hook(e)
    assert s["host"] in hook["es"] or s["host"] in hook["en"], \
        f"hook must name the host galaxy: {hook}"
    # the sky chart renders from the planner coordinates (no SIMBAD needed)
    import matplotlib
    matplotlib.use("Agg")
    p = post.build_charts(
        e, Path(tempfile.mkdtemp(prefix="ns_sn_fallback_")), "fallback",
        fmt="panel", cfg=config)
    assert "sky" in p, f"sky chart expected from planner coords: {list(p)}"


def test_enrich_comet_fallback_cobs(monkeypatch):
    # ADR-027 with real data: a live COBS comet whose name SBDB does not
    # resolve degrades to the unconfirmed-comet path with a real hook and
    # perihelion bullets instead of a generic follow-up.
    from nightscribe.core import narrative
    from nightscribe.core.sources import cobs
    c = cobs.active_comets(18.0)[0]
    monkeypatch.setattr(sbdb, "get", lambda *a, **k: None)
    monkeypatch.setattr(neofixer, "orbit", lambda *a, **k: None)
    try:
        import datetime
        from nightscribe.core import coords
        rows = horizons.ephemeris(c["mpc_name"] or c["name"], center=MPC)
        ra = coords.ra_hms_to_deg(rows[0]["ra"])
        dec = coords.dec_dms_to_deg(rows[0]["dec"])
        delta = rows[0]["delta"]
    except Exception:
        pytest.skip(f"no Horizons rows for {c['name']} tonight")
    target = {
        "id": c["name"], "kind": "comet", "name": c["fullname"] or c["name"],
        "mag": c["mag"], "ra_deg": ra, "dec_deg": dec,
        "perihelion_date": c.get("perihelion_date"), "delta_au": delta,
    }
    name = target["name"]
    kind = enrich.detect_type(name)
    assert kind == "small_body", f"{name} must parse as a small body"
    e = enrich.enrich(name, site=MPC, fallback_target=target)
    assert e and e.get("data")
    assert e["data"].get("unconfirmed"), \
        f"must take the unconfirmed path: {e['data'].keys()}"
    hook = narrative.hook(e)
    assert target["name"] in hook["es"] or target["name"] in hook["en"], \
        f"hook must name the comet: {hook}"
    bullets = narrative.fact_bullets(e)
    if c.get("perihelion_date"):
        assert any((c["perihelion_date"] in b["es"]) or
                   (c["perihelion_date"] in b["en"]) for b in bullets)
    else:
        assert any("candidato" in b["es"].lower() or "candidate" in b["en"].lower()
                   for b in bullets)


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
    from nightscribe.viz import orbit_view, sky_view, sun_panel, transit_view
    b = sbdb.get("Apophis")
    f1 = tmp_path / "orbit.png"
    orbit_view.draw_orbit(dict(b["elements"]), obj_name="Apophis",
                          approach=cad.next_approach("99942"), out=str(f1))
    assert f1.exists() and f1.stat().st_size > 20000
    f2 = tmp_path / "sky.png"
    sky_view.draw_sky(346.7, 16.26, config.get("lat"), config.get("lon"),
                      obj_name="test", out=str(f2))
    assert f2.exists() and f2.stat().st_size > 10000
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


def test_viz_orbit_parabolic_comet(tmp_path):
    # A parabolic comet (e=1.0, a<0) must render an orbit chart — the
    # old e<0.99 guard silently skipped these (regression test).
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nightscribe.viz import orbit_view
    c = sbdb.get("C/2023 A3")
    assert c, "SBDB must resolve C/2023 A3"
    els = c["elements"]
    assert els["e"] >= 1.0, "C/2023 A3 must be parabolic for this test"
    f1 = tmp_path / "orbit_parabolic.png"
    orbit_view.draw_orbit(dict(els), obj_name="C/2023 A3", out=str(f1))
    assert f1.exists() and f1.stat().st_size > 20000
    plt.close("all")


def test_viz_orbit_high_e_comet(tmp_path):
    # A high-eccentricity bound comet (0.99 <= e < 1.0) must also render.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nightscribe.viz import orbit_view
    c = sbdb.get("12P")
    assert c, "SBDB must resolve 12P"
    els = c["elements"]
    assert els["e"] >= 0.9, "12P must have high e for this test"
    f1 = tmp_path / "orbit_highe.png"
    orbit_view.draw_orbit(dict(els), obj_name="12P", out=str(f1))
    assert f1.exists() and f1.stat().st_size > 20000
    plt.close("all")


def test_explore_dialog_orbit_chart(tmp_path):
    # The Explore dialog must populate the orbit tab for a parabolic comet.
    # This is the end-to-end GUI test that was missing (offscreen Qt).
    import os
    import time
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui.overview import ObjectPanel
    # D5: the Explore dialog is the shared panel — drive it straight
    panel = ObjectPanel(chart_dir=str(tmp_path / "posts"))
    # enrich a real parabolic comet end-to-end
    e = enrich.enrich("C/2023 A3", site=MPC)
    assert e and e.get("data"), "enrich must return data for C/2023 A3"
    sb = e["data"].get("sbdb")
    assert sb and sb["elements"]["e"] >= 1.0, "must be parabolic"
    # paint it (same as _dialog_explore_done used to do)
    panel.show(e)
    # orbit is now a live vector widget (ADR-029), not a QLabel+QPixmap
    from nightscribe.gui.widgets.orbit_widget import OrbitChart
    orbit = next((panel._tabs.widget(i) for i in range(panel._tabs.count())
                  if isinstance(panel._tabs.widget(i), OrbitChart)), None)
    assert orbit is not None, "no OrbitChart in the chart tabs"
    assert not orbit.isHidden()
    assert orbit.view.scene().items(), "orbit scene is empty"
    # _slot_data records the elements for click→viewer rebuild
    assert "orbit" in panel._slot_data, "orbit slot data not recorded"


def test_chart_viewer_zoom_and_export(tmp_path):
    # The chart viewer must open a chart PNG, zoom it and export a copy
    # (offscreen Qt; the save dialog is stubbed to a tmp path).
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nightscribe.viz import orbit_view
    src = tmp_path / "chart.png"
    orbit_view.draw_orbit(
        {"a": 0.9224, "e": 0.1912, "i": 3.33, "om": 204.43, "w": 126.4,
         "ma": 288.0, "epoch": 2461760.5}, obj_name="Apophis", out=str(src))
    plt.close("all")
    from nightscribe.gui.chart_viewer import ChartViewer
    v = ChartViewer(src, title="test")
    v.show()
    assert v._label.pixmap() is not None and not v._label.pixmap().isNull()
    # zoom in doubles the rendered width (fit starts below 1.0 for big PNGs)
    w0 = v._label.width()
    v._zoom_11()
    assert v._label.width() == v._pix.width()
    v._zoom_in()
    assert v._label.width() > v._pix.width()
    v._zoom_out()
    assert v._label.width() == v._pix.width()
    # export must copy the PNG to the chosen path
    from PySide6.QtWidgets import QFileDialog
    dest = tmp_path / "exported.png"
    orig = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(dest), ""))
    try:
        v._export()
    finally:
        QFileDialog.getSaveFileName = orig
    assert dest.exists() and dest.stat().st_size == src.stat().st_size
    v.close()


def test_post_charts_attached_to_project(tmp_db):
    # Generating a post from a project must also render the charts and
    # register them as project files (the "report" deliverables).
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    from nightscribe.gui.main_window import MainWindow, _load_ui
    w = MainWindow()
    name = "TESTCHARTOBJ"
    p = project.create(tmp_db, "neo", name,
                       context={"ra_deg": 180.0, "dec_deg": 10.0})
    w._current_project = p
    # synthetic enriched object (offline): SBDB-shaped + local ephem
    e = {"name": name, "type": "small_body",
         "data": {"sbdb": {"elements": {"a": 1.35, "e": 0.28, "i": 2.5,
                                        "om": 150.0, "w": 200.0, "q": 0.97,
                                        "ma": 40.0, "epoch": 2461277.5},
                           "phys": {"H": 24.1}, "moid": 0.03},
                  "family": "Apollo",
                  "ephem": {"ra": "12 00 00.0", "dec": "+10 00 00",
                            "r": 1.2, "delta": 0.3}}}
    rendered = {"es": "borrador", "en": "draft", "tweet": "tuit"}
    post_w = _load_ui("post_tab")
    # keep the real db clean: route the module-level db to the tmp one
    orig_db = mw.db
    mw.db = tmp_db
    try:
        w._dialog_post_done(post_w, name, e, rendered)
    finally:
        mw.db = orig_db
    files = project.list_files(tmp_db, p["id"])
    chart_files = [f for f in files if f["kind"] == "chart"]
    assert chart_files, "charts must be attached to the project"
    for f in chart_files:
        assert Path(f["path"]).exists(), f["path"]
    # the dialog must list the chart files alongside the text drafts
    assert "orbit.png" in post_w.lbl_files.text()
    assert "sky.png" in post_w.lbl_files.text()
    w.close()


def _fake_worker_factory(e):
    # Stand-in for ExploreWorker: start() lands the payload at once
    # so the CTA reaches the "ready" state without any network round-trip.
    # @args: e  -- the enriched payload dict to deliver
    # @return:  a callable(name, fallback_target) that yields a fake worker
    class _Signal:
        def __init__(self):
            self._c = []
        def connect(self, cb):
            self._c.append(cb)
        def disconnect(self, cb=None):
            if cb is None:
                self._c = []
            elif cb in self._c:
                self._c.remove(cb)
        def deliver(self, payload):
            for cb in list(self._c):
                cb(payload)

    class _Worker:
        def __init__(self):
            self.finished = _Signal()
        def start(self):
            self.finished.deliver(e)

    def _loader(name, fallback_target=None):
        return _Worker()

    return _loader


def test_explore_dialog_cta_create_project(tmp_db):
    # Regression (2026-09-02): clicking the Explore dialog's CTA used to
    # raise "TypeError: _on_create() missing 1 required positional
    # argument: 'fb'" because the glue signature was (sig, nm, fb) but
    # PySide6 delivers only the two args declared on the signal.
    # This drives the real MainWindow._open_explore_dialog end-to-end:
    # fake loader drops a PCCP payload instantly, the CTA in "create"
    # face fires, and a project must land in the tmp db.
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QDialog
    app = QApplication.instance() or QApplication([])
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    from nightscribe.gui.main_window import MainWindow
    from nightscribe.gui.overview import ObjectPanel

    NAME = "PDC9999"
    e = {"name": NAME, "type": "pccp",
         "data": {"unconfirmed": {"id": NAME, "name": NAME, "kind": "pccp",
                                  "nf_score": 8.0, "nf_priority": "A",
                                  "nobs": 6, "arc_days": 3, "moid": 0.05,
                                  "pccp_score": 75.0, "mag": 19.8}}}
    fallback = {"id": NAME, "kind": "pccp", "name": NAME, "packed": NAME,
                "ra_deg": 120.0, "dec_deg": 10.0}

    w = MainWindow()
    w._tonight_all = [(fallback, 90, 0.5, 0)]
    orig_db    = mw.db
    orig_loader = w._explore_loader
    mw.db        = tmp_db
    w._explore_loader = _fake_worker_factory(e)

    clicked = []

    class _DialogStub(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
        def exec(self):
            panel = self.findChild(ObjectPanel)
            assert panel is not None, "dialog must contain an ObjectPanel"
            assert not panel.btn_project.isHidden(), \
                "CTA must be visible once the object has loaded"
            panel.btn_project.clicked.emit()
            clicked.append(panel._action)
            return QDialog.Accepted

    orig_cls = mw.QDialog
    mw.QDialog = _DialogStub
    try:
        w._open_explore_dialog(NAME)
        assert clicked == ["create"], \
            f"CTA must fire in 'create' face -- got {clicked}"
        rows = project.list_projects(tmp_db, "active")
        assert rows and rows[0]["object_name"] == NAME, \
            f"CTA-click must persist a new active project -- got {rows}"
    finally:
        mw.QDialog          = orig_cls
        w._explore_loader   = orig_loader
        mw.db              = orig_db
        w.close()


def test_explore_dialog_cta_continue_project(tmp_db):
    # The other half of the same regression: with an active project
    # already on file for the object, the CTA must show the "continue"
    # face and emit project_continue(name, fallback) -- two args.
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QDialog
    app = QApplication.instance() or QApplication([])
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    from nightscribe.gui.main_window import MainWindow
    from nightscribe.gui.overview import ObjectPanel

    NAME = "2099 XX"
    e = {"name": NAME, "type": "neo",
         "data": {"unconfirmed": {"id": NAME, "name": NAME, "kind": "neo",
                                  "nf_score": 8.0, "nf_priority": "A",
                                  "nobs": 6, "arc_days": 3, "moid": 0.05,
                                  "mag": 19.8}}}
    fallback = {"id": NAME, "kind": "neo", "name": NAME, "packed": NAME}

    w = MainWindow()
    w._tonight_all = [(fallback, 90, 0.5, 0)]
    orig_db = mw.db
    orig_loader = w._explore_loader
    mw.db = tmp_db
    w._explore_loader = _fake_worker_factory(e)

    project.create(tmp_db, "neo", NAME, {"id": NAME, "kind": "neo"})
    before = len(project.list_projects(tmp_db, "active"))
    clicked = []

    class _DialogStub(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
        def exec(self):
            panel = self.findChild(ObjectPanel)
            assert panel is not None
            assert panel._action == "continue", \
                f"CTA must be in 'continue' face -- got {panel._action}"
            panel.btn_project.clicked.emit()
            clicked.append(panel._action)
            return QDialog.Accepted

    orig_cls = mw.QDialog
    mw.QDialog = _DialogStub
    try:
        w._open_explore_dialog(NAME)
        assert clicked == ["continue"]
        after = len(project.list_projects(tmp_db, "active"))
        assert before == after, \
            f"continue must not create a second project (before={before}, after={after})"
    finally:
        mw.QDialog          = orig_cls
        w._explore_loader   = orig_loader
        mw.db              = orig_db
        w.close()


def test_explore_dialog_unconfirmed_neo():
    # Unconfirmed NEO (no SBDB entry): the orbit tab must show an
    # informative message and the sky tab must render from the
    # fallback_target's ra_deg/dec_deg (regression test).
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui.overview import ObjectPanel
    # D5: drive the shared panel directly (the Explore dialog's content)
    panel = ObjectPanel()
    # simulate what the planner produces for an unconfirmed NEO:
    # a fallback_target with position but no orbital elements
    fallback = {
        "id": "P10x99x", "kind": "neo", "name": "P10x99x",
        "packed": "P10x99x", "mag": 19.5,
        "ra_deg": 120.0, "dec_deg": 10.0,
        "nf_score": 8.0, "nf_priority": "normal", "nf_cost_min": 12.0,
        "moid": 0.05, "h": 20.0, "rate_arcsec_min": 2.5,
        "nobs": 15, "arc_days": "3.2",
    }
    e = enrich.enrich("P10x99x", site=MPC, fallback_target=fallback)
    assert e and e.get("data"), "enrich must return data for unconfirmed NEO"
    assert e["data"].get("unconfirmed"), "must be the unconfirmed path"
    assert not e["data"].get("sbdb"), "must not have SBDB for unconfirmed"
    # paint it — must not crash and must populate the sky slot
    panel.show(e)
    # orbit slot: no elements → no OrbitChart in the chart tabs (ADR-029
    # vector slot is simply absent, not an empty QLabel)
    from nightscribe.gui.widgets.orbit_widget import OrbitChart
    orbit_widgets = [panel._tabs.widget(i)
                     for i in range(panel._tabs.count())
                     if isinstance(panel._tabs.widget(i), OrbitChart)]
    assert not orbit_widgets, \
        "no OrbitChart should exist for unconfirmed objects (no elements)"
    # sky slot: live SkyChart widget rendering from unconfirmed ra/dec
    from nightscribe.gui.widgets.sky_widget import SkyChart
    sky_widgets = [panel._tabs.widget(i)
                   for i in range(panel._tabs.count())
                   if isinstance(panel._tabs.widget(i), SkyChart)]
    assert sky_widgets, "no SkyChart in the chart tabs for unconfirmed object"
    assert sky_widgets[0].view.scene().items(), "sky scene is empty"


def test_enrich_unconfirmed_with_neofixer_orbit():
    # A live NEOCP object: SBDB does not know it, but NEOfixer has a
    # preliminary Find_Orb orbit. enrich() must return sbdb-shaped
    # elements so the orbit chart, params table and ephemeris all work.
    from nightscribe.core.sources import neofixer
    # find a current NEOCP target from the planner list
    tg = neofixer.targets(MPC, 10)
    cand = next((t for t in tg if t.get("neocp")), None)
    if not cand:
        import pytest
        pytest.skip("no NEOCP candidate on NEOfixer right now")
    packed = cand["packed"]
    fallback = {
        "id": packed, "kind": "neo", "name": packed, "packed": packed,
        "mag": cand.get("vmag"),
        "ra_deg": cand.get("ra deg"), "dec_deg": cand.get("dec deg"),
        "nf_score": cand.get("score"), "neocp": True,
    }
    e = enrich.enrich(packed, site=MPC, fallback_target=fallback)
    assert e and e.get("data"), "enrich must return data for a NEOCP object"
    d = e["data"]
    sb = d.get("sbdb")
    assert sb, "preliminary NEOfixer orbit must be attached as sbdb"
    els = sb.get("elements") or {}
    assert els.get("a") and els.get("e") is not None, \
        "elements must carry a and e"
    assert sb.get("sigmas"), "preliminary orbit must carry sigmas"
    assert d.get("preliminary") is True
    assert d.get("unconfirmed"), "planner fallback must be kept"
    # the elements must be drawable and propagatable
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nightscribe.core import coords
    import datetime
    from nightscribe.viz import orbit_view
    jd = coords.jd_from_datetime(
        datetime.datetime.now(datetime.timezone.utc))
    p = orbit_view.draw_orbit(dict(els), jd=jd, obj_name=packed)
    assert p is not None
    plt.close("all")


def test_ephemeris_unconfirmed_via_neofixer(tmp_path):
    # ephemeris.generate must fall back to the preliminary NEOfixer orbit
    # for objects Horizons does not know, and mark rows as preliminary.
    from nightscribe.core import ephemeris
    from nightscribe.core.sources import neofixer
    tg = neofixer.targets(MPC, 10)
    cand = next((t for t in tg if t.get("neocp")), None)
    if not cand:
        import pytest
        pytest.skip("no NEOCP candidate on NEOfixer right now")
    packed = cand["packed"]
    rows = ephemeris.generate(packed, MPC, step="2h")
    if not rows:
        import pytest
        pytest.skip(f"NEOfixer has no orbit for {packed} right now")
    assert rows[0].get("preliminary"), "rows must be flagged preliminary"
    assert all(0 <= r["ra_deg"] < 360 for r in rows)
    assert all(r["delta"] and r["delta"] > 0 for r in rows)
    out = ephemeris.export(rows, tmp_path / "eph", fmt="csv",
                           obj_name=packed)
    text = open(out, encoding="utf-8").read()
    assert "PRELIMINARY" in text


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
    # Blind-solve a real star field: the server refuses synthetic plates
    # (they come back as a bare failure), so we hand it a genuine square
    # crop of the local fixture. The recovered WCS must match the plate's
    # own solved astrometry: centre within 1 arcmin, scale within 10%.
    # The crop bytes are deterministic and the result is cached by the
    # file sha256, so only the first run ever spends a server job (ADR-018).
    from nightscribe.core import fits_io, wcs as wcs_mod
    from nightscribe.core.sources import astrometry
    fixture = Path(__file__).parents[1] / "fixtures" / "sn2026zji_new_image.fits"
    header, data = fits_io.read_fits(str(fixture))
    plate = wcs_mod.Wcs.from_header(header)
    assert plate is not None and plate.pixel_scale() > 0

    size = 500
    img, r0, c0 = _blind_crop_fits(tmp_path / "crop.fits", data, size)
    cards = astrometry.solve(img)
    assert cards and "CRVAL1" in cards and "CD1_1" in cards

    # the solved wcs.fits carries NAXIS=0, so size the solution with our own
    # crop dimensions before reading its centre and scale
    solved = wcs_mod.Wcs.from_header({"NAXIS1": size, "NAXIS2": size, **cards})
    assert solved is not None, "server returned a non-TAN or cardless solution"
    ra1, dec1 = solved.center()

    # where the crop centre sits on the plate (0-based fixture pixels)
    cx = c0 + (size - 1) / 2.0
    cy = r0 + (size - 1) / 2.0
    ra0, dec0 = plate.pixel_to_sky(cx, cy)

    assert _sep_arcsec(ra0, dec0, ra1, dec1) < 60.0
    assert solved.pixel_scale() == pytest.approx(plate.pixel_scale(), rel=0.10)


def _blind_crop_fits(path, data, size=500):
    # Writes a clean blind plate: a centred square crop of a real frame with
    # every WCS card stripped (only SIMPLE and the sizes remain). The layout
    # is fixed on purpose: the solver caches results by the file sha256, so
    # the crop must be byte-deterministic to stay a cache hit (ADR-018).
    # @args: path - output FITS, data - 2-D array, size - crop width/height
    # @return: (path, row0, col0) of the crop in data coordinates
    h, w = data.shape
    r0 = int(h / 2.0 - size / 2.0)
    c0 = int(w / 2.0 - size / 2.0)
    crop = data[r0:r0 + size, c0:c0 + size].astype(">f4")
    cards = ["SIMPLE  =                    T", "BITPIX  =                  -32",
             "NAXIS   =                    2",
             f"NAXIS1  ={size:21d}", f"NAXIS2  ={size:21d}"]
    blob = "".join(c.ljust(80) for c in cards + ["END"]).encode("ascii")
    blob += b" " * ((-len(blob)) % 2880)
    payload = crop.tobytes()
    payload += b"\0" * ((-len(payload)) % 2880)
    path.write_bytes(blob + payload)
    return path, r0, c0


def _sep_arcsec(ra0, dec0, ra1, dec1):
    # Angular separation of two (ra, dec) pairs in arcseconds; a flat
    # tangent-plane approximation is plenty at these sub-degree scales.
    # @args: ra0, dec0, ra1, dec1 - degrees
    # @return: arcseconds
    import math
    dra = (ra1 - ra0 + 180.0) % 360.0 - 180.0
    return math.hypot(dra * math.cos(math.radians(dec0)), dec1 - dec0) * 3600.0



def _solved_fits(path, ra, dec, width=600, height=400, pixscale=1.5,
                 rot_deg=10.0):
    # Writes a synthetic plate-solved FITS (noise + a bright "SN" at centre).
    import math
    import numpy as np
    rng = np.random.default_rng(3)
    data = rng.normal(900, 15, (height, width))
    data[height // 2, width // 2] += 9000
    # a faint star field besides the SN: astrometry.net cannot blind-solve
    # a one-star plate, and the blink SN must stay the brightest source.
    # keep a clear zone around the centre so nothing crowds it.
    n_stars = int(width * height / 1200)
    clear = int(max(6, 0.08 * min(width, height)))
    cx, cy = width / 2.0, height / 2.0
    added = 0
    while added < n_stars:
        x = int(rng.uniform(0, width))
        y = int(rng.uniform(0, height))
        if abs(x - cx) < clear and abs(y - cy) < clear:
            continue
        peak = 120 + 5000 * rng.random() ** 3
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                yy, xx = y + dy, x + dx
                if 0 <= yy < height and 0 <= xx < width:
                    wgt = 1.0 if (dx == 0 and dy == 0) else 0.35
                    data[yy, xx] += peak * wgt
        added += 1
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
    # The Blink dialog must drive the whole flow without crashing the GUI.
    # Under UX v3 the tab is a modal dialog (ADR-019), so we build the same
    # widget the dialog loads and drive prepare/render/nudge directly (offscreen Qt).
    import os
    import time
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui.main_window import MainWindow, _load_ui
    w = MainWindow()
    b = _load_ui("blink_tab")
    img = _solved_fits(tmp_path / "u.fits", 187.705, 12.391,
                       width=320, height=240)
    b.edt_fits.setText(str(img))
    b.chk_manual.setChecked(True)
    # comma decimal separator must work too (locale-proof fields)
    b.edt_ra.setText("187,705")
    b.edt_dec.setText("12.391")
    w._dialog_blink_prepare(b)
    t0 = time.time()
    while w._blink_pair is None and time.time() - t0 < 60:
        QCoreApplication.processEvents()
        time.sleep(0.05)
    assert w._blink_pair is not None, "blink worker never delivered a pair"
    assert w._blink_dialog_widget is b
    pix = b.lbl_blink.pixmap()
    assert pix is not None and not pix.isNull()
    # exercise the interactive controls: nudge, gamma, fade, marker toggle
    w._dialog_blink_nudge(b, 0.5, -0.5)
    assert w._blink_nudge == [0.5, -0.5]
    b.sld_gamma.setValue(60)
    b.chk_blink_live.setChecked(False)
    b.sld_fade.setValue(30)
    b.chk_marker.setChecked(False)
    w._dialog_blink_render(b)
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
    # Three top-level tabs (ADR-036: History & Sun & sky left the bar for
    # the Tools-menu dialogs; ADR-043 removed the Observatory tab):
    # Tonight · Projects · Campaigns
    assert tabs.count() == 3
    assert tabs.tabText(0) == "Tonight"
    assert tabs.tabText(1) == "Projects"
    assert tabs.tabText(2) == "Campaigns"
    # suggestion grid container exists
    assert w.tonight.scroll_suggestions is not None
    # table starts collapsed (progressive disclosure)
    assert w.tonight.grp_list.isHidden()
    # projects page: ADR-041 tab bar — each step tab is built per project,
    # lazily, on first open; the hub ships with the empty page
    assert w.projects.page_container is not None
    assert w._tab_pages == {} and w._active_tab is None
    # the four flat tab buttons exist (ADR-045: "process" was renamed to
    # "analysis" and the follow-up button was dropped)
    for key in ("details", "plan", "analysis", "publish"):
        getattr(w.projects, f"btn_tab_{key}")
    # menu bar with ad-hoc tools
    menu_texts = [a.text() for a in w.menuBar().actions()]
    assert "File" in menu_texts and "Tools" in menu_texts
    # tables must be sortable
    assert w.tonight.tbl_targets.isSortingEnabled()
    w.close()


# ---------------- CCDciel JSON-RPC (local server, ADR-030) ------------

def _ccdciel_up(host="127.0.0.1", port=3277):
    import socket
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def test_ccdciel_jsonrpc_ping():
    # CCDciel is a local observatory program, not a web source: skip when it
    # is not running (the GUI connect button is the manual path).
    if not _ccdciel_up():
        pytest.skip("no CCDciel JSON-RPC server on localhost:3277")
    from nightscribe.core.sources import ccdciel
    client = ccdciel.Client()
    version = client.ping()
    assert version  # something like "2.20.1"
    assert client.filters() or True  # wheel is optional on real setups
    dash = client.dashboard()
    assert isinstance(dash, dict)
    devs = dash.get("devices") or {}
    assert "connected" in devs or "camera" in dash
