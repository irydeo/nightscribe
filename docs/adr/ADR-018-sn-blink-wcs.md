# ADR-018: Supernova blink — own FITS/WCS + geometry-matched survey cutouts

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-22

## Español

**Contexto**: ADR-016 decidió el «antes/después» de supernovas (cutout de referencia
+ imagen del propio observatorio). Para hacer *blinking* de verdad hace falta leer el
FITS del usuario, entender su astrometría (WCS) y alinearlo con la imagen de survey.
La conversación de diseño proponía `astropy` + `reproject`, pero ADR-004 prohíbe
astropy (pesado y frágil de empaquetar).

**Decisión**:

1. **FITS/WCS propio y mínimo** (`core/fits_io.py`, `core/wcs.py`), sobre numpy (ya
   presente vía matplotlib; se declara dependencia explícita). Lector FITS básico
   (BITPIX 8/16/32/64/−32/−64, `BSCALE/BZERO`, RGB→luminancia) y WCS TAN
   (`CRVAL/CRPIX`, `CD` o `PC+CDELT` o `CDELT+CROTA2`). Las distorsiones `-SIP` se
   ignoran con aviso: en campos amateur (<1–2°) el error es de pocos píxeles.
   Misma filosofía que ADR-009 (Schlyter): ~300 líneas de math propio, documentado
   y testeado.
2. **Alineación por construcción**: el cutout de survey se pide a CDS hips2fits
   (`CDS/P/PanSTARRS/DR1/g`, FITS) con el **centro celeste, escala y rotación de la
   imagen del usuario** (calculados de su WCS; el centro es el píxel central, no
   `CRVAL`, que puede estar desplazado). Las dos imágenes quedan alineadas a ~1 px
   **sin remuestrear jamás los píxeles del usuario**. Fallback `CDS/P/DSS2/red` si
   dec < −30° (fuera de la cobertura PS1). Nudge manual (dx, dy) en la GUI para
   el ajuste fino. Si el WCS viene **espejado** (det(CD) > 0 — algunos pipelines
   escriben la solución así, p. ej. el frame CDK17/QHY de 2026zji), ninguna
   rotación puede alinearlo con el survey: la imagen del usuario se **voltea
   horizontalmente** (`Wcs.flipped_x`, una operación de vista, no un remuestreo)
   y la GUI lo notifica.
3. **Imagen sin WCS**: se intenta resolver automáticamente con **Astrometry.net**
   (nova) si el usuario ha configurado su clave de API en Ajustes
   (`astrometry_key`); la solución se cachea por hash del fichero (fuente
   `astrometry`, TTL 30 d) y se fusiona en la cabecera del usuario descartando
   tarjetas WCS obsoletas (`merge_solved_wcs`). Sin clave, mensaje bilingüe
   claro: configurar la clave o resolver con ASTAP, NINA, Ekos o PixInsight.
4. **Resolución del nombre** (`2026ziz` → `SN2026ziz`): RA/Dec manual → **TNS**
   (página pública del objeto; los transientes más frescos solo están ahí) →
   SIMBAD → lista Rochester (ya cacheada). No se toca `enrich.detect_type` (el
   blink tiene su propio resolvedor). El pipeline reporta sus etapas por un
   callback de progreso bilingüe (la GUI las muestra en la barra de estado).
5. **Salidas**: GIF animado (blink y fade) + **vídeo MP4 (H.264)** con la misma
   configuración —algunos sitios rechazan GIF; el ciclo se repite hasta ≥6 s porque
   los vídeos no se repiten solos como los GIF— + PNG lado a lado para posts;
   estirado por
   percentiles con ajuste manual, balance de brillo del survey por ganancia (mediana,
   `auto_gain`), zoom de recorte sobre la SN, tamaño de marca ajustable y cadencia
   del blink configurable. Los rótulos de los exports son **monolingües** (idioma de
   la UI) y nombran al observatorio configurado. UI en pestaña nueva «Blink» + CLI
   `nightscribe blink <nombre> <imagen.fits>` (con `--zoom`, `--intervalo`,
   `--video`). El MP4 se codifica con el binario ffmpeg estático de
   `imageio-ffmpeg` (única dependencia nueva; el Qt Multimedia empaquetado no
   incluye codificador H.264).

**Alternativas**: astropy+reproject (robusto pero rompe ADR-004, +100 MB empaquetado);
API oficial PS1 `fitscut.cgi` (stack nativo a 0,25″/px pero sin control de rotación →
exigiría remuestreo propio); API bot oficial de TNS (las credenciales ya están
previstas en config; la página pública no necesita credenciales y se cachea 6 h).

