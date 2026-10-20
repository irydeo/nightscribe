############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - EXOTIC environment packer
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Prune a built EXOTIC environment and pack it into the published zip.

    python tools/exotic-env/pack.py <env-dir> <out.zip> [root-name]

`root-name` is the folder the observer will see when they unzip (default
`exotic-env`), and it is fixed on purpose: the documentation has to be able to
say where the interpreter is, and that sentence cannot depend on the name the
build machine happened to use.

Written in Python and not with `zip`/`Compress-Archive` on purpose: the zip is
built on two different runners, and the two shells disagree about almost
everything (Git Bash has no `zip`, PowerShell writes a different archive). One
script that behaves the same on both is one less way for the artifact to differ
from what the smoke test approved.

TWO THINGS IT DOES THAT ARE NOT OBVIOUS:

* **It prunes.** Byte-compiled caches go, and not only for tidiness: a `.pyc`
  records the modification time of the source it was built from, which is the
  build machine's clock, so leaving them in would make two builds of the same
  pinned tree produce different bytes for no reason. The standard library's own
  test suite goes too: it is tens of megabytes no observer will ever run.
  Nothing else is touched, because an environment missing a piece of the
  standard library fails months later, in the dark, and costs far more than the
  megabytes saved.
* **It writes every entry with the SAME timestamp.** Zip stores modification
  times, so with a fixed date the sha256 printed here is a faithful fingerprint
  of THIS artifact: packing the same tree twice gives the same number, and the
  sidecar can be checked by whoever downloaded the zip.

  It does NOT promise that two builds of the same lock produce the same bytes,
  and they do not. Three of EXOTIC's dependencies ship as source only and are
  built on the runner (`imreg_dft`, `pylightcurve`, `ultranest`), and setuptools
  and the C compiler record build-time data in what they produce: measured
  2026-10-20, two builds of the same lock gave different wheel hashes for all
  three (ultranest's even differs in size, because its compiled extension keeps
  the build directory in its debug info). What the lock pins is the **versions**,
  which is what decides the physics, and that part is identical every time.
"""

import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

# The zip epoch: 1980-01-01 is the earliest a zip can record, so it is the one
# value that every reader accepts.
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def prune(env_dir):
    # @args: env_dir - the environment root
    # @return: (folders removed, bytes freed), for the log
    removed, freed = 0, 0

    def _size(path):
        try:
            return path.stat().st_size
        except OSError:
            return 0

    # 1. Byte-compiled caches, anywhere.
    for cache in list(env_dir.rglob("__pycache__")):
        freed += sum(_size(f) for f in cache.rglob("*") if f.is_file())
        shutil.rmtree(cache, ignore_errors=True)
        removed += 1
    for pyc in list(env_dir.rglob("*.pyc")):
        freed += _size(pyc)
        pyc.unlink(missing_ok=True)

    # 2. The standard library's test package. It is not imported by anything at
    #    run time (only by CPython's own suite, which nobody runs here), and on
    #    a portable CPython it is one of the biggest single directories.
    for candidate in (env_dir / "lib" / "python3.11" / "test",
                      env_dir / "Lib" / "test"):
        if candidate.is_dir():
            freed += sum(_size(f) for f in candidate.rglob("*") if f.is_file())
            shutil.rmtree(candidate, ignore_errors=True)
            removed += 1

    return removed, freed


def _sha256(path):
    # @args: path - a file
    # @return: its sha256 as hex. Read in chunks: the zip is a few hundred
    #          megabytes, and there is no reason to hold it all in memory just
    #          to hash it.
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pack(env_dir, out_zip, root_name):
    # @args: env_dir - the environment root, out_zip - the zip to write,
    #        root_name - the folder name the entries are written under
    # @return: (bytes written, sha256 hex)
    env_dir = Path(env_dir)
    out_zip = Path(out_zip)
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in env_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for path in files:
            arcname = Path(root_name) / path.relative_to(env_dir)
            info = zipfile.ZipInfo(str(arcname), date_time=_FIXED_DATE)
            # 0644 for files, but an executable has to stay executable: the
            # environment's python and the console scripts are useless without
            # the bit, and zip carries it in the top 16 bits of external_attr.
            mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(path, "rb") as fh:
                zf.writestr(info, fh.read())

    return out_zip.stat().st_size, _sha256(out_zip)


def main(argv):
    # @args: argv - [env_dir, out_zip, root_name?]
    # @return: 0 on success, 2 on a bad invocation
    if len(argv) not in (3, 4):
        print(__doc__.strip().splitlines()[1].strip(), file=sys.stderr)
        return 2
    env_dir = Path(argv[1])
    root_name = argv[3] if len(argv) == 4 else "exotic-env"
    if not env_dir.is_dir():
        print(f"{env_dir} is not a directory", file=sys.stderr)
        return 2
    # A quick sanity check that we are packing a Python and not, say, an empty
    # folder because the download failed silently.
    interpreters = [env_dir / "bin" / "python", env_dir / "python.exe"]
    if not any(p.is_file() for p in interpreters):
        print(f"{env_dir} has no interpreter in it", file=sys.stderr)
        return 2

    removed, freed = prune(env_dir)
    print(f"pruned {removed} folder(s), {freed / 1e6:.1f} MB freed")
    size, digest = pack(env_dir, argv[2], root_name)
    print(f"{argv[2]}: {size / 1e6:.1f} MB (unzips into {root_name}/)")
    print(f"sha256 {digest}")
    # The sidecar travels with the zip: the release notes carry the same number,
    # but whoever downloaded only the zip can still check it.
    Path(argv[2] + ".sha256").write_text(f"{digest}  {Path(argv[2]).name}\n",
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
