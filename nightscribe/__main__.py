############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Command line interface
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import argparse
import datetime
import logging
import sys
from pathlib import Path

from . import __app_name__, config, paths
from .config import config as cfg
from .core.db import db

logger = logging.getLogger(__name__)


def _setup_logging(verbose):
    # @args: verbose - bool
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s")


def _no_site():
    # ADR-042: no observatory configured. The CLI keeps its honesty and
    # tells the user what to do, instead of silently computing everything
    # around the geocenter (the wizard fixes it in a couple of minutes).
    # @return: True when the site is missing (the command should stop)
    if cfg.is_configured():
        return False
    print("No site configured / No hay observatorio configurado.")
    print("Run the GUI once: a short wizard sets up your observatory.")
    print(f"You can also edit {paths.config_dir() / 'nightscribe.json'} "
          "with your coordinates and MPC code (optional).")
    return True


def cmd_tonight(args):
    # Best targets for tonight at the configured site.
    from .core import planner, suggest
    if _no_site():
        return 1
    date = datetime.date.fromisoformat(args.fecha) if args.fecha else None
    print(f"{__app_name__} — {cfg.get('observatory_name')} "
          f"(MPC {cfg.get('mpc_code')})")
    print(f"Noche / Night: {date or datetime.date.today()}  "
          f"(lat {cfg.get('lat')}, lon {cfg.get('lon')})")
    targets = planner.build_tonight(cfg, date)
    top, all_scored = suggest.top_n(targets, cfg, db, args.top)
    medals = ["🥇", "🥈", "🥉"] + ["•"] * max(args.top - 3, 0)
    print("\n=== LO MEJOR DE ESTA NOCHE / BEST OF TONIGHT ===")
    n_beyond = 0
    limit = float(cfg.get("limit_mag", 20.0))
    for i, (t, score, parts, phrase) in enumerate(top):
        mag = f"{t['mag']:.1f}" if t.get("mag") else "—"
        alt = t.get("safe_max_alt", t.get("max_alt"))
        alt = f"{alt:.0f}°" if alt else "—"
        beyond, _delta = suggest.beyond_limit(t, cfg)
        if beyond:
            n_beyond += 1
        flag = f"  ▲ mag>{limit:.0f}" if beyond else ""
        print(f"\n{medals[i]} {t['name']}  [{t['kind']}]  score {score}{flag}")
        print(f"   mag {mag} · alt. máx {alt}")
        print(f"   ES: {phrase['es']}")
        print(f"   EN: {phrase['en']}")
    print(f"\n({len(all_scored)} objetivos evaluados / targets evaluated)")
    if n_beyond:
        print(f"({n_beyond} objetivos por encima de la magnitud límite "
              f"{limit:.0f} / targets beyond the mag {limit:.0f} limit)")


def cmd_explore(args):
    # Explained object card.
    from .core import enrich, narrative, orbits
    if _no_site():
        return 1
    e = enrich.enrich(args.objeto, site=cfg.get("mpc_code"))
    if not e or not e.get("data"):
        print(f"No se encontró / Not found: {args.objeto}")
        return 1
    print(f"== {e['name']} ({e['type']}) ==")
    h = narrative.hook(e)
    print(f"\nES: {h['es']}\nEN: {h['en']}\n")
    for b in narrative.fact_bullets(e):
        print(f"  • ES: {b['es']}")
        print(f"    EN: {b['en']}")


def cmd_post(args):
    # Bilingual post drafts + tweet + PNG charts, and the ES/EN markdown
    # always references every generated image (ready for a web page).
    import re
    from .core import enrich, post
    if _no_site():
        return 1
    e = enrich.enrich(args.objeto, site=cfg.get("mpc_code"))
    if not e or not e.get("data"):
        print(f"No se encontró / Not found: {args.objeto}")
        return 1
    rendered = post.render_post(e, cfg)
    outdir = args.salida or (paths.data_dir() / "posts")
    if args.png:
        # build the charts and have the markdown reference them
        safe = re.sub(r"[^\w.-]+", "_", args.objeto)
        charts = post.build_charts(e, outdir, safe + "_", cfg=cfg)
        written = post.save_outputs(rendered, outdir, args.objeto, e=e,
                                    charts=charts, cfg=cfg)
    else:
        written = post.save_outputs(rendered, outdir, args.objeto)
    for k, p in written.items():
        print(f"[{k}] -> {p}")
    db.mark_posted(args.objeto)


