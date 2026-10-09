# ADR-074: El catálogo de cámaras y una linealidad que no miente

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-09

## Español

**Contexto**: `core/cameras.py` nació con **nueve** presets y dos defectos que
se notaban al usarlos:

1. **Faltaban los modelos que la gente usa.** La propia AAVSO recomienda hoy el
   IMX571 (ASI2600/QHY268) y el IMX455 (QHY600/ASI6200) como la mejor relación
   para fotometría, y los CCD clásicos de fotometría (ICX694, ICX814) y el
   MN34230 de la ASI1600 tampoco estaban. El observador que no encontraba su
   cámara elegía "None" y tecleaba todo a mano.
2. **La linealidad sugerida era un `50000` fijo.** Da igual que el sensor sea de
   12 bits (su ADC no pasa de 4095) o que se use a ganancia alta (el full well,
   no el ADC, es el techo): el número no distinguía ninguno de los dos casos. Y
   la corriente de oscuridad venía a `None` en seis de los nueve presets, con la
   temperatura (`dark_temp_c`) que **nunca se escribía** en la config, de modo
   que el dato perdía su sentido al elegir el preset.

**Decisión**:

1. **Ampliar a 21 sensores**, agrupados por familia (`FAMILY_ORDER`): CMOS Sony
   de 16 bits (IMX455/461/411/571/533), CMOS Sony de 12/14 bits
   (IMX492/294/183/178/174/290 y el MN34230), sCMOS Gpixel
   (GSENSE400/4040/6060), CCD Sony (ICX694/814) y CCD Kodak/ON
   (KAF-8300/16803/09000 y KAI-11002). Sin DSLR: es otra liga (AAVSO los manda
   a su manual propio) y no mezclan bien con un perfil de cámara fría.
2. **Cada preset gana los datos del sensor** que faltaban: `bit_depth` (el techo
   real del ADC), `sensor_w_mm`/`sensor_h_mm` y la resolución (para el FOV en la
   línea de referencia), y un `read_noise_note` que dice a qué modo de ganancia
   pertenece el ruido de lectura. Cada cifra cita su fuente en `source`.
3. **La linealidad se deriva, no se inventa**: `suggested_linearity_adu(p, gain)`
   toma el **menor** entre el full well a esa ganancia y el techo del ADC
   (`2^bit_depth − 1`), y lo multiplica por `linearity_frac` (0.9 por defecto;
   los KAF la publican como "lineal hasta el 90% de Vsat"). Sin ganancia cae al
   techo del ADC, que es lo máximo que se puede afirmar. El GSENSE400 conserva
   un `linearity_adu` absoluto porque es una medida real de una unidad.
4. **La oscuridad viaja con su temperatura**: `profile_from_preset` escribe
   `cam_dark_temp_c` junto a `cam_dark_current_e_s` (y Ajustes lo persiste al
   guardar), porque un e-/pix/s sin la temperatura a la que se midió no dice
   nada.
5. **El combo se agrupa** por familia (`combo_entries()`), con una cabecera
   deshabilitada por grupo, compartida por Ajustes y Bienvenida.

**Consecuencias**:

- Un sensor de 12 bits ya no sugiere un techo que su ADC no alcanza, ni uno de
  16 bits a ganancia alta sugiere más de lo que aguanta el píxel.
- El catálogo cubre lo que de verdad se compra hoy sin llenar la lista de
  modelos que nadie tiene.
- `cam_regime` se queda como estaba (se escribe, no se lee): el régimen del
  sCMOS solo informa en la etiqueta de referencia. Darle uso al motor de serie
  es otra decisión, y no entra aquí.
- Guardián: `tests/unit/test_cameras.py` (forma, claves y alias únicos, la
  linealidad por techos, el par oscuridad↔temperatura y el agrupado del combo)
  y `tests/unit/test_wizard_site.py` (el conteo del combo con cabeceras).

**Enmienda (2026-10-09, el catálogo es un fichero).** Los 21 presets vivían en
el código (`core/cameras.py`). Ahora los datos viven en
`nightscribe/assets/cameras.toml` (empaquetado, fuente de verdad) y el módulo
solo conserva la lógica (búsqueda, etiqueta, agrupado, conversión a claves de
config y la linealidad sugerida). Añadir, corregir o quitar una cámara es
editar un TOML, sin tocar Python.

