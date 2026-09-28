# ADR-051: Local plate solver with ASTAP (dispatcher, persisted WCS)

**Estado / Status**: Accepted · revisado / revised 2026-09-28 · **Fecha / Date**: 2026-09-27

## Español

**Contexto**: hoy la solución de placa va a `nova.astrometry.net`
(`core/sources/astrometry.py`, contrato `solve(path, progress) -> cards|None`), que
necesita red y clave; el modo en vivo y las series locales se beneficiarían de un
solver en la máquina. ASTAP (Hans Roh, `hnsky.org`) es gratuito, rápido y se
instala aparte.

**Decisión**: solver local ASTAP detrás de un dispatcher, **sin mutar nunca el
FITS del usuario por defecto**.

- **Módulos**: `core/sources/astap.py` con el mismo contrato que nova
  (`solve(path, progress) -> cards|None`), y `core/solve.py` de despacho con
  `solver = auto|astap|astrometry` y `astap_path` (Configuración: combo, ruta con
  Examinar, botón «Probar», casilla de `-update`).
- **WCS en memoria por defecto**: se pasa `-wcs` y se lee el lado `*.wcs` con
  `fits_io.read_header` (cabecera FITS mínima `SIMPLE/BITPIX/NAXIS=0` + tarjetas
  WCS, tal cual se verifica con el binario real, ver más abajo); la anotación
  `core/blink.merge_solved_wcs` y el UFE la usan sin tocar el fichero original.
- **`-update` opcional y solo explícito**: escribe la solución en la cabecera del
  FITS (verificado: añade `CTYPE1`, `CRVAL1`, `CDELT1`, ...) y solo se activa desde
  el botón Solve del UFE con la casilla marcada; además sigue emitiendo el lado
  `*.wcs`.
- **Pistas correctas** (Ayuda del propio binario + documentación oficial): `-ra` en
  **horas**, `-spd` = **dec + 90** (siempre positivo), `-fov` en grados de **altura**
  de imagen; los parámetros de línea de comandos tienen prioridad sobre la cabecera.
- **Base de estrellas**: `-d <ruta>` explícita tras sondear rutas conocidas
  (`/opt/astap`, `/usr/share/astap/data/`, junto al binario, Windows
  `C:\Program Files\astap`, macOS `/usr/local/opt/astap`). Verificado: sin `-d` el
  binario puede quedarse esperando un diálogo modal «No star database found!».
- **Preferir `astap_cli`** si existe (versión «barebone», sin pop-up notifier); con
  el binario GUI el despachador corre con timeout acotado y interpreta la salida,
  porque los diálogos modales colgarían la llamada.
- **Salidas**: `<base>.ini` (solución: `PLTSOLVD=T`, `CRPIX/CRVAL/CDELT/CROTA/CD`),
  `<base>.wcs` y `<base>.log` con `-log`; `-o <base>` **nombra** los ficheros de
  salida (no es «overwrite»).
- **Caché** por hash de fichero + backend (el mismo WCS no se resuelve dos veces) y
  **mensajes de fallo bilingües** en lenguaje llano (sin solver: cómo instalarlo;
  sin base: dónde ponerla).

**Verificación empírica (2026-09-27, fase 0)**: con el binario real
(`/usr/bin/astap`, 2024-05-01) y la fixture `tests/fixtures/AT2026acka.fit` (2048²,
WCS eliminado de la copia), resuelto con `-d /opt/astap -fov 0.61 -ra 22.0375
-spd 129.833 -wcs -log` en **1,1 s**: «Solution found: 22:02:14.86 +39°49'59.0,
Δ was 1.6", stars down to magnitude 15.4». `-update` añadió las tarjetas WCS a la
cabecera; `-o` renombró las salidas. Comportamientos modales observados: diálogo de
«No star database found!» y aviso de «ya hay solución en la cabecera» (usar copia
o `-update`, nunca tocar el original sin pedirlo).

**Alternativas**: exigir astropy/astrometry.net local (rechazado: ADR-004 y peso);
solo nova (rechazado: necesita red y clave); escribir siempre con `-update`
(rechazado: mutar ficheros del usuario sin permiso); reimplementar un solver
(rechazado: LOC sin valor).

**Consecuencias**: las series en vivo se resuelven en local sin clave; el flujo
nova sigue siendo el `auto` de reserva cuando ASTAP no está instalado; la
instalación de ASTAP queda documentada en la guía de usuario (dónde descargar el
programa y **una** base de estrellas); los tests usan un binario simulado, y la
resolución real queda como verificación funcional opcional.