def cmd_solar(args):
    # Sun state summary.
    from .core import solar
    s = solar.solar_now()
    print("== Sol ahora / Sun now ==")
    print(f"SSN: {s.get('ssn')}  F10.7: {s.get('f107')} sfu  Kp: {s.get('kp')}")
    if s.get("flare_7d"):
        f = s["flare_7d"]
        print(f"Fulguración semanal / weekly flare: {f['class']}{f['value']}")
    print(f"Regiones activas / active regions: {s.get('n_regions')}")
    if args.png:
        from .core.sources import sdo
        from .viz import sun_panel
        img = sdo.latest_image("0193", 1024)
        hmi = sdo.latest_image("HMII", 1024)
        s["hmi_img"] = str(hmi) if hmi else None
        out = paths.data_dir() / "posts" / "sun.png"
        sun_panel.draw_sun(img, s, out=out,
                           lang=cfg.ui_language() if hasattr(cfg, "ui_language")
                           else "es")
        print(f"PNG -> {out}")


def cmd_history(args):
    # Observing journal (ADR-036): the derived activity view, grouped by
    # observing night (noon-to-noon local).
    from .core import journal
    nights = journal.build_journal(db, days=90)
    if not nights:
        print("Sin actividad registrada / No activity recorded yet")
        return
    for n in nights[:14]:
        print(f"== Noche / Night {n['night']} ==")
        for e in n["events"]:
            es, en = e["text"]
            print(f"  {journal.hm_local(e['ts'])}  {e['object']:<22s} "
                  f"{es} / {en}")


def cmd_blink(args):
    # Supernova blink: user FITS vs PanSTARRS DR1 g (ADR-018).
    import re
    from .core import blink
    from .viz import blink_view
    try:
        pair = blink.prepare_pair(args.imagen, sn_name=args.nombre,
                                  ra=args.ra, dec=args.dec,
                                  progress=lambda m: print(
                                      f"… {m['es']} / {m['en']}"))
    except blink.BlinkError as err:
        print(f"ES: {err.messages['es']}\nEN: {err.messages['en']}")
        return 1
    # equalize backgrounds so the blink does not pump brightness
    ref_f = blink_view.apply_stretch(pair["ref"],
                                     *blink_view.auto_limits(pair["ref"]))
    obs_f = blink_view.apply_stretch(pair["obs"],
                                     *blink_view.auto_limits(pair["obs"]))
    gain = blink_view.auto_gain(ref_f, obs_f)
    ref8 = blink_view.to_uint8(blink_view.apply_gain(ref_f, gain))
    obs8 = blink_view.to_uint8(obs_f)
    outdir = Path(args.salida) if args.salida else paths.data_dir() / "posts"
    outdir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", pair["name"])
    gif = outdir / f"{safe}_blink.gif"
    png = outdir / f"{safe}_before_after.png"
    lang = cfg.ui_language()
    observatory = cfg.get("observatory_name", "")
    blink_view.make_blink_gif(ref8, obs8, pair["sn_xy"], gif,
                              effect=args.efecto, name=pair["name"],
                              ref_label=pair["ref_label"],
                              watermark=f"NightScribe · {pair['ref_label']}",
                              lang=lang, observatory=observatory,
                              zoom=args.zoom, interval_ms=args.intervalo)
    blink_view.draw_pair(ref8, obs8, pair["sn_xy"], name=pair["name"],
                         ref_label=pair["ref_label"], out=png,
                         watermark=f"NightScribe · {pair['ref_label']}",
                         lang=lang, observatory=observatory, zoom=args.zoom)
    mp4 = None
    print(f"{pair['name']} @ ({pair['ra']:.5f}, {pair['dec']:.5f}) "
          f"— {pair['ref_label']}")
    print(f"GIF -> {gif}")
    print(f"PNG -> {png}")
    if args.video:
        # same animation as the GIF, as H.264 MP4 (for sites without GIFs)
        mp4 = outdir / f"{safe}_blink.mp4"
        blink_view.make_blink_video(
            ref8, obs8, pair["sn_xy"], mp4, effect=args.efecto,
            name=pair["name"], ref_label=pair["ref_label"],
            watermark=f"NightScribe · {pair['ref_label']}",
            lang=lang, observatory=observatory, zoom=args.zoom,
            interval_ms=args.intervalo)
        print(f"MP4 -> {mp4}")
    if args.post:
        # bilingual draft that references the blink resources, ready for a
        # web page: the ES/EN markdown links the GIF/MP4/before-after PNG
        from .core import enrich, post
        en = enrich.enrich(pair["name"], site=cfg.get("mpc_code"))
        if not en:
            en = {"type": "transient", "name": pair["name"], "data": {}}
        rendered = post.render_post(en, cfg)
        resources = {"gif": gif, "pair": png}
        if mp4:
            resources["mp4"] = mp4
        written = post.save_outputs(rendered, outdir, pair["name"], e=en,
                                    resources=resources)
        for k, p in written.items():
            print(f"[{k}] -> {p}")
        db.mark_posted(pair["name"])
