# NightScribe — Arquitectura

*[English version](ARCHITECTURE.md)*

## Visión general

Arquitectura por capas, aburrida a propósito. El CLI y la GUI son cáscaras finas sobre
el mismo núcleo; todo el trabajo costoso (red, efemérides) se cachea en SQLite.

```
            ┌──────────────┐   ┌──────────────┐
            │  CLI         │   │  GUI (Qt6)   │
            │ __main__.py  │   │ gui/ (.ui)   │
            └──────┬───────┘   └──────┬───────┘
                   │    mismo núcleo  │
        ┌──────────▼──────────────────▼──────────┐
        │  core: planner · suggest · orbits ·     │
        │  solar · transits · enrich · narrative  │
        │  · post · coords · ephem_minor · blink  │
        │  · fits_io · wcs (FITS/WCS propio, ADR-018)│
        └──────────┬─────────────────────────────┘
                   │ solo sources/ habla con la red
        ┌──────────▼──────────┐    ┌─────────────┐
        │  core/sources/*     │───►│ core/db.py  │  SQLite:
        │  neofixer, sbdb,    │    │ caché http  │  caché + objetivos +
        │  horizons, cobs...  │    │ (TTL)       │  observaciones + settings
        └─────────────────────┘    └─────────────┘
                   │
                   ▼
             viz/  (matplotlib: un render, lienzo GUI + export PNG)
```

## Módulos

| Módulo | Responsabilidad |
|---|---|
| `nightscribe/__main__.py` | Entrada CLI: `tonight`, `explore`, `post`, `solar`, `blink`, `history`, `gui` |
| `nightscribe/config.py` | Ajustes persistentes (observatorio, apertura, idioma, claves); código MPC → coordenadas |
| `nightscribe/paths.py` | Directorios de config/datos por SO (platformdirs) |
| `core/db.py` | SQLite: `http_cache` (TTL por fuente), `targets`, `observations`, `settings`. Punto único de acceso |
| `core/coords.py` | Hora sidereal, alt-az, crepúsculos — math puro, sin astropy |
| `core/ephem_minor.py` | Sol/Luna/planetas (Schlyter, baja precisión) + propagación kepleriana para cuerpos menores |
| `core/planner.py` | Construye la lista cruda de objetivos de la noche desde las fuentes |
| `core/suggest.py` | Score unificado 0–100, Top N, frases «por qué esta noche» (ver SCORING) |
| `core/orbits.py` | Familias orbitales + traducción de parámetros (ver ORBITS) |
| `core/solar.py` | Estado del Sol agregado (SSN, regiones, fulguraciones, Kp, viento) |
| `core/transits.py` | Tránsitos de exoplanetas: t0 + n·P, cruce con la noche, visibilidad |
| `core/enrich.py` | Detección de tipo de objeto + orquestación de datos crudos |
| `core/narrative.py` | Prosa divulgativa bilingüe ES/EN |
| `core/post.py` | Plantillas → post_ES / post_EN / tuit |
| `core/fits_io.py` | Lector FITS mínimo sobre numpy, sin astropy (ADR-018) |
| `core/wcs.py` | WCS TAN mínimo: píxel↔cielo, escala, rotación (ADR-018) |
| `core/blink.py` | Orquestador del blink de SN: nombre → coordenadas, pareja PanSTARRS DR1 g casada en geometría (ADR-018) |
| `core/sources/*` | Un módulo por fuente externa (ver DATA_SOURCES) |
| `viz/*` | Renderers matplotlib compartidos por lienzo GUI y export PNG |
| `gui/*` | Cáscara PySide6: ficheros `.ui` (Qt Designer), workers QThread, asistente |

## Flujo de datos — «esta noche»

1. `planner` pide a las fuentes las listas crudas: targets de NEOfixer (site = código MPC),
   supernovas de Rochester, cometas activos de COBS, página PCCP del MPC, catálogo ExoClock.
2. Cada respuesta cruda se guarda en `http_cache` con su TTL; las llamadas repetidas son gratis.
3. Visibilidad por objetivo: NEOs vía `ephem` de NEOfixer (específico del sitio);
   SNs/cometas/PCCP con math alt-az propio (`coords.py`); tránsitos calculados en local
   (t0 + n·P) y luego alt-az.
4. `suggest` puntúa todo 0–100, construye el Top N y las frases «por qué esta noche».
5. Los flags de observado y el historial de posts vienen de SQLite y realimentan el score
   (lo publicado recientemente pierde novedad; lo observado sin publicar gana urgencia).

## Flujo de datos — «post»

1. `enrich` detecta el tipo de objeto (regex + `kind` de SBDB) y reúne los datos crudos.
2. `orbits` traduce parámetros; `narrative` escribe la prosa ES/EN; `viz` renderiza los PNG.
3. `post` rellena plantillas → ficheros + vista previa en la GUI. Historial en SQLite.

## Hilos

La red y el render nunca corren en el hilo de la GUI: `gui/workers.py` (QThread) con
señales Qt de vuelta a la interfaz. El CLI es síncrono.

## Internacionalización

Qt Linguist: toda cadena visible pasa por `self.tr()`; fuentes en
`gui/i18n/nightscribe_{es,en}.ts`, compiladas a `.qm` con `pyside6-lrelease`.
Idioma de interfaz seleccionable en Configuración (por defecto, el del SO). El contenido
generado (posts, frases) se produce siempre en ambos idiomas, al margen del idioma de la
interfaz.

## Persistencia

Fichero SQLite en el directorio de datos del usuario (ver `paths.py`). Esquema
versionado con una escalera de migraciones sobre `PRAGMA user_version`. Los TTL por
fuente se definen en `core/db.py` (NOAA 1 h, NEOfixer/efemérides 12 h,
Rochester/COBS/ESA/PCCP 6 h, SBDB/SIMBAD/CAD/ExoClock 7 d).

## Errores

Mensajes legibles por humanos, sin trazas en la interfaz. Los fallos de red degradan con
elegancia: una fuente caída simplemente no aporta objetivos (se registra un aviso); la
app nunca se cae porque un sitio web falle.
