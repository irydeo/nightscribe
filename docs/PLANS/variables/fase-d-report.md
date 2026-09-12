# Track V — Fase D: asesor, plan de captura y reporte fotométrico

> Subplanes VD.1–VD.9 del plan maestro
> [../variables-campaigns.md](../variables-campaigns.md). Un subplan = un
> commit. Anclas verificadas a HEAD `4b7635a`; si una no coincide: **parar y
> reportar**. Lee antes `LEEME.md`.
> Precondición: fases 0–C hechas.

---

## VD.1 — Chip Tonight generalizado + aviso de evento en Follow-up

**Contexto a leer (solo esto)**:
`nightscribe/gui/main_window.py:1022-1067` (`_show_cadence_hints`);
tu bloque de protocolo de VC.10 en `_build_followup_tab`.
**Precondición**: VC.10, VA.1.

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. `_show_cadence_hints` (:1035-1039): el comentario y el SQL pasan a:
   ```python
           # campaign projects already surface in Tonight via the planner's
           # "campaigns" phase (ADR-035, V-d): the chip only watches
           # campaign-less SN projects
           rows = db.execute(
               "SELECT id, object_name FROM projects"
               " WHERE status='active' AND kind='sn'"
               " AND (campaign_id IS NULL)").fetchall()
   ```
2. Evento en Follow-up: en `_build_followup_tab`, **tras** el bloque de
   protocolo de VC.10 (paso 4), añade:
   ```python
           # event advisor (V-h): warn when the latest own point jumped
           from ..core import variables as _vars
           ev = _vars.detect_event(
               fu.list_points(db, pid),
               threshold=float(config.get("event_mag_threshold", 0.5)))
           if ev:
               if ev["direction"] == "drop":
                   msg = self.tr("⚠ Possible brightness drop (Δ≈+%1 mag, filter %2): consider raising the cadence tonight")
               else:
                   msg = self.tr("⚠ Possible outburst (Δ≈−%1 mag, filter %2): top priority tonight")
               lbl_ev = QLabel(msg.replace("%1", f"{ev['delta_mag']:.2f}")
                               .replace("%2", ev["filter"]))
               lbl_ev.setWordWrap(True)
               lbl_ev.setStyleSheet("color: #e0c060;")
               layout.addWidget(lbl_ev)
   ```

**Tests a añadir** (al final de `tests/unit/test_projects_hub.py`; el patrón
del chip está en `:1245-1288`):

```python
def test_cadence_chip_ignores_campaign_projects(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    import time
    # campaign-less stale SN -> chip
    p1 = proj_mod.create(mw.db, "sn", "SN 2026zzz", {"mag": 14.0})
    fu.create_session(mw.db, p1["id"])
    # campaign SN equally stale -> NO chip (it surfaces in the list instead)
    cid = camp_mod.create(mw.db, "Campaña SN")
    p2 = proj_mod.create(mw.db, "sn", "SN 2026yyy", {"mag": 14.0},
                         campaign_id=cid)
    fu.create_session(mw.db, p2["id"])
    for pid in (p1["id"], p2["id"]):
        sid = fu.list_sessions(mw.db, pid)[0]["id"]
        mw.db.execute("UPDATE project_sessions SET created=? WHERE id=?",
                      (time.time() - 9 * 86400, sid))
        mw.db.commit()
    window._show_cadence_hints()
    chip = window.tonight.findChild(QLabel, "ns_cadence_chip")
    assert chip is not None
    assert "SN 2026zzz" in chip.text()
    assert "SN 2026yyy" not in chip.text()


def test_followup_event_advisor_label(window):
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "variable", "V1490 Cyg", {"mag": 12.0})
    for i, m in enumerate((12.0, 12.1, 11.9, 12.0, 12.9)):
        fu.add_point(mw.db, p["id"], 61000.0 + i, "V", m)
    window._build_step_tabs(proj_mod.get(mw.db, p["id"]))
    fu_tab = window.projects.tabs_steps.findChild(QWidget, "tab_followup")
    texts = [l.text() for l in fu_tab.findChildren(QLabel)]
    assert any("brightness drop" in t or "descenso" in t for t in texts)
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| ⚠ Possible brightness drop (Δ≈+%1 mag, filter %2): consider raising the cadence tonight | ⚠ Posible descenso de brillo (Δ≈+%1 mag, filtro %2): considera subir la cadencia esta noche | ⚠ Possible brightness drop (Δ≈+%1 mag, filter %2): consider raising the cadence tonight |
| ⚠ Possible outburst (Δ≈−%1 mag, filter %2): top priority tonight | ⚠ Posible erupción (Δ≈−%1 mag, filtro %2): máxima prioridad esta noche | ⚠ Possible outburst (Δ≈−%1 mag, filter %2): top priority tonight |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: cadence chip generalised + event advisor in follow-up (ADR-035, subplan VD.1)`
**Estado**: Hecho ✅

---

