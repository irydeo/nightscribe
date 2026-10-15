# 12. The graphics card

The two heaviest stages of a **track & stack** can run on your **graphics
card** instead of on the processor: the **registration** (finding where every
frame sits and which stars it holds) and the **stacking** (deforming every
frame onto the reference and combining them). It is **on by default** and it
does not change what is measured: the result is the same, and a machine with no
card runs on the processor exactly as it always did.

## What it accelerates

- **The registration.** The per-frame estimate is two medians over the whole
  frame (the per-block background and the noise), and a card is an order of
  magnitude faster at them.
- **The stacking.** The warp (deforming each frame onto the reference) and the
  combine (reducing the frames into one image). The combine now holds **any
  number of frames**, so the whole-sequence stack of a long visit stays on the
  card too, not just the short per-observation stacks.

> **Why is a card faster here?** Both stages read and write frame-sized arrays,
> so what decides is **memory bandwidth**, and a card's is an order of
> magnitude above the processor's. It is not a different algorithm: it is the
> same one running on hardware built to move pixels.

## Turning it on and off

The switch is in **Settings → Measurement → Work** (behind the **Advanced** door): **Warp and
combine on the GPU**, with a **Backend** selector beside it. It comes **on**,
and it does nothing on a machine with no card: the app notices and runs on the
processor.

The run's own note says **which device** did the work, so a reduction never has
to guess. The row itself shows the **card it sees right now** (or that none was
found), so you know before you run. To force the processor, uncheck the switch.

## The backend: OpenCL by default

- **OpenCL** (the default) runs on **NVIDIA, AMD and Intel** and needs nothing
  installed by hand: it travels with the app.
- **Auto** tries CUDA first and falls back to OpenCL.
- **CUDA** is NVIDIA only and is installed by hand (below).

> **Why OpenCL and not CUDA by default?** Because OpenCL is the one the app can
> ship, so it works out of the box on any card, and it is measured not slower
> than CUDA on the same machine. CUDA stays for whoever wants it.

## Enabling CUDA by hand (NVIDIA)

CUDA is not shipped: it is a manual install for an NVIDIA card.

1. Install CuPy with the wheel that matches your CUDA runtime: `cupy-cuda12x`
   for CUDA 12.x, `cupy-cuda11x` for CUDA 11.x. (The suffix follows the major
   version of the CUDA toolkit your driver provides.)
2. Check that it imports: `python -c "import cupy; print(cupy.__version__)"`.
3. In **Settings → Measurement → Work** (behind the **Advanced** door), set **Backend** to
   **CUDA** and start the run again.

> **A packaged install cannot take CUDA.** The Windows and macOS builds carry
> their own Python, so a `pip install` into them is not possible: there,
> **OpenCL** is the only backend. CUDA is for a run from the source, or for the
> Linux packages, which use the system Python.

## What it changes, and what it does not

- The **method**, the flags and the measurements are the same.
- The stack is the same image **within a fraction of an ADU** (the two paths are
  pinned to agree by a test).
- The **processor path is always the reference** and the fallback: any trouble
  with the card, and the run continues on the processor.

## When it pays, and when it does not

It pays where the work is large and continuous: the per-frame estimate and the
stacks of **whole frames** or **many frames**. It does not pay on small cutouts,
and the **velocity sweep stays on the processor on purpose** (its window is
small, and re-reading it for every candidate costs more than it saves).
