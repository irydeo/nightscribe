############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometry engine benchmark: the report
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Turn the benchmark JSONs into the tables the decision is read from.

Bench code: not imported by the app. It reads what the other three scripts
wrote (inject.json, series.json, series_seeing.json) and writes BENCH.md.

Usage:
    python tools/bench/report.py [--out /tmp/opencode/nsbench]
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness as H                                    # noqa: E402

MMAG = 2.5 / math.log(10.0) * 1000.0

ENGINE_LABELS = {
    "ours": "nuestra (matched filter)",
    "ours_refined": "momentos (barato)",
    "ours_none": "sin centroide",
    "ours_pu_cen": "photutils cen + nuestra aritmetica",
    "pu_cen_ours": "nuestro cen + photutils aritmetica",
    "pu": "photutils completa",
}


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def inject_tables(rep, out):
    if not rep:
        return
    out.append("## 1. Medida individual: inyeccion y recuperacion\n")
    out.append("Estrella de flujo conocido inyectada en copias de frames reales, "
               "medida desde un click dibujado a su alrededor. El flujo se escala "
               "al SNR nominal contra el **suelo de ruido real** de la placa "
               "(medido a pelo en cielo vacio, sin el corte de positividad de los "
               "motores).\n")
    for ds in rep:
        out.append(f"### {ds['dataset']}\n")
        out.append("| motor | SNR | ideal | sesgo (mmag) | rms (mmag) | +-se | "
                   "rms/suelo | pos_rms (px) | n | fallos |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for eng, block in ds["engines"].items():
            for snr, b in block.items():
                if b["rms_mmag"] is None:
                    continue
                ratio = b["rms_mmag"] / b["ideal_mmag"]
                out.append(
                    f"| {ENGINE_LABELS.get(eng, eng)} | {float(snr):.0f} | "
                    f"{b['ideal_mmag']:.1f} | {b['bias_mmag']:+.2f} | "
                    f"{b['rms_mmag']:.2f} | {b['rms_se_mmag'] or 0:.2f} | "
                    f"{ratio:.3f} | {b['pos_rms_px'] or 0:.3f} | {b['n']} | "
                    f"{b['n_failed']} |")
        out.append("")


def series_tables(rep, out, title, note=""):
    if not rep:
        return
    out.append(f"## {title}\n")
    if note:
        out.append(note + "\n")
    out.append("| conjunto | frames | motor | ms/frame | rms mediano (mmag) | "
               "rms minimo | err declarado | puntos | alineados |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for ds in rep:
        for eng, blk in ds["engines"].items():
            curves = blk["curves"]
            rms = [c["rms_mmag"] for c in curves.values()
                   if c["rms_mmag"] is not None]
            errs = [c["err_med_mmag"] for c in curves.values()
                    if c["err_med_mmag"] is not None]
            ns = [c["n"] for c in curves.values() if c["n"]]
            med = sorted(rms)[len(rms) // 2] if rms else float("nan")
            out.append(
                f"| {ds['dataset']} | {ds['n_frames']} | "
                f"{ENGINE_LABELS.get(eng, eng)} | {blk['ms_per_frame']:.1f} | "
                f"{med:.2f} | {min(rms) if rms else float('nan'):.2f} | "
                f"{(sorted(errs)[len(errs)//2] if errs else float('nan')):.2f} | "
                f"{int(sorted(ns)[len(ns)//2]) if ns else 0} | {blk['align']} |")
    out.append("")
    # la comparacion directa
    out.append("### Comparacion directa (mismo conjunto, mismas comparsas, "
               "mismas aperturas)\n")
    out.append("| conjunto | motor base | rms base | motor nuevo | rms nuevo | "
               "mejora | velocidad |")
    out.append("|---|---|---|---|---|---|---|")
    for ds in rep:
        engs = list(ds["engines"])
        if len(engs) < 2:
            continue
        base, new = engs[0], engs[-1]
        def _med(e):
            rms = [c["rms_mmag"] for c in ds["engines"][e]["curves"].values()
                   if c["rms_mmag"] is not None]
            return sorted(rms)[len(rms) // 2] if rms else float("nan")
        rb, rn = _med(base), _med(new)
        out.append(
            f"| {ds['dataset']} | {ENGINE_LABELS.get(base, base)} | {rb:.2f} | "
            f"{ENGINE_LABELS.get(new, new)} | {rn:.2f} | "
            f"{(1 - rn / rb) * 100:+.1f} % | "
            f"{ds['engines'][base]['ms_per_frame'] / ds['engines'][new]['ms_per_frame']:.2f}x |")
    out.append("")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out_dir = args.out or H.results_dir()
    lines = ["# Motor de fotometria propio frente a photutils: la medida\n",
             "Generado por `tools/bench/report.py`. Los numeros salen de "
             "`inject.json`, `series.json` y `series_seeing.json`.\n"]
    inject_tables(_load(os.path.join(out_dir, "inject.json")), lines)
    series_tables(_load(os.path.join(out_dir, "series.json")), lines,
                  "2. Serie real: mismo conjunto, mismas comparsas, "
                  "solo cambia la medida")
    series_tables(_load(os.path.join(out_dir, "series_seeing.json")), lines,
                  "3. Serie real con la apertura siguiendo el seeing (H3)",
                  "El camino que la app recomienda: la apertura escala con el "
                  "FWHM de cada frame y la receta de placa recibe ese FWHM.")
    path = os.path.join(out_dir, "BENCH.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"informe -> {path}")
    print("\n".join(lines[:6]))


if __name__ == "__main__":
    main()
