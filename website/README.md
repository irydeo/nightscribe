# The NightScribe website

The site is not written by hand: it is **generated** from the sources that
already exist, so the page a visitor reads and the page the application shows
in **Help → Technical Documentation** cannot tell different stories (ADR-070).

| The site's pages | Come from |
|---|---|
| `index.html`, `index.es.html` (the landing) | `README.md`, `README.es.md` |
| `docs/*.html` (the manual) | `docs/user/*.md` |
| the kind cards, the palette, the chips | `nightscribe/core/kinds.py`, `nightscribe/gui/theme.py` (and the Spanish from the `.ts` catalogue) |

## Rebuild it

```bash
python3 website/tools/build_site.py             # writes website/
python3 website/tools/build_site.py --check     # compares with what is committed
```

The HTML is committed so the site can be served from a plain folder and read
from a checkout, and `tests/unit/test_site_build.py` rebuilds it and compares
it: a guide edited without rebuilding fails the suite instead of shipping a
stale page.

**Edit `tools/site.css` and `tools/site.js`, never `assets/`**: those two are
the generator's output.

## Publish it

`.github/workflows/pages.yml` builds the site and publishes it to GitHub Pages
on every push to `main` or `release/v0.1` (and on demand). It needs no
dependency: the generator uses the standard library only, and it reads the
app's modules without starting Qt.

One-time setup in the repository: **Settings → Pages → Source: GitHub Actions**.
