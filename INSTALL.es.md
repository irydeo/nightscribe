# Instalación de NightScribe

*[English version](INSTALL.md)*

## Requisitos

- **Python 3.11+** (recomendado 3.12)
  - Linux: `sudo apt install python3 python3-venv` (Debian/Ubuntu)
  - Windows: instalador desde [python.org](https://www.python.org/downloads/)
    (marca *"Add python.exe to PATH"*)
- Conexión a Internet (las fuentes de datos son online; todo lo demás es offline)
- ~500 MB libres (dependencias de Python)

## Opción A — desde el código fuente (recomendada para colaborar)

### Linux

```bash
git clone <url-del-repo> nightscribe && cd nightscribe
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nightscribe gui
```

### Windows, paso a paso

**1 · Instala Python**

1. Abre [python.org/downloads](https://www.python.org/downloads/) y pulsa el
   botón amarillo grande **Download Python 3.12.x**.
2. Ejecuta el fichero descargado. En la **primera pantalla del instalador**,
   marca ***"Add python.exe to PATH"*** (la casilla de abajo) — el paso que
   todo el mundo olvida — y pulsa **Install Now**.
3. Si la última pantalla ofrece ***"Disable path length limit"***, púlsalo
   (requiere permisos de administrador) y después *Close*.

Comprueba que funcionó: abre **PowerShell** (menú Inicio → escribe
`PowerShell` → Enter) y ejecuta:

```powershell
py --version
```

Debe responder algo como `Python 3.12.5`. Si en su lugar se abre la Microsoft
Store o ves *"Python was not found"*, la casilla de PATH no estaba marcada —
vuelve a ejecutar el instalador (*Modify → Repair*) o simplemente usa siempre
`py` en lugar de `python`; el lanzador `py` se instala siempre.

**2 · Consigue el código de NightScribe**

Lo más fácil, sin herramientas extra: en la página de GitHub pulsa **Code →
Download ZIP**, haz clic derecho sobre el fichero descargado → ***Extraer
todo***, y recuerda dónde queda la carpeta `nightscribe`.

(Si ya tienes [Git para Windows](https://git-scm.com/download/win):
`git clone <url-del-repo> nightscribe`.)

**3 · Abre PowerShell dentro de esa carpeta**

En el Explorador de archivos abre la carpeta `nightscribe`, haz **Mayús +
clic derecho** sobre una zona vacía → ***Abrir la ventana de PowerShell
aquí*** (Windows 10) o ***Abrir en Terminal*** (Windows 11).

**4 · Crea el entorno e instala** (copia y pega línea a línea):

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

La instalación descarga ~500 MB; con una conexión lenta puede tardar.

**5 · Arranca NightScribe**

```powershell
.venv\Scripts\python -m nightscribe gui
```

El primer arranque abre el asistente de configuración (ver *Primer arranque*
más abajo). A partir de ahí solo necesitas los pasos 3 y 5.

## Opción B — paquete pip

```bash
python3 -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install nightscribe
nightscribe gui
```

## Opción C — instalador autónomo (sin Python)

Los paquetes precompilados están en la página de Releases. Para generar el tuyo:

```bash
.venv/bin/pip install -r requirements-dev.txt   # incluye pyinstaller
.venv/bin/pyinstaller installer/nightscribe.spec
# -> dist/nightscribe/ (binario Linux) ; en Windows lo mismo -> nightscribe.exe
```

El spec de PyInstaller empaqueta los `.ui`, las traducciones `.qm` y el estilo de
matplotlib; detalles en los comentarios de `installer/nightscribe.spec`.

## Primer arranque

El asistente solo pide tu **observatorio**: introduce tu código MPC
(p. ej. `Z41`) y tus coordenadas se resuelven automáticamente desde la lista
del MPC — o escribe nombre, latitud, longitud y altitud a mano.

Todo lo demás vive en **Configuración** (puedes cambiarlo en cualquier momento):

- **Sitio y equipo** — idioma de la interfaz, datos del observatorio, apertura
  del telescopio, magnitud límite, escala de placa de la cámara (píxel, focal,
  tipo, binning) y tu código de observador AAVSO (se usa en el handoff a
  EXOTIC).
- **Observación** — fichero de horizonte local (`.hrz` de TheSkyX o pares
  «az alt») con margen de seguridad, tipos de objeto mostrados en Esta noche,
  restricción lunar, valores de sesión, lista de vigilias de variables y la
  carpeta de proyectos.
- **Integraciones** — conexión CCDciel (host/puerto, autoconexión; el control
  solo funciona con CCDciel abierto) y las claves API opcionales: NEOfixer
  (reporte comunitario), Astrometry.net (resolución ciega de FITS sin WCS en
  el blink), bot de TNS (imágenes de descubrimiento en la app) y token AAVSO
  (fotometría de la comunidad para las vigilias de estrellas brillantes).

Ninguna clave es obligatoria: cada integración opcional degrada con elegancia.

## Entorno de desarrollo (tests)

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/unit          # rápido, sin red
.venv/bin/pytest tests/functional    # con red, extremo a extremo
```

## Problemas comunes

- **`No module named 'PySide6'`** → estás fuera del venv; actívalo o usa
  `.venv/bin/python`.
- **Linux, la GUI no arranca** → instala las dependencias Qt del sistema:
  `sudo apt install libegl1 libxkbcommon0 libdbus-1-3`.
- **Windows: `python` abre la Microsoft Store** → usa `py`, o desactiva el
  alias en *Configuración → Aplicaciones → Configuración avanzada de
  aplicaciones → Alias de ejecución de aplicación*.
- **Windows: `'git' is not recognized`** → Git no está instalado; usa la vía
  del ZIP (paso 2 de arriba).
- **Windows: SmartScreen avisa sobre el exe autónomo** → *Más información →
  Ejecutar de todas formas* (el instalador se construye desde este mismo
  código).
- **Una fuente falla** (p. ej. NEOfixer caído) → la app sigue funcionando con el
  resto; revisa el menú *Fuentes de datos* para ver el estado de cada una.
- **Acciones CCDciel deshabilitadas** → el control solo está disponible con
  CCDciel en ejecución; revisa host/puerto en *Configuración → Integraciones*.
- **Faltan traducciones tras editar** → ejecuta
  `pyside6-lupdate`/`pyside6-lrelease` como se describe en CONTRIBUTING.
