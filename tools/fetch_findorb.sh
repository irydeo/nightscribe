#!/bin/sh
# NightScribe - prepare a Find_Orb payload for packaging (ADR-079).
#
# Downloads micromamba, creates a private conda-forge environment with the
# `findorb` package and leaves the result in ./findorb-payload, WITHOUT the
# 95 MB DE430t ephemerides (they are optional and downloaded from Settings,
# not bundled). The PyInstaller spec, tools/build_deb.py, the RPM spec and
# the PKGBUILD all pick this folder up.
#
# Why micromamba and not a raw .conda extraction: the `fo` binary has its
# package prefix baked in, and conda RELOCATES it on install. Extracting the
# archive by hand leaves a binary that tries to copy its data from a path
# that does not exist. The app also seeds Find_Orb's config folder from the
# shipped data (core/findorb._seed_findorb_home), which is what makes the
# final, RELOCATED copy work.
#
# Usage:  sh tools/fetch_findorb.sh [target_dir]
set -eu

# The payload is SHIPPED, so it has to be readable by whoever installs the
# package. Without this, the umask of the build machine (or the 0700 that
# `mktemp -d` below creates) travelled into the .deb: the tree was installed
# as drwx------ root root and the app, running as the observer, could not even
# enter it, so Find_Orb "was not there" with its 63 files sitting on disk
# (reported 2026-10-17).
umask 022

TARGET="${1:-findorb-payload}"
ARCH="${NIGHTSCRIBE_ARCH:-linux-64}"

echo "== downloading micromamba ($ARCH) =="
curl -Ls "https://micro.mamba.pm/api/micromamba/${ARCH}/latest" \
    | tar -xj bin/micromamba
chmod +x bin/micromamba

echo "== creating the findorb environment in $TARGET =="
rm -rf "$TARGET"
MAMBA_ROOT_PREFIX="$PWD/.mamba-root" ./bin/micromamba create -y \
    -p "$PWD/$TARGET" -c conda-forge findorb

echo "== dropping the optional DE430t ephemerides (not bundled) =="
rm -f "$TARGET"/share/findorb/jpl_eph/*.430t 2>/dev/null || true

echo "== keeping only bin/fo and its data =="
# The package manager also installs a bundled libstdc++/libgcc, ncurses and
# the interactive `find_orb`; none of it is needed. `fo` links against the
# SYSTEM libstdc++/libgcc (every glibc distro has them) and the app only ever
# runs `fo`, so the payload goes from ~50 MB to ~8 MB.
_tmp=$(mktemp -d)
mkdir -p "$_tmp/bin" "$_tmp/share/findorb"
mv "$TARGET/bin/fo" "$_tmp/bin/"
mv "$TARGET/share/findorb/data" "$_tmp/share/findorb/"
rm -rf "$TARGET"
mv "$_tmp" "$TARGET"
# `mktemp -d` creates 0700 and `mv` keeps it: without this the payload's ROOT
# travels unreadable into every package (the bug above).
chmod -R a+rX "$TARGET"

echo "== payload ready =="
# The payload is what the packages SHIP, so an empty one is a failed run and
# not a smaller package: it used to be reported with a tolerant `ls`, which is
# how a build could carry no Find_Orb and say nothing (2026-10-17).
test -x "$TARGET/bin/fo" || {
    echo "no $TARGET/bin/fo: the findorb package did not land" >&2
    exit 1
}
test -d "$TARGET/share/findorb/data" || {
    echo "no $TARGET/share/findorb/data: fo cannot run without it" >&2
    exit 1
}
ls "$TARGET/bin"
du -sh "$TARGET"