**Consecuencias**: cero dependencias nuevas pesadas, píxeles del usuario intactos,
alineación trivial y robusta; los FITS sin resolver funcionan vía Astrometry.net
cuando hay clave. A cambio mantenemos el lector FITS/WCS propio y aceptamos la
limitación SIP. Atribución en los exports: «PanSTARRS DR1 g (CDS hips2fits)» /
«DSS2-red (CDS hips2fits)», coherente con ADR-008.

## English

**Context**: ADR-016 decided the supernova "before/after" (reference cutout + the
observatory's own image). Real blinking requires reading the user's FITS,
understanding its astrometry (WCS) and aligning it with the survey image. The design
conversation suggested `astropy` + `reproject`, but ADR-004 forbids astropy (heavy,
fragile to package).

**Decision**:

1. **Own minimal FITS/WCS** (`core/fits_io.py`, `core/wcs.py`) on top of numpy
   (already pulled in by matplotlib; declared as an explicit dependency). Basic FITS
   reader (BITPIX 8/16/32/64/−32/−64, `BSCALE/BZERO`, RGB→luminance) and TAN WCS
   (`CRVAL/CRPIX`, `CD` or `PC+CDELT` or `CDELT+CROTA2`). `-SIP` distortions are
   ignored with a warning: on amateur fields (<1–2°) the error is a few pixels.
   Same philosophy as ADR-009 (Schlyter): ~300 lines of own, documented, tested math.
2. **Alignment by construction**: the survey cutout is requested from CDS hips2fits
   (`CDS/P/PanSTARRS/DR1/g`, FITS) at the **celestial centre, scale and rotation of
   the user's image** (computed from its WCS; the centre is the central pixel, not
   `CRVAL`, which may be offset). Both images end up aligned to ~1 px **without ever
   resampling the user's pixels**. Fallback `CDS/P/DSS2/red` when dec < −30° (outside
   PS1 coverage). Manual nudge (dx, dy) in the GUI for fine tuning. If the WCS comes
   out **mirrored** (det(CD) > 0 — some pipelines write the solution that way, e.g.
   the CDK17/QHY 2026zji frame), no rotation can match it to a survey: the user's
   image is **flipped horizontally** (`Wcs.flipped_x`, a view operation, not a
   resample) and the GUI says so.
3. **Image without WCS**: automatically blind-solved with **Astrometry.net**
   (nova) when the user has configured their API key in Settings
   (`astrometry_key`); the solution is cached by file hash (source
   `astrometry`, TTL 30 d) and merged into the user's header, dropping stale
   WCS cards (`merge_solved_wcs`). Without a key, a clear bilingual message:
   configure the key or solve with ASTAP, NINA, Ekos or PixInsight.
4. **Name resolution** (`2026ziz` → `SN2026ziz`): manual RA/Dec → **TNS**
   (public object page; the freshest transients live only there) → SIMBAD →
   Rochester list (already cached). `enrich.detect_type` is untouched (blink
   has its own resolver). The pipeline reports its stages through a bilingual
   progress callback (the GUI shows them in the status area).
5. **Outputs**: animated GIF (blink and fade) + **MP4 video (H.264)** with the
   same configuration —some sites reject GIFs; the cycle repeats until ≥6 s
   because videos do not self-loop like GIFs— + side-by-side PNG for posts;
   percentile stretch with manual adjustment, survey brightness balance by gain
   (median, `auto_gain`), zoom crop around the SN, adjustable marker size and
   configurable blink dwell. Export captions are **single-language** (UI language)
   and name the configured observatory. UI in a new "Blink" tab + CLI
   `nightscribe blink <name> <image.fits>` (with `--zoom`, `--intervalo`,
   `--video`). The MP4 is encoded with the static ffmpeg binary from
   `imageio-ffmpeg` (the only new dependency; packaged Qt Multimedia ships no
   H.264 encoder).

**Alternatives**: astropy+reproject (robust but breaks ADR-004, +100 MB packaged);
official PS1 `fitscut.cgi` API (native stack at 0.25″/px but no rotation control →
would require own resampling); official TNS bot API (credentials already reserved
in config; the public page needs no credentials and is cached 6 h).

**Consequences**: no new heavy dependencies, user's pixels untouched, trivial and
robust alignment; unsolved FITS work via Astrometry.net when a key is configured.
In exchange we maintain our own FITS/WCS reader and accept the SIP limitation.
Export attribution: "PanSTARRS DR1 g (CDS hips2fits)" / "DSS2-red (CDS
hips2fits)", consistent with ADR-008.
