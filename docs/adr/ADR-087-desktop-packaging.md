# ADR-087: Empaquetado de escritorio: Find_Orb dentro, y tres paquetes de Linux con el Python del sistema

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
   e `installer/arch/PKGBUILD`, y el CI en `.github/workflows/preview.yml` (un
   solo workflow que, al mergear a `main`, construye Windows y Linux y publica
   los cuatro artefactos juntos).
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
   `.github/workflows/preview.yml` (one workflow that, on a merge to `main`,
   builds Windows and Linux and publishes all four artifacts together).
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

**Revisión (2026-10-14): el paquete enseña lo que es.** Instalado el `.deb` en
Ubuntu, el observador vio tres cosas mal y una cuarta encadenada: el paquete
aparecía **sin licencia y sin editor**, la **versión era `0.0.0`**, y la app se
comportaba como si cada arranque fuese una actualización (arrancaba en el
informe de Datos con los tres primeros pasos marcados como hechos, y los
objetivos no cargaban). Causas y arreglos:

1. **La versión se perdía al copiar el paquete a mano.** `build_deb.py` (y el
   spec RPM) copiaban `nightscribe/` a `dist-packages` sin `*.dist-info`, así
   que `importlib.metadata.version("nightscribe")` fallaba y caía al `0.0.0` de
   respaldo. El paquete escribe ahora `nightscribe-<version>.dist-info/METADATA`
   (y `usr/share/nightscribe/version` como último recurso), y `version.py` avisa
   por el log cuando la versión es desconocida. El `0.0.0` hacía que la
   detección de actualización comparase `(0,0,0)` consigo misma.
2. **Sin AppStream no hay licencia, editor ni icono en el centro de software.**
   Un `.desktop` solo no basta. Se añade
   `installer/io.github.irydeo.nightscribe.metainfo.xml` (id reverse-DNS, que
   debe coincidir con el nombre del `.desktop`, renombrado a
   `io.github.irydeo.nightscribe.desktop`), con `project_license`,
   `developer_name` y `<launchable>`. El CI lo valida con `appstreamcli
   validate`.
3. **`usr/share/doc/nightscribe/copyright`** (política Debian), que además
   nombra la licencia separada del Find_Orb empaquetado.

**Consecuencias**: el `.deb`/`.rpm` enseñan versión, licencia, editor e icono
en GNOME Software / App Center, y la detección de actualización vuelve a
funcionar porque la versión es la real. Se revisan también ADR-033 (el
versionado) y ADR-055 (el primer arranque ya no se confunde con una
actualización). El `PKGBUILD` de Arch ya usaba un wheel y no estaba afectado.

**Revisión (2026-10-15): la versión del `METADATA` tiene que ser PEP 440.** El
`.rpm` dejó de construirse: el workflow convertía el `+` del segmento local de
la versión en `-` (para los nombres de fichero) y el job de RPM lo pasaba a
`.`, de modo que el `METADATA` del dist-info llevaba `0.1.0a2.dev53.g242f1b98e`.
El generador de dependencias de RPM (`pythondistdeps.py`) lee ese campo con
`packaging`, que lo rechaza (`Invalid version`) y aborta la construcción entera
con `PYTHONDISTDEPS_GENERATORS_FAILED`. Arreglo: la versión viaja sin tocar
(con su `+`) hasta el spec, porque RPM acepta el `+` (su comparador lo trata
como separador) y PEP 440 lo exige; sólo la etiqueta que va en los nombres de
fichero pierde el `+`. Medido: el mismo árbol con `0.1.0a2.dev53+g242f1b98e`
construye el `.rpm` y el generador emite `python3dist(nightscribe) = 0.1~a2`.

**Revision (2026-10-14): the package shows what it is.** With the `.deb`
installed on Ubuntu the observer saw three wrong things and a fourth that
followed: the package showed **no licence and no developer**, the **version was
`0.0.0`**, and the app behaved as if every launch were an update (it opened on
the Data report with the first three steps marked as done, and the targets did
not load). Causes and fixes:

