############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the website is generated from the sources
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The website and the documentation cannot drift apart (ADR-070).

The site is not written: it is GENERATED from `README.md`, `README.es.md` and
`docs/user/*.md`, which are also what the application renders in Help. These
tests hold that bargain:

  * the committed pages are exactly what the generator produces today (build
    into a temporary folder and compare), so editing the guide and forgetting
    to rebuild fails here instead of shipping a stale site;
  * the markdown converter handles the subset the project writes, including
    the two traps the real files have: a bold run that spans a line break and
    a fenced code block indented inside a list item;
  * every chapter has its page in both languages, and no link on the site
    points at a file that is not there;
  * the palette and the kind colours come from the application's theme, not
    from a second copy of them.

Offline, no Qt needed.
"""

import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SITE = ROOT / "website"
GUIDE_SRC = ROOT / "docs" / "user"


def _generator():
    # @return: the build_site module, loaded from the tools folder (it is a
    #          script, not a package, so it is loaded by path)
    spec = importlib.util.spec_from_file_location(
        "build_site", SITE / "tools" / "build_site.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_site"] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------- converter

def test_a_bold_run_spanning_a_line_break_is_bold():
    # The guide is hard-wrapped: "(**Tools → NightScribe Image
    # Workbench**, or ...)" is ONE run of bold split by the wrap. Rendering
    # line by line left the asterisks on the page.
    gen = _generator()
    html, _heads = gen.md_to_html(
        "Photometry lives in the (**Tools → NightScribe Image\n"
        "Workbench**, or by opening a plate).\n")
    assert "<strong>Tools → NightScribe Image Workbench</strong>" in html
    assert "**" not in html


def test_a_fence_inside_a_list_item_is_a_code_block():
    # The README's install steps carry their commands in a fenced block
    # indented under the item.
    gen = _generator()
    html, _heads = gen.md_to_html(
        "1. **Install**:\n\n"
        "   ```bash\n"
        "   pip install -r requirements.txt\n"
        "   ```\n"
        "2. Next.\n")
    assert html.count("<li>") == 2
    assert 'class="code"' in html
    assert "pip install -r requirements.txt" in html
    assert "```" not in html


def test_a_list_item_keeps_its_continuation_lines():
    gen = _generator()
    html, _heads = gen.md_to_html(
        "- **The afternoon ritual.** Before dinner you open NEOfixer\n"
        "  for the NEOs, and the MPC page for comets.\n"
        "- **The trap.** Trailed frames.\n")
    assert html.count("<li>") == 2
    assert "and the MPC page for comets" in html


def test_tables_carry_their_alignment_and_cells():
    gen = _generator()
    html, _heads = gen.md_to_html(
        "| | |\n|---|---|\n| **Required** | Linux or Windows |\n")
    assert "<table>" in html and "<th" in html
    assert "<strong>Required</strong>" in html
    assert "Linux or Windows" in html


def test_a_why_box_is_a_callout_and_a_plain_quote_is_not():
    gen = _generator()
    why, _ = gen.md_to_html("> **Why two methods?** Because each one sees\n"
                            "> something the other does not.\n")
    assert 'class="why"' in why and "Why two methods?" in why
    plain, _ = gen.md_to_html("> A plain note.\n")
    assert 'class="quote"' in plain


def test_inline_code_protects_its_asterisks():
    gen = _generator()
    assert gen.inline("use `a**b` here") == "use <code>a**b</code> here"
    assert gen.inline("**bold**") == "<strong>bold</strong>"


def test_headings_get_anchors_and_they_do_not_repeat():
    gen = _generator()
    html, heads = gen.md_to_html("## The night\n\ntext\n\n## The night\n")
    assert [h["id"] for h in heads] == ["the-night", "the-night-x"]
    assert html.count('id="the-night') == 2


def test_links_are_rewritten_by_the_caller():
    gen = _generator()
    html, _heads = gen.md_to_html(
        "See [the chapter](02-tonight.md).\n",
        lambda href: href.replace(".md", ".html"))
    assert 'href="02-tonight.html"' in html


# ------------------------------------------------------------------- build

def test_the_committed_site_matches_the_sources(tmp_path):
    # The guard of ADR-070: build into a temporary folder and compare it,
    # byte for byte, with what is committed. A stale site fails here.
    import filecmp
    gen = _generator()
    gen.build(tmp_path)
    fresh = gen._generated(tmp_path)
    assert fresh, "the generator produced nothing"
    committed = set(gen._generated(SITE))
    missing = [str(p) for p in fresh if p not in committed]
    differs = [str(p) for p in fresh
               if p in committed and not filecmp.cmp(
                   SITE / p, Path(tmp_path) / p, shallow=False)]
    assert not missing and not differs, (
        "the committed site is out of date (run website/tools/build_site.py):"
        f" missing {missing}, differs {differs}")
    assert not (committed - set(fresh)), (
        "the site carries files the generator no longer produces: "
        f"{sorted(committed - set(fresh))}")


def test_every_chapter_has_its_page_in_both_languages():
    gen = _generator()
    chapters = gen._chapters()
    assert len(chapters) >= 10, chapters
    for chapter in chapters:
        for suffix in ("", ".es"):
            page = SITE / "docs" / f"{chapter['stem']}{suffix}.html"
            assert page.is_file(), page
            assert chapter["title"]["en"] in page.read_text(
                encoding="utf-8") or chapter["title"]["es"] in \
                page.read_text(encoding="utf-8")


def test_the_guide_index_lists_every_chapter():
    gen = _generator()
    text = (SITE / "docs" / "index.html").read_text(encoding="utf-8")
    for chapter in gen._chapters():
        assert f'{chapter["stem"]}.html' in text
    es = (SITE / "docs" / "index.es.html").read_text(encoding="utf-8")
    for chapter in gen._chapters():
        assert f'{chapter["stem"]}.es.html' in es


def test_no_link_on_the_site_is_broken():
    # Every local href must land on a file that exists: a renamed chapter
    # would otherwise leave dead links behind, in two languages.
    broken = []
    for page in SITE.rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        for href in re.findall(r'href="([^"]+)"', html):
            if href.startswith(("http", "#", "mailto:")):
                continue
            target = (page.parent / href.split("#")[0]).resolve()
            if not target.is_file():
                broken.append(f"{page.relative_to(SITE)} -> {href}")
    assert not broken, broken


def test_the_palette_and_the_kinds_come_from_the_app():
    # The site's colours are the application's, injected at build time: no
    # placeholder may survive, and the accent and the kind hues must be the
    # theme's own values.
    gen = _generator()
    sys.path.insert(0, str(ROOT))
    from nightscribe.gui import theme
    css = (SITE / "assets" / "style.css").read_text(encoding="utf-8")
    assert re.search(r"--accent:\s*" + re.escape(theme.C_ACCENT), css)
    for kind, color in theme.KIND_COLORS.items():
        assert f"--kind-{kind}: {color};" in css
    assert "/*accent*/" not in css and "/*kinds*/" not in css


def test_the_landing_shows_the_kinds_with_the_app_colours():
    gen = _generator()
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert html.count('class="kind"') == len(gen.kinds_catalogue("en"))
    for kind in gen.kinds_catalogue("en"):
        assert kind["color"] in html
    es = (SITE / "index.es.html").read_text(encoding="utf-8")
    assert es.count('class="kind"') == len(gen.kinds_catalogue("es"))


def test_the_top_bar_shows_the_curated_sections():
    # The bar is CURATED on purpose: with every heading it needed a scroll,
    # and a scrollbar in the header is the one thing the landing must not
    # have. Each title it shows has to exist in the README (and reach the
    # page), or a rewording would drop an entry without anybody noticing.
    gen = _generator()
    for lang, suffix in (("en", ""), ("es", ".es")):
        readme = (ROOT / f"README{suffix}.md").read_text(encoding="utf-8")
        for title in gen.NAV_MAIN[lang]:
            assert f"## {title}" in readme, (lang, title)
        page = (SITE / f"index{suffix}.html").read_text(encoding="utf-8")
        nav = page[page.index('<nav class="bar-nav">'):]
        nav = nav[:nav.index("</nav>")]
        assert nav.count("<a ") == len(gen.NAV_MAIN[lang]) + 1, lang
        for anchor in re.findall(r'href="#([^"]+)"', nav):
            assert f'id="{anchor}"' in page, (lang, anchor)


def test_the_landing_and_the_guide_are_the_readme_and_the_chapters():
    # The point of the whole thing: the prose is not written twice. The
    # landing's definition is the README's own opening and the guide's pages
    # carry the chapters' own words.
    gen = _generator()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    _tagline, definition = gen._hero_text(readme)
    landing = (SITE / "index.html").read_text(encoding="utf-8")
    assert definition in landing
    chapter = (GUIDE_SRC / "06-photometry.md").read_text(encoding="utf-8")
    sentence = "the best comparison is the one that resembles the target"
    # the source is hard-wrapped (and inside a "why" box): the claim is that
    # the page carries the chapter's own words
    assert "best comparison" in chapter
    assert sentence in (SITE / "docs" / "06-photometry.html").read_text(
        encoding="utf-8")


def test_the_site_is_offline_and_loads_nothing_from_elsewhere():
    # No analytics, no CDN, no external font: the page must open from a file
    # on a machine without network (the app's own promise). Links may point
    # anywhere (the author's site, the data services), but nothing may be
    # LOADED from outside.
    for page in SITE.rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        loaded = re.findall(r'src="(https?://[^"]+)"', html) + re.findall(
            r'<link[^>]+href="(https?://[^"]+)"', html)
        assert not loaded, (page, loaded)
