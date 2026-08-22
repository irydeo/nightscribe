# ADR-016: Supernova images — own reference cutouts + user blink

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: algunos reportes de descubrimiento de supernovas incluyen imagen de
descubrimiento e imagen original del survey. Queremos usar recursos así en los posts
(el «antes/después» es contenido muy potente), pero esas imágenes tienen copyright
del survey/descubridor.

**Decisión**: el «antes» lo genera NightScribe: cutout del campo desde **DESI Legacy
Survey** o **CDS hips2fits** (DSS/Pan-STARRS), servicios públicos, con crosshair en la
posición SIMBAD de la SN (`core/sources/cutouts.py`, `viz/sn_view.py`). El «después»
es la **imagen del propio observatorio** (del usuario): lado a lado o GIF blink
animado. Las imágenes de descubrimiento de TNS solo se muestran dentro de la app
(credenciales opcionales) o se enlazan; solo entran en posts si la licencia del survey
lo permite (ZTF/ATLAS con crédito). Coherente con ADR-008.

**Alternativas**: usar imágenes TNS en posts (riesgo legal); sin comparación visual
(pierde el mejor gancho).

**Consecuencias**: comparaciones legales, bonitas y con estilo propio; la imagen del
usuario se integra arrastrándola a la carpeta del post o desde la GUI.

## English

**Context**: some supernova discovery reports include the discovery image and the
original survey image. We want to use such resources in posts (before/after is very
powerful content), but those images are copyrighted by the survey/discoverer.

**Decision**: NightScribe builds the "before": field cutout from **DESI Legacy
Survey** or **CDS hips2fits** (DSS/Pan-STARRS), public services, with a crosshair at
the SN's SIMBAD position (`core/sources/cutouts.py`, `viz/sn_view.py`). The "after"
is the **observatory's own image** (user's): side-by-side or animated blink GIF. TNS
discovery images are only shown inside the app (optional credentials) or linked;
they enter posts only if the survey licence allows it (ZTF/ATLAS with credit).
Consistent with ADR-008.

**Alternatives**: use TNS images in posts (legal risk); no visual comparison (loses
the best hook).

**Consequences**: legal, beautiful comparisons with our own style; the user's image
is integrated by dropping it into the post folder or from the GUI.
