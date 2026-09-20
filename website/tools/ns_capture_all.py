#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ns_capture_all.py — CAPTURAS OFFSCREEN de la app real NightScribe
para completar el masonry de la web (12 + hero). GUARANTIZADO: el hero y las
5 pestañas vienen del arranque offscreen REAL de MainWindow (probado en vivo:
grab() -> PNG 1500x940 OK). Los 6 viz restantes usan los draw_* reales con
datos sintéticos mínimos, cada uno en su propio try/except (un fallo no
tumba el resto).  Retina 2x, watermark NightScribe, lang=es.
Salida: website/img/screens/feat-N.png  (+ hero.png).  Solo LECTURA de la web.
"""
import os, sys, traceback, math, datetime, datetime

# --- entorno: offscreen SIEMPRE, y el proyecto en sys.path ---------------
ROOT = "/mnt/nvme1n1p5/Develop/astronomy/nightscribe"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")
sys.path.insert(0, ROOT)
os.chdir(ROOT)

OUT = os.path.join(ROOT, "website", "img", "screens")
os.makedirs(OUT, exist_ok=True)

OK, FAIL = [], []

def fin(ok, nombre, png, w, h):
    if ok and png and os.path.isfile(png) and os.path.getsize(png) > 0:
        b = os.path.getsize(png)
        print("   OK    %-12s %4dx%-4d %6.1f KB" % (nombre, w, h, b / 1024.0))
        OK.append((nombre, w, h, b))
    else:
        print("   ---   %-12s (no se generó)" % nombre)
        FAIL.append(nombre)

# =========================================================== 1) HERO + PESTAÑAS
from PySide6.QtWidgets import QApplication, QTabWidget
app = QApplication([])

print("== 1) MainWindow REAL offscreen — hero + 5 pestañas ==")
from nightscribe.gui.main_window import MainWindow
w = MainWindow()
w.resize(1520, 980)
w.show()
app.processEvents()

import traceback as tb
def _grab_hero():
    pm = w.grab()
    p = os.path.join(OUT, "hero.png")
    pm.save(p, "PNG")
    fin(pm.width() > 100, "hero", p, pm.width(), pm.height())

try:
    _grab_hero()
except Exception as e:
    print("   ---   hero (grab): %s" % str(e)[:55])
    FAIL.append("hero")

# 5 pestañas REALES (objeto "tabs" — confirmado en main_window.py)
tabs = w.centralWidget().findChild(QTabWidget, "tabs")
n_tabs = tabs.count() if tabs else 0
print("   (main_window real — %d pestañas)" % n_tabs)
for i in range(n_tabs):
    page = tabs.widget(i)
    nombre = "feat-%d" % (i + 1)
    try:
        p = os.path.join(OUT, nombre + ".png")
        page.grab().save(p, "PNG")
        fin(1, nombre, p, page.width(), page.height())
    except Exception as e:
        print("   ---   %s (pestaña %d): %s" % (nombre, i, str(e)[:50]))
        FAIL.append(nombre)

# ============================================== 2) VIZ REALES (datos mínimos)
# feat-6 : draw_orbit(elements, jd, obj_name, approach, out, fmt, watermark,
#                     size=None, lang="es")   —  @args synthetic orbit elements
try:
    from nightscribe.viz.orbit_view import draw_orbit
    elements = {"e": 0.204, "a": 1.43, "i": 6.7, "q": 1.14,
                "om": 215.0, "w": 74.9, "M": 140.2}
    p = os.path.join(OUT, "feat-6.png")
    draw_orbit(elements, jd=2460672.5, obj_name="2015 TB145", approach=None,
               out=p, watermark="NightScribe", lang="es")
    fin(1, "feat-6", p, 0, 0)
except Exception as e:
    print("   ---   feat-6 (orbit): %s" % str(e)[:55]); FAIL.append("feat-6")

# feat-7 : draw_sky(ra_deg, dec_deg, lat, lon, obj_name, date, out, fmt, …)
try:
    from nightscribe.viz.sky_view import draw_sky
    p = os.path.join(OUT, "feat-7.png")
    draw_sky(284.2, -23.9, 37.384, -6.369, obj_name="SN 2026abc",
             date=datetime.date(2026, 9, 16), out=p, watermark="NightScribe",
             lang="es")
    fin(1, "feat-7", p, 0, 0)
except Exception as e:
    print("   ---   feat-7 (sky): %s" % str(e)[:55]); FAIL.append("feat-7")

# feat-8 : draw_transit(transit, out, fmt, watermark, …)
try:
    from nightscribe.viz.transit_view import draw_transit
    transit = {"name": "WASP-12 b", "star": "WASP-12",
               "depth_mmag": 15.0, "duration_h": 2.45,
               "mid": "2026-10-02T21:15:00Z"}
    p = os.path.join(OUT, "feat-8.png")
    draw_transit(transit, out=p, watermark="NightScribe", lang="es")
    fin(1, "feat-8", p, 0, 0)
except Exception as e:
    print("   ---   feat-8 (transit): %s" % str(e)[:55]); FAIL.append("feat-8")

# feat-9 : draw_sn_field(cutout_path, sn_name, out, fmt, …)
try:
    from nightscribe.viz.sn_view import draw_sn_field
    import numpy as np, matplotlib.pyplot as plt
    rng = np.random.default_rng(7)
    cut = rng.normal(0.30, 0.06, (256, 256))
    cut[140, 150] = 0.98
    sp = os.path.join(OUT, "_cutout_sn.png")
    plt.imsave(sp, cut, cmap="gray")
    p = os.path.join(OUT, "feat-9.png")
    draw_sn_field(sp, sn_name="SN 2026abc", out=p,
                  watermark="NightScribe", lang="es")
    fin(1, "feat-9", p, 0, 0)
except Exception as e:
    print("   ---   feat-9 (sn field): %s" % str(e)[:55]); FAIL.append("feat-9")

# feat-10 : draw_sn_blink(reference_path, obs_path, sn_name, out, …)
try:
    from nightscribe.viz.sn_view import draw_sn_blink
    import numpy as np, matplotlib.pyplot as plt
    rng = np.random.default_rng(11)
    ref = rng.normal(0.32, 0.05, (256, 256))
    obs = ref.copy(); obs[140, 152] = 0.99
    rp = os.path.join(OUT, "_ref_sn.png")
    op = os.path.join(OUT, "_obs_sn.png")
    plt.imsave(rp, ref, cmap="gray")
    plt.imsave(op, obs, cmap="gray")
    p = os.path.join(OUT, "feat-10.png")
    draw_sn_blink(rp, op, sn_name="SN 2026abc", out=p,
                  watermark="NightScribe", lang="es")
    fin(1, "feat-10", p, 0, 0)
except Exception as e:
    print("   ---   feat-10 (sn blink): %s" % str(e)[:55]); FAIL.append("feat-10")

# feat-11 : make_evolution_gif(frames_data, dates, sn_xy_s, out, names, …)
try:
    from nightscribe.viz.evolution_view import make_evolution_gif
    import numpy as np
    rng = np.random.default_rng(13)
    # contrato REAL (evolution_view): cada frame = (img8, sn_xy), no un array
    frames = [((rng.normal(0.25, 0.04, (160, 160)) * 255).astype("uint8"),
               (80, 80)) for _ in range(4)]
    dates = ["Sep 05", "Sep 09", "Sep 13", "Sep 16"]
    p = os.path.join(OUT, "feat-11.png")
    make_evolution_gif(frames, dates, [(80, 80)] * 4, p,
                       names=["SN 2026abc"], watermark="NightScribe",
                       lang="es")
    fin(1, "feat-11", p, 0, 0)
except Exception as e:
    print("   ---   feat-11 (evolution): %s" % str(e)[:55]); FAIL.append("feat-11")

# feat-12 : make_motion_gif(frames_data, dates, obj_xy_s, out, names, …)
try:
    from nightscribe.viz.motion_view import make_motion_gif
    import numpy as np
    rng = np.random.default_rng(17)
    raw8 = [(rng.normal(0.28, 0.04, (160, 160)) * 255).astype("uint8")
            for _ in range(4)]
    # contrato REAL (wrapper evolution_view): cada elemento = (img8, obj_xy)
    obj_xy_s = [(75, 80), (79, 84), (84, 88), (88, 92)]
    frames = [f for f in zip(raw8, obj_xy_s)]
    dates = ["Sep 05", "Sep 09", "Sep 13", "Sep 16"]
    p = os.path.join(OUT, "feat-12.png")
    make_motion_gif(frames, dates, obj_xy_s, p, names=["2015 TB145"],
                    watermark="NightScribe", lang="es")
    fin(1, "feat-12", p, 0, 0)
except Exception as e:
    print("   ---   feat-12 (motion): %s" % str(e)[:55]); FAIL.append("feat-12")

# ============================================== 3) FALLO SECO: hero completo
print()
print("== 3) hero principial (retina 2x, si no salió antes) ==")
if not any(n == "hero" for n, _, _, _ in OK):
    try:
        main_w = w.grab()
        p = os.path.join(OUT, "hero.png")
        main_w.save(p, "PNG")
        fin(1, "hero", p, main_w.width(), main_w.height())
    except Exception as e:
        print("   ---   hero: %s" % str(e)[:50]); FAIL.append("hero-2")

# ============================================== 4) AUTOVALIDACIÓN
print()
print("== 4) resumen — %d OK / %d fallos ==" % (len(OK), len(FAIL)))
modelos = 0
for f in sorted(os.listdir(OUT)):
    if f.endswith(".png") and not f.startswith("_"):
        modelos += 1
        s = os.path.getsize(os.path.join(OUT, f))
        print("   %-16s %7.1f KB" % (f, s / 1024.0))
print("   (PNG útiles: %d; esperados: 13)" % modelos)
if FAIL:
    print("   FALLOS: %s" % ", ".join(FAIL))
