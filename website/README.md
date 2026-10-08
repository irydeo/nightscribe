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

## The screenshots

The site shows **real captures** of the application, taken by hand with the
observer's own data: they are not mockups (ADR-070). The raw files live
outside the repository (they are big, and they carry real data); the site's
copies are prepared from them:

```bash
python3 website/tools/prepare_screens.py --from ~/ruta/a/las/capturas
```

It resizes them to 1400 px, converts them to WebP (a 2181 px PNG of the dark
interface weighs 2.9 MB; the same at 1400 px and quality 92 weighs 240 KB,
with no visible loss at the size the page shows them) and writes them as
`website/assets/screens/<name>.webp`.

The names the generator expects are in `SHOTS` (with the caption each one
carries) and the chapters they belong to in `CHAPTER_SHOTS`, both in
`build_site.py`. **A capture that is still missing simply leaves its figure
out**, so they can arrive a few at a time and the page is never broken; the
preparer prints which ones are still pending.

## Publish it

`.github/workflows/pages.yml` builds the site and publishes it to GitHub Pages
on every push to `main` or `release/v0.1` (and on demand). It needs no
dependency: the generator uses the standard library only, and it reads the
app's modules without starting Qt.

One-time setup in the repository: **Settings → Pages → Source: GitHub Actions**.
