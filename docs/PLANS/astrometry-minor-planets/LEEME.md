# LEEME: astrometría de cuerpos menores por track & stack

> Léelo **antes** de abrir cualquier fase. El plan maestro es
> [`PLAN.md`](PLAN.md); los detalles de implementación viven en los
> `fase-*.md` de esta carpeta. Si algo de una fase contradice `PLAN.md`,
> manda `PLAN.md` y se corrige la fase.

## 1. Qué es esta carpeta

Diseño completo de dos capacidades nuevas y encadenadas:

1. **Calibración de imágenes** (bias, dark, flat) con una biblioteca de masters
   del observatorio.
2. **Astrometría de cuerpos menores por track & stack**: apilar una secuencia
   de tomas guiando el desplazamiento con la efeméride del objeto, repartirla
   en varias observaciones, validarlas (visualmente y contra otros
   observadores) y generar el reporte para el Minor Planet Center.

El MVP cubre solo **objetos conocidos** (NEO, cometa, PCCP con efemérides).
La búsqueda a ciegas (grid search) queda fuera, con el hueco previsto.

## 2. Orden de lectura

1. `CONCEPT.md` (en el repo, `docs/PLANS/astrometry-minor-planets/CONCEPT.md`):
   la idea original del autor (shift & stack, fine-tuning, no detección,
   comparación de algoritmos).
2. [`PLAN.md`](PLAN.md): contexto, decisiones firmadas, arquitectura,
   integración en NightScribe, fases, criterios y riesgos.
3. `fase-0-adrs-dependencias.md` a `fase-10-validacion-docs.md`: el detalle de
   cada fase, en orden.

## 3. Estado

- **Decisiones cerradas con el autor**: sí (D1 a D32 en `PLAN.md`).
- **Código escrito**: no. La fase 0 no ha empezado.
- **Punto de entrada**: `fase-0-adrs-dependencias.md` (firmar ADR-060, ADR-061
  y ADR-062, reabrir ADR-004, ADR-018 y ADR-022, y cerrar el checklist de
  verificaciones de `PLAN.md`).

## 4. Reglas de la casa que esta obra toca

- **La interfaz se define en `gui/ui/*.ui`** (ADR-005): toda ventana, diálogo
  o pestaña lleva su estructura, textos y tooltips en Designer; el código
  cablea señales y rellena datos. Los widgets propios (visores, gráficas) van
  por placeholder `QWidget` + `replaceWidget`.
- **Toda cadena visible pasa por `self.tr()`** (ADR-014). Cuidado con
  `lupdate`: no extrae `self.tr()` dentro de f-strings.
- **Toda consulta de red pasa por `core/db.py`** y solo desde
  `core/sources/`. En este plan la red es Horizons (efemérides) y el MPC
  (observaciones de otros observadores).
- **Código didáctico** (AGENTS.md y ADR-058): quien lo lea tiene que entender
  el **qué** y el **por qué**. Nada de comentarios obvios del tipo «incrementa
  el contador»; cada bloque no obvio explica el motivo, la física o el fallo
  que evita, y los números medidos van en el comentario. Una decisión que no
  se explica es una decisión que se perderá.
- **Ninguna cifra ni clasificación sin explicación** (ADR-058): al usuario
  nunca se le enseña un SNR, un residual, una magnitud límite o un método de
  combinación a secas; siempre con qué significa y por qué importa. Las
  taxonomías y cifras se explican una sola vez, en `core/explain.py` (dos
  densidades: `short` para tooltips, `long` para fichas y posts).
- **Cabecera obligatoria** en todos los `.py` nuevos:

```python
############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - <Module name> module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################
```

## 5. Nota sobre dependencias (ADR-004 reabierta)

Este plan **reabre ADR-004**: la prohibición de scipy y astropy cae para toda
la app (D18), aunque en la práctica la usan solo los módulos nuevos. Los
módulos que ya funcionan (`fits_io`, `wcs`, `register`, `photometry`,
`series_measure`) **no se migran** en este plan.

Consecuencia práctica: el `LEEME.md` de otros planes (`docs/PLANS/variables/`)
todavía dice «Prohibido astropy/photutils (ADR-004)». Al cerrar la fase 0 hay
que actualizar esa frase y `AGENTS.md` para que no se contradigan con ADR-060.

## 6. Comandos

```bash
# suite unitaria, sin red (la que cierra cada fase)
.venv/bin/python -m pytest tests/unit -q
# en paralelo
.venv/bin/python -m pytest -n auto --dist loadfile tests/unit
# funcionales (con red: Horizons, ASTAP, MPC)
.venv/bin/python -m pytest tests/functional -q
# i18n (solo si la fase toca cadenas)
pyside6-lupdate nightscribe/gui/*.py nightscribe/gui/widgets/*.py \
    nightscribe/gui/ui/*.ui \
    -ts nightscribe/gui/i18n/nightscribe_es.ts \
        nightscribe/gui/i18n/nightscribe_en.ts
pyside6-lrelease nightscribe/gui/i18n/nightscribe_*.ts
```

Si no existe `.venv`, créalo (ver `AGENTS.md`) antes de empezar y úsalo
siempre.

## 7. Índice de ficheros

| Fichero | Contenido |
|---|---|
| `PLAN.md` | Plan maestro: decisiones, arquitectura, integración, fases, riesgos. |
| `fase-0-adrs-dependencias.md` | ADRs, reaperturas, dependencias, spike del build Windows. |
| `fase-1-calibracion.md` | `core/calibration.py`, biblioteca de masters, receta. |
| `fase-2-ingesta-solve-registro.md` | Lectura de la visita, T_mid, ASTAP, WCS compuesto. |
| `fase-3-apilado.md` | Reparto en grupos, cutout, desplazamiento, métodos, barrido, no detección. |
| `fase-4-medida-astrometrica.md` | Centroide doble por grupo, comparación, magnitud, errores. |
| `fase-5-validacion-observaciones.md` | Secuencia centrada, chequeo contra otros, ficha del objeto. |
| `fase-6-reporte-mpc.md` | Generadores ADES PSV y 80 columnas, ida y vuelta. |
| `fase-7-gui.md` | Pestañas del UFE, workers, Ajustes, i18n. |
| `fase-8-persistencia-proyecto.md` | Migración v17, Undo, integración con la visita. |
| `fase-9-liberar-espacio.md` | Mover originales a `procesados`, manifiesto, restaurar. |
| `fase-10-validacion-docs.md` | Validación real, docs bilingües, cierre. |
| `doc-findorb.es.md` | Sección de usuario (ES): qué es Find_Orb, instalación, configuración y uso. |
| `doc-findorb.md` | Sección de usuario (EN): espejo del anterior. |
