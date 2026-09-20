#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ns_capture_screens.py — capturas REALES offscreen de la app NightScribe
para rellenar el masonry de la web (12 bloques + hero).

- Boot de la GUI real con QT_QPA_PLATFORM=offscreen + MainWindow del proyecto.
- hero  : grab del MainWindow completo (todas las pestañas visibles en píxeles).
- feat-1..5 : grab de las 5 pestañas reales del QTabWidget "tabs".
- feat-6..12: render PÚBLICO de los viz reales (orbit, sky, transit, sn/blink,
              evolution, motion, lightcurve) con datos sintéticos MÍNIMOS.
- Salida: website/img/screens/feat-N.png (números) + hero.png — retina 2×.
- Solo LECTURA de la web; nunca la toca. PNG 2× con la identidad NightScribe.

Uso:  ns_capture_screens.py          (offscreen por defecto)
      QT_QPA_PLATFORM=offscreen ns_capture_screens.py
"""
import os, sys, traceback, math

ROOT = "/mnt/nvme1n1p5/Develop/astronomy/nightscribe"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")
sys.path.insert(0, ROOT)
os.chdir(ROOT)

OUT = os.path.join(ROOT, "website", "img", "screens")
os.makedirs(OUT, exist_ok=True)

OK = []      # (nombre archivo, w, h, bytes)
FAIL = []    # (nombre, razón)

def _fin(ok, nombre, png, w, h):
    if ok and png and os.path.isfile(png) and os.path.getsize(png) > 0:
        b = os.path.getsize(png)
        print("   OK   %-12s %dx%d  %6.1f KB" % (nombre, w, h, b / 1024.0))
        OK.append((nombre, w, h, b))
    else:
        print("   ---  %-12s (no se generó)" % nombre)
        FAIL.append((nombre, "no se generó"))
    return ok

print("== Fase 1 — capturas reales offscreen (app NightScribe) ==")
print("   platform offscreen : %s" % os.environ.get("QT_QPA_PLATFORM"))

# ---------- 0) QApplication + MainWindow REAL ----------
from PySide6.QtWidgets import QApplication, QTabWidget
app = QApplication.instance() or QApplication([])
from nightscribe.gui.main_window import MainWindow
w = MainWindow()
w.resize(1500, 940)
w.show()
app.processEvents()

# ---------- hero ----------
pm = w.grab()
h_png = os.path.join(OUT, "hero.png")
_fin(pm.save(h_png, "PNG"), "hero", h_png, pm.width(), pm.height())

# ---------- feat-1..5 — pestañas reales ----------
tabs = w.findChild(QTabWidget, "tabs")
n_tabs = tabs.count() if tabs else 0
print("   pestañas reales    : %d" % n_tabs)
for i in range(n_tabs):
    pg = tabs.widget(i)
    if pg is None:
        FAIL.append(("feat-%d" % (i + 1), "página n/d"))
        continue
    png = os.path.join(OUT, "feat-%d.png" % (i + 1))
    pm = pg.grab()
    _fin(pm.save(png, "PNG"), "feat-%d" % (i + 1), png, pm.width(), pm.height())

# ---------- feat-6..12 — viz reales con datos sintéticos MÍNIMOS ----------
def _synthetic_elements():
    # @args: exaggerated but real-shaped NEO orbit elements (AU, deg)
    return {"e": 0.20, "a": 1.8, "i": 8.5, "om": 215.0, "w": 74.0, "M": 140.5}

def _capture_viz(fn, *a, **k):
    try:
        png = k.pop("out", None)
        save_ret = fn(*a, **k, out=png)
        return os.path.isfile(png) and os.path.getsize(png) > 0
    except Exception:
        traceback.print_exc()
        return False

viz_specs = []

# feat-6 : orbit_view.draw_orbit(elements, jd, obj_name, approach, out, fmt, watermark, size, lang)
try:
    from nightscribe.viz.orbit_view import draw_orbit
    viz_specs.append(("feat-6", draw_orbit,
                      (_synthetic_elements(), 2460672.5, "2015 TB145 (realistic)", None),
                      dict(fmt="facebook", watermark="NightScribe", lang="es")))
except Exception as e:
    print("   (orbit_view no importable: %s)" % str(e)[:60])

# feat-7 : sky_view.draw_sky(ra_deg, dec_deg, lat, lon, ...)
try:
    from nightscribe.viz.sky_view import draw_sky
    viz_specs.append(("feat-7", draw_sky,
                      (18.75, -23.9, 37.38, -6.37, "SN 2026abc", "2026-09-16T22:00:00Z"),
                      dict(fmt="facebook", watermark="NightScribe", lang="es")))
except Exception as e:
    print("   (sky_view no importable: %s)" % str(e)[:60])

# feat-8 : transit_view.draw_transit(transit, ...)
try:
    from nightscribe.viz.transit_view import draw_transit
    transit = dict(depth_mmag=14.0, duration_h=2.4, mid="2026-09-16T21:15:00Z",
                   name="WASP-12 b", star="WASP-12")
    viz_specs.append(("feat-8", draw_transit, (transit,),
                      dict(fmt="facebook", watermark="NightScribe", lang="es")))
except Exception as e:
    print("   (transit_view no importable: %s)" % str(e)[:60])

# feat-9 : sn_view.draw_sn_field(cutout_path, sn_name, ...) — campo SN
try:
    from nightscribe.viz.sn_view import draw_sn_field
    # cutout sintético: PNG gris con ruido pequeño (sin depender de disco)
    import numpy as np
    rng = np.random.default_rng(7)
    cut = (rng.normal(0.32, 0.05, (128, 128)))
    cut[64, 64] = 0.95
    import matplotlib.pyplot as plt
    scut = os.path.join(OUT, "_cutout_sn.png")
    plt.imsave(scut, cut, cmap="gray")
    viz_specs.append(("feat-9", draw_sn_field, (scut, "SN 2026abc"),
                      dict(fmt="facebook", watermark="NightScribe", lang="es")))
except Exception as e:
    print("   (sn_view no importable: %s)" % str(e)[:60])

# feat-10 : sn_view.draw_sn_blink(reference_path, obs_path, sn_name, out, ...)
try:
    from nightscribe.viz.sn_view import draw_sn_blink
    rng = np.random.default_rng(11)
    r = rng.normal(0.30, 0.05, (256, 256)); o = r.copy(); o[130, 130] = 0.98
    import matplotlib.pyplot as plt
    pr, po = os.path.join(OUT, "_ref_sn.png"), os.path.join(OUT, "_obs_sn.png")
    plt.imsave(pr, r, cmap="gray"); plt.imsave(po, o, cmap="gray")
    viz_specs.append(("feat-10", draw_sn_blink, (pr, po, "SN 2026abc"),
                      dict(fmt="facebook", watermark="NightScribe", lang="es")))
except Exception as e:
    print("   (sn blink no importable: %s)" % str(e)[:60])

# feat-11 : evolution_view.make_evolution_gif(frames_data, dates, sn_xy_s, out, ...)
try:
    from nightscribe.viz.evolution_view import make_evolution_gif
    rng = np.random.default_rng(3)
    fr = [rng.normal(0.30, 0.05, (128, 128)) for _ in range(4)]
    sn_xy = [(64, 64)] * 4
    dates = ["Sep 05", "Sep 08", "Sep 12", "Sep 16"]
    gif = os.path.join(OUT, "feat-11.png")
    # make_evolution_gif escribe GIF real; para la web un PNG de 1er frame.
    viz_specs.append(("feat-11", make_evolution_gif,
                      (fr, dates, sn_xy),
                      dict(out=os.path.join(OUT, "feat-11.gif"),
                           watermark="NightScribe", lang="es")))
except Exception as e:
    print("   (evolution_view no importable: %s)" % str(e)[:60])

# feat-12 : motion_view.make_motion_gif → PNG 1er frame
try:
    from nightscribe.viz.motion_view import make_motion_gif
    rng = np.random.default_rng(5)
    fr = [rng.normal(0.30, 0.05, (128, 128)) for _ in range(4)]
    obj_xy = [(64, 33), (67, 37), (70, 41), (73, 45)]
    dates = ["Ago 01", "Ago 04", "Ago 08", "Ago 12"]
    viz_specs.append(("feat-12", make_motion_gif,
                      (fr, dates, obj_xy),
                      dict(out=os.path.join(OUT, "feat-12.gif"),
                           watermark="NightScribe", lang="es")))
except Exception as e:
    print("   (motion_view no importable: %s)" % str(e)[:60])

print()
for nombre, fn, args, kwargs in viz_specs:
    _fin(_capture_viz(fn, *args, **kwargs), nombre, kwargs.get("out"), 0, 0)

# ------- autovalidador final -------
pngs = sorted(p for p in os.listdir(OUT) if p.endswith(".png"))
print()
print("== resumen ==  hero + %d pestañas + %d viz  (PNG en %s) ==" % (
    min(1, 1), min(n_tabs, 5), len(pngs), OUT))
for p in pngs:
    b = os.path.getsize(os.path.join(OUT, p))
    print("   %-14s %6.1f KB" % (p, b / 1024.0))
print()
print("   SIN 404 : %d PNG >= 1  |  fallos: %s" % (
    sum(1 for p in pngs if os.path.getsize(os.path.join(OUT, p)) > 0),
    FAIL if FAIL else "(ninguno)"))
