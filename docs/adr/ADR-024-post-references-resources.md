# ADR-024: The post is a web-ready document — charts and blink resources live inside the markdown

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-25

## Español

**Contexto**: el borrador ES/EN que genera NightScribe era texto suelto; los
gráficos (órbita, familias, cielo, campo) y los recursos del blink (GIF, MP4,
PNG antes/después) salían a la carpeta por separado y el usuario tenía que
montar el post a mano para publicarlo (arrastrar imágenes, escribir enlaces,
repetir el trabajo en inglés). La misión 3 del proyecto es precisamente
"contarlo: posts bilingües + tuit + gráficos listos para redes", y un post
que no referencia sus propios recursos no está listo.

**Decisión**:

1. `core/post.py` es la única fuente de verdad para el post completo.
   - `CHART_LABELS` (orbit, families, sky, field, transit, sun) y el dict
     `MEDIA` (gif, mp4, pair) llevan el texto alt + encabezado por idioma,
     con marcador `%s` para el nombre del objeto.
   - `chart_section()` y `media_section()` construyen los bloques
     `## Galería`/`## Gallery` y `## Recursos`/`## Resources` con enlaces
     markdown **relativos** (`![alt](nombre.png)`): la imagen va junto al
     `.md`, por lo que el resultado se publica tal cual en cualquier web
     (GitHub, blog, MediaWiki…).
   - `attach_charts(post, charts, resources)` es idempotente: si el texto ya
     tiene un bloque, lo reemplaza antes de añadir el nuevo (corta en el
     primer `\n## `).
   - `build_charts(e, outdir, safe, cfg)` (antes `_build_charts`, ahora
     público) dibuja todos los gráficos de un objeto en uno solo de core y
     añade la rama de tránsito de exoplanetas (curva de luz
     `transit_view.draw_transit`, activada por `data.transit.mid` +
     `type in (transit, exoplanet)`). La rama del Sol sigue reservada al
     comando `solar`.
   - `save_outputs(post, outdir, base, e, charts, cfg, resources)` escribe
     los tres textos, hace que el markdown referencia cada PNG/GIF/MP4
     presente y devuelve el mapa de ficheros con claves `chart_*` y `res_*`.

2. La GUI no duplica lógica: `_render_object_charts()` de
   `gui/main_window.py` es un wrapper fino sobre `post.build_charts` (se usa
   también en el diálogo Explore para las miniaturas). En el flujo de post,
   `_dialog_post_done()` construye los gráficos con el prefijo por objeto
   (`<safe>_`), recoge del directorio de salida cualquier GIF/MP4/PNG
   `_before_after` ya existente para el mismo objeto (el blink puede haberse
   hecho en una sesión anterior) y todo pasa por `save_outputs()`; los
   archivos se registran en el proyecto con `project.add_file()`.

3. CLI: `nightscribe post OBJETO --png` genera los gráficos y un borrador
   que ya los referencia; `nightscribe blink NOMBRE IMAGEN --video --post`
   genera GIF+MP4+antes/después **y** un borrador bilingüe con sección
   Recursos que enlaza los tres (con un intento de `enrich` para la
   prosa, y un fallback a un dict mínimo si la SN aún no está en ninguna
   fuente).

**Consecuencias**: un post de NightScribe es un documento autocontenido y
portable; no hay que "montar" nada antes de publicarlo. Las tests cubren el
referenciamiento ES/EN de gráficos y de recursos, la combinación de ambos,
y la idempotencia (`test_transits_post.py`). Los nombres de gráfico
permanecen previsibles (`<objeto>_orbit.png` …) porque el markdown depende
de `Path(p).name`. El vídeo MP4 y el GIF no se convierten uno en el otro:
cada formato se enlaza con su alt-texto propio, útil para plataformas que
no reproducen GIFs o viceversa.

## English

**Context**: the ES/EN draft NightScribe generated was loose text; the charts
(orbit, families, sky, field) and the blink resources (GIF, MP4, before/after
PNG) landed in the folder separately and the user had to assemble the post by
hand to publish it (dragging images in, writing the links, redoing it all in
English). Mission 3 of the project is exactly "report it: bilingual posts +
tweet + charts ready for social media", and a post that does not reference
its own resources is not ready.

**Decision**:

1. `core/post.py` is the single source of truth for the full post.
   - `CHART_LABELS` (orbit, families, sky, field, transit, sun) and the
     `MEDIA` dict (gif, mp4, pair) carry per-language alt text + section
     headers, with a `%s` placeholder for the object name.
   - `chart_section()` and `media_section()` build the
     `## Galería`/`## Gallery` and `## Recursos`/`## Resources` blocks with
     **relative** markdown links (`![alt](name.png)`): the images sit next
     to the `.md`, so the result can be published as-is on any web site
     (GitHub, a blog, MediaWiki…).
   - `attach_charts(post, charts, resources)` is idempotent: if the text
     already has a block, it is replaced before the new one is appended
     (the cut is at the first `\n## `).
   - `build_charts(e, outdir, safe, cfg)` (was private `_build_charts`, now
     public) draws every chart an object supports in one single core place,
     and adds the exoplanet-transit branch (light curve via
     `transit_view.draw_transit`, enabled by `data.transit.mid` +
     `type in (transit, exoplanet)`). The Sun branch stays with the
     `solar` command.
   - `save_outputs(post, outdir, base, e, charts, cfg, resources)` writes
     the three texts, makes the markdown reference every PNG/GIF/MP4 that
     exists, and returns the file map with `chart_*` / `res_*` keys.

2. The GUI does not duplicate logic: `_render_object_charts()` in
   `gui/main_window.py` is a thin wrapper over `post.build_charts` (it is
   also used by the Explore dialog for the thumbnails). In the post flow,
   `_dialog_post_done()` builds the charts with a per-object prefix
   (`<safe>_`), collects any existing GIF/MP4/`_before_after` PNG in the
   output folder for the same object (the blink may have been built in an
   earlier session), and routes everything through `save_outputs()`; the
   files are registered in the project with `project.add_file()`.

3. CLI: `nightscribe post OBJECT --png` generates the charts and a draft
   that already references them; `nightscribe blink NAME IMAGE --video
   --post` generates GIF+MP4+before/after **and** a bilingual draft whose
   Resources section links all three (with an `enrich` attempt for the
   prose, and a minimal-dict fallback if the SN is not in any source yet).

**Consequences**: a NightScribe post is a self-contained, portable
document; nothing has to be "assembled" before publishing. Tests cover the
ES/EN referencing of charts and of resources, both combined, and
idempotency (`test_transits_post.py`). Chart file names stay predictable
(`<object>_orbit.png` …) because the markdown depends on `Path(p).name`.
The MP4 video and the GIF are not converted one into the other: each format
is linked with its own alt text, useful for platforms that do not play
GIFs, or vice versa.
