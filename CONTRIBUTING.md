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
# note: list sources explicitly — scanning the directory silently skips .py files
pyside6-lupdate nightscribe/gui/*.py nightscribe/gui/ui/*.ui \
    -ts nightscribe/gui/i18n/nightscribe_es.ts \
    nightscribe/gui/i18n/nightscribe_en.ts
pyside6-linguist nightscribe/gui/i18n/nightscribe_es.ts    # translate
pyside6-lrelease nightscribe/gui/i18n/nightscribe_*.ts     # compile .qm
```

English is the base language in code; Spanish is a translation. Tests fail if any
string is left `unfinished`.

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
