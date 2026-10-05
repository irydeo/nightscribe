# Campaña SNR del objeto débil

> Continuación de `docs/PLANS/astrometry-minor-planets/`. Aquella campaña
> cerró el bucle: medir, reportar y liberar espacio. Esta sube la **señal
> frente al ruido** del objeto, que es lo que decide si una observación se
> puede enviar (el MPC pide SNR ≥ 20 por observación) y cuánto se puede
> apretar hacia objetos más débiles.

## Por qué

El track & stack ya concentra la luz del objeto sumando muchas tomas, pero
el pipeline deja SNR sobre la mesa en cuatro sitios distintos, y cada uno
se puede medir por separado:

1. **Fotogramas que no se apilan.** Una visita que mezcla dos tandas de
   observación perdía la segunda entera. Medido en 2025 UR: 62 de 140
   tomas fuera, y recuperarlas subió el SNR del apilado de estrellas de
   **1.826 a 2.702 (×1,48)**.
2. **Co-adición con peso igual.** La combinación óptima de tomas con
   ruidos distintos es la media ponderada por 1/σ²; hoy `combine` promedia
   a peso igual, y una noche con nubes o Luna se pierde sin decirlo.
3. **Medida por apertura.** A bajo SNR el detector óptimo para una PSF
   conocida es el filtro adaptado (sumar píxel × PSF / σ²), no una
   apertura dura que pesa igual el núcleo y las alas.
4. **Fotogramas sin flat.** La mayoría no tiene flats y el motor solo
   avisa: un pseudo-flat construido de las propias tomas corrige viñeteado
   y motas y además normaliza el fondo.

Y una cosa que **no** vamos a hacer: meter un denoiser de IA en el camino
de la medida. La razón está medida y razonada en el ADR correspondiente
(ruido correlacionado, incertidumbres que dejarían de ser ciertas).

## Orden, y por qué

**P0 → P4 → P1 → P2 → P3 → P5**, con P6 como decisión escrita.

Deliberadamente **el instrumento antes de las mejoras**: P4 (inyección y
recuperación) mide lo que el pipeline alcanza de verdad, así que cada
mejora posterior se justifica con un número, no con la intuición. Es la
misma disciplina que llevó a medir la ganancia de P0 sobre datos reales en
vez de suponerla.

| Fase | Qué | Estado |
| --- | --- | --- |
| **P0** | Los fotogramas que se quedan en el suelo | **Hecho** (`p0-fotogramas-perdidos.md`) |
| **P4** | Inyección y recuperación (el instrumento) | Pendiente |
| **P1** | Co-adición con pesos y normalización | Pendiente |
| **P2** | Filtro adaptado y la estela | Pendiente |
| **P3** | Diagnóstico: magnitud límite y calidad de la solución | Pendiente |
| **P5** | Pseudo-flat | Pendiente |
| **P6** | Decisión sobre nxt (denoiser de IA) | Pendiente |

## Reglas de la casa

Las de siempre, sin excepción: cabecera en todo `.py`, código en inglés,
comentarios `# @args:` / `# @return:`, comentarios **didácticos** con el
porqué y con los números medidos (lo que se ganó, lo que costó), ninguna
cifra ni clasificación sin explicación (ADR-058), sin números mágicos, la
interfaz en `gui/ui/*.ui` (ADR-005) con las cadenas por `self.tr()`, la red
solo por `core/db.py`, numpy primero (ADR-060) y docs sin raya «—».

## Cómo se verifica cada fase

- **Test unitario sin red** con datos sintéticos de respuesta conocida
  (una PSF inyectada, un ruido inyectado, una rotación conocida).
- **Medida sobre los datos reales** de `2025 UR` (140 tomas, dos tandas,
  `3 s`, `−28 °C`, Clear) y `2026 PY9` (247 tomas, `5 s`, `−16 °C`, Clear),
  con el número en el comentario del código y en esta documentación.
- **ADR bilingüe** por decisión, o enmienda al ADR que ya la tomó.
