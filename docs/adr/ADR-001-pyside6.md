# ADR-001: PySide6 (Qt6) for the GUI

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: la app necesita una GUI de escritorio multiplataforma (Windows/Linux),
publicable y con aspecto moderno. El proyecto hermano `saas` usaba PyQt5.

**Decisión**: usar **PySide6** (Qt6).

**Alternativas**: PyQt5 (instalado en el sistema del autor, pero legacy y GPL);
PyQt6 (GPL/comercial); Tkinter (ni instalado ni moderno); web local (más compleja).

**Consecuencias**: licencia LGPL (cómoda para publicar), wheels oficiales
Win/Linux/macOS, HiDPI y temas nativos, `pyside6-designer`/`pyside6-lupdate`/`lrelease`
incluidos. PySide6 se instala en el `.venv` del proyecto (no en el sistema).

## English

**Context**: the app needs a cross-platform desktop GUI (Windows/Linux), publishable
and modern-looking. The sibling project `saas` used PyQt5.

**Decision**: use **PySide6** (Qt6).

**Alternatives**: PyQt5 (installed on the author's system, but legacy and GPL);
PyQt6 (GPL/commercial); Tkinter (neither installed nor modern); local web app
(more complex).

**Consequences**: LGPL licence (comfortable for publishing), official Win/Linux/macOS
wheels, HiDPI and native themes, `pyside6-designer`/`lupdate`/`lrelease` included.
PySide6 lives in the project `.venv`, not the system.
