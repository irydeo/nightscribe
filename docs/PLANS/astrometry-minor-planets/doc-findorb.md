# Find_Orb: what it is, how to install it and how NightScribe uses it

> User section of the `docs/ASTROMETRY.es.md` / `docs/ASTROMETRY.md` pair
> (phase 10 of the plan). This documents it in full so the observer can set it
> up unaided. The Spanish version is `doc-findorb.es.md`, the sister of this
> file.

## 1. What Find_Orb is and why NightScribe uses it

**Find_Orb** is a program by Bill Gray (Project Pluto) that determines the
orbit of an asteroid, a comet or a satellite from its astrometric
observations. It has been proven by the community for years and it is what the
Minor Planet Center itself recommends.

NightScribe **does not reimplement orbit fitting**: that would be reinventing
the wheel, and worse. It uses Find_Orb as the referee of the quality check: it
hands it the object's observations (ours and those of the other observers) and
reads back the residuals of ours against the orbit fitted to the others. If
our point fits, the measurement is sound; if it falls outside the cloud, we
warn before it is sent to the MPC.

Why this matters: stacking (track & stack) can produce phantom detections. The
MPC warns about this and explains that a false tracklet on the NEOCP can make
the object be lost. Seeing the object (the centred sequence) and checking it
against the others (Find_Orb) are the two safety nets.

NightScribe **does not distribute Find_Orb**: it only detects your copy and
runs it, just as it does with ASTAP for plate solving. Find_Orb is licensed
under GPL-2.0-or-later.

## 2. Installation

### 2.1 Linux (and macOS): the easy route, conda-forge

There is a package with **pre-built binaries** for Linux and macOS, so nothing
has to be compiled:

```bash
conda install -c conda-forge findorb
# or, with micromamba (lighter):
micromamba install -c conda-forge findorb
# or, with pixi:
pixi add findorb
```

The package installs **two executables**:

- `fo`: the **non-interactive** one, which is the one NightScribe uses.
- `find_orb`: the interactive one, to look at things by hand.

It also pulls in **`findorb-data-de430t`**, the JPL DE430t ephemerides that
Find_Orb needs for perturbations. It installs automatically as a dependency.

After installing, check that it exists:

```bash
which fo
```

If your processor is ARM (aarch64) and the package is not available for that
architecture, use the source build of section 2.3.

### 2.2 Windows: ready-made binaries

On the Find_Orb download page (`https://www.projectpluto.com/find_orb.htm`)
download:

1. The **console version** (64-bit): `find_c64.zip`. Unzip it into its own
   folder, for example `C:\Find_Orb`.
2. The **non-interactive executable** `fo64.exe`, from the `fo` download link
   on that same page, and leave it **in the same folder** as the console. Find_Orb
   shares its configuration and ephemeris files with `fo`, so they must live
   together.

In NightScribe you will point to the `fo64.exe` file (section 3).

### 2.3 Building from source (Linux, BSD, macOS)

The official route for Linux, if you do not want conda: the source is on GitHub
(`https://github.com/Bill-Gray/find_orb`) and the build instructions are at
`https://www.projectpluto.com/find_sou.htm`. In short, four repositories are
cloned **side by side** (`find_orb`, `lunar`, `jpl_eph`, `sat_code`) and built
in order (`lunar`, `jpl_eph`, `lunar` with integration, `sat_code` and
`find_orb`), and `ncurses` and `zlib` are required. It is the same recipe the
conda-forge package follows, which you can use as an exact reference.

## 3. Configuring it in NightScribe

1. Open **Settings** and go to the **Calibration** area (or to "Site &
   equipment").
2. In the **Find_Orb** field pick the executable:
   - Linux/macOS: `fo` (not `find_orb`, which is the interactive one).
   - Windows: `fo64.exe`.
3. Press **Test**. NightScribe runs the binary on a sample observation file and
   checks that it responds. If something fails, it tells you what (missing, not
   the `fo` binary, does not start).
4. Leave the run-automatically box ticked. If you prefer not to run it,
   NightScribe will only write the observation file for you to open by hand.

If you configure nothing, the check is **not available**: the app tells you so
on the card, and the remaining safety nets are the centred sequence and the SNR
threshold. It never pretends to have run a check it did not run.

## 4. What NightScribe does with Find_Orb, step by step

1. **Downloads the object's observations**: those published at the MPC, or the
   NEOCP ones if it is not confirmed yet. They are public data; nothing of
   yours is uploaded.
2. **Writes a file** with ours and those of the others, in ADES PSV format (or
   80-column).
3. **Runs `fo`** in a temporary folder, with two precautions:
   - `-D <environment file>`: uses its own configuration, so the result does
     not depend on what you have in `~/.find_orb`.
   - `-r 60,65`: CPU time limit (warns at 60 s and kills at 65), so a stuck fit
     does not hang the app.
4. **Reads `total.json`**, the file where `fo` writes the elements, the
   observations and **the residual of each one**. Our residuals and those of
   the others come from there.
5. **Decides**: compares our residual with the scatter of the others (robust,
   so a single bad observer does not raise the bar) and with our own
   uncertainty. If we are far outside, it blocks the report by default; you can
   force it, and the fact that you forced it is recorded.
6. **Shows you** the residual, the scatter, how many observatories there are
   and the verdict, with an explanation of what each figure means.

For the check to be a true *leave-one-out*, ours are excluded from the fit:
Find_Orb computes the orbit only from the others and then reports the residual
of ours. That is exactly what Tycho-Tracker does.

## 5. What you will see on screen

- **Our residual**: how far our measurement is from what the orbit predicts, in
  arcseconds.
- **Scatter of the others**: how far they are. It is the fair scale: with a bad
  orbit every residual is large, and what matters is whether we are **outside
  the cloud**.
- **Distinct observatories** that have seen the object and the **date of the
  last observation** (this is also shown on the object card).
- **Verdict**: `ok`, `outlier` (blocks, can be forced), `no reference` (there
  are no other observations to compare with) or `not available` (no Find_Orb
  configured).

## 6. Troubleshooting

- **"Not available" even though I have Find_Orb.** Almost always you pointed
  at the interactive one (`find_orb`) instead of the non-interactive one (`fo`
  or `fo64.exe`).
- **The first run creates `~/.find_orb`.** That is normal: Find_Orb prepares
  its configuration folder the first time. NightScribe does not touch your
  configuration because it uses `-D`.
- **`fo` writes files where it is run.** NightScribe runs it in a temporary
  folder and picks up `total.json` from there; it does not litter your project.
- **The object has no other observations.** A real discovery has nothing to
  compare with: you will see `no reference`, and it does not block. The SNR and
  the centred sequence decide.
- **An object recovered after months.** Its orbit may have drifted; a large
  residual may be the orbit's fault, not yours. That is why the verdict relies
  on the scatter of the others and not on an absolute number.
- **`fo` does not converge.** With very short arcs it may not produce a useful
  orbit; the check flags it as a weak reference and does not block. The MPC
  warns of the same thing: on a short arc, a wrong observation fits just as
  well.
- **Windows: SmartScreen or antivirus.** An executable downloaded from the
  internet may warn the first time; allow the file in your Find_Orb folder.

## 7. Privacy, network and licence

- **Network**: NightScribe downloads the object's observations from the MPC
  (public data). Find_Orb runs **on your machine** and needs no network: the
  DE430t ephemerides are local.
- **Nothing of yours is uploaded**: you do the MPC submission yourself, as
  always.
- **Licence**: Find_Orb is GPL-2.0-or-later. NightScribe does not distribute or
  bundle it; it only detects and runs your copy, just as with ASTAP.