## VD.2 — Plan tab: bloque variable/campaña

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:1950-1994`
(`_build_plan_tab` hasta el bloque hads), `:3047-3130` (`_build_hads_block`,
molde), `:3047-3057` (firma y lectura de plan_data).
**Precondición**: VC.10.

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. En `_build_plan_tab`, tras el bloque hads (:1992-1994), añade:
   ```python
           # Track V: variable/campaign block (protocol, extremum, exposure)
           if kind == "variable":
               self._build_variable_block(layout, p, ctx, spn_exp)
   ```
2. Nueva función tras `_build_hads_block` (búscala con grep
   `def _hads_checklist_save` y colócala justo antes):

```python
    def _build_variable_block(self, layout, p, ctx, spn_exp):
        # The variable/campaign plan block (ADR-035): the campaign protocol
        # reminder, the next expected extremum, tonight's safe window and
        # the heuristic exposure (the SN brightness table, B8) with a
        # saturation warning for bright stars (the T CrB lesson).
        # @args: layout - plan tab layout, p - project dict, ctx - context,
        #        spn_exp - the capture-plan exposure spin (preselected here)
        v = ctx.get("variable") or {}
        grp = QGroupBox(self.tr("Variable star plan"))
        gl = QVBoxLayout(grp)
        if p.get("campaign_id"):
            from ..core import campaign as _camp
            camp = _camp.get(db, p["campaign_id"])
            if camp:
                prot = camp.get("protocol") or {}
                bits = [self.tr("Campaign: %1").replace("%1", camp["name"])]
                if prot.get("cadence_nights"):
                    bits.append(self.tr(
                        "one measurement every %1 night(s) per filter"
                    ).replace("%1", str(prot["cadence_nights"])))
                if prot.get("filters"):
                    bits.append(self.tr("filters: %1").replace(
                        "%1", ", ".join(prot["filters"])))
                lbl = QLabel(" · ".join(bits))
                lbl.setWordWrap(True)
                gl.addWidget(lbl)
        nxt = v.get("next_extremum") or {}
        if nxt.get("days") is not None:
            lab = self.tr("Maximum") if nxt.get("kind") == "max" \
                else self.tr("Minimum")
            gl.addWidget(QLabel(self.tr("%1 expected in ~%2 days").replace(
                "%1", lab).replace("%2", f"{nxt['days']:.0f}")))
        from ..core import narrative
        swt = narrative.safe_window_text(ctx)
        if swt:
            lbl_win = QLabel(self._txt(swt))
            lbl_win.setWordWrap(True)
            gl.addWidget(lbl_win)
        if ctx.get("mag") is not None:
            from ..core import exposure
            exp_rec = exposure.recommended_sn_exposure(ctx["mag"])
            if exp_rec:
                lbl_exp = QLabel(
                    "<small>" + self.tr("Recommended exposure")
                    + f": {exp_rec} s · " + self.tr("guide, not SNR — confirm with a test shot")
                    + "</small>")
                lbl_exp.setWordWrap(True)
                gl.addWidget(lbl_exp)
                spn_exp.setValue(float(exp_rec))
            try:
                if float(ctx["mag"]) <= 10.0:
                    lbl_sat = QLabel(self.tr(
                        "⚠ Bright star: watch the saturation — a slight "
                        "defocus helps (T CrB lesson)"))
                    lbl_sat.setWordWrap(True)
                    lbl_sat.setStyleSheet("color: #e0c060;")
                    gl.addWidget(lbl_sat)
            except (TypeError, ValueError):
                pass
        layout.addWidget(grp)
        self._project_widgets["variable_block"] = grp
```

**Tests a añadir** (al final de `test_projects_hub.py`):

```python
def test_variable_plan_block_shows_protocol_and_extremum(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña T CrB",
                          protocol={"cadence_nights": 1,
                                    "filters": ["B", "V"]})
    ctx = {"mag": 10.1,
           "variable": {"period_d": 227.55,
                        "next_extremum": {"kind": "max", "mjd": 61250.0,
                                          "days": 3.0}},
           "safe_window": "2026-09-11T22:00|2026-09-12T04:00"}
    p = proj_mod.create(mw.db, "variable", "T CrB", ctx, campaign_id=cid)
    window._build_step_tabs(proj_mod.get(mw.db, p["id"]))
    plan = window.projects.tabs_steps.findChild(QWidget, "tab_plan")
    texts = [l.text() for l in plan.findChildren(QLabel)]
    assert any("Campaña T CrB" in t for t in texts)
    assert any("3" in t and ("ays" in t or "ías" in t) for t in texts)
    # the saturation warning does NOT fire at mag 10.1
    assert not any("aturat" in t for t in texts)


