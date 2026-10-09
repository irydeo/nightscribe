############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SN follow-up post (Track B, B9)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core.post import (
    render_post, build_charts, CHART_LABELS, MEDIA,
)


_CFG = type("C", (), {
    "_v": {"observatory_name": "Test Obs", "mpc_code": "Z41"},
    "get": lambda self, k, d=None: self._v.get(k, d),
    "ui_language": lambda self=None: "es",
})()


def _sn_enriched(points, sn_type="SN Ia", peak_mjd=None, peak_mag=None):
    # @return: a minimal enriched dict for SN post tests
    return {
        "name": "SN2026abc",
        "type": "transient",
        "data": {
            "simbad": {"otype": sn_type},
            "host": {"name": "NGC 5908"},
            "dist_mly": 74,
            "mag": 16.0,
            "disc_date": "2026-09-01",
            "followup": {"points": points,
                        "peak_mjd": peak_mjd,
                        "peak_mag": peak_mag},
        },
    }


_POINTS = [
    {"mjd": 60600.0, "mag": 16.0, "err": 0.02, "filter": "Clear",
     "source": "manual"},
    {"mjd": 60605.0, "mag": 16.3, "err": 0.03, "filter": "Clear",
     "source": "manual"},
    {"mjd": 60610.0, "mag": 16.6, "err": 0.02, "filter": "Clear",
     "source": "manual"},
]


# ---------------- render_post with follow-up ----------------

def test_render_post_sn_has_followup_narrative():
    e = _sn_enriched(_POINTS)
    post = render_post(e, _CFG)
    # the ES hook for a transient mentions tracking/following
    txt = post["es"].lower()
    assert "noche" in txt or "seguim" in txt or "brillo" in txt


def test_render_post_both_languages():
    e = _sn_enriched(_POINTS)
    post = render_post(e, _CFG)
    assert "SN2026abc" in post["es"]
    assert "SN2026abc" in post["en"]


# ---------------- build_charts with light curve ----------------

def test_build_charts_produces_lightcurve(tmp_path):
    e = _sn_enriched(_POINTS, sn_type="SN Ia",
                     peak_mjd=60600.0, peak_mag=16.0)
    charts = build_charts(e, tmp_path, "SN2026abc_",
                    cfg=_CFG, fmt="facebook")
    assert "lightcurve" in charts
    from pathlib import Path
    assert Path(charts["lightcurve"]).exists()


def test_build_charts_no_lightcurve_without_points(tmp_path):
    # no followup points → no light curve chart
    e = _sn_enriched([])
    charts = build_charts(e, tmp_path, "SNx_",
                    cfg=_CFG, fmt="facebook")
    assert "lightcurve" not in charts


def test_build_charts_lightcurve_omitted_for_non_sn(tmp_path):
    # a NEO enriched dict has no SN followup → no light curve
    e = {"name": "2026AB", "type": "neo",
          "data": {"sbdb": {"elements": {"a": 1.0, "e": 0.1}}}}
    charts = build_charts(e, tmp_path, "2026AB_",
                    cfg=_CFG, fmt="facebook")
    assert "lightcurve" not in charts


# ---------------- CHART_LABELS + MEDIA ----------------

def test_chart_labels_include_lightcurve():
    assert "lightcurve" in CHART_LABELS


def test_media_labels_include_evolution():
    assert "evo_gif" in MEDIA
    assert "evo_mp4" in MEDIA


# ---------------- gallery + report attachment (2026-10-09) -------------

def test_gallery_entries_name_the_exact_files(tmp_path):
    from nightscribe.core.post import gallery_entries
    charts = {"orbit": tmp_path / "SN2026abc_orbit.png",
              "lightcurve": tmp_path / "SN2026abc_lightcurve.png"}
    resources = {"gif": tmp_path / "SN2026abc_blink.gif"}
    gal = gallery_entries(charts, resources, "SN2026abc")
    names = {g["key"]: g["name"] for g in gal}
    assert names["orbit"] == "SN2026abc_orbit.png"
    assert names["gif"] == "SN2026abc_blink.gif"
    # every entry carries a caption in both languages (from the labels)
    assert all(g["caption"]["es"] and g["caption"]["en"] for g in gal)


def test_attach_charts_also_fills_the_report(tmp_path):
    from nightscribe.core.post import attach_charts
    png = tmp_path / "x_orbit.png"
    png.write_bytes(b"x")
    post = {"es": "ES", "en": "EN", "report_es": "Informe",
            "report_en": "Report", "tweet": "t"}
    attach_charts(post, {"orbit": png})
    assert "## Galería" in post["report_es"]
    assert "x_orbit.png" in post["report_es"]
    assert "## Gallery" in post["report_en"]
    assert post["tweet"] == "t"          # the tweet never gets a gallery


def test_attach_charts_keeps_the_reports_own_headings(tmp_path):
    # The report is an ARTICLE with "##" section headings. Attaching the
    # gallery must NOT cut the body at its first heading (the defect that
    # left only the title: "the short report in the long slot").
    from nightscribe.core.post import attach_charts
    png = tmp_path / "x_orbit.png"
    png.write_bytes(b"x")
    report = ("# V0526 Per\n\n## What it is\n\nA variable star.\n\n"
              "## The night\n\nMore text.")
    post = {"report_es": report}
    attach_charts(post, {"orbit": png})
    assert "## What it is" in post["report_es"]
    assert "A variable star." in post["report_es"]
    assert "## The night" in post["report_es"]
    assert "## Galería" in post["report_es"]


def test_attach_charts_replaces_a_previous_gallery(tmp_path):
    # a second call replaces the gallery instead of duplicating it, and the
    # article body is untouched
    from nightscribe.core.post import attach_charts
    png = tmp_path / "x_orbit.png"
    png.write_bytes(b"x")
    post = {"report_es": "# Title\n\n## Section\n\nBody."}
    attach_charts(post, {"orbit": png})
    attach_charts(post, {"orbit": png})
    assert post["report_es"].count("## Galería") == 1
    assert "Body." in post["report_es"]


def test_collect_assets_labels_evolution_files(tmp_path):
    from nightscribe.core.post import collect_assets
    (tmp_path / "SN_blink.gif").write_bytes(b"x")
    (tmp_path / "SN_evo.gif").write_bytes(b"x")
    (tmp_path / "SN_evo.mp4").write_bytes(b"x")
    e = {"name": "SN", "type": "neo", "data": {}}
    _charts, resources = collect_assets(e, tmp_path, "SN", cfg=_CFG)
    assert resources.get("evo_gif")           # the _evo_ check wins
    assert resources.get("evo_mp4")
    assert resources.get("gif")
