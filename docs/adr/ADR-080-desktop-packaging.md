# ADR-080: Empaquetado de escritorio: Find_Orb dentro, y tres paquetes de Linux con el Python del sistema

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-11

## Español

**Contexto**: el observador pidió simplificar la instalación. Hasta ahora Find_Orb
era externo y se instalaba guiado (ADR-062, D31), lo que en Linux obliga a tener
un gestor de paquetes (micromamba/mamba/conda); en Linux no había paquete de la
app, solo ejecución desde el código. Se estudiaron dos cosas: meter Find_Orb
dentro y repartir la app como paquete.

Hechos medidos (2026-10-11):

1. **Find_Orb pesa poco de verdad**: `fo` (766 KB) + `find_orb` (918 KB) + datos
   (7,4 MB). Lo que pesa es la efeméride **DE430t (95 MB)**, que es **dominio
   público** y **opcional** (Find_Orb funciona sin ella, con posiciones
   planetarias más gruesas). El paquete conda la marca como dependencia, pero se
   puede omitir.
2. **La licencia de Find_Orb**: GPLv2 con una cláusula extra de Project Pluto
   («prohibido su uso en o con software comercial sin permiso escrito»). Para una
   app **no comercial GPLv3** como esta, llevarlo como **programa separado** es
   mera agregación (GPLv2 §2): legal. Lo que no se puede es meterlo en un `.deb`
   de **Debian main** (contenido non-free); nuestro `.deb` se publica en GitHub
   Releases, así que no aplica. Redistribuirlo obliga a ofrecer su fuente (un
   enlace basta).
3. **El `fo` de conda no es relocalizable por sí solo**: lleva el prefijo de
   build compilado y en el primer arranque copia `share/findorb/data` a
   `$HOME/.find_orb`; en una ruta que no existe, esa copia **aborta** el programa
   (reproducido). Pero si el directorio de configuración **ya está poblado**,
   arranca sin problema (probado). Ese es el truco que hace viable llevarlo
   dentro.
4. **PySide6 está empaquetado en casi todas las distros modernas** (Arch, Fedora,
   openSUSE, Nix, Alpine, Mageeia…), y el hueco es **Ubuntu 24.04 LTS**. El resto
   de dependencias (astropy, scipy, numpy, matplotlib, photutils, lxml, requests,
   PyYAML, platformdirs, Pillow) también están; los huecos reales son
   **`imageio-ffmpeg`** (Fedora no lo empaqueta; Arch solo en AUR) y
   **`photutils`** (Arch solo en AUR).

**Decisión**:

1. **Find_Orb viaja dentro** de los paquetes (Windows y Linux), con un aviso de
   licencia y el enlace a su fuente en el instalador. `findorb.probe()` busca la
   copia incluida **antes** que el PATH; el campo de Ajustes sigue para apuntar a
   una copia propia.
2. **Un `HOME` privado** para el subproceso `fo` (dentro de la carpeta de datos de
   la app), **pre-poblado** desde los datos incluidos. Es lo que hace funcionar
   la copia relocalizada, y de paso encierra la configuración de Find_Orb dentro
   de NightScribe en vez de ensuciar el `~` del observador.
3. **Tres paquetes Linux con el Python del sistema** (no se embebe Python ni Qt):
   - **`.deb`** para Debian 13+ / Ubuntu 25.10+ (`python3-pyside6.*` y el resto de
     paquetes de la distro);
   - **`.rpm`** para Fedora 42+ / openSUSE Tumbleweed (dependencias automáticas
     `python3dist(...)`);
   - **PKGBUILD** para Arch (con `python-photutils` e `python-imageio-ffmpeg` del
     AUR).
   El build de cada uno está en `tools/build_deb.py`, `installer/rpm/nightscribe.spec`
   e `installer/arch/PKGBUILD`, y el CI en `.github/workflows/linux-packages.yml`.
4. **`imageio-ffmpeg` es opcional** (Recomienda): solo alimenta la exportación
   MP4. Sin él, el GIF y el montaje siguen, y el MP4 dice qué falta en vez de
   reventar.
5. **DE430t descargable desde Ajustes**: un botón baja el fichero (dominio
   público) **directo a la carpeta que lee Find_Orb**, de forma persistente; la
   URL es configurable. No se incluye por defecto (95 MB, opcional).

**Consecuencias**: el chequeo de órbita funciona recién instalado, sin ruta que
configurar; el `.deb`/`.rpm` pesan unos pocos MB; las distros sin PySide6
empaquetado (Ubuntu 24.04 LTS) quedan fuera y se documentan como instalación
manual. `findorb.run()` gana un `HOME` privado (cambia dónde vive `~/.find_orb`:
ya no es el `~` real). El `fo` que se empaqueta es el de conda-forge
(GPL-2.0-or-later), redistribuido con su fuente enlazada.