def test_variable_plan_block_saturation_warning(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 9.0})
    window._build_step_tabs(proj_mod.get(mw.db, p["id"]))
    plan = window.projects.tabs_steps.findChild(QWidget, "tab_plan")
    texts = [l.text() for l in plan.findChildren(QLabel)]
    assert any("aturat" in t for t in texts)
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Variable star plan | Plan de la estrella variable | Variable star plan |
| one measurement every %1 night(s) per filter | una medida cada %1 noche(s) por filtro | one measurement every %1 night(s) per filter |
| Maximum | Máximo | Maximum |
| Minimum | Mínimo | Minimum |
| %1 expected in ~%2 days | %1 esperado en ~%2 días | %1 expected in ~%2 days |
| Recommended exposure | Exposición recomendada | Recommended exposure |
| guide, not SNR — confirm with a test shot | guía, no SNR — confirma con una toma de prueba | guide, not SNR — confirm with a test shot |
| ⚠ Bright star: watch the saturation — a slight defocus helps (T CrB lesson) | ⚠ Estrella brillante: cuidado con la saturación — un ligero desenfoque ayuda (lección de T CrB) | ⚠ Bright star: watch the saturation — a slight defocus helps (T CrB lesson) |

 **Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q` + pipeline i18n
 **Hecho cuando**: verde; suite verde (N→M).
 **Commit**: `Gui: variable/campaign plan block — protocol, extremum, exposure, saturation warning (ADR-035, subplan VD.2)`
 **Estado**: Hecho ✅ (66 tests en test_projects_hub.py; i18n 702/702; suite 1080 passed)

---

## VD.3 — Secuencia multi-filtro del protocolo (CCDciel/NINA/CSV)

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:2033-2058`
(filas multi-filtro SN) y `:4038-4062` (`_project_export_sequence`, rama
steps).
**Precondición**: VD.2.

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. `:2034` — la condición del bloque multi-filtro pasa de
   `if kind == "sn" and ctx.get("mag") is not None:` a:
   ```python
           if kind in ("sn", "variable") and ctx.get("mag") is not None:
   ```
   (el comentario B8 lo menciona: «B8/Track V: SN and variable exposure hint
   by brightness + multi-filter step rows»).
2. En ese bloque, sustituye el pre-relleno (:2049-2051) por:
   ```python
               self._sn_steps = []
               default_filters = ("Clear",)
               if kind == "variable" and p.get("campaign_id"):
                   from ..core import campaign as _camp
                   camp = _camp.get(db, p["campaign_id"])
                   prot_filters = ((camp or {}).get("protocol") or {}).get(
                       "filters") or []
                   if prot_filters:
                       default_filters = tuple(prot_filters)
               for filt in default_filters:
                   self._sn_add_step_row(steps_vlay, filt, 30,
                                         spn_exp.value())
   ```
3. `:4054` — la condición de export pasa a:
   ```python
           if self._current_project["kind"] in ("sn", "variable") \
                   and self._sn_steps:
   ```

**Tests a añadir** (al final de `test_projects_hub.py`):

```python
def test_variable_plan_prefills_protocol_filters(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña T CrB",
                          protocol={"cadence_nights": 1,
                                    "filters": ["B", "V"]})
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 10.1},
                        campaign_id=cid)
    window._build_step_tabs(proj_mod.get(mw.db, p["id"]))
    filters = [e["cmb"].currentText() for e in window._sn_steps]
    assert filters == ["B", "V"]


def test_variable_without_campaign_keeps_clear_default(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "variable", "V1490 Cyg", {"mag": 12.0})
    window._build_step_tabs(proj_mod.get(mw.db, p["id"]))
    filters = [e["cmb"].currentText() for e in window._sn_steps]
    assert filters == ["Clear"]
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py tests/unit/test_sequence.py -q`
**Hecho cuando**: verde; suite verde (N→M). **No hay cadenas nuevas.**
**Commit**: `Gui: protocol filters pre-fill the multi-filter capture plan for variables (ADR-035, subplan VD.3)`
**Estado**: Pendiente

---

## VD.4 — `core/photometry_export.py`: CSV

**Contexto a leer (solo esto)**: `nightscribe/core/followup.py:151-169`
(puntos); tu `core/variables.py` de V0.5/V0.6.
**Precondición**: V0.6.

**Toca**: `nightscribe/core/photometry_export.py` (**nuevo**);
`tests/unit/test_photometry_export.py` (**nuevo**).

**Escribe exactamente esto** — `nightscribe/core/photometry_export.py`
(cabecera GPL; «Photometry report export module (ADR-035)»):

