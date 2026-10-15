# Contributing to NightScribe

*[Versión en español](CONTRIBUTING.es.md)*

Thanks for your interest! These rules keep the project maintainable by humans.

## Code style (mandatory)

1. **Code is always English**: identifiers, comments, headers.
2. Every `.py` starts with the project header (copy from any existing module,
   adjust the module name). See `AGENTS.md`.
3. Human voice: short `# @args:` / `# @return:` comments above each method; TODOs as
   `# TODO:`; no robotic docstrings, no over-engineering.
4. Short functions, minimal dependencies, no magic.
5. Every GUI-visible string goes through `self.tr()` — never hard-code Spanish or
   English in the interface.
6. All network access goes through the cache in `core/db.py`; `requests` is only
   imported inside `core/sources/`.

## Translations (GUI)

```bash
# rebuild the catalogues: lupdate + ATOMIC lrelease (see below)
.venv/bin/python tools/i18n.py
pyside6-linguist nightscribe/gui/i18n/nightscribe_es.ts    # translate
.venv/bin/python tools/i18n.py --release-only              # recompile the .qm
```

`tools/i18n.py` runs `lupdate` with the same source list as before (the `.py`
files of `gui/` and `gui/widgets/`, `core/kinds.py`, `core/db.py` and the `.ui`
files) and then compiles each `.qm` **atomically**: it writes a sibling temp file
and renames it over the target. Never use the raw `lrelease` command while the
app is open: `QTranslator` **memory-maps the `.qm`**, and rewriting it in place
invalidates an open session's mapping, which then crashes on the next
translation (that was a real GUI core dump, 2026-10-10). The app also loads the
`.qm` **from memory** (no mmap), so a rebuild can no longer take it down; the
atomic rename protects any other app that has it mapped.

English is the base language in code; Spanish is a translation. Tests fail if any
string is left `unfinished`.

**A help names no concrete case** (AGENTS.md, permanent rule): a tooltip or a help
string explains WHY and, at most, the ORDER OF MAGNITUDE ("loses about a quarter of a
magnitude"); it never cites the visit, the date, the object or the number of frames the
measurement came from, and it never gives an example with a proper name. The exact
figures live in the ADR and in the code's comments, which is where they can be checked.
`tests/unit/test_help_texts.py` walks every tooltip, label and `tr()` string and fails
on a case; if a string is legitimately about the vigils (whose list IS T CrB and
R CrB), the test says so in its own words.

## Packaging

```bash
# Windows: Inno Setup over the PyInstaller onedir (the workflow does both)
pyinstaller installer/nightscribe.spec --clean --noconfirm

# Linux (.deb): system Python, Find_Orb included (ADR-087)
sh tools/fetch_findorb.sh findorb-payload
.venv/bin/python tools/build_deb.py --version 0.1.0 --findorb findorb-payload

# Linux (.rpm): installer/rpm/nightscribe.spec   (rpmbuild -bb)
# Arch:          installer/arch/PKGBUILD
```

The three Linux packages use the DISTRO's Python and Qt (ADR-087): `.deb` for
Debian 13+ / Ubuntu 25.10+, `.rpm` for Fedora 42+ / openSUSE Tumbleweed and a
PKGBUILD for Arch. Find_Orb travels inside them (a separate program, legal
aggregation for this non-commercial GPLv3 app); the DE430t ephemeris does not,
it is downloaded from Settings. Distros without a packaged PySide6 (Ubuntu
24.04 LTS) are a documented manual install.

## Tests

```bash
.venv/bin/python -m pytest tests/unit      # offline, must always pass
.venv/bin/python -m pytest tests/functional  # online, end-to-end per feature
```

New features come with unit tests (fixtures from real responses live in
`tests/fixtures/`) and, if they touch a source or a user-facing feature, a functional
test.

## Design decisions

Read `docs/adr/` first. To change a decision, update or supersede the ADR. To add a
data source, follow `docs/DATA_SOURCES.md` (one module per source, TTL, graceful
degradation) and record it in an ADR. For the three recipes that come up most (a new
source, a new target kind, a new editor tab), see `docs/DEVELOPING.md`.

## Release

The version comes from the git tag: `setuptools-scm` reads it, so tagging
`v0.1.0` makes the built package and the app's own `--version` report `0.1.0`.
Nothing to edit by hand.

1. Move the `[Unreleased]` entries of `CHANGELOG.md` (and its Spanish twin)
   under the new version, with today's date.
2. Check the `Development Status` classifier in `pyproject.toml` still matches
   the milestone (`3 - Alpha`, `4 - Beta`, `5 - Production/Stable`).
3. Land it on `main`: the `preview.yml` workflow builds the artifacts (Windows
   installer and portable zip, `.deb`, `.rpm`) and publishes them as the rolling
   pre-release, after the unit suite passes.
4. Tag and push: `git tag -a v0.1.0 -m "NightScribe 0.1.0"` then
   `git push origin v0.1.0`.
5. Create the GitHub release from the tag, with the artifacts from step 3 and
   the notes from the CHANGELOG. Mark it as the latest release, not a
   pre-release.

## Pull requests

One concern per PR, tests green, docs updated (both languages).
