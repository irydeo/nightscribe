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
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nightscribe gui
```

### Windows (PowerShell)

```powershell
git clone <url-del-repo> nightscribe; cd nightscribe
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m nightscribe gui
```

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

El asistente pide tu **código de observatorio MPC** (p. ej. `Z41`) y resuelve tus
coordenadas automáticamente desde la lista del MPC — o introduce latitud/longitud/
altitud a mano. Define el nombre del observatorio (firma los posts), la apertura del
telescopio y el idioma de la interfaz. Opcional: clave API de NEOfixer (reporte
comunitario) y credenciales bot de TNS (imágenes de descubrimiento en la app).

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
- **Una fuente falla** (p. ej. NEOfixer caído) → la app sigue funcionando con el
  resto; revisa *Configuración → Estado de las fuentes*.
- **Faltan traducciones tras editar** → ejecuta
  `pyside6-lupdate`/`pyside6-lrelease` como se describe en CONTRIBUTING.