```python
"""Photometry report export (V-i): the project's photometry points as a
plain CSV or an AAVSO Extended File Format text, with heliocentric Julian
dates computed in-app (variables.jd_to_hjd). Quick-look points are
"indicative" (T6) and only leave the app on explicit request.
"""

import logging
from pathlib import Path

from . import followup, variables

logger = logging.getLogger(__name__)

CSV_HEADER = ("name", "hjd", "mag", "err", "filter", "comp_stars",
              "observer", "notes")


def collect_points(db, project_id, include_quicklook=False):
    # The exportable points of the project, MJD-ordered.
    # @args: include_quicklook - quick-look points are indicative (T6) and
    #        only export on explicit request
    # @return: list of point dicts
    pts = followup.list_points(db, project_id)
    return [p for p in pts
            if include_quicklook or (p.get("source") or "") != "quicklook"]


def hjd_of(point, ra_deg, dec_deg):
    # @return: the point's HJD (MJD -> JD -> HJD), or None when the instant
    #          or the coordinates are missing
    if point.get("mjd") is None or ra_deg is None or dec_deg is None:
        return None
    return variables.jd_to_hjd(point["mjd"] + variables.MJD0, ra_deg,
                               dec_deg)


def export_csv(points, out, name, ra_deg=None, dec_deg=None, observer="",
               comp_stars=None):
    # The documented group CSV (V-i): one row per point, dot decimal,
    # comma-separated, comparison stars joined by "+" in one cell.
    # @return: Path written
    comps = "+".join(comp_stars or [])
    lines = [f"# name: {name}",
             "# generated by NightScribe — dates are HJD",
             ",".join(CSV_HEADER)]
    for p in points:
        hjd = hjd_of(p, ra_deg, dec_deg)
        err = f"{p['err']:.3f}" if p.get("err") is not None else ""
        lines.append(",".join([
            name, f"{hjd:.5f}" if hjd is not None else "",
            f"{p['mag']:.3f}", err, p.get("filter") or "", comps,
            observer, ""]))
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("photometry CSV written: %s (%d points)", out, len(points))
    return Path(out)
```

**Tests a añadir** — `tests/unit/test_photometry_export.py` (cabecera GPL;
«Unit tests: photometry export (Track V, VD.4/VD.5)»):

```python
import pytest

from nightscribe.core import followup, photometry_export
from nightscribe.core.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _pid_with_points(db):
    from nightscribe.core import project
    p = project.create(db, "variable", "WeSb 1",
                       {"ra_deg": 15.2254, "dec_deg": 55.0667})
    for i, m in enumerate((15.10, 15.12, 15.09)):
        followup.add_point(db, p["id"], 59650.94800 + i, "V", m, err=0.02)
    followup.add_point(db, p["id"], 59660.0, "V", 15.2, source="quicklook")
    return p["id"]


def test_collect_points_excludes_quicklook_by_default(db):
    pid = _pid_with_points(db)
    assert len(photometry_export.collect_points(db, pid)) == 3
    assert len(photometry_export.collect_points(db, pid,
                                                include_quicklook=True)) == 4


def test_csv_columns_and_hjd(db, tmp_path):
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    out = tmp_path / "report.csv"
    photometry_export.export_csv(pts, out, "WeSb 1", ra_deg=15.2254,
                                 dec_deg=55.0667, observer="ZABC",
                                 comp_stars=["C1", "C2"])
    lines = out.read_text().splitlines()
    assert lines[0] == "# name: WeSb 1"
    assert lines[2] == "name,hjd,mag,err,filter,comp_stars,observer,notes"
    row = lines[3].split(",")
    assert row[0] == "WeSb 1"
    # frozen reference: MJD 59650.94800 -> JD 2459651.448 -> HJD corr known
    # within 30 s of +250.09 s at JD 2459653.448 (same geometry, 2 d apart)
    hjd = float(row[1])
    corr_s = (hjd - (59650.94800 + 2400000.5)) * 86400
    assert corr_s == pytest.approx(250.09, abs=30.0)
    assert row[2] == "15.100" and row[3] == "0.020" and row[4] == "V"
    assert row[5] == "C1+C2" and row[6] == "ZABC"


def test_csv_without_coordinates_leaves_hjd_empty(db, tmp_path):
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    out = tmp_path / "report.csv"
    photometry_export.export_csv(pts, out, "WeSb 1")
    row = out.read_text().splitlines()[3].split(",")
    assert row[1] == ""
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_photometry_export.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: photometry CSV export with in-app HJD (ADR-035, subplan VD.4)`
**Estado**: Pendiente

---

## VD.5 — `photometry_export.py`: AAVSO Extended File Format

**Contexto a leer (solo esto)**: tu `core/photometry_export.py` de VD.4.
**Precondición**: VD.4.

**Toca**: `nightscribe/core/photometry_export.py` (ampliar);
`tests/unit/test_photometry_export.py` (ampliar).

**Escribe exactamente esto** — al final de `core/photometry_export.py`:

```python
# ---------------- AAVSO Extended File Format ----------------

EFF_FIELDS = ("NAME,DATE,MAG,MERR,FILT,TRANS,MTYPE,CNAME,CMAG,KNAME,KMAG,"
              "AMASS,GROUP,CHART,NOTES")


def export_eff(points, out, name, ra_deg=None, dec_deg=None, obscode=""):
    # AAVSO Extended File Format (the WebObs/FotoDif interchange): header
    # lines starting with '#', then one line per point. Dates are HJD
    # (#DATE=HJD). Points without a full HJD are skipped — EFF has no
    # empty-date concept.
    # @args: obscode - the AAVSO observer code (config aavso_code)
    # @return: Path written
    lines = ["#TYPE=EXTENDED",
             f"#OBSCODE={obscode or 'UNKNOWN'}",
             "#SOFTWARE=NightScribe",
             "#DELIM=,",
             "#DATE=HJD",
             "#OBSTYPE=CCD",
             EFF_FIELDS]
    n = 0
    for p in points:
        hjd = hjd_of(p, ra_deg, dec_deg)
        if hjd is None:
            continue
        merr = f"{p['err']:.3f}" if p.get("err") is not None else "0.000"
        filt = p.get("filter") or "Clear"
        lines.append(f"{name.upper()},{hjd:.5f},{p['mag']:.3f},{merr},"
                     f"{filt},NA,STD,na,na,na,na,na,na,na,")
        n += 1
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("photometry EFF written: %s (%d points)", out, n)
    return Path(out)


def export_report(points, out, fmt="csv", **meta):
    # Single entry point for the GUI.
    # @args: fmt - "csv" | "eff", meta - export_csv/export_eff keywords
    if fmt == "eff":
        return export_eff(points, out, **meta)
    return export_csv(points, out, **meta)
```

