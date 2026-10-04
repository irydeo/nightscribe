# Fase 1: calibración de imágenes y biblioteca de masters

> Fase del plan maestro [`PLAN.md`](PLAN.md). Decisiones: D2, D3, D4, D5, D6.

## Por qué

Un objeto débil no emerge del ruido si la imagen trae el patrón térmico del
sensor y las motas del tren óptico. El apilado amplifica la señal, pero también
el pedestal y el viñeteado. Sin calibrar, el sigma-clipped rechaza píxeles que
deberían ser cielo y el centroide se desplaza. Esta fase construye el paso que
convierte un frame crudo en un frame utilizable, y lo deja reutilizable para la
fotometría de series, no escondido dentro del track & stack.

## Implementación

### 1.1 Módulo `core/calibration.py`

Cabecera obligatoria y comentarios didácticos: cada bloque explica el qué y el
por qué, con los números medidos (cuánto pedestal se quita, qué residuo deja).

**Biblioteca de masters.** El índice vive en la base de datos y los ficheros en
disco. La clave de búsqueda es lo que hace válido un master: cámara, ganancia,
temperatura del sensor, tiempo de exposición y filtro.

- `add_master(db, path, meta) -> int`: indexa un master ya construido. `meta`
  trae `camera`, `gain`, `temp_c`, `exptime_s`, `filter` y `kind`.
- `list_masters(db, camera=None, kind=None) -> list[MasterRef]`.
- `delete_master(db, master_id, delete_file=False)`: retira del índice y, si se
  pide, borra el fichero.
- `find_master(db, kind, camera, gain, temp_c, exptime_s, filter, tol_c=3.0)
  -> MasterRef | None`: coincidencia **exacta** en cámara, ganancia, exposición
  y filtro; **temperatura más cercana** dentro de la tolerancia. Si hay varios
  candidatos para la misma clave, gana el más reciente.

Por qué la exposición es exacta y la temperatura es tolerante: en CMOS el
patrón térmico no escala bien con el tiempo (no es lineal), así que un dark de
otra exposición deja residuo; la temperatura sí se puede tolerar porque su
efecto es suave y monótono, y ±3 °C es lo que el autor acepta.

`MasterRef` es un dataclass con `id, camera, gain, temp_c, exptime_s, filter,
kind, path, created, meta`.

**Receta declarativa.** No se cablea a un sensor. La receta dice qué piezas hay
y el motor aplica lo que encuentra.

- `resolve_recipe(db, meta) -> RecipeReport`: mira la biblioteca para los
  metadatos del light y devuelve qué master usaría para cada pieza, o qué
  falta. `RecipeReport` lleva `offset` (`dark` o `bias` o `None`), `dark`
  (`dark` o `None`), `flat` (`flat` o `None`) y `warnings` en lenguaje llano.
- `calibrate(data, header, recipe) -> (data_cal, report)`: aplica la receta a
  un array.

La aritmética, en orden, y el porqué de cada paso:

1. **Offset y térmica.** Si existe un master **dark a la exposición exacta del
   light**, se resta ese dark: ya incluye el bias y la corriente térmica, así
   que restar además un bias sería restar dos veces el pedestal. Si no hay
   dark, se resta el **bias** y se avisa de que la corriente térmica no se ha
   quitado (queda un pedestal que crece con la exposición). Si no hay ninguno
   de los dos, no se toca y se avisa.
2. **Flat.** Se corrige con el flat **del mismo filtro**, restándole antes su
   propio offset (su dark-flat a la exposición del flat, o el bias si el flat
   es corto), y **normalizando por la mediana** para que la división no cambie
   el nivel de flujo. Sin normalizar, dividir por el flat cambiaría la escala
   fotométrica de toda la imagen.
3. **Sin flat**: no se divide y se avisa de que el residuo de flat queda sin
   corregir (importa para la magnitud, poco para el centroide).

Cuidado didáctico: el orden importa. Si se dividiera por el flat antes de
restar el offset, se amplificaría el pedestal en las zonas oscuras del flat.

**Aplicación en lote.**

- `calibrate_paths(paths, db, cfg, progress=None, cancel=None)
  -> CalibrationReport`: calibra una lista de frames, con progreso y
  cancelación.
- `calibrate_region(data, header, recipe, box) -> array`: la variante que
  calibra **solo la ROI** (D32): los masters son pocos y caben en RAM, así que
  se guardan completos en float32 una vez y se recortan a la caja de cada
  frame, en lugar de calibrar los 16 MP para usar un trozo. El resultado es
  float32 (D32).
- `export_calibrated(paths, outdir, ...)`: escribe copias calibradas (opt-in,
  D6). Reutiliza `astropy.io.fits` para conservar la cabecera y añadir el
  rastro de la calibración (qué masters se usaron, con su ruta y su fecha).

### 1.2 Migración `user_version` 15 → 16

Aditiva e idempotente, al estilo de las migraciones existentes de `core/db.py`:

```sql
CREATE TABLE IF NOT EXISTS calib_masters (
    id        INTEGER PRIMARY KEY,
    camera    TEXT,
    gain      REAL,
    temp_c    REAL,
    exptime_s REAL,
    filter    TEXT,
    kind      TEXT,          -- bias | dark | dark_flat | flat
    path      TEXT NOT NULL,
    created   TEXT,
    meta      TEXT           -- JSON: tamaño, fecha de construcción, notas
);
CREATE INDEX IF NOT EXISTS idx_calib_key
    ON calib_masters(camera, gain, exptime_s, filter, kind);
```

### 1.3 Configuración

- `calib_root`: carpeta base de los masters.
- `calib_temp_tol_c`: 3,0.
- `calib_export`: False.

## Tests

`tests/unit/test_calibration.py`:

- **Aritmética exacta**: con masters sintéticos de valores conocidos, el
  resultado es `(light - dark)` y `(light - offset) / flat_norm` calculados a
  mano; se comprueba también que **no** se resta bias y dark a la vez.
- **Matching**: misma clave, distinta temperatura dentro y fuera de la
  tolerancia; exposición distinta no casa; filtro distinto no casa; varios
  candidatos, gana el más reciente.
- **Ausencia**: sin master, `resolve_recipe` devuelve aviso y `calibrate` no
  lanza excepción.
- **Flat**: el residuo de flat desaparece con un flat sintético de viñeteado
  conocido; sin flat, el viñeteado permanece.
- **Migración**: `tests/unit/test_db_v16.py` con migración desde v15 y desde
  esquema limpio, idempotencia y reapertura.

## Salida limpia

`core/calibration.py` usable desde tests y CLI, con la biblioteca indexada y la
receta resuelta; la GUI todavía no expone la acción (llega en la fase 7).

## Hecho cuando

La suite unitaria está verde, la migración v16 abre bases existentes sin
pérdida, y la calibración de un frame sintético deja el residuo por debajo del
nivel de ruido.
