# 08. Reporting it

NightScribe's last mission is keeping your observation from dying on the
hard drive: it generates the drafts to tell it, in Spanish and English, with
your session's real data.

## The draft

In a project's **Publishing** step, **Generate** enriches the object (its
orbital, physical and context data) and builds three pieces:

- **ES**: the post in Spanish, with the outreach hook, the key facts as
  bullets and the hashtags (including your MPC code, if you have one).
- **EN**: the same post in English.
- **X**: the short version for the bird network, within the character limit.

Each piece has its own **Copy** button; choose the output folder with
**Browse…** if you want them saved as files next to the charts. The draft is
written on the page itself, with no window to open; while it works, a progress
bar tells you it is still going, because an AI draft can take a couple of
minutes with a model that "thinks".

> **Why a draft and not a publishable post?** Because the voice is yours.
> NightScribe supplies the correct data (the distance, the size, the "why it
> matters" sentence) so you do not have to look it up, but the tone, the
> picture and the final touch belong to your observatory. Edit freely: the
> draft regenerates whenever you want.

## Writing with AI (optional)

If you configure a language model in **Settings → Integrations** (an
OpenAI-compatible service, in the cloud or on your own machine), the Publishing
step gains two buttons:

- **Write with AI…**: drafts the post from **everything** the app knows about
  the project: the object with its explained parameters, the planned night,
  your visits, the measured magnitudes and the campaign verdict.
- **What will be sent…**: shows the exact fact sheet the model would read, so
  you see what would leave your machine before it does.

The AI only phrases: it does not measure, it does not classify and it invents
no figure. Everything it says comes from the dossier, and what is not there it
does not mention. The draft is still yours: review it before publishing.

> **Why off by default?** Because the app works the same without it: the usual
> template stays and needs no network. With a local server (Ollama, for
> instance) nothing leaves your machine; with a cloud one, the cost and the
> privacy are that service's.

## The charts

Alongside the text, NightScribe generates PNGs ready to attach: the orbit,
the sky chart, the night view, the light curve (with the supernova templates
in the background when applicable), the confirmation blink or the animation
of a NEO's motion. They follow the interface language.

> **Why is the blink the "acid test"?** Because in transient outreach,
> credibility is everything: an animation where your object moves (or blinks)
> against the fixed star background proves in two seconds that something is
> there, without a single equation. It is the image that turns a "I saw it"
> into a "see for yourself".

And with that, the loop closes: from the afternoon's target to the next
morning's post. The appendix [09. The command line](09-cli.md) summarises
how to do all of this without opening the window.
