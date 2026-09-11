# HADS — Fase 0: fuente de datos (sheet → runtime)

> Subplanes H0.1–H0.5 del plan maestro [../hads-stars.md](../hads-stars.md).
> Un subplan = un commit. Anclas verificadas a HEAD `c607b81`; si una no
> coincide: **parar y reportar**.
> Contexto de datos: [../../HADS.md](../../HADS.md) §3 (formatos) y la leyenda
> de colores (tabla en el maestro). Fuente de verdad: Google Sheet de P. Wils
> <https://docs.google.com/spreadsheets/d/1oGA2HaEHE8L6eX19ZoHqQQTu0LYV56HX3Srg7oCtOHo/>
> (público; una pestaña por año; se actualiza a diario).

Reglas recordatorio: cabecera GPL en todo `.py` nuevo (AGENTS.md), código en
inglés, comentarios `# @args:` / `# @return:`, red solo desde `core/sources/`
a través de la caché de `core/db.py`.

---

## H0.1 — Mini-lector XLSX stdlib

**Lee primero**: `nightscribe/core/sources/exoclock.py` (patrón de fuente,
59 líneas); formato XLSX (resumen abajo).

**Toca**: `nightscribe/core/sources/hads_sheet.py` (**nuevo**);
`tests/unit/test_hads_sheet.py` (**nuevo**).

**Implementa** en `hads_sheet.py` (por ahora solo el lector; el resto llega en
H0.2/H0.3):

```python
def _read_xlsx(data):
    # @args: data - raw bytes of an .xlsx workbook
    # @return: dict {sheet_name: [row, ...]} where each row is
    #          {col_letter: (text, font_rgb)}; font_rgb is the 6-hex font
    #          color of the cell ("FF0000") or None when unstyled
```

Formato XLSX (zip): `xl/workbook.xml` (`<sheet name=… r:id=…>`),
`xl/_rels/workbook.xml.rels` (r:id → `worksheets/sheetN.xml`),
`xl/sharedStrings.xml` (`<si>`: concatenar todos los `<t>` descendientes),
`xl/styles.xml` (`<fonts><font>` en orden — color en `color/@rgb`, quedarse
con los últimos 6 hex; `<cellXfs><xf fontId=…>`: índice de estilo → índice de
fuente), `xl/worksheets/sheetN.xml` (`<c r="A1" s="…" t="s|str|inlineStr|n">
<v>…`): letra de columna del `@r`; valor: `t="s"` → sharedStrings[int(v)],
`t="inlineStr"` → `is/t`, resto → `v` crudo. Namespaces con URI completa
(`{http://schemas.openxmlformats.org/spreadsheetml/2006/main}` y el de
relationships). Solo `zipfile` + `io` + `xml.etree.ElementTree` — **prohibido
openpyxl en runtime** (dependencia solo-dev descartada, decisión H-j).
Tolerante: sin sharedStrings/styles, celdas sin `s`, color ausente → `None`.
Solo lanza `ValueError` si el zip no es un xlsx válido.

Tests: helper `_make_xlsx(sheets)` en el propio test que fabrique los bytes con
`zipfile` + plantillas XML (sin fixture binario). Casos: dos hojas con nombre;
cadena compartida con fuente roja; numérica sin estilo; celda inline; celda
con color en estilo. Aserciones: nombres de hoja, valores, `(texto, rgb)` por
celda, tolerancia a celdas sin estilo.

**Hecho cuando**: `pytest tests/unit/test_hads_sheet.py -q` verde; suite
unitaria verde (anota N→M); cabeceras GPL; comentarios `@args/@return`.
**Commit**: `Core: HADS sheet XLSX reader (stdlib zipfile+xml) + unit tests (ADR-034, subplan H0.1)`
**Estado**: **Hecho** (898→904)

---

## H0.2 — Descarga + caché (workbook crudo)

> **Resecuencia al ejecutar**: `parsed()` (caché de segundo nivel) necesita
> `_parse_workbook` → se implementa en H0.3 junto al parser. H0.2 entrega
> `workbook()` completo y testeado; ningún commit queda a medias.

**Lee primero**: `nightscribe/core/db.py` (`SOURCE_TTL` líneas 29-51,
`http_get` 308-322, `cache_get` 271, `cache_put` 295);
`nightscribe/core/sources/exoclock.py:24-39` (patrón fetch+caché).