def cmd_gui(args):
    # Desktop application.
    from .gui import app
    return app.run()


def _resolve_target(name):
    # @args: name - object name (variable, star)
    # @return: (ra_deg, dec_deg, vsx_dict_or_None) or None when unknown
    from .core.sources import simbad, vsx
    from .core import coords
    v = vsx.lookup(name)
    if v and v.get("ra_deg") is not None:
        return v["ra_deg"], v["dec_deg"], v
    s = simbad.query_id(name)
    if s:
        try:
            return (coords.ra_hms_to_deg(s["ra"]),
                    coords.dec_dms_to_deg(s["dec"]), None)
        except (ValueError, TypeError):
            pass
    return None


def _fits_background(path, progress):
    # The user's own FITS as chart background: stretched luminance plus its
    # WCS, blind-solved with Astrometry.net when the header lacks one (the
    # shared blink loader, ADR-018; the original file is never modified).
    # @args: path - FITS path, progress - callable(str) for stage messages
    # @return: (numpy array 0..1, Wcs) or (None, None) with the reason
    #          printed by the caller-visible BlinkError message
    from .core import blink
    from .viz import blink_view
    try:
        img = blink.load_user_image(
            path, progress=lambda m: progress(f"{m['es']} / {m['en']}"))
    except blink.BlinkError as err:
        logger.warning("no usable FITS background: %s", err.messages["en"])
        return None, None
    data = img["data"]
    stretched = blink_view.apply_stretch(data, *blink_view.auto_limits(data))
    return stretched, img["wcs"]


