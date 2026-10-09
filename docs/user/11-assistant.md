# 11. The assistant

NightScribe can carry an assistant to ask about the object you are working on,
about the application itself, or about what you have in front of you in the
editor. It does not measure, it does not classify and it does not decide: it
only reads what the app already knows and puts it into words.

## Where it is

Under **Help → Assistant…**. If you have a project open, the assistant can talk
about it; if not, it talks about the app. In the FITS editor there is also a
**?** button in the bar: it opens the assistant focused on what you have
loaded.

## The three scopes

The selector on top decides what it answers about:

- **This object**: your open project. The assistant reads its fact sheet: the
  object with its explained parameters, the planned night, your visits, the
  measured magnitudes and the campaign verdict.
- **The app**: the user guide and the ADRs. Questions like "how do I calibrate
  the frames?" or "what does MOID mean?".
- **The editor**: what you have loaded (the plate, the tab, whether it has a
  WCS) plus the guide. "I want to make the light curve, can I?" is answered
  from what is on screen and from the guide's steps.

Under each answer you will see **the sources** that were used: the fact sheet's
fields or the documents. If there was nothing to ground it on, it says so; the
assistant does not fill the gaps.

> **Why is it different from a chatbot?** Because it only talks about what the
> app has in front of it. It invents no figures or classifications and it does
> not touch your data: if something is not in the fact sheet or the guide, it
> answers that it does not know. It is a companion that looks at your screen,
> not a data source.

## What you need

A language model configured in **Settings → Integrations** (chapter 10).
Without one, the assistant says so and sends nothing. The conversation lives
only in its window: closing it forgets it. Nothing is stored in your database.
