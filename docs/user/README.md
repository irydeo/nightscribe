# NightScribe: user guide

NightScribe is a desktop application for amateur astronomical observatories
that covers the full life cycle of an observing project:

1. **Plan the night**: it suggests the best targets visible from your
   observatory tonight (NEOs, comets, PCCP candidates, supernovae, variable
   stars, exoplanet transits), each with a 0-100 score and the reason behind
   the suggestion.
2. **Understand each object**: it translates orbital and physical parameters
   into clear explanations, so you know what you are looking at and why it
   matters.
3. **Capture and reduce**: it talks to CCDciel to launch your captures and, in
   its FITS editor, it calibrates, stacks and measures your images: photometry
   (variables, exoplanets, supernovae) and MPC-ready astrometry of minor
   bodies.
4. **Report it**: it drafts bilingual (ES/EN) posts and tweets, with charts
   ready for social media.

> **Why does NightScribe exist?** The bottleneck of an amateur observatory is
> not the telescope: it is deciding what to observe, reducing the data without
> fighting five different programs, and publishing the results. NightScribe
> joins those three parts in one place, with scientific judgement.

## How to read this guide

The chapters follow the natural order of an observing night, so you can read
them start to finish or jump to the one you need:

| Chapter | What you will find |
|---------|--------------------|
| [01. First steps](01-getting-started.md) | Installation, initial wizard and observatory settings |
| [02. Planning the night](02-tonight.md) | The Tonight view, the score, the sky calendar |
| [03. Projects](03-projects.md) | Creating and tracking projects: from the card to publication |
| [04. Campaigns and vigils](04-campaigns.md) | Follow-up campaigns and variable star vigils |
| [05. Capture](05-capture.md) | CCDciel, sequences and image calibration |
| [06. Photometry](06-photometry.md) | Measuring brightness, series, light curves and periods |
| [07. Astrometry](07-astrometry.md) | Positions of asteroids and comets, and the MPC report |
| [08. Reporting it](08-posts.md) | Posts, tweets and charts |
| [09. The command line](09-cli.md) | Appendix: all of the above from the terminal |
| [10. Settings](10-settings.md) | Reference appendix: every Settings section, what it decides and when to touch it |

Conventions:

- Button, tab and menu names appear **in bold**, exactly as you will see them
  in the application.
- The **"Why?"** boxes explain the physics or observing practice behind an
  option, so you can choose with judgement. You can skip them without losing
  the thread.
- Command examples are shown in `code`.

This guide does not aim to be exhaustive: it aims to get you observing sooner
and better. If you miss something, open an issue in the repository.