**Tests a añadir** (al final de `tests/unit/test_photometry_export.py`):

```python
def test_eff_header_and_rows(db, tmp_path):
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    out = tmp_path / "report.txt"
    photometry_export.export_eff(pts, out, "WeSb 1", ra_deg=15.2254,
                                 dec_deg=55.0667, obscode="ZABC")
    lines = out.read_text().splitlines()
    assert lines[:6] == ["#TYPE=EXTENDED", "#OBSCODE=ZABC",
                         "#SOFTWARE=NightScribe", "#DELIM=,", "#DATE=HJD",
                         "#OBSTYPE=CCD"]
    assert lines[6] == photometry_export.EFF_FIELDS
    row = lines[7].split(",")
    assert row[0] == "WESB 1"                    # upper-cased
    assert row[2] == "15.100" and row[3] == "0.020" and row[4] == "V"
    assert row[5] == "NA" and row[6] == "STD"
    assert len(row) == 15
    assert len(lines) == 10                       # 7 header + 3 rows


def test_eff_skips_points_without_hjd(db, tmp_path):
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    out = tmp_path / "report.txt"
    photometry_export.export_eff(pts, out, "WeSb 1")   # no coords
    assert len(out.read_text().splitlines()) == 7      # header only


def test_export_report_dispatch(db, tmp_path):
    pid = _pid_with_points(db)
    pts = photometry_export.collect_points(db, pid)
    o1 = photometry_export.export_report(pts, tmp_path / "a.csv", fmt="csv",
                                         name="WeSb 1")
    o2 = photometry_export.export_report(pts, tmp_path / "a.txt", fmt="eff",
                                         name="WeSb 1", obscode="ZABC")
    assert o1.exists() and o2.exists()
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_photometry_export.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: AAVSO Extended File Format photometry export (ADR-035, subplan VD.5)`
**Estado**: Pendiente

---

## VD.6 — Diálogo de exportación + registro en `project_files`

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:3302-3310`
(fila `fu_btns` del Follow-up) y `:3878-3920` (`_fu_import_file`, molde de
diálogo de fichero).
**Precondición**: VD.5, VC.10.

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. En `_build_followup_tab`, en la fila `fu_btns` tras el botón «Import
   file…» (:3307-3309), añade:
   ```python
           btn_export = QPushButton(self.tr("Export photometry report…"))
           btn_export.setToolTip(self.tr(
               "CSV or AAVSO EFF with heliocentric dates, for the campaign "
               "form / WebObs"))
           btn_export.clicked.connect(lambda: self._fu_export_report(pid))
           fu_btns.addWidget(btn_export)
   ```
2. Nuevo handler junto a `_fu_import_file`:

```python
    def _fu_export_report(self, pid):
        # Exports the project's photometry to CSV or AAVSO EFF (HJD in-app,
        # ADR-035 V-i) and registers the file in the project.
        from ..core import photometry_export, project
        p = project.get(db, pid)
        ctx = p.get("context") or {}
        # quick-look inclusion is an explicit choice (T6)
        from PySide6.QtWidgets import QCheckBox, QComboBox
        from PySide6.QtWidgets import (QDialog, QDialogButtonBox,
                                       QFormLayout)
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Export photometry report"))
        form = QFormLayout(dlg)
        cmb_fmt = QComboBox()
        cmb_fmt.addItem(self.tr("CSV (group format)"), "csv")
        cmb_fmt.addItem(self.tr("AAVSO EFF (WebObs)"), "eff")
        form.addRow(self.tr("Format:"), cmb_fmt)
        chk_ql = QCheckBox(self.tr("Include quick-look (indicative) points"))
        form.addRow(chk_ql)
        box = QDialogButtonBox(QDialogButtonBox.Save
                               | QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() != QDialog.Accepted:
            return
        pts = photometry_export.collect_points(db, pid,
                                               include_quicklook=
                                               chk_ql.isChecked())
        if not pts:
            self.statusBar().showMessage(
                self.tr("No photometry points to export"), 6000)
            return
        # comparison stars and observer code come from the campaign/config
        comps, observer = [], config.get("aavso_code", "")
        if p.get("campaign_id"):
            from ..core import campaign as _camp
            camp = _camp.get(db, p["campaign_id"])
            if camp:
                comps = (camp.get("protocol") or {}).get("comp_stars") or []
        ext = ".txt" if cmb_fmt.currentData() == "eff" else ".csv"
        outdir = project.storage_dir(p)
        default = outdir / f"{p['object_name']}_photometry{ext}"
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export photometry report"), str(default),
            f"*{ext};;All files (*)")
        if not out:
            return
        meta = {"name": p["object_name"], "ra_deg": ctx.get("ra_deg"),
                "dec_deg": ctx.get("dec_deg")}
        if cmb_fmt.currentData() == "eff":
            path = photometry_export.export_eff(pts, out, obscode=observer,
                                                **meta)
        else:
            path = photometry_export.export_csv(pts, out, observer=observer,
                                                comp_stars=comps, **meta)
        project.add_file(db, pid, str(path), "report")
        self.statusBar().showMessage(
            self.tr("Written to %1").replace("%1", str(path)), 8000)
