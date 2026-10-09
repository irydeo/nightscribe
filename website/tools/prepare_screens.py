############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Website: prepare the screenshots
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Turns the raw captures of the application into the site's images.

The website shows REAL screenshots of NightScribe (ADR-070): they are taken
by hand, with the observer's own data, and dropped in a folder; this script
resizes them, converts them to WebP (a 2181 px PNG of the dark interface
weighs 2.9 MB, the same at 1400 px and quality 92 weighs 240 KB, with no
visible loss at the size the page shows them) and writes them with the name
the generator expects, under `website/assets/screens/`.

It never touches the raw folder, and a file that is not there is simply
skipped: the generator draws a chapter's figure only when its image exists,
so the captures can arrive a few at a time.

Usage:  python3 website/tools/prepare_screens.py [--from DIR]
"""

import argparse
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent           # website/
OUT = SITE / "assets" / "screens"

# The observer's raw captures live outside the repository (they are big, and
# they carry real data): this is where the last batch was left.
RAW_DEFAULT = Path.home() / "Develop" / "astronomy" / "nightscribe-tmp" / \
    "capturas"

# The raw file's stem -> the name the site uses. A file already named like its
# target is taken as is, so a new capture only has to be dropped with the
# right name (welcome, tonight, campaigns, capture, posts, settings).
NAMES = {
    "AT2026acka-main": "project",
    "2025FG18-track-stack": "astrometry",
    "V0526-photometry": "photometry",
    "Transit": "projects",
    "V0526-curve": "curve",
    "AT2026acka": "measure",
    "Transit-result": "transit",
}

# The width the page shows them at, doubled for a retina screen: the landing
# caps a figure at ~1100 px and the guide at ~900, so 1400 is the honest
# compromise between sharpness and weight.
WIDTH = 1400
QUALITY = 92


def prepare(raw_dir, out_dir=OUT, width=WIDTH):
    # @args: raw_dir - the folder with the captures, out_dir - where the
    #        site's copies go, width - the target width in pixels
    # @return: (written, missing) - the names written and the ones still to
    #          capture, so the run says what it did instead of being silent
    from PIL import Image
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    if not raw_dir.is_dir():
        raise SystemExit(f"no captures at {raw_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    written, missing = [], []
    for raw in sorted(raw_dir.glob("*.png")):
        name = NAMES.get(raw.stem, raw.stem)
        im = Image.open(raw).convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)),
                           Image.LANCZOS)
        target = out_dir / f"{name}.webp"
        im.save(target, "WEBP", quality=QUALITY, method=6)
        written.append(name)
        print(f"  {raw.name:<28} -> {target.name:<18} "
              f"{target.stat().st_size // 1024:>4} KB")
    # what the site has, and what it is still waiting for
    have = {p.stem for p in out_dir.glob("*.webp")}
    for name in sorted(set(NAMES.values()) - have):
        missing.append(name)
    return written, missing


def main(argv=None):
    # @args: argv - the command line, or None for sys.argv
    # @return: 0
    parser = argparse.ArgumentParser(description="Prepare the site's captures")
    parser.add_argument("--from", dest="raw", default=str(RAW_DEFAULT),
                        help=f"the raw captures (default: {RAW_DEFAULT})")
    args = parser.parse_args(argv)
    written, missing = prepare(args.raw)
    print(f"{len(written)} image(s) written to {OUT}")
    if missing:
        print("still to capture: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