1. **The version was lost when the package was copied by hand.** `build_deb.py`
   (and the RPM spec) copied `nightscribe/` into `dist-packages` with no
   `*.dist-info`, so `importlib.metadata.version("nightscribe")` failed and fell
   back to `0.0.0`. The package now writes
   `nightscribe-<version>.dist-info/METADATA` (and
   `usr/share/nightscribe/version` as a last resort), and `version.py` logs a
   warning when the version is unknown. The `0.0.0` made the update detection
   compare `(0,0,0)` with itself.
2. **Without AppStream there is no licence, developer or icon in the software
   centre.** A `.desktop` entry alone is not enough.
   `installer/io.github.irydeo.nightscribe.metainfo.xml` is added (reverse-DNS
   id, which must match the `.desktop` name, renamed to
   `io.github.irydeo.nightscribe.desktop`), with `project_license`,
   `developer_name` and `<launchable>`. The CI validates it with
   `appstreamcli validate`.
3. **`usr/share/doc/nightscribe/copyright`** (Debian policy), which also names
   the separate licence of the bundled Find_Orb.

**Consequences**: the `.deb`/`.rpm` show version, licence, developer and icon
in GNOME Software / App Center, and the update detection works again because
the version is the real one. ADR-033 (versioning) and ADR-055 (the first run is
no longer confused with an update) are revised too. Arch's `PKGBUILD` already
used a wheel and was not affected.

**Revision (2026-10-17): the window must be the launcher's own.** The dock
showed the app as **"python3"** with a generic icon (reported). Cause: on
Wayland the compositor identifies a window by its app_id, and Qt takes that from
`QGuiApplication::setDesktopFileName()`, which the app never called; with it
empty nothing matches the window against the launcher, and the shell falls back
to the process name, which in the Linux packages is literally `python3` (the
launcher is `exec python3 -m nightscribe`). Fix: `DESKTOP_ID` in `gui/app.py`
(fed to `setDesktopFileName`) is now the `.desktop` file's basename, and the
entry carries `StartupWMClass=NightScribe` for the X11/XWayland half of the same
bargain. `tests/unit/test_packaging.py` holds the app id, the file name and the
AppStream `<id>`/`<launchable>` together, so the three cannot drift.

**Revisión (2026-10-17): la ventana tiene que ser la del lanzador.** La barra de
tareas mostraba la app como **«python3»** con un icono genérico (reportado).
Causa: en Wayland el compositor identifica una ventana por su app_id, y Qt lo
toma de `QGuiApplication::setDesktopFileName()`, que la app nunca llamaba; al
estar vacío no hay con qué casar la ventana con el lanzador, y el shell cae al
nombre del proceso, que en los paquetes Linux es literalmente `python3` (el
lanzador es `exec python3 -m nightscribe`). Arreglo: `DESKTOP_ID` en
`gui/app.py` (lo que recibe `setDesktopFileName`) es ahora el nombre base del
fichero `.desktop`, y la entrada lleva `StartupWMClass=NightScribe` para la
mitad X11/XWayland del mismo trato. `tests/unit/test_packaging.py` mantiene
juntos el id de la app, el nombre del fichero y el `<id>`/`<launchable>` de
AppStream, para que los tres no se separen.

**Revision (2026-10-15): the `METADATA` version must be PEP 440.** The `.rpm`
stopped building: the workflow turned the `+` of the version's local segment
into `-` (for file names) and the RPM job then turned it into `.`, so the
dist-info `METADATA` carried `0.1.0a2.dev53.g242f1b98e`. RPM's dependency
generator (`pythondistdeps.py`) reads that field with `packaging`, which rejects
it (`Invalid version`) and aborts the whole build with
`PYTHONDISTDEPS_GENERATORS_FAILED`. Fix: the version travels untouched (with its
`+`) all the way to the spec, because RPM accepts the `+` (its comparator treats
it as a separator) and PEP 440 requires it; only the label used in file names
drops the `+`. Measured: the same tree with `0.1.0a2.dev53+g242f1b98e` builds the
`.rpm` and the generator emits `python3dist(nightscribe) = 0.1~a2`.