**Toca**: `nightscribe/core/db.py` (SOURCE_TTL);
`nightscribe/core/sources/hads_sheet.py` (continúa); tests.

**Implementa**:
- `db.py` tras la línea 39 (`"exoclock": 24 * HOUR,`):
  `"hads": 12 * HOUR,  # Wils updates the sheet daily; tonight is a nightly run`.
- En `hads_sheet.py`:
  ```python
  WORKBOOK_URL = ("https://docs.google.com/spreadsheets/d/"
                  "1oGA2HaEHE8L6eX19ZoHqQQTu0LYV56HX3Srg7oCtOHo/"
                  "export?format=xlsx")

  def workbook(force=False):
      # @return: raw xlsx bytes (cached ≤12 h) or None on network failure
      def fetch():
          r = requests.get(WORKBOOK_URL, timeout=60)
          r.raise_for_status()
          return r.content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      try:
          body, _ = db.http_get("hads:workbook", "hads", fetch, force=force)
          return body
      except requests.RequestException as err:
          logger.warning("HADS sheet fetch failed: %s", err)
          return None
  ```

Tests (`test_hads_sheet.py`, fixture `tmp_db` de `tests/conftest.py`;
patrón `monkeypatch.setattr(hads_sheet, "db", tmp_db)`):
fetch falsa vía `monkeypatch.setattr(hads_sheet.requests, "get", ...)`;
1ª llamada descarga, 2ª lee la caché sin red; `force=True` repite la
descarga; fallo de red → `None`; expiración por TTL (envejecer `fetched`
en `http_cache`).

**Hecho cuando**: tests verdes; suite verde (N→M). Sin red en los unitarios.
**Commit**: `Core: HADS sheet fetch with 12 h TTL (ADR-034, subplan H0.2)`
**Estado**: **Hecho** (904→908)

---

## H0.3 — Workbook → estrellas (colores, cobertura) + `parsed()` + test funcional

**Lee primero**: la leyenda de colores (maestro §Decisiones, H-i);
`tests/functional/test_functional.py` línea 21 (`pytestmark`).

**Toca**: `nightscribe/core/sources/hads_sheet.py` (continúa);
`tests/functional/test_hads_live.py` (**nuevo**).

**Implementa** `_parse_workbook(data) -> dict`:
- Pestañas: nombre casa `^\d{4}$` (año). Catálogo = pestaña de año máximo;
  cobertura = todas las pestañas-año. Ignora cualquier otra pestaña.
- Filas: cabecera = la fila cuya col A ∈ `{"Ster", "vvs", "Name"}`
  (case-insensitive); si no aparece, se salta la primera fila igualmente.
  Datos desde la siguiente hasta la primera col A vacía.
- **Columnas por posición** (tolerante a variantes `Ster`/`vvs` y meses
  NL/EN): A nombre, B RA, C DEC, D Max, E Min, F Periodo(h), G..R = ene..dic.
  Numéricos tolerantes (coma decimal, vacío → `None`). RA/DEC se devuelven
  **crudos** (la conversión a grados es de `hads.py` con `coords.*`).
- Colores → flags (hue de los 6 hex vía `colorsys.rgb_to_hsv`):
  - nombre: rojo (h<15° o >340°) → `priority="period_change"`; naranja
    (15-45°) → `"period_change_possible"`; morado (260-320°) →
    `multiperiodic_sheet=True`.
  - col B (RA): azul (200-260°) → `observed=False`.
  - negro/None → sin flag; otro color → `logger.debug` y seguir.
  - **Paso dev obligatorio antes de fijar los rangos**: descargar una vez el
    workbook real (`curl -L "<WORKBOOK_URL>" -o /tmp/hads.xlsx`), imprimir los
    RGB reales de unas cuantas estrellas conocidas de cada clase y dejar los
    valores/rangos exactos comentados en el código (enlace a la leyenda).
- Resultado:
  ```python
  {"fetched_year": int,                      # pestaña más reciente
   "stars": [{"sheet_name", "ra", "dec", "max", "min", "period_h",
              "priority",                    # None | "period_change" | "period_change_possible"
              "observed",                    # False si coords azules
              "multiperiodic_sheet"}],
   "coverage": {year: {sheet_name: [meses 1-12 cubiertos]}}}
  ```