**Revisión (2026-09-28): la WCS resuelta se guarda**. El WCS solo en memoria dejaba
la placa «sin resolver» para NINA, PixInsight o un futuro reanálisis, y el flujo de
tránsitos llegaba a pedir las coordenadas del objetivo a mano, sin sentido. Ahora:

- **Resolver es automático**: cualquier acción que necesite un WCS (campo de
  comparación, medir, referencia alineada, inicio de una serie, reducción EXOTIC)
  lanza el solver configurado (`solver = auto|astap|astrometry`) y continúa cuando
  llega la solución; ya no se pide pulsar «Resolver astrometría…» ni, mucho menos,
  escribir píxeles.
- **Persistencia por defecto**: `core/wcs_store.py` escribe las tarjetas WCS en la
  cabecera del propio FITS, de forma **atómica** (temporal hermano + `os.replace`;
  los píxeles y las extensiones se copian verbatim). La casilla de Ajustes
  `solve_save` (por defecto activada) lo desactiva; si el fichero es de solo lectura,
  se avisa y la solución se mantiene en memoria. Se sigue pasando `-wcs` a ASTAP
  (nunca `-update`): el mismo escritor sirve para ASTAP y nova.
- **Un solo camino**: `UfeDialog.request_wcs` encola la acción; al resolver, el
  diálogo y el handoff EXOTIC persisten las tarjetas con el mismo módulo.

Esto **sustituye** el rechazo original a «escribir siempre con `-update`»: la
decisión de no mutar el fichero sin pedirlo se mantiene en espíritu (la escritura
es explícita en Ajustes y atómica), pero el defecto pasa a ser guardar, porque una
placa resuelta debe quedar resuelta.

## English

**Context**: today plate solving goes to `nova.astrometry.net`
(`core/sources/astrometry.py`, contract `solve(path, progress) -> cards|None`),
which needs network and a key; live mode and local series would benefit from an
on-machine solver. ASTAP (Hans Roh, `hnsky.org`) is free, fast and installed
separately.

**Decision**: a local ASTAP solver behind a dispatcher, **never mutating the
user's FITS by default**.

- **Modules**: `core/sources/astap.py` with the same contract as nova
  (`solve(path, progress) -> cards|None`), and a `core/solve.py` dispatcher with
  `solver = auto|astap|astrometry` and `astap_path` (Settings: combo, path with
  Browse, a "Test" button, and the `-update` checkbox).
- **In-memory WCS by default**: pass `-wcs` and read the `*.wcs` sidecar with
  `fits_io.read_header` (a minimal `SIMPLE/BITPIX/NAXIS=0` FITS header plus WCS
  cards, as verified with the real binary below); `core/blink.merge_solved_wcs` and
  the UFE use it without touching the original file.
- **`-update` opt-in and explicit only**: it writes the solution into the FITS
  header (verified: adds `CTYPE1`, `CRVAL1`, `CDELT1`, ...) and is enabled only
  from the UFE Solve button with the checkbox ticked; it still emits the `*.wcs`
  sidecar.
