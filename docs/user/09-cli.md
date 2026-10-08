# 09. The command line

Everything that matters in NightScribe can be done without opening the
window, with `python -m nightscribe <command>` (or `nightscribe <command>`
if you installed the package). Useful for scripts, cron jobs and hurried
nights.

| Command | What it does |
|---------|--------------|
| `gui` | Starts the desktop application |
| `tonight` | Tonight's best targets, with score and reasons |
| `explore <object>` | The explained object card (orbit, physics, visibility) |
| `post <object>` | The ES/EN drafts and the tweet |
| `solar` | The Sun's state (spots, flares, wind) |
| `blink <object> <fits>` | Blink your FITS against the PanSTARRS reference (supernovae) |
| `history` | Your observing history |
| `sequence <object>` | Proposed photometric sequence and comparison chart |
| `inject` | Injection/recovery: measures how deep your pipeline truly reaches |
| `project …` | Project management: `list`, `create`, `show`, `advance`, `close`, `reopen`, `files` |

Examples:

```bash
python -m nightscribe tonight            # tonight's plan in the terminal
python -m nightscribe explore 2021EQ3    # a NEO's card
python -m nightscribe project list       # your active projects
python -m nightscribe project show "T CrB"
```

> **Why does `inject` deserve its own command?** Because "my telescope
> reaches magnitude 20" is a sentence to be measured, not believed. `inject`
> seeds sources of known brightness into your own frames and checks which
> ones the pipeline recovers: the result is your *real* limit, with your
> sky, your camera and your reduction. It is the honest number you should
> put in the limiting magnitude in Settings.

The GUI and the CLI share database, cache and settings: whatever you do in
one is visible to the other.
