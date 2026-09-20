# LEEME — patrones y errores frecuentes (Track V)

> Léelo **antes** de tu tarjeta. Todo subplan del track asume lo aquí escrito.
> Si algo de tu tarjeta contradice este documento, manda la tarjeta.

## 1. Cabecera obligatoria en todo `.py` nuevo

Copia tal cual (cambia solo el nombre del módulo):

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

## 2. Estilo de código (ADR-007)

- Código, identificadores y comentarios **en inglés**. Documentación en
  `docs/` en español.
- Comentario corto sobre cada función pública con `# @args:` / `# @return:`,
  al estilo de `core/project.py`. Sin docstrings robóticos.
- Funciones cortas. Sin magia. Sin dependencias nuevas.
- **Prohibido** astropy/photutils (ADR-004); numpy/PIL sí.
- Toda consulta de red va por `core/db.py` (`db.http_get` / `db.cache_get`),
  y solo desde módulos de `core/sources/`. Nunca `requests` fuera de ahí.
- Toda cadena visible en la GUI pasa por `self.tr()`. Pares ES/EN de datos
  por `orbits.pick` o dicts `{"es":…, "en":…}`.

## 3. Comandos

```bash
# un test concreto (lo habitual en tu tarjeta)
.venv/bin/python -m pytest tests/unit/test_<x>.py -q
# suite unitaria completa (al cerrar la tarjeta: anota N→M)
.venv/bin/python -m pytest tests/unit -q
# pipeline i18n (solo si tu tarjeta tiene tabla de cadenas):
pyside6-lupdate nightscribe/gui/*.py nightscribe/gui/widgets/*.py \
    nightscribe/gui/ui/*.ui \
    -ts nightscribe/gui/i18n/nightscribe_es.ts \
        nightscribe/gui/i18n/nightscribe_en.ts
# traducir los .ts (tu tarjeta trae la tabla ES/EN literal; EN suele ser
# igual a la fuente), luego:
pyside6-lrelease nightscribe/gui/i18n/nightscribe_*.ts
```

Si no existe `.venv`, créalo (ver AGENTS.md) antes de empezar y úsalo siempre.

## 4. Tests: patrones que ya existen (úsanos, no inventes)

- **BD real temporal**: `db = Database(str(tmp_path / "t.db"))`
  (`from nightscribe.core.db import Database`). Ejemplos:
  `tests/unit/test_project.py`, `test_project_storage.py`.
- **Fuentes de red**: se testea el **parser** contra un fixture de
  `tests/fixtures/` y el fetch se simula con
  `monkeypatch.setattr(<modulo>.db, "http_get", fake)`. Los fixtures de este
  track ya existen (los escribió el commit 0):
  `vsx_t_crb.json`, `vsx_omi_cet.json`, `vsx_ee_cep.json`,
  `vsx_not_found.json`, `alerce_conesearch_wesb1.json`,
  `alerce_lightcurve_wesb1.json`.
- **GUI offscreen**: patrón de `tests/unit/test_overview_panel.py` /
  `test_projects_hub.py`: `QApplication` offscreen + `theme.apply_theme` +
  widgets directos + payloads fake. Sin red jamás.
- **Planner**: `monkeypatch.setattr(...)` sobre el catálogo/fuente y
  `horizon.FlatHorizon(10.0)`; sitio fijo `LAT, LON = 28.3, -16.5`,
  `DATE = datetime.date(2026, 9, 11)` (patrón de `test_hads_planner.py`).

## 5. Errores frecuentes (aprendidos en tracks anteriores)

1. **`lupdate` no extrae `self.tr()` dentro de llaves de f-string.**
   Escribe el `tr()` plano y concatena/formatea fuera:
   `self.tr("Period {p:.2f} h").format(p=per)` — no
   `f"...{self.tr('x')}..."`.
2. **`lupdate` debe incluir `gui/widgets/*.py`** (ver §3); sin eso marca
   «vanished» cadenas vivas y `test_i18n.py` falla.
3. **`enabled_kinds` tiene migración amable**: la lista «vieja» contra la que
   se compara en `config.py` es exacta. Tu tarjeta te da la lista literal.
4. **El eje de magnitudes es invertido**: `amp = min - max > 0`; un
   «descenso de brillo» (dip) es `mag` que **sube**.
5. **`Epoch` de VSX es JD; nuestros puntos fotométricos son MJD**
   (`MJD = JD − 2400000.5`). La conversión vive en el parser de VSX y en
   `variables.py`; no la dupliques.
6. **Los `ALTER TABLE` se guardan con `PRAGMA table_info`** (patrón v4/v6 de
   `core/db.py`) para que reabrir una BD ya migrada sea un no-op.
7. **`sqlite3` en la app es mono-conexión con candado**: todo SQL pasa por
   `db.execute(...)` + `db.commit()` (ver `core/followup.py`).
8. **No edites tests existentes salvo que tu tarjeta lo diga
   explícitamente** (y entonces, solo el trozo que dice).
9. Si un ancla de línea no coincide: **para y reporta** pegando lo que ves.
   No busques el sitio «parecido» por tu cuenta.

## 6. Estructura de una tarjeta

```
## Vx.y — <título>
**Contexto a leer (solo esto)**: fichero:líneas
**Toca**: ficheros exactos
**Escribe exactamente esto**: código/diffs completos
**Tests a añadir**: código completo
**Cadenas nuevas**: tabla ES/EN (si aplica)
**Ejecuta**: comando de test
**Hecho cuando**: condición binaria
**Commit**: mensaje literal
**Estado**: Pendiente
```