def cmd_sequence(args):
    # Photometric sequence + comparison chart around a target (ADR-042).
    from .core import compstars
    from .core.sources import cutouts
    from .viz import finder_view
    lang = cfg.ui_language()
    if args.ra is not None and args.dec is not None:
        ra, dec, v = args.ra, args.dec, None
        name = args.objeto or f"J{ra:.4f}{dec:+.4f}"
    else:
        if not args.objeto:
            print("ES: falta el objetivo (nombre o --ra/--dec)\n"
                  "EN: missing target (name or --ra/--dec)")
            return 1
        resolved = _resolve_target(args.objeto)
        if not resolved:
            print(f"ES: no se pudo resolver «{args.objeto}» (VSX/SIMBAD)\n"
                  f"EN: could not resolve '{args.objeto}' (VSX/SIMBAD)")
            return 1
        ra, dec, v = resolved
        name = (v or {}).get("name") or args.objeto
    fov = max(3.0, min(60.0, args.fov))
    field = compstars.load_field(args.catalog, ra, dec, fov)
    if field is None:
        print("ES: VizieR no respondió; inténtalo de nuevo en unos minutos\n"
              "EN: VizieR did not answer; try again in a few minutes")
        return 1
    if field["vsx_warning"]:
        print("⚠ ES: sin consulta VSX (las variables del campo no se marcan)\n"
              "  EN: no VSX query (field variables are not flagged)")
    # background: the user's FITS when given (its WCS rules), else DSS2
    image, wcs, img_label = None, None, "DSS2 color (CDS)"
    if args.fits:
        image, wcs = _fits_background(args.fits, print)
        if wcs is not None:
            x, y = wcs.sky_to_pixel(ra, dec)
            if not (0 <= x < wcs.naxis1 and 0 <= y < wcs.naxis2):
                print("⚠ ES: el objetivo cae fuera de tu imagen; uso DSS2\n"
                      "  EN: the target falls outside your image; using DSS2")
                image, wcs = None, None
            else:
                img_label = Path(args.fits).name
        if wcs is None:
            print("⚠ ES: sin astrometría en tu FITS; uso DSS2\n"
                  "  EN: no astrometry for your FITS; using DSS2")
    if wcs is None and not args.sin_imagen:
        pixscale = fov * 60.0 / 1000.0
        image = cutouts.reference_cutout(ra, dec, size=1000,
                                         pixscale=pixscale)
    # the proposal needs a target magnitude: VSX max, --mag, or the
    # field median as an honest middle
    target_mag = args.mag
    if target_mag is None and v and v.get("max") is not None:
        target_mag = v["max"]
    if target_mag is None and field["stars"]:
        mags = sorted(s["mag"] for s in field["stars"])
        target_mag = mags[len(mags) // 2]
    seq = compstars.propose_comps(field["stars"], target_mag, n=args.comps)
    entries = seq["comps"] + ([seq["check"]] if seq["check"] else [])
    outdir = Path(args.salida) if args.salida else paths.data_dir() / "sequences"
    outdir.mkdir(parents=True, exist_ok=True)
    import re
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    csv_path = compstars.export_sequence_csv(
        entries, outdir / f"{safe}_secuencia.csv", target_name=name,
        catalog_label=field["catalog_name"])
    png_path = outdir / f"{safe}_carta.png"
    target = {"name": name, "ra": ra, "dec": dec}
    finder_view.draw_finder(field, target=target, entries=entries,
                            image=image, wcs=wcs, out=png_path, lang=lang,
                            watermark=f"NightScribe · {img_label}")
    print(f"{name} @ ({ra:.5f}, {dec:+.5f}) — {field['catalog_name']}, "
          f"{len(entries)} estrellas / stars (objetivo mag "
          f"{target_mag:.2f} / target)")
    for e in entries:
        star = e["star"]
        print(f"  {e['name']:<7s} {star['band']} {star['mag']:.2f}  "
              f"ES: {e['why']['es']}  /  EN: {e['why']['en']}")
    print(f"CSV -> {csv_path}")
    print(f"PNG -> {png_path}")


def cmd_project(args):
    # Minimal project management from the CLI (ADR-019, GUI-first).
    from .core import project as proj_mod
    if args.action == "list":
        projects = proj_mod.list_projects(db, args.status)
        if not projects:
            print("No projects / Sin proyectos")
            return
        for p in projects:
            cur = proj_mod.current_step(db, p["id"])
            step = cur or "done"
            star = "★ " if p.get("favorite") else ""
            outcome = f"  ({p['outcome']})" if p.get("outcome") else ""
            print(f"  [{p['id']:3d}] {star}[{p['kind']:7s}] "
                  f"{p['object_name']:<24s} {p['status']:8s} "
                  f"step={step}{outcome}")
    elif args.action == "create":
        p = proj_mod.create(db, args.kind, args.name)
        if p:
            print(f"Created project {p['id']}: [{p['kind']}] {p['object_name']}")
        else:
            print(f"Bad kind '{args.kind}' (valid: {', '.join(proj_mod.VALID_KINDS)})")
            return 1
    elif args.action == "advance":
        p = proj_mod.advance(db, args.id)
        if p:
            cur = proj_mod.current_step(db, p["id"]) or "done"
            print(f"Project {p['id']} -> step={cur}, status={p['status']}")
        else:
            print(f"Project {args.id} not found")
            return 1
    elif args.action == "close":
        p = proj_mod.close(db, args.id, outcome=args.outcome)
        if p:
            print(f"Closed project {p['id']}: status={p['status']}"
                  f" outcome={p.get('outcome')}")
        else:
            print(f"Project {args.id} not found or not active")
            return 1
    elif args.action == "reopen":
        p = proj_mod.reopen(db, args.id)
        if p:
            print(f"Reopened project {p['id']}: status={p['status']}")
        else:
            print(f"Project {args.id} not found")
            return 1
    elif args.action == "show":
        p = proj_mod.get(db, args.id)
        if not p:
            print(f"Project {args.id} not found")
            return 1
        print(f"== [{p['kind']}] {p['object_name']} — {p['status']} ==")
        print(f"  folder: {proj_mod.storage_dir(p)}")
        for s in p["steps"]:
            print(f"  {s['status']:8s} {s['step']}")
        for f in p["files"]:
            print(f"  file: {f['kind']:10s} {f['path']}")
    elif args.action == "files":
        files = proj_mod.list_files(db, args.id)
        if not files:
            print(f"Project {args.id} has no files")
            return
        for f in files:
            print(f"  [{f['kind']:10s}] {f['path']}")


def main(argv=None):
    # CLI entry point.
    # @args: argv - optional argument list (tests)
    # @return: exit code
    parser = argparse.ArgumentParser(
        prog="nightscribe",
        description="Planifica tu noche, entiende cada objeto, cuenta tu ciencia.")
    from .version import full_version
    parser.add_argument("--version", action="version",
                        version=f"{__app_name__} {full_version()}")
    parser.add_argument("--verbose", "-v", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("tonight", help="mejores objetivos de esta noche")
    p.add_argument("--fecha", help="YYYY-MM-DD (noche, UTC)")
    p.add_argument("--top", type=int, default=3)
    p.set_defaults(func=cmd_tonight)

    p = sub.add_parser("explore", help="ficha explicada de un objeto")
    p.add_argument("objeto")
    p.set_defaults(func=cmd_explore)

    p = sub.add_parser("post", help="borradores ES/EN + tuit")
    p.add_argument("objeto")
    p.add_argument("--salida", help="directorio de salida")
    p.add_argument("--png", action="store_true", help="generar gráficos PNG")
    p.set_defaults(func=cmd_post)

    p = sub.add_parser("solar", help="estado del Sol")
    p.add_argument("--png", action="store_true")
    p.set_defaults(func=cmd_solar)

    p = sub.add_parser("blink", help="blink SN: tu FITS vs PanSTARRS DR1 g")
    p.add_argument("nombre", help="nombre de la SN (p. ej. 2026ziz)")
    p.add_argument("imagen", help="FITS con astrometría (WCS)")
    p.add_argument("--salida", help="directorio de salida")
    p.add_argument("--efecto", choices=["blink", "fade"], default="blink")
    p.add_argument("--ra", type=float, help="RA manual (grados)")
    p.add_argument("--dec", type=float, help="Dec manual (grados)")
    p.add_argument("--zoom", type=int, default=1, choices=[1, 2, 4],
                   help="recorte alrededor de la SN (1 = completo)")
    p.add_argument("--intervalo", type=int, default=500,
                   help="duración de cada frame del blink (ms)")
    p.add_argument("--video", action="store_true",
                   help="exportar también el blink como vídeo MP4 (H.264)")
    p.add_argument("--post", action="store_true",
                   help="generar borrador ES/EN + tuit que referencia el blink")
    p.set_defaults(func=cmd_blink)

    p = sub.add_parser("history", help="historial de observaciones")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("sequence",
                       help="secuencia fotométrica + carta de comparación")
    p.add_argument("objeto", nargs="?", default=None,
                   help="nombre del objetivo (VSX/SIMBAD)")
    p.add_argument("--ra", type=float, help="RA del centro (grados)")
    p.add_argument("--dec", type=float, help="Dec del centro (grados)")
    p.add_argument("--catalog", choices=["gaia", "apass"], default="gaia",
                   help="catálogo de magnitudes (por defecto Gaia EDR3)")
    p.add_argument("--fov", type=float, default=18.0,
                   help="campo de visión en minutos de arco (3-60)")
    p.add_argument("--comps", type=int, default=8,
                   help="número de estrellas de comparación propuestas")
    p.add_argument("--mag", type=float,
                   help="magnitud del objetivo (por defecto: máx. VSX o "
                        "mediana del campo)")
    p.add_argument("--fits", help="tu FITS como fondo (WCS propio o "
                                  "resuelto con Astrometry.net)")
    p.add_argument("--sin-imagen", action="store_true",
                   help="sin imagen de fondo (solo anotaciones)")
    p.add_argument("--salida", help="directorio de salida")
    p.set_defaults(func=cmd_sequence)

    p = sub.add_parser("gui", help="aplicación de escritorio")
    p.set_defaults(func=cmd_gui)

    p = sub.add_parser("project", help="gestión de proyectos (CLI mínimo)")
    p_sub = p.add_subparsers(dest="action", required=True)
    p_list = p_sub.add_parser("list", help="listar proyectos")
    p_list.add_argument("--status", choices=["active", "done", "archived"],
                        default=None)
    p_create = p_sub.add_parser("create", help="crear un proyecto")
    p_create.add_argument("--kind", required=True,
                          help="sn|neo|comet|pccp|transit|hads|variable")
    p_create.add_argument("--name", required=True, help="object name")
    p_advance = p_sub.add_parser("advance", help="avanzar un paso")
    p_advance.add_argument("id", type=int, help="project id")
    p_show = p_sub.add_parser("show", help="mostrar un proyecto")
    p_show.add_argument("id", type=int, help="project id")
    p_close = p_sub.add_parser("close", help="cerrar un proyecto")
    p_close.add_argument("id", type=int, help="project id")
    p_close.add_argument("--outcome", default=None,
                         help="resultado final (texto libre)")
    p_reopen = p_sub.add_parser("reopen", help="reabrir un proyecto")
    p_reopen.add_argument("id", type=int, help="project id")
    p_files = p_sub.add_parser("files", help="listar ficheros del proyecto")
    p_files.add_argument("id", type=int, help="project id")
    p.set_defaults(func=cmd_project)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