```

**Tests a añadir** (al final de `test_projects_hub.py`):

```python
def test_followup_has_export_report_button(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 10.1})
    window._build_step_tabs(proj_mod.get(mw.db, p["id"]))
    fu_tab = window.projects.tabs_steps.findChild(QWidget, "tab_followup")
    texts = [b.text() for b in fu_tab.findChildren(QPushButton)]
    assert any("Export photometry report" in t or "Exportar" in t
               for t in texts)
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Export photometry report… | Exportar reporte de fotometría… | Export photometry report… |
| CSV or AAVSO EFF with heliocentric dates, for the campaign form / WebObs | CSV o EFF de AAVSO con fechas heliocéntricas, para el formulario de la campaña / WebObs | CSV or AAVSO EFF with heliocentric dates, for the campaign form / WebObs |
| Export photometry report | Exportar reporte de fotometría | Export photometry report |
| CSV (group format) | CSV (formato del grupo) | CSV (group format) |
| AAVSO EFF (WebObs) | AAVSO EFF (WebObs) | AAVSO EFF (WebObs) |
| Format: | Formato: | Format: |
| Include quick-look (indicative) points | Incluir puntos quick-look (indicativos) | Include quick-look (indicative) points |
| No photometry points to export | No hay puntos de fotometría que exportar | No photometry points to export |
| Written to %1 | Escrito en %1 | Written to %1 |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: photometry report export dialog + project file registration (ADR-035, subplan VD.6)`
**Estado**: Pendiente

---

## VD.7 — Botón «Descargar fotometría de surveys» en Follow-up

**Contexto a leer (solo esto)**: `nightscribe/gui/main_window.py:3302-3310`
(fila `fu_btns`); tu `core/sources/surveys.py` de V0.9.
**Precondición**: V0.9, VC.10.

**Toca**: `nightscribe/gui/main_window.py`;
`tests/unit/test_projects_hub.py` (ampliar).

**Escribe exactamente esto**:

1. En `_build_followup_tab`, tras el botón de export de VD.6, añade:
   ```python
           if kind in ("sn", "variable"):
               btn_survey = QPushButton(self.tr("Download survey photometry…"))
               btn_survey.setToolTip(self.tr(
                   "ASAS-SN/ZTF context points, drawn in grey and never "
                   "mixed with your own measurements"))
               btn_survey.clicked.connect(
                   lambda: self._fu_download_survey(pid))
               fu_btns.addWidget(btn_survey)
   ```
2. Nuevo handler:

```python
    def _fu_download_survey(self, pid):
        # Pulls the survey context points (V-f; closes the B12 option) into
        # photometry_points as source="survey:ztf". Idempotent: a point with
        # the same mjd+filter+source is not duplicated.
        from ..core import followup as fu
        from ..core import project
        from ..core.sources import surveys
        p = project.get(db, pid)
        ctx = p.get("context") or {}
        ra, dec = ctx.get("ra_deg"), ctx.get("dec_deg")
        if ra is None or dec is None:
            self.statusBar().showMessage(
                self.tr("The project has no coordinates"), 6000)
            return
        pts = surveys.fetch_points(ra, dec)
        if not pts:
            self.statusBar().showMessage(
                self.tr("No survey data for this position"), 6000)
            return
        existing = {(q["mjd"], q["filter"]) for q in fu.list_points(db, pid)
                    if (q.get("source") or "").startswith("survey:")}
        n = 0
        for pt in pts:
            if (pt["mjd"], pt["filter"]) in existing:
                continue
            fu.add_point(db, pid, pt["mjd"], pt["filter"], pt["mag"],
                         err=pt.get("err"), source=pt["source"])
            n += 1
        self.statusBar().showMessage(
            self.tr("Added %1 survey points").replace("%1", str(n)), 8000)
        # rebuild the tab so the curve/points update in place
        self._build_step_tabs(project.get(db, pid))