1. **Fichero de usuario**: `<config>/cameras.toml` (junto a
   `nightscribe.json`) se funde encima: una `[[camera]]` con un `key` nuevo se
   añade, con un `key` existente corrige campo a campo, y `hide = [...]` quita
   presets empaquetados. Cualquier familia nueva se añade al orden.
2. **Validación al cargar**: campos y tipos obligatorios, `key` y alias
   únicos, familia declarada, el par oscuridad↔temperatura y
   `linearity_adu`/`linearity_frac`. Un fichero de usuario inválido **no
   tumba la app**: se registra, se conserva el último catálogo bueno y Ajustes
   → Cámara lo dice en la línea de referencia (`USER_ERROR`).
3. **Recarga en caliente**: `cameras.reload()` relee ambos ficheros; se llama
   al abrir Ajustes y al montar el paso Equipo de Bienvenida, así que editar el
   fichero surte efecto sin reiniciar.
4. **Guarda**: `tests/unit/test_cameras.py` añade el fichero empaquetado, la
   fusión (añadir/corregir/ocultar) y que un fichero roto se reporta sin
   romper el catálogo.

**Enmienda (2026-10-09, el preset es una plantilla).** Elegir un preset
rellenaba solo los campos vacíos ("no pisar lo que el observador puso a mano"),
así que al cambiar de cámara el full well, el ruido de lectura, la oscuridad y
la linealidad se quedaban los de la cámara anterior: el preset parecía no hacer
nada. La regla venía de proteger el perfil medido al **abrir** Ajustes (donde
`setCurrentIndex` disparaba el relleno).

1. **`profile_from_preset(p, gain_e_per_adu=None)` devuelve la plantilla
   completa**: elegir una cámara carga sus datos por encima de lo que hubiera,
   y un campo que el datasheet no publica se limpia (0/None) para que no quede
   el de la cámara anterior. La ganancia nunca se escribe: solo se lee para
   derivar la linealidad.
2. **El abrir Ajustes se protege de verdad**: se bloquea la señal del combo
   mientras se restaura el índice guardado, así el perfil medido que se ve no
   se toca. Re-seleccionar la misma cámara no dispara nada.
3. **El tope de exposición**: la plantilla pone la sugerencia del sCMOS y 0
   (sin tope) para una cámara clásica.
4. **La oscuridad sube a 6 decimales** en Ajustes, para no perder un dígito
   (0.00012 no es 0.0001).
5. **Guarda**: `test_cameras.py` (la plantilla completa) y
   `test_settings_tabs.py` (seleccionar otra cámara cambia los campos).
6. **Las cabeceras de familia leen como cabeceras**: negrita, color de acento,
   mayúsculas y una banda tenue (`theme.style_combo_header`), porque el gris de
   "deshabilitado" solo no se distinguía de una cámara.

## English

**Context**: `core/cameras.py` started with **nine** presets and two defects
that showed the moment they were used:

1. **The models people actually use were missing.** The AAVSO itself today
   recommends the IMX571 (ASI2600/QHY268) and the IMX455 (QHY600/ASI6200) as
   the best value for photometry, and the classic photometry CCDs (ICX694,
   ICX814) and the ASI1600's MN34230 were absent too. An observer who could not
   find their camera picked "None" and typed everything by hand.
2. **The suggested linearity was a flat `50000`.** It did not matter whether
   the sensor is 12-bit (its ADC never passes 4095) or is used at high gain
   (the full well, not the ADC, is the ceiling): the number told neither case
   apart. And the dark current was `None` in six of the nine presets, with the
   temperature (`dark_temp_c`) **never written** to config, so the figure lost
   its meaning the moment the preset was chosen.

**Decision**:

1. **Expand to 21 sensors**, grouped by family (`FAMILY_ORDER`): 16-bit Sony
   CMOS (IMX455/461/411/571/533), 12/14-bit Sony CMOS (IMX492/294/183/178/174/
   290 and the MN34230), Gpixel sCMOS (GSENSE400/4040/6060), Sony CCD
   (ICX694/814) and Kodak/ON CCD (KAF-8300/16803/09000 and KAI-11002). No
   DSLR: that is another league (AAVSO sends them to their own manual) and it
   does not mix well with a cooled-camera profile.
