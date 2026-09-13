# NightScribe — Fuentes de datos

*[English version](DATA_SOURCES.md)*

Todas las fuentes externas usadas por NightScribe, un módulo por fuente en
`core/sources/`. Verificadas en funcionamiento el 21-08-2026. Todo acceso a red pasa
por la caché HTTP de SQLite (`core/db.py`) con el TTL indicado.

## Fuentes de planificación (alimentan «Esta noche»)

### NEOfixer — `neofixer.py` — fuente primaria de NEOs

- `GET https://neofixerapi.arizona.edu/targets/?site=<código MPC>&num=N` — pública,
  JSON-RPC. Lista de objetivos específica del sitio con score, prioridad, coste
  (minutos), vmag, movimiento, incertidumbre, flag NEOCP, flags
  impacto/radar/NHATS/Yarkovsky.
- `GET .../ephem/?site=<código>&object=<packed>` — pública. Efeméride por sitio
  (alt, az, mag, movimiento) precalculada por NEOfixer (find_orb de Bill Gray).
- `GET .../orbit/?object=<packed>` — pública. **Elementos orbitales preliminares**
  de objetos sin confirmar (NEOCP), calculados con Find_Orb desde la astrometría del
  MPC: elementos keplerianos completos (`a, e, q, Q, i, asc_node, arg_per, M, Tp,
  epoch`) con sigma por elemento, MOIDs por planeta, `p_NEO`, nº de residuos y arco
  observado. `parse_neofixer_orbit()` los normaliza a la forma SBDB (ADR-023);
  alimentan el dibujo de órbita, la tabla de parámetros (con sigmas) y la efeméride
  local de `core/ephemeris.py`.
- `GET .../report/?key=<api key>&site=<código>&object=<id>&status=<s>` — **requiere
  la clave API del usuario** (Configuración). Reporta `will_observe`/`observed`/...
  para coordinación comunitaria. Opcional.
- TTL: 12 h (`targets`, `ephem`); 1.5 h (`orbit` — las órbitas preliminares cambian
  rápido). Ojo: `object` debe ser designación *empaquetada* (packed).

### Rochester Astronomy (David Bishop) — `rochester.py` — supernovas recientes

- `https://www.rochesterastronomy.org/snimages/sndate.html` — tabla HTML pública,
  parseada con lxml (mismo layout que el histórico `saas/supernova.py`).
- TTL: 6 h. Es la web de una sola persona: sé buen ciudadano (¡cachea!).

### COBS — `cobs.py` — cometas activos

- `https://cobs.si/api/comet_list.api` — JSON público: magnitud actual observada,
  fecha/magnitud de perihelio, flag de actividad, tipo (C/P/N), nombre MPC.
- TTL: 6 h.

### PCCP del MPC — `pccp.py` — posibles cometas

- `https://www.minorplanetcenter.net/iau/NEO/pccp_tabular.html` — tabla HTML pública:
  designación temporal, score de cometa (0–100), RA/Dec, V, arco, notas.
  No existe endpoint JSON; se parsea con lxml.
- TTL: 6 h.

### ESA NEOCC — `esa_neo.py` — próximas aproximaciones (alertas)

- `https://neo.ssa.esa.int/PSDB-portlet/download?file=esa_upcoming_close_app` —
  texto público de ancho fijo: objeto, fecha, distancia (km/AU/LD), diámetro, H,
  magnitud máxima, velocidad relativa.
- TTL: 6 h. (El endpoint de lista de prioridad ESA responde 200 con cuerpo vacío a
  fecha 2026-08; se mantiene con degradación elegante.)

### ExoClock (ESA Ariel) — `exoclock.py` — tránsitos de exoplanetas

- `https://www.exoclock.space/database/planets_json` — JSON público, ~776 planetas:
  efeméride de tránsito (`ephem_mid_time`, `ephem_period`), profundidad (mmag),
  duración, prioridad, `min_telescope_inches`, deriva O-C, magnitud estelar y
  coordenadas.
- TTL: 24 h. Los instantes de tránsito se calculan en local (t0 + n·P) — ver
  `core/transits.py`.

### Catálogo HADS (P. Wils / VVS) — `hads_sheet.py` — δ Scuti de alta amplitud

- `https://docs.google.com/spreadsheets/d/1oGA2HaEHE8L6eX19ZoHqQQTu0LYV56HX3Srg7oCtOHo/export?format=xlsx`
  — libro público de Google Sheets (una pestaña por año, actualizado a diario
  por el coordinador del programa): nombre (con aliases), RA/Dec, magnitudes
  Max/Min, periodo (h), **prioridades por color de fuente** (nombre rojo/naranja
  = cambios de periodo encontrados/posibles — ¡prioridad!; coordenadas azules =
  aún no observada; nombre morado = multiperiódica) y las celdas mensuales de
  cobertura por observador.