- `parsed(force=False)` (caché de segundo nivel — el parseo XLSX de ~1-2 s
  ocurre una vez por TTL, no por llamada):
  ```python
  def parsed(force=False):
      # @return: parsed workbook dict or None
      cached = db.cache_get("hads:parsed")
      if cached:
          return json.loads(cached[0].decode("utf-8"))
      data = workbook(force=force)
      if data is None:
          return None
      try:
          result = _parse_workbook(data)
      except (ValueError, KeyError, zipfile.BadZipFile) as err:
          logger.warning("HADS sheet parse failed: %s", err)
          return None                              # never cache a failure
      db.cache_put("hads:parsed", "hads", json.dumps(result).encode("utf-8"))
      return result
  ```
  Tests: 1ª llamada descarga+parsea, 2ª lee `hads:parsed` sin red ni parseo;
  xlsx corrupto → `None` y NO envenena la caché.

Test funcional `tests/functional/test_hads_live.py` (**nuevo**, con
`pytestmark = pytest.mark.network`): descarga real → ≥150 estrellas; existe
"GP And"; ≥1 estrella con cada prioridad roja/naranja; ≥1 no observada;
coverage cubre 2011..año actual. Además imprime un **informe de deriva**
(por cada estrella del bundle casada por nombre: diffs de period/max/min
bundle vs hoja) — informativo, **nunca falla** por deriva.

**Hecho cuando**: unitarios verdes (N→M) + `pytest tests/functional -k hads_live`
verde con red.
**Commit**: `Core: HADS workbook parsing — color priorities + monthly coverage (ADR-034, subplan H0.3)`
**Estado**: **Hecho** (908→914). Hallazgos al inspeccionar el workbook real:
colores de la leyenda = FF0000/FF9900/9900FF/0000FF puros (mapeo por tono
con guarda de saturación/valor: el negro explícito 000000 daría hue=0=rojo
falso); las pestañas-año tienen sección «Southern stars» tras la leyenda →
fila de datos = A+B+C no vacías (nunca «parar en Legend»); las claves de
`coverage` son strings para que el JSON de la caché no cambie la forma;
coordenadas azules **hoy no hay ninguna** (todas observadas alguna vez) —
el mecanismo queda listo para cuando Wils marque una; el GP And del bundle
(1.89 h) **coincide con la pestaña 2026** (el 2.89 solo vive en la pestaña
2010): el informe de deriva sale vacío.

---

## H0.4 — `core/hads.py` (catálogo, merge, derivados)

**Lee primero**: `nightscribe/core/exposure.py:127-145`
(`recommended_transit_exposure`); patrón de assets
`nightscribe/gui/theme.py:29`; `coords.angular_separation` (existe; uso en
`suggest.py:133`).

**Toca**: `nightscribe/core/hads.py` (**nuevo**);
`tests/unit/test_hads.py` (**nuevo**).

**Implementa**:
- `_ASSETS = Path(__file__).resolve().parent.parent / "assets"`;
  `BUNDLED_CSV = _ASSETS / "HADS-stars.csv"`.
- `catalog_bundled() -> list[dict]` con `@lru_cache(maxsize=1)`: `csv.reader`
  (maneja CRLF + comillas él solo); columnas `Name,RA,DEC,Max,Min,Period_h`.
  Parseo de `Name`: nombre primario = texto hasta `" ="` o `" (="`; aliases de
  los grupos `(=A=B)` (split por `"="`) y de los `"X = Y"` sueltos; flags de
  texto: `multiperiodic?`/`multiperiodic!` → `multiperiodic`;
  `-- Non-radial` → `non_radial`; `change in amplitude?` → `amp_change`.
  `ra_deg`/`dec_deg` vía `coords.ra_hms_to_deg` / `coords.dec_dms_to_deg`.
  Filas malformadas → `logger.debug` + skip. Dict:
  `{name, aliases, ra_deg, dec_deg, max, min, period_h, multiperiodic,
  non_radial, amp_change, priority: None, observed: True, coverage: {}}`.
