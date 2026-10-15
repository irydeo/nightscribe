# NightScribe: developing

*[Versión en español](DEVELOPING.es.md)*

This is the short path for a maintainer: how to run things and the three
recipes that come up most (a new data source, a new target kind, a new editor
tab). The rules live in [`AGENTS.md`](../AGENTS.md); the decisions live in
[`docs/adr/`](adr/README.md).

## Running it

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest tests/unit -n auto --dist loadfile   # fast, offline
.venv/bin/python -m pytest tests/functional                     # hits the network
.venv/bin/python -m nightscribe gui
```

The unit suite is offline by design: a `requests` call raises and the source's
own fallback must handle it. It also caps its own thread pools (the combine).
On a machine with many cores, `-n auto` can still make a worker die now and
then (a native crash we have not pinned down); `-n 4`, or
`PYTEST_XDIST_AUTO_NUM_WORKERS=4`, is steadier. The CI, with 2-4 cores, is
unaffected.

## The rules that are tests

Some house rules are held by a test, so a PR breaks loudly instead of quietly:
`test_help_texts.py` (a help names no concrete case), `test_em_dash.py` (no em
dash in the guide or the interface strings), `test_import_boundaries.py`
(`requests` only in `core/sources/`, no SQLite in the GUI),
`test_docs_links.py` (every doc link resolves, the ADR index is complete),
`test_site_build.py` (the committed website is what the generator produces),
`test_i18n.py` (both catalogues complete and in sync), and
`test_kinds_contract.py` (every kind has a colour, a chip, an analysis, context
fields and hashtags).

## Recipe: a new data source

1. **One module per source**, `nightscribe/core/sources/<name>.py`. It exposes
   a small `fetch(...)`/client function and never calls `requests` directly:
   it goes through the cache, `db.http_get(key, "<source>", fetch)`, so the TTL
   and the offline behaviour are not its business.
2. **Register the TTL** in `core/db.py` (`SOURCE_TTL`). Pick it from how often
   the upstream really changes (a static atlas is 30 days, a discovery list is
   hours).
3. **Wire it in**: `core/planner.py` if it feeds Tonight (add a stage to the
   `stages` list and a phase to `PHASES`), `core/enrich.py` if it is context
   for the object card.
4. **Document it** in `docs/DATA_SOURCES.md` (the endpoint, what it gives, the
   TTL, whether it needs a key), and add it to the source list in the **About**
   box.
5. **Test it**: a unit test with the source faked (the suite is offline) and a
   functional test that hits the real endpoint.

## Recipe: a new target kind

A kind is a string id written by hand in a lot of places, so this is a hunt.
Start at `core/kinds.py` (the canonical `KINDS` list, plus `ANALYSIS` and
`_CONTEXT_FIELDS`), then:

- `gui/theme.py`: `KIND_COLORS` and `KIND_LABELS` (the chip);
- `core/planner.py`: a builder and its phase;
- `core/suggest.py`: how it scores and its "why tonight";
- `core/narrative.py`: the hook and the hashtags;
- `gui/overview.py`: the object card's rows for the kind;
- `core/project.py`: `VALID_KINDS` if it can be a project.

`test_kinds_contract.py` fails until the maps cover the new id, which is the
cheap safety net; the if-chains are still yours to find. Add the kind's tests
and, if it brings a source, its `DATA_SOURCES.md` entry.

## Recipe: a new editor (UFE) tab

The unified FITS editor's tabs follow ADR-005: the interface is a Designer
file, the code wires it.

1. **The structure** in `nightscribe/gui/ui/ufe_<name>_tab.ui`: every text and
   tooltip lives here, with `<class>` = the owning class and `objectName` =
   the Python attribute.
2. **The tab** in `nightscribe/gui/ufe_<name>_tab.py`: load the `.ui` with
   `ui_loader.load_ui`, wire the signals, fill the data. Custom widgets (a
   canvas, a histogram) never enter the `.ui`: a placeholder `QWidget` plus
   `replaceWidget`.
3. **Every visible string through `self.tr()`**, and run `tools/i18n.py` (never
   a raw `lrelease`).
4. **Register it** in `gui/ufe_dialog.py` (the tab bar and the shared state,
   `gui/ufe_state.py`).
5. **Test it** offscreen: build the tab against a temp plate and assert what it
   shows and what it writes.

## Committing

Code, comments and commit messages in English; one concern per commit; the
tests green; the docs (both languages) updated. If you change a decision,
update or supersede its ADR.
