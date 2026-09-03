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

from . import __app_name__, __version__, config, paths
from .config import config as cfg
from .core.db import db

logger = logging.getLogger(__name__)


def _setup_logging(verbose):
    # @args: verbose - bool
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s")


def cmd_tonight(args):
    # Best targets for tonight at the configured site.
    from .core import planner, suggest
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
    # Observation history.
    rows = db.history(50)
    if not rows:
        print("Sin observaciones registradas / No observations recorded yet")
        return
    print("== Historial / History ==")
    for r in rows:
        posted = "✓ post" if r["posted"] else "  —   "
        print(f"{r['obs_date']}  {r['object']:<22s} [{r['type'] or '?':8s}] {posted}")


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
            print(f"  [{p['id']:3d}] [{p['kind']:7s}] {p['object_name']:<24s} "
                  f"{p['status']:8s} step={step}")
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
    elif args.action == "show":
        p = proj_mod.get(db, args.id)
        if not p:
            print(f"Project {args.id} not found")
            return 1
        print(f"== [{p['kind']}] {p['object_name']} — {p['status']} ==")
        for s in p["steps"]:
            print(f"  {s['status']:8s} {s['step']}")
        for f in p["files"]:
            print(f"  file: {f['kind']:10s} {f['path']}")


def main(argv=None):
    # CLI entry point.
    # @args: argv - optional argument list (tests)
    # @return: exit code
    parser = argparse.ArgumentParser(
        prog="nightscribe",
        description="Planifica tu noche, entiende cada objeto, cuenta tu ciencia.")
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

    p = sub.add_parser("gui", help="aplicación de escritorio")
    p.set_defaults(func=cmd_gui)

    p = sub.add_parser("project", help="gestión de proyectos (CLI mínimo)")
    p_sub = p.add_subparsers(dest="action", required=True)
    p_list = p_sub.add_parser("list", help="listar proyectos")
    p_list.add_argument("--status", choices=["active", "done", "archived"],
                        default=None)
    p_create = p_sub.add_parser("create", help="crear un proyecto")
    p_create.add_argument("--kind", required=True,
                          help="sn|neo|comet|pccp|transit")
    p_create.add_argument("--name", required=True, help="object name")
    p_advance = p_sub.add_parser("advance", help="avanzar un paso")
    p_advance.add_argument("id", type=int, help="project id")
    p_show = p_sub.add_parser("show", help="mostrar un proyecto")
    p_show.add_argument("id", type=int, help="project id")
    p.set_defaults(func=cmd_project)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