```

**Tests a añadir** (al final de `test_projects_hub.py`):

```python
def test_download_survey_points_are_stored_and_deduped(window, monkeypatch):
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj_mod
    from nightscribe.core.sources import surveys
    from nightscribe.gui import main_window as mw
    fake = [{"mjd": 59000.0 + i, "filter": "g", "mag": 15.5 + i * 0.01,
             "err": 0.02, "source": "survey:ztf"} for i in range(5)]
    monkeypatch.setattr(surveys, "fetch_points", lambda ra, dec: fake)
    p = proj_mod.create(mw.db, "variable", "WeSb 1",
                        {"ra_deg": 15.2254, "dec_deg": 55.0667})
    window._fu_download_survey(p["id"])
    pts = fu.list_points(mw.db, p["id"])
    assert len(pts) == 5
    assert all(q["source"] == "survey:ztf" for q in pts)
    window._fu_download_survey(p["id"])          # again: no duplicates
    assert len(fu.list_points(mw.db, p["id"])) == 5
```

**Cadenas nuevas**:

| Fuente | ES | EN |
|---|---|---|
| Download survey photometry… | Descargar fotometría de surveys… | Download survey photometry… |
| ASAS-SN/ZTF context points, drawn in grey and never mixed with your own measurements | Puntos de contexto ASAS-SN/ZTF, en gris y nunca mezclados con tus medidas | ASAS-SN/ZTF context points, drawn in grey and never mixed with your own measurements |
| The project has no coordinates | El proyecto no tiene coordenadas | The project has no coordinates |
| No survey data for this position | Sin datos de surveys para esta posición | No survey data for this position |
| Added %1 survey points | Añadidos %1 puntos de survey | Added %1 survey points |

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_projects_hub.py -q` + pipeline i18n
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Gui: survey context download in follow-up (closes the B12 option) (ADR-035, subplan VD.7)`
**Estado**: Pendiente

---

## VD.8 — Narrativa variable (hook, facts, hashtags)

**Contexto a leer (solo esto)**: `nightscribe/core/narrative.py:94-99` (hook
dispatch), `:152-170` (facts dispatch), `:367-395` (`_hads_hook`, molde),
`:524-541` (hashtags).
**Precondición**: VB.6.

**Toca**: `nightscribe/core/narrative.py`;
`tests/unit/test_narrative_variable.py` (**nuevo**).

**Escribe exactamente esto**:

1. `narrative.py`, dispatch del hook (:94-99): tras la rama hads, añade:
   ```python
       if kind == "variable":
           return _variable_hook(e.get("name") or "", d.get("variable") or {},
                                 d.get("campaign") or {})
   ```
2. Dispatch de facts (:166-170): tras la rama hads, añade:
   ```python
       if kind == "variable":
           return _variable_facts(d) + _safe_window_bullets(d)
   ```
3. `hashtags` (:529-540): el dict `per_kind` gana
   `"variable": "#VariableStars #AAVSO",` tras `"hads"`.
4. Nuevas funciones tras `_hads_facts` (ojo: hay código muerto tras su
   `return` en :452-468 — **no lo toques**; inserta antes de `def
   _sun_facts` :471):

```python
def _variable_hook(name, v, camp):
    # The variable hook: the campaign that watches it and its next extremum.
    # @args: name - object name, v - "variable" sub-dict, camp - "campaign"
    # @return: {"es": str, "en": str}
    who_es = f"la estrella {name}" if name else "esta estrella"
    who_en = f"the star {name}" if name else "this star"
    if camp.get("name"):
        es = f"Seguimos {who_es} dentro de la campaña «{camp['name']}»."
        en = (f"We are following {who_en} inside the “{camp['name']}” "
              "campaign.")
    else:
        es = f"Seguimos {who_es}, una estrella variable."
        en = f"We are following {who_en}, a variable star."
    nxt = v.get("next_extremum") or {}
    if nxt.get("days") is not None:
        lab_es = "máximo" if nxt.get("kind") == "max" else "mínimo"
        lab_en = "maximum" if nxt.get("kind") == "max" else "minimum"
        es += f" Su próximo {lab_es} se espera en ~{nxt['days']:.0f} días."
        en += f" Its next {lab_en} is expected in ~{nxt['days']:.0f} days."
    return {"es": es, "en": en}


def _variable_facts(d):
    # @args: d - data dict of a variable star
    # @return: bullet list ES/EN
    out = []
    v = d.get("variable") or {}
    fam, _epoch_min = orbits._variable_family_text(v.get("var_type"))
    out.append({"es": fam["es"], "en": fam["en"]})
    per, amp = v.get("period_d"), v.get("amp")
    if amp is None and v.get("max") is not None and v.get("min") is not None:
        amp = v["min"] - v["max"]
    if per:
        out.append({"es": f"Varía con un periodo de {per:.1f} días"
                          + (f" y una amplitud de {amp:.1f} mag."
                             if amp else "."),
                    "en": f"It varies with a {per:.1f}-day period"
                          + (f" and a {amp:.1f}-mag amplitude."
                             if amp else ".")})
    c = d.get("campaign") or {}
    if c.get("name"):
        out.append({"es": f"Forma parte de la campaña «{c['name']}»: "
                          "cada noche cuenta.",
                    "en": f"It belongs to the “{c['name']}” campaign: "
                          "every night counts."})
    return out