- TTL: 12 h, caché de dos niveles (XLSX crudo + JSON parseado). Parseo con
  `zipfile`+`xml.etree` de la stdlib (sin openpyxl en runtime). El snapshot
  empaquetado `assets/HADS-stars.csv` (168 estrellas, aliases ricos) es el
  respaldo offline; el merge vive en `core/hads.py` (ADR-034).

### AAVSO VSX — `vsx.py` — estrellas variables (Track V, ADR-035)

- `GET https://vsx.aavso.org/index.php?view=api.object&ident=<nombre>&format=json`
  — API pública del Variable Star Index. **Ojo: el dominio `www.aavso.org` está
  tras Cloudflare y bloquea clientes simples; el subdominio `vsx.aavso.org`
  responde 200 limpio** (verificado 2026-09-11). Extracción: nombre + AUID,
  RA/Dec, tipo variable, periodo (d), época (JD→MJD en el parser), máx/min con
  banda, clasificación espectral, constelación.
- TTL: 7 d. **Degradación**: `lookup()` devuelve `None` si no existe o falla →
  ficha por SIMBAD (coordenadas) → alta manual; Tonight es local y nunca rompe.

### ALeRCE ZTF API v1 — `surveys.py` — contexto de curvas (V-f)

- `GET https://api.alerce.online/ztf/v1/conesearch?_ra=..&_dec=..&_radius=..` y
  `GET .../lightcurve?oid=<oid>` — dos llamadas cacheadas por objeto (oid →
  curva). Puntos grises de referencia `source="survey:ztf"` bajo los propios,
  nunca mezclados (bandas ZTF g/r/i mapeadas a filtros). Verificado 2026-09-11.
- TTL: 30 d (la fotometría de survey no cambia). Fallo → `[]`; el botón de
  surveys avisa y nada más se rompe.

## Fuentes de datos de objeto (alimentan «Explora» y «Post»)

### JPL SBDB — `sbdb.py` — identidad y datos físicos de cuerpos menores

- `GET https://ssd-api.jpl.nasa.gov/sbdb.api?sstr=<nombre>&phys-par=1` — JSON público:
  nombre completo, `kind` (asteroide/cometa), clase orbital, elementos
  (a, e, i, q, Q, per...), MOID y parámetros físicos (H, diámetro, rotación, albedo,
  clase espectral; M1/K1 en cometas). TTL: 7 d.

### JPL Horizons — `horizons.py` — efemérides precisas

- `GET https://ssd.jpl.nasa.gov/api/horizons.api?...` — pública. `CENTER` acepta
  códigos de observatorio MPC directamente (p. ej. `'Z41'`). QUANTITIES usados:
  `1` (RA/Dec), `4` (az/el aparente), `19` (rango heliocéntrico), `20` (rango al
  observador). TTL: 12 h.

### JPL CAD — `cad.py` — aproximaciones cercanas

- `GET https://ssd-api.jpl.nasa.gov/cad.api?des=<des>&date-min=..&date-max=..` —
  JSON público: fecha de aproximación, distancia (AU), velocidad relativa. TTL: 7 d.

### SIMBAD (CDS) — `simbad.py` — transitorios y galaxias anfitrionas

- `POST https://simbad.cds.unistra.fr/simbad/sim-script` — interfaz de scripts
  pública. Consultas: `query id <nombre>` (tipo, coordenadas, flujo V),
  `query around <nombre> radius=<r>` (candidatas a galaxia anfitriona con redshift
  vía `%RV`). TTL: 7 d.
  Respaldo: ante un fallo de red el mismo script se reintenta una vez contra el
  espejo de Harvard (`https://simbad.harvard.edu/simbad/sim-script`) — los
  `query around` pesados superan con frecuencia el timeout de 40 s en Estrasburgo
  mientras el espejo responde 3× más rápido (medido 2026-09); los scripts
  `around` usan 60 s, los `id` 40 s.

### TNS (Transient Name Server) — `tns.py` — posiciones de transientes frescos

- `GET https://www.wis-tns.org/object/<nombre>` — página pública del objeto (HTML),
  parseada con lxml: el bloque `field-radec` lleva las coordenadas J2000 en grados
  decimales, más tipo/magnitud/fecha de descubrimiento. Sin credenciales; una
  descarga cacheada por objeto, TTL 6 h — sé buen ciudadano. Primer resolvedor de
  la función blink (ADR-018): los transientes frescos aparecen en TNS días antes
  de que SIMBAD los ingeste. (La API bot oficial queda disponible cuando se
  conecten `tns_bot_name`/`tns_bot_key`.)

