# 04. Campaigns and vigils

There are two kinds of long-term commitment in NightScribe, and they should
not be confused: **campaigns** (a shared group commitment, with a protocol)
and **vigils** (a permanent eye on one specific star).

## Campaigns

A campaign is the *shared* commitment of a group of observatories: a
scientific goal ("measure the full T CrB eruption"), a protocol (cadence in
nights, filters, comparison stars) and the links where results are reported
and data deposited. Many projects hang from one campaign; deleting the
campaign does not delete the projects, it just releases them.

The **Campaigns** tab shows each campaign's health at a glance: how many
projects it has, how many are *due* against the cadence, and a ⚡ when any
member shows an event. The buttons do what they say:

- **New project…**: creates a new project already linked (it resolves the
  name against VSX and SIMBAD; if not found, you enter it by hand).
- **Attach project…**: links an already existing project.
- **Detach…**: unlinks it without deleting anything.

> **Why is cadence the only thing NightScribe "reads" from the protocol?**
> Because it is the only thing it can check. If your campaign asks for one
> measurement every 3 nights and a member has gone 5 without being observed,
> the app pushes it onto tonight's list (computed locally, no network). The
> rest of the protocol (filters, comparisons, notes) is stored as reference,
> but each group's physics is too varied to model: you read it, the app
> remembers it.

## Vigils

A vigil is an alarm over a star that can change *any day*: you edit the
curated list yourself in Settings, and the canonical examples are **T CrB**
(a recurrent nova that can erupt at any moment) and **R CrB** (which fades
without warning).

NightScribe periodically checks the recent photometry (ZTF, and the AAVSO if
you gave it your token) and compares it with each star's baseline. If
something strays from normal, it warns you.

> **Why compare against the baseline and not "the catalogue magnitude"?**
> Because these stars have no "catalogue" brightness: they have a quiescent
> level around which they wander. The anomaly is not T CrB sitting at
> magnitude 10; the anomaly is it departing from its ~10.5 baseline. An
> eruption is detected against the star's own history, not against a table.

> **Why the AAVSO token for the bright ones?** Below ~11.5 mag, ZTF stops
> being reliable because of saturation, so watching the bright stars depends
> on AAVSO community photometry, whose API requires identification. Without
> a token, those vigils stay silent rather than feed you dubious data.

Next: [05. Capture](05-capture.md).