- **Correct hints** (the binary's own help plus the official docs): `-ra` in
  **hours**, `-spd` = **dec + 90** (always positive), `-fov` in degrees of image
  **height**; command-line parameters have priority over the header.
- **Star database**: explicit `-d <path>` after probing known locations
  (`/opt/astap`, `/usr/share/astap/data/`, next to the binary, Windows
  `C:\Program Files\astap`, macOS `/usr/local/opt/astap`). Verified: without `-d`
  the binary can sit forever on a modal "No star database found!" dialog.
- **Prefer `astap_cli`** when available (the "barebone" build with no pop-up
  notifier); with the GUI binary the dispatcher runs with a bounded timeout and
  parses the output, since modal dialogs would hang the call.
- **Outputs**: `<base>.ini` (solution: `PLTSOLVD=T`,
  `CRPIX/CRVAL/CDELT/CROTA/CD`), `<base>.wcs` and `<base>.log` with `-log`;
  `-o <base>` **names** the output files (it is not "overwrite").
- **Cache** by file hash + backend (never solve the same WCS twice) and
  **bilingual, plain-language failure messages** (no solver: how to install it; no
  database: where to put it).

**Empirical verification (2026-09-27, phase 0)**: with the real binary
(`/usr/bin/astap`, 2024-05-01) and fixture `tests/fixtures/AT2026acka.fit`
(2048², WCS stripped from a copy), solved with `-d /opt/astap -fov 0.61 -ra
22.0375 -spd 129.833 -wcs -log` in **1.1 s**: "Solution found: 22:02:14.86
+39°49'59.0, Δ was 1.6", stars down to magnitude 15.4". `-update` added the WCS
cards to the header; `-o` renamed the outputs. Observed modal behaviours: a "No
star database found!" dialog and an "already a solution in the header" notice
(use a copy or `-update`, never touch the original unasked).

**Alternatives**: require local astropy/astrometry.net (rejected: ADR-004 and
weight); nova only (rejected: needs network and a key); always write with
`-update` (rejected: mutating user files unasked); write our own solver (rejected:
lines of code with no value).

**Consequences**: live series solve locally without a key; nova stays the `auto`
fallback when ASTAP is not installed; ASTAP installation is documented in the user
guide (where to download the program and **one** star database); tests use a
simulated binary, with real solving as an optional functional check.

**Revision (2026-09-28): the solved WCS is stored**. Keeping the WCS in memory left
the plate "unsolved" for NINA, PixInsight or a later reanalysis, and the transit
flow even asked for the target's pixel coordinates, which makes no sense. Now:

- **Solving is automatic**: any action that needs a WCS (comparison field, measure,
  aligned reference, starting a series, the EXOTIC reduction) runs the configured
  solver (`solver = auto|astap|astrometry`) and continues when the solution lands;
  no more "press Solve astrometry…" and never a pixel prompt.
- **Persistence by default**: `core/wcs_store.py` writes the WCS cards into the
  FITS header itself, **atomically** (a sibling temp file plus `os.replace`; the
  pixels and extensions are copied verbatim). The `solve_save` Settings checkbox
  (on by default) turns it off; a read-only file reports a warning and the solution
  stays in memory. ASTAP is still asked for `-wcs` (never `-update`): the same
  writer serves both ASTAP and nova.
- **One path**: `UfeDialog.request_wcs` queues the action; on success the dialog and
  the EXOTIC handoff persist the cards through the same module.

This **supersedes** the original rejection of "always write with `-update`": the
decision not to mutate the file unasked stands in spirit (the write is explicit in
Settings and atomic), but the default is now to save, because a solved plate should
stay solved.

**Corrección (2026-09-28, velocidad y aviso)**: la causa real del bucle
"Found 0 references" era la **FOV**, no la posición. El cliente calculaba `-fov`
como `max(NAXIS1, NAXIS2) × escala de Ajustes`; con los recortes de MicroObservatory
(650x500, `IM_SCALE = 5.21`"/px, otra cámara) daba 0,186° cuando el campo es ~0,72°,
y ASTAP barría el cielo entero. Ahora:

- La escala es por imagen: **cabecera** (`IM_SCALE`, `PIXSCALE`, `SECPIX`/`SECPIX1`,
  `CDELT1`, o `XPIXSZ`+`FOCALLEN`) y, si no, los Ajustes (`pixel_um`+`focal_mm`).
- `fov = escala_arcsec × NAXIS2 (altura) / 3600`; el `max()` sobreestimaba placas
  apaisadas. Sin escala: `-fov 0` (auto de ASTAP) explícito.
- **Intento acotado** (30 s) con la FOV derivada y **auto de reserva** (`-fov 0`):
  una pista mala ya no puede colgar el proceso.
- Sigue sin pasar `-ra`/`-spd` (unidad ambigua) y prefiere `astap_cli`, con `-d`,
  `-progress` y Cancel real. Medido: `HATP-32171220013343.FITS` pasa de bucle a
  **0,31 s** (FOV 0,724° de `IM_SCALE`); `-fov 0.186` no resuelve, sin `-fov` tarda
  66 s.

**Correction (2026-09-28, speed and feedback)**: the real cause of the "Found 0
references" loop was the **FOV**, not the position. The client computed `-fov` as
`max(NAXIS1, NAXIS2) × the Settings scale`; on the MicroObservatory crops
(650x500, `IM_SCALE = 5.21`"/px, a different camera) that gave 0.186° where the
field is ~0.72°, so ASTAP swept the whole sky. Now:

- The scale is per image: the **header** (`IM_SCALE`, `PIXSCALE`, `SECPIX`/`SECPIX1`,
  `CDELT1`, or `XPIXSZ`+`FOCALLEN`), else the Settings (`pixel_um`+`focal_mm`).
- `fov = scale_arcsec × NAXIS2 (height) / 3600`; the `max()` over-estimated landscape
  plates. Without a scale: an explicit `-fov 0` (ASTAP auto).
- A **bounded attempt** (30 s) at the derived FOV and an **auto fallback** (`-fov 0`):
  a bad hint can no longer hang the run.
- `-ra`/`-spd` stay out (ambiguous unit); `astap_cli` is still preferred, with `-d`,
  `-progress` and a real Cancel. Measured: `HATP-32171220013343.FITS` goes from a
  loop to **0.31 s** (FOV 0.724° from `IM_SCALE`); `-fov 0.186` never solves, no
  `-fov` takes 66 s.