```

**Tests a añadir** — `tests/unit/test_narrative_variable.py` (cabecera GPL;
«Unit tests: variable narrative (Track V, VD.8)»; el fixture `fake_cfg` viene
del conftest de `tests/`):

```python
from nightscribe.core import narrative, post


def _e():
    return {"type": "variable", "name": "T CrB",
            "data": {"variable": {"var_type": "NR+ELL", "period_d": 227.55,
                                  "max": 2.0, "min": 10.8, "amp": 8.8,
                                  "next_extremum": {"kind": "max",
                                                    "mjd": 61250.0,
                                                    "days": 3.0}},
                     "campaign": {"name": "Campaña T CrB"}}}


def test_variable_hook_mentions_campaign_and_extremum():
    h = narrative.hook(_e())
    assert "Campaña T CrB" in h["es"] and "campaign" in h["en"]
    assert "máximo" in h["es"] and "3" in h["en"]


def test_variable_facts_bilingual_pairs():
    bullets = narrative.fact_bullets(_e())
    assert bullets
    for b in bullets:
        assert b["es"] and b["en"]
    joined = " ".join(b["es"] for b in bullets)
    assert "Nova recurrente" in joined
    assert "227.6 días" in joined


def test_variable_hashtags():
    assert "#VariableStars" in narrative.hashtags("variable")


def test_render_post_tells_the_variable_story(fake_cfg):
    out = post.render_post(_e(), cfg=fake_cfg)
    assert "T CrB" in out["es"] and "T CrB" in out["en"]
    assert len(out["tweet"]) <= 280
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_narrative_variable.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core: variable narrative — hook, fact bullets, hashtags ES/EN (ADR-035, subplan VD.8)`
**Estado**: Pendiente

---

## VD.9 — Post con curva plegada para variable

**Contexto a leer (solo esto)**: `nightscribe/core/post.py:302-331` (rama de
curva de luz en `build_charts`); `tests/unit/test_hads_post.py:44-55` (molde
del test).
**Precondición**: VD.8, VC.2.

**Toca**: `nightscribe/core/post.py`;
`tests/unit/test_variable_post.py` (**nuevo**).

**Escribe exactamente esto**:

1. `post.py:306` — la condición pasa a incluir `"variable"`:
   ```python
       if fu_points and e.get("type") in ("transient", "sn", "hads",
                                          "variable"):
   ```
2. En el cuerpo, tras el bloque hads (:311-322), añade:
   ```python
               if e.get("type") == "variable":
                   v = d.get("variable") or {}
                   if v.get("period_d"):
                       kw["fold_period_d"] = v["period_d"]
                       if v.get("epoch_mjd") is not None:
                           kw["epoch_mjd"] = v["epoch_mjd"]
                       amp = v.get("amp")
                       if amp is None and v.get("max") is not None \
                               and v.get("min") is not None:
                           amp = v["min"] - v["max"]     # inverted axis
                       if amp and v.get("max") is not None:
                           from . import hads as hads_mod
                           kw["schematic"] = hads_mod.sawtooth_template(
                               v["period_d"] * 24.0, amp,
                               (v["max"] + v["min"]) / 2)
   ```

**Tests a añadir** — `tests/unit/test_variable_post.py` (cabecera GPL;
«Unit tests: variable post with folded light curve (Track V, VD.9)»):

```python
from nightscribe.core import post


def _variable_e():
    return {"type": "variable", "name": "T CrB",
            "data": {"variable": {"var_type": "NR+ELL", "period_d": 227.55,
                                  "epoch_mjd": 55828.4, "max": 2.0,
                                  "min": 10.8, "amp": 8.8},
                     "campaign": {"name": "Campaña T CrB"},
                     "followup": {"points": [
                         {"mjd": 61000.0 + 5 * i,
                          "mag": 10.1 + 0.2 * (i % 3), "err": 0.02,
                          "filter": "V", "source": "file"}
                         for i in range(9)]}}}


def test_post_chart_folds_the_variable_curve(tmp_path, fake_cfg):
    charts = post.build_charts(_variable_e(), tmp_path, "", cfg=fake_cfg)
    lc = charts.get("lightcurve")
    assert lc is not None and lc.exists() and lc.stat().st_size > 1000


def test_post_mentions_the_campaign(tmp_path, fake_cfg):
    out = post.render_post(_variable_e(), cfg=fake_cfg)
    assert "Campaña T CrB" in out["es"]
```

**Ejecuta**: `.venv/bin/python -m pytest tests/unit/test_variable_post.py -q`
**Hecho cuando**: verde; suite verde (N→M).
**Commit**: `Core/Post: variable posts ship the epoch-folded light curve (ADR-035, subplan VD.9)`
**Estado**: Pendiente

---

## Cierre de la fase D

Cuando VD.1–VD.9 estén hechas: `.venv/bin/python -m pytest tests/unit -q`
verde y anota el conteo total aquí: 1076 → 1078 (tras VD.1) → 1080 (tras VD.2).