### Astrometry.net (nova) — `astrometry.py` — resolución ciega de astrometría

- `POST /api/login` + `POST /api/upload` + sondeo `/api/submissions/<id>` y
  `/api/jobs/<id>` + `GET /wcs_file/<jobid>` — requiere la clave de API gratuita
  del usuario (`astrometry_key` en Ajustes). La usa la función blink cuando el
  FITS del usuario no tiene WCS (ADR-018). Las tarjetas WCS resueltas se cachean
  por hash del fichero (TTL 30 d): la misma imagen nunca se resuelve dos veces.

### NASA Exoplanet Archive — `exoplanet_archive.py` — detalle de exoplanetas

- Consulta TAP sync (`https://exoplanetarchive.ipac.caltech.edu/TAP/sync`,
  `format=json`) sobre `pscomppars`: período, radio, masa, temperatura de equilibrio,
  distancia del sistema, estrella anfitriona. TTL: 7 d.

## Sol y entorno

### NOAA SWPC — `noaa.py`

- `services.swpc.noaa.gov/json/solar-cycle/observed-solar-cycle-indices.json` (SSN, F10.7)
- `.../products/noaa-planetary-k-index.json` (Kp)
- `.../json/solar_regions.json` (regiones activas — alimenta nuestro mapa de manchas)
- `.../json/goes/primary/xrays-7-day.json` (flujo de rayos X → clases de fulguración)
- Todo JSON público. TTL: 1 h.

### SILSO (SIDC, Real Observatorio de Bélgica) — `silso.py`

- Series de número de manchas para contexto del ciclo. Datos públicos con crédito.
  TTL: 24 h.

### NASA SDO — `sdo.py`

- `https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_<canal>.jpg`
  (0193, 0304, HMII, ...). Imágenes de dominio público con crédito
  («Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams»). TTL: 1 h.

## Imágenes

### Cutouts — `cutouts.py` — campos de referencia para supernovas

- DESI Legacy Survey: `https://www.legacysurvey.org/viewer/jpeg-cutout?ra=..&dec=..`
  (color, bonitos). hips2fits del CDS: `https://alasky.cds.unistra.fr/
  hips-image-services/hips2fits?...` (DSS color, Pan-STARRS). Ambos servicios públicos.
- **Referencia para blink (ADR-018)**: hips2fits `hips=CDS/P/PanSTARRS/DR1/g`, formato
  FITS, pedido con el centro celeste, escala de píxel y rotación exactos de la imagen
  del usuario (parámetro `rotation_angle`) de modo que ambas imágenes queden alineadas
  por construcción. Fallback `CDS/P/DSS2/red` si dec < −30° (fuera de la cobertura 3π
  de PS1). Atribución en los exports: «PanSTARRS DR1 g (CDS hips2fits)» /
  «DSS2-red (CDS hips2fits)».
- TTL: 30 d (los campos de referencia no cambian).

### Imágenes de descubrimiento (TNS) — opcional, solo dentro de la app

- Las páginas de objeto de TNS muestran imágenes de descubrimiento del survey; el
  acceso automatizado requiere las credenciales bot TNS del usuario (Configuración).
  Se muestran **dentro de la app** como referencia; solo se reutilizan en posts si la
  licencia del survey lo permite (ZTF/ATLAS con crédito). Si no, enlazamos a la
  página TNS del objeto. Ver ADR-016.

## Enlaces externos (nunca incrustados — copyright)

Mapas solares de Raben, SolarMonitor, SIDC/uset, universemonitor, ETD (var.astro.cz),
web de NEOfixer, web de TNS. La app los abre en el navegador.

## Efemérides locales

 Sol, Luna y planetas: algoritmos de baja precisión de Paul Schlyter
 (`core/ephem_minor.py`) — math puro, precisión de arcminutos, offline. Cuerpos
 menores: propagación kepleriana desde elementos SBDB. Ver ADR-009.

 *Superficie* de la Luna (solo el icono de fase, no efemérides): una fotografía
 empaquetada, `nightscribe/assets/moon_disk.png` — Gregory H. Revera,
 "FullMoon2010", Wikimedia Commons, CC BY-SA 3.0 (crédito completo en
 `assets/ATTRIBUTION.txt`). Generada una vez en desarrollo; la app no necesita
 red para ella.