2. **Each preset gains the sensor facts** that were missing: `bit_depth` (the
   real ADC ceiling), `sensor_w_mm`/`sensor_h_mm` and the resolution (for the
   FOV in the reference line), and a `read_noise_note` naming the gain mode the
   read noise belongs to. Every figure cites its source in `source`.
3. **Linearity is derived, not invented**: `suggested_linearity_adu(p, gain)`
   takes the **lesser** of the full well at that gain and the ADC ceiling
   (`2^bit_depth − 1`), times `linearity_frac` (0.9 by default; the KAF parts
   publish it as "linear to 90% of Vsat"). Without a gain it falls back to the
   ADC ceiling, the most that can be claimed. The GSENSE400 keeps an absolute
   `linearity_adu` because it is a real measurement of one unit.
4. **The dark current travels with its temperature**: `profile_from_preset`
   writes `cam_dark_temp_c` next to `cam_dark_current_e_s` (and Settings
   persists it on save), because an e-/pix/s without the temperature it was
   measured at says nothing.
5. **The combo is grouped** by family (`combo_entries()`), with one disabled
   header per group, shared by Settings and Welcome.

**Consequences**:

- A 12-bit sensor no longer suggests a ceiling its ADC cannot reach, nor does a
  16-bit one at high gain suggest more than the pixel holds.
- The catalogue covers what people actually buy today without filling the list
  with models nobody owns.
- `cam_regime` stays as it was (written, not read): the sCMOS regime only
  informs in the reference line. Giving it a consumer in the series engine is
  another decision, and it is not part of this one.
- Guards: `tests/unit/test_cameras.py` (shape, unique keys and aliases, the
  linearity by ceilings, the dark↔temperature pair and the combo grouping) and
  `tests/unit/test_wizard_site.py` (the combo count with headers).

**Amendment (2026-10-09, the catalogue is a file).** The 21 presets lived in
the code (`core/cameras.py`). The data now lives in
`nightscribe/assets/cameras.toml` (bundled, the source of truth) and the module
keeps only the logic (lookup, label, grouping, the mapping to config keys and
the suggested linearity). Adding, fixing or removing a camera is editing a
TOML, no Python involved.

1. **User file**: `<config>/cameras.toml` (next to `nightscribe.json`) is
   merged on top: a `[[camera]]` with a new `key` is added, with an existing
   `key` corrects field by field, and `hide = [...]` drops bundled presets.
   Any new family is appended to the order.
2. **Validation at load**: required fields and types, unique keys and aliases,
   declared family, the dark↔temperature pair and
   `linearity_adu`/`linearity_frac`. A broken user file does **not** crash the
   app: it is logged, the last good catalogue stays and Settings → Camera says
   so in the reference line (`USER_ERROR`).
3. **Hot reload**: `cameras.reload()` re-reads both files; it is called when
   Settings opens and when the Welcome equipment step is built, so editing the
   file takes effect without a restart.
4. **Guard**: `tests/unit/test_cameras.py` adds the bundled file, the merge
   (add/correct/hide) and that a broken file is reported without breaking the
   catalogue.

**Amendment (2026-10-09, the preset is a template).** Choosing a preset filled
only the empty fields ("do not stomp a value the observer set by hand"), so
switching cameras left the full well, read noise, dark current and linearity
from the previous camera: the preset looked like it did nothing. The rule came
from protecting the measured profile when Settings **opens** (where
`setCurrentIndex` fired the fill).

1. **`profile_from_preset(p, gain_e_per_adu=None)` returns the full template**:
   choosing a camera loads its figures over whatever was there, and a field the
   datasheet does not publish is cleared (0/None) so the previous camera's does
   not linger. The gain is never written: it is only read to derive the
   linearity.
2. **Opening Settings is guarded for real**: the combo signal is blocked while
   the saved index is restored, so the measured profile on screen is not
   touched. Re-selecting the same camera fires nothing.
3. **The max exposure**: the template sets the sCMOS suggestion and 0 (no cap)
   for a classic camera.
4. **The dark current goes to 6 decimals** in Settings, so a digit is not lost
   (0.00012 is not 0.0001).
5. **Guard**: `test_cameras.py` (the full template) and `test_settings_tabs.py`
   (selecting another camera changes the fields).
6. **The family headers read as headers**: bold, accent colour, uppercase and a
   faint band (`theme.style_combo_header`), because the "disabled" grey alone
   did not stand out from a camera.