**Revisión (2026-10-17, un paquete sin Find_Orb no puede salir en silencio)**:
`build_deb._stage` copiaba el payload con `if findorb_dir and Path(findorb_dir).is_dir()`,
así que un build al que se le pasaba `--findorb` con una carpeta vacía (o a medias)
construía el `.deb` **sin Find_Orb** y sin decir nada; el observador acababa leyendo en
Ajustes que Find_Orb no está y viendo la guía de instalación de lo que el paquete debía
traer (reportado). Ahora el build **falla** si el payload no trae `bin/fo*` y
`share/findorb/data`, y `tools/fetch_findorb.sh` verifica lo mismo al terminar (cubre
también el `.rpm` y el PKGBUILD, que consumen ese payload); el `.spec` de PyInstaller avisa
en alto cuando no hay payload, para que un build de desarrollo sepa por qué su bundle no
lleva el chequeo de órbita.

**Review (2026-10-17, a package without Find_Orb cannot leave in silence)**:
`build_deb._stage` copied the payload behind `if findorb_dir and
Path(findorb_dir).is_dir()`, so a build handed `--findorb` with an empty (or half)
folder built the `.deb` **without Find_Orb** and said nothing; the observer then read in
Settings that Find_Orb was missing and got the install guide for what the package was
supposed to bring (reported). The build now **fails** when the payload has no `bin/fo*`
and no `share/findorb/data`, and `tools/fetch_findorb.sh` verifies the same at the end
(which also covers the `.rpm` and the PKGBUILD, both fed by that payload); the PyInstaller
spec warns out loud when there is no payload, so a developer build knows why its bundle
carries no orbit check.

**Revisión (2026-10-17, el payload viajaba sin permisos)**: `tools/fetch_findorb.sh` arma el
árbol de Find_Orb con `_tmp=$(mktemp -d)`, y **`mktemp -d` crea el directorio en 0700**;
el `mv` conserva ese modo, `copytree` (`.deb`) y `cp -a` (`.rpm`, PKGBUILD) lo copian tal
cual, y el paquete se instalaba como `drwx------ root root /usr/lib/nightscribe/findorb`.
La app corre como el observador, así que **no podía ni entrar en la carpeta**: decía «Find_Orb
is not configured» con los 63 ficheros en disco (reportado, y reproducible con `ls -l`: el
`.deb` publicado lo grababa así). El payload se crea con `umask 022` y un `chmod -R a+rX`
final, y **cada empaquetador normaliza los modos** al copiarlo (directorios 755, ficheros
644, el `fo` de `bin/` ejecutable) y **falla** si el árbol quedaría ilegible: un paquete que
no se puede leer no es un paquete. Un test del stage comprueba los modos uno a uno. Y la app
deja de mentir en el otro sentido: si la copia empaquetada está pero no se puede leer, lo
dice (y `find_fo` ya no lanza `PermissionError`).

**Review (2026-10-17, the payload shipped without permissions)**: `tools/fetch_findorb.sh`
builds Find_Orb's tree with `_tmp=$(mktemp -d)`, and **`mktemp -d` creates the directory as
0700**; the `mv` keeps that mode, `copytree` (the `.deb`) and `cp -a` (the `.rpm`, the
PKGBUILD) copy it as it is, and the package installed it as
`drwx------ root root /usr/lib/nightscribe/findorb`. The app runs as the observer, so it
**could not even enter the folder**: it said "Find_Orb is not configured" with the 63 files
on disk (reported, and reproducible with `ls -l`: the published `.deb` recorded it that
way). The payload is created with `umask 022` and a final `chmod -R a+rX`, and **every
packager normalises the modes** when copying it (directories 755, files 644, the `fo` of
`bin/` executable) and **fails** when the tree would end up unreadable: a package that
cannot be read is not a package. A test walks the staged tree's modes one by one. And the
app stops lying in the other direction: when the shipped copy is there but cannot be read,
it says so (and `find_fo` no longer raises `PermissionError`).

