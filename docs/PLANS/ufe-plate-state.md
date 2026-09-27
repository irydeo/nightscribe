# Plan de implementación: persistencia del estado de placa en el UFE (2026-09-25)

> **ESTADO: fase 1 completada (2026-09-26, ADR-047).**
> Fase 2 (empaquetado XISF): diseñado, sin tocar todavía.
>
> **Objetivo**: una placa medida dentro de un proyecto se reabre
> *entera*: el estiramiento, la receta de medida, la secuencia de
> comparaciones y la última medición asociada a ese fichero. Nada se
> pierde al cerrar el editor, y las mediciones no pueden ir por libre:
> cada punto guarda la referencia a la placa de la que salió.
>
> **Regla del usuario**: "las mediciones asociadas a ficheros, no pueden
> ir por libre". Clic en una medición registrada: carga la placa, la
> secuencia y el estado; si no tiene placa asociada, mensaje de aviso.
> Reset de los puntos de esa placa alcanzable desde el UFE.

## Decisiones del diseño

### Almacenamiento (dos tiendas, un mismo proyecto)

1. **Mediciones**: columna `file_id INTEGER` (FK `project_files.id`,
   `ON DELETE SET NULL`) en `photometry_points`. Migración en
   `core/db.py`, `PRAGMA user_version` 10 -> 11, con índice. Es
   la única fuente de verdad de la curva: reports (CSV, AAVSO EFF),
   dashboard de atención y vigilias siguen leyendo la tabla.
2. **Estado de trabajo de la placa**: JSON dentro de
   `project_files.meta["ufe"]` (sin migración, `meta` ya es JSON):

   ```
   {
     "stretch":    {black, white, gamma, invert},
     "measure":    {band, rap, rin, rout, radii_manual, sigmaclip,
                    seeing, color, target_bv, sky},
     "sequence":   {catalog, catalog_name, fov_arcmin, target_mag,
                    entries: [{name, kind, star: {...}}]},
     "saved_at":   "ISO-8601"
   }
   ```

   `subtract` NO se persiste (depende de una placa de referencia del
   blink que no se conserva; al cambiar de imagen se resetea igual).
   El estado de `subtract` se restaura siempre a "apagado".

### Dos guardar, ambos explícitos (sin autoguardado)

- **Guardar medida** (`_ufe_point_hook`): resuelve la fila de
  `project_files` de la placa abierta (`dlg.state.path` ->
  `project.find_file`), pasa `file_id` a `add_point` y escribe
  `meta["ufe"]` (stretch + medida + secuencia) en la misma llamada.
  Si no hay proyecto o la placa no está registrada: la medición se
  guarda sin `file_id` y no se toca estado (sin proyecto no hay
  "ir por libre").
- **Guardar secuencia a CSV** (`_ufe_save_hook`, kind `sequence`):
  además del CSV en disco, escribe `sequence` en `meta["ufe"]` de la
  placa abierta y sigue escribiendo `project.context["sequence"]`
  (respaldo global por compatibilidad).
- **Sin hook al cerrar el diálogo**: cerrando no se guarda nada
  (decisión del usuario). `closeEvent` sin cambios.

### Restaurar (API simétrica en las pestañas)

- `UfeMeasureTab.capture_state()` / `apply_state(st)`.
- `UfeCompareTab.capture_state()` / `apply_state(st)`: rellena
  `_entries` y reconstruye la tabla (hoy solo hay lector `entries()`).
- `UfeDialog.apply_plate_state(st)`: primero estiramiento
  (`set_stretch` + invertir) y luego ambas pestañas.
- Se aplica DESPUÉS del señal `_on_image_loaded` (que resetea el
  estado por placa), en el mismo flujo, sin destello de estado vacío.
- Puntos de entrada de la restauración:
  1. `_visit_open_in_editor` (main_window): tras `open_plate` +
     `set_object`, si existe `meta["ufe"]` en la fila se aplica.
  2. Clic en una medición en la ventana de visitas: `point_by_id`
     -> si `file_id`, abrir el UFE en esa placa con hooks de proyecto
     + restauración completa; si no, aviso en barra de estado.
- Aperturas sueltas (sin proyecto) nunca persisten estado: los hooks
  se ponen a `None` y cualquier `apply_plate_state` queda inactivo.

### Reset desde el UFE (pestaña Medir)

