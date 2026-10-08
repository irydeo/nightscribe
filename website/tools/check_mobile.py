############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Website: check it on a phone
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Checks that no page of the site is wider than the screen.

A page that scrolls sideways on a phone is broken, not "desktop-only": the
audit of 2026-10-08 measured the guide at 1764 px on a 390 px phone (the
contents' links are nowrap and the grid could not shrink) and the landing at
754 (a code block without its own scroll). Both were invisible on a desktop.

The widths are the real ones (320, 360, 390, 430) and they are tested with an
IFRAME, because headless Chrome refuses to lay out a viewport narrower than
500 px: the iframe IS the viewport, and the page inside gets its media
queries right. The outer page reads the inner one's `scrollWidth` (the pages
are local files, so `--allow-file-access-from-files` lets them talk) and
writes the verdict into its own DOM, which is what `--dump-dom` prints.

It also leaves a screenshot of each combination, which is what a person
actually looks at.

Usage:  python3 website/tools/check_mobile.py [--widths 320,360,390,430]
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
WIDTHS = (320, 360, 390, 430)
HEIGHT = 1400

# The pages worth checking: the landing (the widest content: tables, code)
# and one chapter per layout (the guide's index and a full chapter).
PAGES = ("index.html", "index.es.html", "docs/index.html",
         "docs/06-photometry.es.html", "docs/07-astrometry.html")

CHROME_CANDIDATES = ("google-chrome", "chromium", "chromium-browser",
                     "google-chrome-stable")

# The harness: an iframe of exactly the width being tested, and a probe that
# compares the inner document with it. Everything is written into #nsresult,
# which the caller reads from the dumped DOM.
HARNESS = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>mobile check</title></head>
<body style="margin:0;background:#222">
<iframe id="page" src="{page}" style="width:{width}px;height:{height}px;
 border:0"></iframe>
<div id="nsresult">waiting</div>
<script>
var frame = document.getElementById("page");
frame.addEventListener("load", function () {{
  setTimeout(function () {{
    try {{
      var doc = frame.contentDocument;
      var sw = doc.documentElement.scrollWidth;
      var over = sw > {width} + 1;
      var wide = [];
      var all = doc.querySelectorAll("body *");
      for (var i = 0; i < all.length && over; i++) {{
        var r = all[i].getBoundingClientRect();
        var ov = getComputedStyle(all[i]).overflowX;
        if (r.right > {width} + 1 && r.width > 0 &&
            ov !== "auto" && ov !== "scroll" && ov !== "hidden") {{
          wide.push(all[i].tagName.toLowerCase() +
                    (all[i].className ? "." + all[i].className : "") +
                    " (" + Math.round(r.right) + ")");
        }}
      }}
      // a heading that cannot fit its own box is cut, and the boxes alone do
      // not say so (the hero's wordmark was, at 320)
      var cut = [];
      var heads = doc.querySelectorAll("h1, h2, h3");
      for (var j = 0; j < heads.length; j++) {{
        if (heads[j].scrollWidth > heads[j].clientWidth + 1) {{
          cut.push(heads[j].tagName.toLowerCase() + " (" +
                   heads[j].scrollWidth + ">" + heads[j].clientWidth + ")");
        }}
      }}
      document.getElementById("nsresult").textContent =
        "RESULT {page} {width} " + sw + " " +
        (over ? "OVERFLOW" : (cut.length ? "CUT" : "ok")) +
        (wide.length ? " :: " + wide.slice(0, 6).join(", ") : "") +
        (cut.length ? " :: " + cut.slice(0, 4).join(", ") : "");
    }} catch (e) {{
      document.getElementById("nsresult").textContent =
        "RESULT {page} {width} ? ERROR " + e;
    }}
  }}, 250);
}});
</script></body></html>
"""


def _chrome(explicit=None):
    # @args: explicit - a path from the command line, or None
    # @return: the browser's command, or None when there is none
    if explicit:
        return explicit
    for name in CHROME_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return None


def check(pages=PAGES, widths=WIDTHS, chrome=None, shots=None):
    # @args: pages - the pages to test, widths - the viewports, chrome - the
    #        browser, shots - where to leave the screenshots (None = nowhere)
    # @return: (results, failed): [(page, width, scrollWidth, verdict, wide)]
    browser = _chrome(chrome)
    if browser is None:
        raise SystemExit("no Chrome found: pass --chrome PATH")
    results, failed = [], []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copytree(SITE, tmp / "site",
                        ignore=shutil.ignore_patterns("tools"))
        for width in widths:
            for page in pages:
                harness = tmp / "frame.html"
                harness.write_text(
                    HARNESS.format(page=f"site/{page}", width=width,
                                   height=HEIGHT), encoding="utf-8")
                args = [browser, "--headless=new", "--no-sandbox",
                        "--disable-gpu", "--allow-file-access-from-files",
                        f"--user-data-dir={tmp / 'profile'}",
                        "--hide-scrollbars", f"--window-size={width + 40},"
                        f"{HEIGHT + 40}", "--virtual-time-budget=6000",
                        "--dump-dom"]
                if shots is not None:
                    args.append(f"--screenshot={shots / f'{width}-{page.replace(chr(47), chr(95))}.png'}")
                args.append(harness.as_uri())
                out = subprocess.run(args, capture_output=True, text=True,
                                     timeout=120).stdout
                # the verdict lives in the #nsresult div (the script's own
                # source also mentions RESULT, so the div is what we look for)
                line = next((ln for ln in out.splitlines()
                             if 'id="nsresult"' in ln), "")
                line = re.sub(r"<[^>]*>", " ", line).strip()
                parts = line.split()
                # RESULT <page> <width> <scrollWidth> <verdict> [:: offenders]
                if len(parts) >= 5 and parts[4] == "ok":
                    results.append((page, width, parts[3], "ok", ""))
                else:
                    sw = parts[3] if len(parts) > 3 else "?"
                    verdict = parts[4] if len(parts) > 4 else "no result"
                    wide = " ".join(parts[5:]).lstrip(": ")
                    results.append((page, width, sw, verdict, wide))
                    failed.append((page, width, verdict, wide))
    return results, failed


def main(argv=None):
    # @args: argv - the command line, or None for sys.argv
    # @return: 0 when every page fits, 1 when one overflows
    parser = argparse.ArgumentParser(description="Check the site on a phone")
    parser.add_argument("--widths", default=",".join(str(w) for w in WIDTHS))
    parser.add_argument("--chrome", default=None)
    parser.add_argument("--shots", default=None,
                        help="folder for the screenshots (default: none)")
    args = parser.parse_args(argv)
    widths = tuple(int(w) for w in args.widths.split(","))
    shots = Path(args.shots) if args.shots else None
    if shots is not None:
        shots.mkdir(parents=True, exist_ok=True)
    results, failed = check(widths=widths, chrome=args.chrome, shots=shots)
    for page, width, sw, verdict, wide in results:
        print(f"  {width:>4}px  {page:<32} {verdict:<8} "
              f"scrollWidth={sw}{('  ' + wide) if wide else ''}")
    if failed:
        print(f"{len(failed)} combination(s) overflow")
        return 1
    print(f"{len(results)} combination(s) fit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