- `catalog(merge_online=True) -> list[dict]`: base = `catalog_bundled()`;
  online = `hads_sheet.parsed()`; `None` → base (offline). Con online:
  casar por `coords.angular_separation(...) < 1/60` deg (1'); del online:
  `period_h`/`max`/`min` (si no `None`), `priority`, `observed`, `coverage`;
  del bundle: `name`, `aliases`, flags. Online sin pareja → entrada nueva
  (`name=sheet_name`, `aliases=[]`); bundle sin pareja → se conserva
  (`logger.debug`). **No memoizar el merge** (168×168 es trivial; así un GUI
  abierto días respeta el TTL de la caché).
- Constantes: `FAMOUS_HADS = ("CY Aqr", "DY Peg", "SZ Lyn", "XX Cyg",
  "V2455 Cyg", "AD CMi")` (las 6 verificadas presentes en el CSV);
  `POINTS_PER_CYCLE = 12`; `CADENCE_CAP_S = 900.0`; `SESSION_CYCLES = 2`.
- `derive(star, hours_up, plate_scale=None) -> dict`: `amp = min - max`
  (¡ojo: en magnitudes Max < Min! GP And 10.4→11 ⇒ amp 0.6);
  `mag_med = (max + min) / 2`; `cycles = hours_up / period_h` si ambos;
  `cadence_s = min(period_h * 3600 / POINTS_PER_CYCLE, CADENCE_CAP_S)`;
  `session_req_h = SESSION_CYCLES * period_h`;
  `exp_s = exposure.recommended_transit_exposure(mag_med, plate_scale)`.
- `span_hours(window_start_iso, window_end_iso) -> float | None`.
- `covered_this_month(star, when=None) -> bool | None`: cobertura del año de
  `when` (default: hoy UTC); sin pestaña del año → `None`; mes actual en la
  lista → `True`/`False`.
- `lookup(name) -> dict | None`: normalizado (casefold, espacios colapsados)
  contra `name`+`aliases` **del bundle** (para `enrich`, B.3; offline por
  diseño).
- `sawtooth_template(period_h, amp, mag_med, rise_frac=0.35, n=40)` →
  lista `(phase, mag)`: subida lineal 0→`rise_frac` (min luz→max luz, ojo al
  eje invertido de magnitudes) y bajada `rise_frac`→1. Comentario:
  *esquemática, nunca datos reales*. API agnóstica de kind a propósito
  (guardarraíl H-n).
- Docstring de módulo: qué es una HADS, fuente híbrida, leyenda (1 línea por
  color), por qué 2×P.

Tests `test_hads.py`: bundle real (168 estrellas; "GP And" lleva alias
"GSC 01739-01964"; conteos de flags: 10 multiperiodic, 3 non_radial,
1 amp_change); `derive` (GP And bundle: P=1.89 → cadence 567 s; amp 0.6);
merge con online fabricado (sin red): prioridad aplicada, estrella nueva
añadida, `parsed()=None` → bundle; `covered_this_month` con coverage
fabricada y `when` fijado; sawtooth: máximo de luz (mínimo mag) en
`phase=rise_frac`, amplitud correcta, n puntos.

**Hecho cuando**: tests verdes; suite verde (N→M).
**Commit**: `Core: hads module — bundled catalog, online merge, session math (ADR-034, subplan H0.4)`
**Estado**: pendiente

---

## H0.5 — Docs de datos

**Toca**: `docs/HADS.md`, `docs/HADS.es.md`, `docs/DATA_SOURCES.md`,
`docs/DATA_SOURCES.es.md`.

**Implementa**:
- `HADS.md`/`HADS.es.md`: nueva sección «Fuente de verdad y refresco» /
  «Source of truth and refresh»: URL del Google Sheet (se actualiza a diario),
  arquitectura híbrida (runtime online TTL 12 h + snapshot empaquetado como
  respaldo y fuente de aliases), tabla de la leyenda de colores, y cómo
  refrescar el snapshot a mano guiado por el informe de deriva del test
  funcional (`pytest tests/functional -k hads_live`). Actualizar la nota del
  §3 («Copy source…») para reflejar la nueva arquitectura.
- `DATA_SOURCES.md`/`.es.md`: entrada nueva espejo de la de ExoClock
  (líneas 58-63): «HADS catalogue (P. Wils / VVS) — `hads_sheet.py` —
  variable stars», con endpoint `export?format=xlsx`, campos (nombre, coords,
  Max/Min, periodo, colores de prioridad, cobertura mensual), TTL 12 h, y la
  nota del fallback empaquetado.

**Hecho cuando**: enlaces correctos, bilingüe ES/EN; suite verde (sin cambios
de código).
**Commit**: `Docs: HADS source-of-truth sheet + refresh procedure + DATA_SOURCES entry (ADR-034, subplan H0.5)`
**Estado**: pendiente