**Revisión (2026-10-18, la firma de Windows: lo único que desbloquea SAC)**: en Windows 11,
SmartScreen y el **Control inteligente de aplicaciones (Smart App Control, SAC)** son dos
barreras distintas y solo una tiene salida. SmartScreen avisa y ofrece *Más información →
Ejecutar de todas formas*; SAC **bloquea** el código sin firmar y no ofrece nada parecido.
Solo deja pasar código firmado por una autoridad del programa raíz de confianza de Microsoft
o reconocido por su servicio de inteligencia, y **no hay excepción por aplicación ni forma de
saltarlo**: evalúa en tiempo de ejecución, así que la marca de Internet, descomprimir el zip,
una carpeta de red o un certificado propio no cambian nada (Microsoft lo dice así en su guía
de firma de código y en su FAQ de SAC). Los binarios del proyecto no están firmados, así que
en un equipo con SAC activado ni el instalador ni el zip portable se ejecutan.

**Decisión**: no se compra certificado (es software libre), pero la firma queda **cableada y
inerte**: `installer/nightscribe.iss` lleva `SignTool` y `SignedUninstaller=yes` bajo
`#ifdef SignToolName`, y el workflow de preview pasa `/DSignToolName` y `/Snssign` **solo** si
existe el secreto `WINDOWS_SIGN_CMD` (una orden con el `$f` de Inno Setup, que sirve a la vez
para firmar todo el árbol de PyInstaller, el instalador y el desinstalador que Inno compila
dentro). Sin el secreto, el paso lo dice en el log y el build sigue sin firmar, exactamente
como antes. El camino **gratuito** para un proyecto GPLv3 es la **SignPath Foundation**, que
la propia Microsoft lista en su guía de firma de código para proyectos de código abierto:
certificado OV y firma en la nube (sin token físico) con una acción de GitHub, a cambio de
firmar solo tu código, MFA, builds reproducibles desde el fuente y **aprobación manual en cada
release** (y dos peticiones por release: el árbol antes de empaquetarlo y el instalador
después, porque lo que va dentro hay que firmarlo antes de que Inno lo meta en el setup).
Mientras no haya firma, lo que sí se hace es **decir la verdad**: la guía de usuario, los
README, INSTALL y la nota del release explican las dos barreras por separado (antes daban un
«Run anyway» que con SAC no existe) y un test lo fija.

**Consecuencias**: el bloqueo de SAC sigue ahí hasta que haya certificado, pero ya no se
promete una salida que no existe y el día que haya firma es un secreto y nada más. La firma
**no** quita el aviso de SmartScreen: la reputación se construye con instalaciones y, desde
2024, firmar no la da al instante (los propios ingenieros de Microsoft lo dicen), así que se
esperan avisos unos días o semanas; para SAC, en cambio, una firma válida de una CA de
confianza **sí** basta, que es la razón de todo esto.

**Review (2026-10-18, Windows signing: the only thing that unblocks SAC)**: on Windows 11,
SmartScreen and **Smart App Control (SAC)** are two different gates and only one has a way
through. SmartScreen warns and offers *More info → Run anyway*; SAC **blocks** unsigned code
and offers nothing of the sort. It only lets through code signed by an authority in
Microsoft's trusted root program, or code its intelligence service recognises, and there is
**no per-application exception and no way around it**: it evaluates at run time, so the Mark
of the Internet, unzipping the zip, a network folder or a self-signed certificate change
nothing (Microsoft says so in its code signing guide and in the SAC FAQ). This project's
binaries are unsigned, so on a machine with SAC on, neither the installer nor the portable
build runs.

