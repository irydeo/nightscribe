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
degradation) and record it in an ADR.

## Pull requests

One concern per PR, tests green, docs updated (both languages).