- "Restablecer estado de la placa": borra `meta["ufe"]` de la fila de
  la placa abierta y aplica los valores por defecto. Sin confirmación
  (no roza mediciones).
- "Borrar mediciones de esta placa": elimina únicamente los puntos
  cuyo `file_id` sea el de la placa abierta. Confirmación explícita
  (destructivo: toca la curva de luz).
- La fila de borrado por medición en la ventana de visitas sigue
  funcionando igual (por `point id`).

## Fase 1: piezas y orden

1. `core/db.py`: migración v11 (columna + índice).
2. `core/followup.py`: `add_point(..., file_id=None)`; `list_points`
   devuelve `file_id` (ambas ramas del SELECT); `point_by_id(db, id)`.
3. `core/project.py`: `find_file(db, project_id, path)` (fila por
   ruta absoluta) y `update_file_meta(db, file_id, patch)` (merge
   JSON en `meta["ufe"]`).
4. Tests unitarios (`tests/unit/test_ufe_integration.py` o vecino)
   de los puntos 1-3 ANTES de tocar la GUI.
5. GUI:
   - `ufe_state.py`: getters de estiramiento (black/white/gamma/invert).
   - `ufe_advanced_dialog.py`: accesores de lectura/escritura para
     `cmb_sky, chk_sigmaclip, chk_seeing, chk_color, spn_target_bv`
     (`chk_subtract` solo lectura, no se restaura).
   - `ufe_measure_tab.py`: `capture_state/apply_state`; botones de
     reset (estado sin confirmation, puntos con confirmation);
     `_on_save_project`: añade `file_path` al payload para que el hook
     resuelva la fila.
   - `ufe_compare_tab.py`: `capture_state/apply_state` (entries +
     campo + objetivo).
   - `ufe_dialog.py`: `apply_plate_state(st)` + punto de anclaje del
     reset; no tocar `closeEvent`.
6. `gui/widgets/visits_panel.py`: señal `on_measure_click(point)` al
   pulsar un ítem (el `Qt.UserRole` ya lleva `pt["id"]`).
7. `gui/main_window.py`:
   - `_ufe_point_hook`: resolve `file_id` + escribe `meta["ufe"]`.
   - `_ufe_save_hook` (sequence): escribe `sequence` por placa.
   - `_visit_open_in_editor`: restauración tras cargar.
   - Clic en medición: flujo de apertura con restauración + aviso
     si la placa no existe.
8. ADR-047 (bilingüe): `docs/adr/ADR-047-ufe-plate-persistence.md`.
9. i18n: strings nuevas por `self.tr()`; actualizar PO si la suite lo
   pide (tests verán cadenas nuevas).

## Fase 2 (seguida, ADR aparte): empaquetado XISF portable

- **Exportar placa (XISF)**: `placa.xisf` con la imagen (compresión
  pérdida, paquete Python `xisf` de Sergio Díaz-Ruiz, Astropy NO
  soporta XISF así que no choca con el ADR-018), sección XML de
  metadatos con el `meta["ufe"]` tal cual, tabla FITS de la secuencia
  y tabla de las mediciones. El FITS original del usuario queda
  intacto.
- **Importar placa (XISF)** (opcional): extender `fits_io` (o un
  lector de placa que dispatcha por extensión) para que `open_plate`
  reconozca `.xisf`; al abrirlo, registra la fila, restaura estado,
  secuencia y puntúa en la curva del proyecto según convenga.
- XISF soporta varias imágenes (pareja de blink) y tablas nativas:
  cubre "llevarlo a otro observatorio con un USB".
- Dependencia nueva solo en esta fase: `xisf` en `requirements.txt`,
  gated, verificado que no se instala en tests unitarios.

## Riesgos y límites conocidos

- Si el usuario mueve/renombra el FITS fuera del proyecto, la fila de
  `project_files` queda huérfana: igual que hoy la aperturas en la
  visita fallarían; el estado de placa vive con la línea, no con el
  PATH absoluto en el sistema de ficheros. Acceptable (la app abre
  por ruta registrada).
- `project.context["sequence"]` sigue escribiéndose (global). Es el
  respaldo de compatibilidad; la verdad para la restauración es la
  per-placa.
- Dos fuentes de verdad (DB y XISF fase 2) se resuelven: la base es
  la única fuente de verdad de la curva; XISF es solo empaquetado
  exportable/importable.