**Decision**: no certificate is bought (this is free software), but the signing is **wired and
inert**: `installer/nightscribe.iss` carries `SignTool` and `SignedUninstaller=yes` under
`#ifdef SignToolName`, and the preview workflow passes `/DSignToolName` and `/Snssign` **only**
when the `WINDOWS_SIGN_CMD` secret exists (a command with Inno Setup's `$f`, which serves both
to sign the whole PyInstaller tree and the installer and the uninstaller Inno compiles inside
it). Without the secret, the step says so in the log and the build carries on unsigned, exactly
as before. The **free** path for a GPLv3 project is the **SignPath Foundation**, which Microsoft
itself lists in its code signing guide for open-source projects: an OV certificate and cloud
signing (no hardware token) through a GitHub action, in exchange for signing only your own
code, MFA, builds reproducible from source and **manual approval on every release** (and two
requests per release: the tree before it is packaged and the installer after, because what goes
inside has to be signed before Inno puts it in the setup). While there is no signature, what
does get done is **telling the truth**: the user guide, the READMEs, INSTALL and the release
note explain the two gates separately (they used to give a "Run anyway" that does not exist
with SAC) and a test holds it.

**Consequences**: SAC keeps blocking until there is a certificate, but a way out that does not
exist is no longer promised, and the day there is a signature it is a secret and nothing else.
Signing does **not** remove the SmartScreen warning: reputation builds with installs and, since
2024, signing does not grant it instantly (Microsoft's own engineers say so), so warnings are
expected for days or weeks; for SAC, on the other hand, a valid signature from a trusted CA
**is** enough, which is the reason for all of this.

**Revisión (2026-10-18, el tag publica la release estable)**: hasta aquí el único
workflow de empaquetado era `preview.yml`, que en cada push a `main` construye los
cuatro artefactos y los publica como una **pre-release rodante** con el sufijo
`-preview.<sha>`. Para probar es lo correcto, pero una primera versión pública no
puede salir como pre-release ni con el sufijo en el nombre: quien llega a la página
de Releases tiene que ver la estable y descargarla sin dudar. Se añade
`.github/workflows/release.yml`, disparado por un **tag `v*`**: corre la misma
puerta de tests unitarios, construye los mismos cuatro artefactos **sin sufijo**
(el instalador sale `NightScribeSetup-0.1.0.exe`) y publica una release estable
marcada como la última, con las notas tomadas de la sección de esa versión en
`CHANGELOG.md`. La versión sigue saliendo del tag (setuptools-scm), así que el
`METADATA`, el `.deb`, el `.rpm` y `--version` dicen `0.1.0`; la fecha del
`metainfo.xml` se alinea con la del tag. La preview rodante se queda como está,
para el día a día.

**Review (2026-10-18, the tag publishes the stable release)**: until now the only
packaging workflow was `preview.yml`, which on every push to `main` builds the four
artifacts and publishes them as a **rolling pre-release** with the `-preview.<sha>`
suffix. That is right for testing, but a first public version cannot ship as a
pre-release or with the suffix in the name: whoever reaches the Releases page has to
see the stable one and download it without hesitating. `.github/workflows/release.yml`
is added, triggered by a **`v*` tag**: it runs the same unit-test gate, builds the
same four artifacts **without the suffix** (the installer comes out as
`NightScribeSetup-0.1.0.exe`) and publishes a stable release marked as the latest,
with the notes taken from that version's section of `CHANGELOG.md`. The version still
comes from the tag (setuptools-scm), so the `METADATA`, the `.deb`, the `.rpm` and
`--version` all say `0.1.0`; the `metainfo.xml` date is aligned with the tag's. The
rolling preview stays as it is, for everyday work.

**Revisión (2026-10-20, el entorno de EXOTIC viaja como artefacto del release)**:
EXOTIC no puede vivir dentro de la app (ADR-004): necesita su propio Python (3.10 a
3.12) y una pila pesada con pines propios (numpy 1.26, astropy 6.1, numba 0.59) que
no se pueden compartir con las de NightScribe. Hasta aquí el observador lo instalaba
a mano y la app ofrecía «Preparar entorno» para construirle un venv, y ese era el
punto donde más gente se caía. Ahora el proyecto **publica un entorno ya construido
en una release propia**, con el tag fijo **`exotic-env`** como URL estable, y **un
artefacto por plataforma** (`nightscribe-exotic-linux-x86_64.zip` y
`nightscribe-exotic-windows-x64.zip`): un CPython portátil con EXOTIC ya instalado
dentro, que se descomprime donde se quiera y se apunta Ajustes a su intérprete, sin
instalar nada. Son **dos** artefactos y no uno porque un entorno Python lleva
binarios compilados y no se puede compartir entre sistemas; son los mismos dos que
ya usa la matriz de la app. **La app no descarga nada**: no hay descargador, ni URL,
ni suma de comprobación en el código; el zip se coge de la página de esa release como
los demás. «Preparar entorno» se queda como alternativa para quien prefiera
construirlo con su Python, y ahora construye **al lado y cambia al final**, de modo
que un fallo o una cancelación no se llevan por delante el entorno que ya había
(ver el plan de orquestación, fase H).

**Consecuencias**: el instalador no engorda (el zip es un artefacto suelto de unos
375 MB comprimidos y solo lo baja quien reduce tránsitos), el flujo de tránsito deja
de depender de que el observador acierte con la versión de Python, y **la release de
la app se queda con sus cuatro artefactos de siempre**: el entorno no se reconstruye
en cada release, sino solo cuando cambia su fichero de versiones fijadas (o cuando un
mantenedor lo lanza a mano), porque reconstruirlo sin motivo sería trabajo tirado y,
peor, un agujero de reproducibilidad: dos observadores que descargaran la misma
versión de la app con meses de diferencia tendrían dentro numpy distinto. El CI
construye el zip desde ese lock y lo **prueba** (`import exotic`) en las dos
plataformas, así que un zip que no funciona no llega a publicarse.

**Review (2026-10-20, the EXOTIC environment ships as a release artifact)**:
EXOTIC cannot live inside the app (ADR-004): it needs a Python of its own (3.10 to
3.12) and a heavy stack with its own pins (numpy 1.26, astropy 6.1, numba 0.59) that
cannot be shared with NightScribe's. Until now the observer installed it by hand and
the app offered "Prepare environment" to build a venv, and that was where most people
fell over. The project now **publishes a prebuilt environment in its own release**,
with the fixed tag **`exotic-env`** as the stable URL, and **one artifact per
platform** (`nightscribe-exotic-linux-x86_64.zip` and
`nightscribe-exotic-windows-x64.zip`): a portable CPython with EXOTIC already
installed, which is unzipped anywhere and pointed at from Settings, with nothing to
install. There are **two** artifacts and not one because a Python environment carries
compiled binaries and cannot be shared across systems; they are the same two the
app's own matrix already uses. **The app downloads nothing**: there is no downloader,
no URL and no checksum in the code; the zip is taken from that release's page like the
rest. "Prepare environment" stays as the alternative for whoever prefers to build it
with their own Python, and it now builds **aside and swaps at the end**, so a failure
or a cancel does not take away the environment that was already there (see the
orchestration plan, phase H).

**Consequences**: the installer does not grow (the zip is a loose artifact of about
375 MB compressed and only whoever reduces transits downloads it), the transit flow
stops depending on the observer getting the Python version right, and **the app's
release keeps its four artifacts as always**: the environment is not rebuilt on every
release, only when its lock file changes (or when a maintainer runs the workflow by
hand), because rebuilding it for no reason would be wasted work and, worse, a
reproducibility hole: two observers downloading the same app version months apart
would get a different numpy inside. CI builds the zip from that lock and **tests** it
(`import exotic`) on both platforms, so a zip that does not work never gets published.