**Alternativas**: (a) no incluir Find_Orb y dejar la instalación guiada,
descartado: era justo la queja del observador; (b) descargar Find_Orb desde la
app en vez de incluirlo, descartado: sigue habiendo descarga y, en Linux, el lío
de la relocalización; (c) `.deb`/`.rpm` autocontenidos (Python embebido),
descartado: ~200 MB y Debian no lo quiere; (d) `.deb` que crea un venv y hace
`pip install` en la instalación, descartado: necesita red y minutos al instalar,
y no es reproducible; (e) `.deb` con `pip install --no-index` de wheels dentro,
descartado: pesa como el autocontenido y no aporta sobre el tarball.

## English

**Context**: the observer asked to simplify the install. Until now Find_Orb was
external and installed guided (ADR-062, D31), which on Linux forces a package
manager (micromamba/mamba/conda); and Linux had no app package at all, only
running from source. Two things were studied: bundling Find_Orb, and shipping
the app as a package.

Measured facts (2026-10-11):

1. **Find_Orb is small where it counts**: `fo` (766 KB) + `find_orb` (918 KB) +
   data (7.4 MB). The weight is the **DE430t ephemeris (95 MB)**, which is
   **public domain** and **optional** (Find_Orb runs without it, with coarser
   planetary positions). The conda package marks it as a dependency, but it can
   be left out.
2. **Find_Orb's licence**: GPLv2 with an extra Project Pluto clause ("use in or
   with commercial software forbidden without written permission"). For a
   **non-commercial GPLv3** app like this, carrying it as a **separate program**
   is mere aggregation (GPLv2 §2): legal. What is not allowed is putting it in a
   **Debian main** `.deb` (non-free content); our `.deb` is published on GitHub
   Releases, so that does not apply. Redistributing it means offering its source
   (a link is enough).
3. **The conda `fo` is not relocatable on its own**: it has the build prefix
   compiled in and copies `share/findorb/data` to `$HOME/.find_orb` on the first
   run; at a path that does not exist that copy **aborts** the program
   (reproduced). But if the config folder is **already populated**, it starts
   fine (tested). That is the trick that makes bundling viable.
4. **PySide6 is packaged on almost every modern distro** (Arch, Fedora, openSUSE,
   Nix, Alpine, Mageia...), the gap being **Ubuntu 24.04 LTS**. The rest
   (astropy, scipy, numpy, matplotlib, photutils, lxml, requests, PyYAML,
   platformdirs, Pillow) are there too; the real gaps are **`imageio-ffmpeg`**
   (Fedora does not package it; Arch only in the AUR) and **`photutils`** (Arch
   only in the AUR).

**Decision**:

1. **Find_Orb travels inside** the packages (Windows and Linux), with a licence
   notice and its source link in the installer. `findorb.probe()` looks for the
   bundled copy **before** PATH; the Settings field stays for pointing at the
   observer's own copy.
2. **A private `HOME`** for the `fo` subprocess (inside the app's data folder),
   **pre-populated** from the shipped data. It is what makes the relocated copy
   work and, as a bonus, it keeps Find_Orb's config inside NightScribe instead
   of dirtying the observer's `~`.
3. **Three Linux packages with the system Python** (Python and Qt are not
   embedded):
   - **`.deb`** for Debian 13+ / Ubuntu 25.10+ (`python3-pyside6.*` and the rest
     of the distro's packages);
   - **`.rpm`** for Fedora 42+ / openSUSE Tumbleweed (automatic `python3dist(...)`
     dependencies);
   - **PKGBUILD** for Arch (`python-photutils` and `python-imageio-ffmpeg` from
     the AUR).
   The build of each lives in `tools/build_deb.py`,
   `installer/rpm/nightscribe.spec` and `installer/arch/PKGBUILD`, and the CI in
   `.github/workflows/linux-packages.yml`.
4. **`imageio-ffmpeg` is optional** (Recommends): it only feeds the MP4 export.
   Without it the GIF and the montage keep working, and the MP4 says what is
   missing instead of crashing.
5. **DE430t downloadable from Settings**: a button fetches the file (public
   domain) **straight to the folder Find_Orb reads**, persistently; the URL is
   configurable. It is not bundled by default (95 MB, optional).

**Consequences**: the orbit check works out of the box, with no path to set; the
`.deb`/`.rpm` weigh a few MB; distros without a packaged PySide6 (Ubuntu 24.04
LTS) are left out and documented as a manual install. `findorb.run()` gains a
private `HOME` (it changes where `~/.find_orb` lives: no longer the real `~`).
The `fo` that is packaged is conda-forge's (GPL-2.0-or-later), redistributed with
its source linked.

**Alternatives**: (a) not bundling Find_Orb and keeping the guided install,
rejected: it was the observer's complaint; (b) downloading Find_Orb from the app
instead of bundling, rejected: there is still a download and, on Linux, the
relocation mess; (c) self-contained `.deb`/`.rpm` (embedded Python), rejected:
~200 MB and Debian does not want it; (d) a `.deb` that creates a venv and pip
installs at install time, rejected: it needs the network and minutes to install,
and is not reproducible; (e) a `.deb` with `pip install --no-index` of vendored
wheels, rejected: it weighs like the self-contained one and adds nothing over
the tarball.
