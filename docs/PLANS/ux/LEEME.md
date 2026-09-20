# LEEME — patrones y errores frecuentes (Track UX)

> Léelo **antes** de tu tarjeta. Todo subplan del track asume lo aquí
> escrito. Si algo de tu tarjeta contradice este documento, manda la
> tarjeta.

## 0. Esto es un track hermano del Track V

**Todo lo de `docs/PLANS/variables/LEEME.md` sigue vigente** (cabecera GPL,
estilo, comandos, tests, errores frecuentes 1-9). Léelo primero; aquí solo
hay lo específico de esta tanda de usabilidad.

## 1. Anclas verificadas a HEAD `4df771b`

Las tarjetas citan `fichero:línea` contra ese HEAD (la rama
`feature/variables-campaigns` cerrada). La rama de trabajo es
`feature/campaigns-ux`, nacida de ahí. Si un ancla no coincide: **para y
reporta** pegando lo que ves; no busques el sitio «parecido».

## 2. Patrones de esta tanda (úsanos, no inventes)

- **Arnés GUI offscreen con MainWindow**: `tests/unit/test_projects_hub.py`
  (fixture `_point_db_at_tmpdir` + `window`, líneas ~107-160): redirige el
  singleton `db` a un tmp, para los timers, `config.is_configured = lambda:
  False`. Cópialo en cada fichero de tests nuevo que toque MainWindow.
- **Arnés GUI ligero** (diálogos sueltos): fixture `qapp` de
  `tests/unit/test_theme.py` + `Database(str(tmp_path / "t.db"))`.
- **`QMessageBox` en tests**: nunca lo lances de verdad (bloquea). Usa
  `monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: ...)`
  capturando la llamada; el código bajo test lo invoca como
  `QMessageBox.warning(self, título, texto)`.
- **Workers en tests**: instancia el worker, monkeypatchea la fuente
  (`vsx.lookup`, `surveys.fetch_points`…), llama a `.run()` **en el mismo
  hilo** y captura la señal con `QSignalSpy` (entrega síncrona al estar en
  el hilo de la GUI).
- **Chips clicables**: clase `_LinkChip` (se crea en UA.6, junto a
  `_ClickableFrame`, `main_window.py:~192`): QLabel con cursor de mano y
  señal `clicked` que **consume** el evento para no propagarlo a la fila
  clicable padre. Reutilízala; no la dupliques.
- **Índices de pestañas principales**: desde UA.2 existen las constantes
  `TAB_TONIGHT, TAB_PROJECTS, TAB_CAMPAIGNS, TAB_SOLAR, TAB_HISTORY`
  (arriba de `main_window.py`), y UD.2 añade `TAB_OBSERVATORY` entre Solar
  y History (6 pestañas en total; Ctrl+1..6). Prohibido usar literales de
  índice de pestaña principal nuevos; migra los viejos solo donde tu
  tarjeta diga.
- **Gestos (UX-c)**: toda lista/tabla nueva o tocada sale con: selección
  por clic, `itemActivated`/`cellDoubleClicked` para abrir,
  `setContextMenuPolicy(Qt.CustomContextMenu)` si hay acciones, y
  `viewport().setCursor(Qt.PointingHandCursor)`.

## 3. Errores frecuentes específicos

1. **Un `QLabel` con `<a href>` emite `linkActivated` solo si
   `openExternalLinks` es False** (es el defecto; no lo actives). Conecta
   la señal una vez en `_connect`, no en cada render de cabecera.
2. **`QListWidget.itemActivated` cubre doble-clic y Enter** según
   plataforma; úsala en vez de conectar las dos por separado.
3. **El filtro de campaña se repuebla en cada refresh**: cualquier
   restauración de selección va dentro de `_rebuild_campaign_filter` con
   `blockSignals(True/False)`, nunca conectando otro camino.
4. **El `ItemDataRole` del id**: tanto `lst_projects` como
   `lst_campaigns`/`tbl_members` guardan el id en `Qt.UserRole`. Las
   cabeceras de año del hub tienen `Qt.NoItemFlags` y `UserRole` vacío —
   todo handler debe tolerar `item.data(Qt.UserRole) is None`.
5. **No lances diálogos modales en tests sin monkeypatch**: `exec()`
   bloquea. Los tests llaman a los métodos internos (`_save`, `_resolve`)
   directamente, como ya hace `test_campaigns_dialog.py`.
6. **El eje de magnitudes es invertido** (vale recordarlo): «vencido por N
   noches» es cadencia, no brillo; un «dip» es `mag` que sube.
7. **`_fill_table` usa `TABLE_COLS.get(want, TABLE_COLS_DEFAULT)`**: al
   añadir la columna «Campaign» a `TABLE_COLS_DEFAULT` no hace falta tocar
   los layouts por kind; el formateador `camp` ya es genérico.
