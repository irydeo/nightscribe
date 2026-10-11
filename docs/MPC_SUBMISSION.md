# MPC submission: how NightScribe sends an astrometry report

*Reference for the people maintaining the report and the submission: what the
formats carry, what the settings provide, what the dialog asks and what the app
does with it. The user-facing guide is `docs/user/07-astrometry.md`; the decision
behind it is ADR-080.*

---

## 1. Where it starts

In the Astrometry tab, **Manage MPC report** opens the report window
(`UfeReportDialog`, non-modal). The tab keeps only the button and the note; the
window holds the format selector, the report and the actions. **Send to MPC…**
opens the submission dialog (`MpcSendDialog`), which asks for the four options
and POSTs the batch.

The report is rebuilt every time from the measured points of the run plus the
header built from the settings, so the text can never disagree with what was
measured.

## 2. The three formats

| Format | What it emits |
|---|---|
| **ADES XML** (the MPC's preference) | `<ades version="2017"><obsBlock><obsContext>…</obsContext><obsData><optical>…` |
| **ADES PSV** | the `obsContext` (`#`/`!` blocks) + a header row + one pipe row per observation |
| **MPC 1992** (80 columns) | the header lines + one 80-character line per observation + `----- end -----` |

All three are built by `core/mpc_astrometry.generate(points, fmt, obs_code,
designation, cfg, context, submission, kind)` and go through
`core/mpc_report.validate` (the same judge a pasted report passes) before they
leave; the XML is judged by the MPC's own schema at submission.

## 3. The MPC 1992 header

Emitted by `mpc_astrometry.mpc80_header(ctx, submission, n_obs)`, in the order
the MPC reads it:

```
COD <obs_code>
CON <observer>            (a second CON [<email>] when the email is set)
OBS <observer>
MEA <measurer>            (empty measurer falls back to the observer)
TEL <telescope>           (built, or the observer's free text)
NET <catalogue name>      (Gaia3E -> "Gaia EDR 3", ...)
COM <comment>             (optional)
ACK <obj_type> <ack>      (the target keyword is prepended when absent)
AC2 <email>
NUM <n observations>
<data lines>
----- end -----
```

Without the header the MPC ignores the batch ("Observation batches that do not
include an observational header will not be recognized", ObsDetails.html).

The **designation** goes in its own columns: the packed number in 1-5, the packed
provisional or the temporary (NEOCP/PCCP) designation in 6-12, the detector in
column 15. The **precision** is the MPC's normal one (5 decimals of a day, 2 of a
second of RA, 1 arcsecond of Dec, 1 tenth of a magnitude), which is what leaves
the separating space between fields; the extra-precision option is not used
because the MPC does not allow most observatories to use it.

## 4. The ADES context

Emitted by `mpc_astrometry.ades_psv_context(ctx)` for PSV and the equivalent
`obsContext` for XML:

```
# version=2017
# observatory      ! mpcCode <code>   ! name <observatory name>
# submitter        ! name <observer>
# telescope        ! aperture <m>   ! fRatio <f/>   ! design <type>   ! detector <CCD|CMO>
# observers        ! name <observer>
# measurers        ! name <measurer>
# comment          ! line <comment>   (optional)
```

ADES keeps personal data OUT of the document: the email is **not** here, it
travels in the submission form (`ac2`). The identifier column is
`permID`/`provID`/`trkSub` (never the legacy `objid`): a number goes in `permID`,
a provisional in `provID`, a temporary tag in `trkSub`.

## 5. The settings it reads

`mpc_astrometry.report_context(cfg)` builds one `ReportContext` from the
Settings (Observatory page):

| Setting | Header field |
|---|---|
| `mpc_code` | COD, and the `stn` column |
| `observer_name` | CON, OBS, the ADES submitter/observers |
| `measurer_name` | MEA, the ADES measurers (empty -> the observer) |
| `observer_email` | AC2 (and CON `[email]`) |
| `telescope_desc` | TEL verbatim when set |
| `telescope_type` + `telescope_focal_ratio` + `aperture_inches` | the built TEL line |
| `camera_type` | the detector (`CCD`/`CMO`) |
| `astrometry_astcat` | NET, and the ADES `astCat` |
| `mpc_report_comment` | COM |

The telescope line is built as `"<aperture>-m f/<ratio> <type>"` plus
`" + <detector>"` for the MPC 1992 TEL; the focal ratio is derived from the
focal length and the aperture when the observer does not set it. The same
builder (`ReportContext.tel_body()`) feeds the image band, so the band and the
report cannot disagree.

## 6. The submission dialog

`MpcSendDialog` (structure in `gui/ui/ufe_mpc_send_dialog.ui`) asks for:

- **Ack. email** (AC2): prefilled with `observer_email`; **required**.
- **Ack.**: a short acknowledgement text; optional.
- **Target** (`obj_type`): how the MPC routes the batch.
- **Mode**: Normal or Test.
- A **log** with the server's own answer, and **Send** / **Close**.

### Target

The keyword the MPC needs to route the batch (ObsDetails.html). It rides the
report's ACK line in MPC 1992 and the `obj_type` form field in ADES.

| Value | Meaning |
|---|---|
| Unclassified | the object is already classified; a normal submission, no keyword needed |
| NEOCP | the object is on the Near-Earth Object Confirmation Page |
| PCCP | it is on the Possible Comet Confirmation Page |
| NEW NEO | a candidate for a new near-Earth object |
| NEW COMET | a candidate for a new comet |
| NEW NATURAL SATELLITE | a candidate for a new natural satellite |
| NEW TNO / NEW KBO / NEW DISTANT / NEW CENTAUR | a candidate for a new TNO, KBO, distant object or centaur |

A missing or wrong keyword can misroute the batch or stop it being processed as
expected. The default is NEOCP when the project is on the NEOCP, Unclassified
otherwise. The list lives once, in `mpc_submit.TARGETS`.

### Mode

- **Normal**: the real endpoint; the MPC processes and publishes the batch.
- **Test**: the `*_test` endpoint, which runs the same format and validity checks
  but does **not** process the batch (a rehearsal).

## 7. What happens internally on Send

1. **Gate** (`UfeTrackStackTab._refresh_send_gate`): `ReportContext.missing()`
   lists what a submission cannot be built without (the observatory code, the
   observer, the telescope, the contact email); while anything is missing the
   dialog shows it and **Send stays disabled**. The email is read from the
   dialog's own field, not only from the settings.
2. **Rebuild**: the tab sets `self._submission = {"ack", "obj_type"}` and calls
   `_on_report(quiet=True)`, so the report carries the chosen ACK line.
3. **Worker**: `workers.MpcSubmitWorker(QThread)` runs the POST off the GUI
   thread.
4. **POST** (`core/sources/mpc_submit.submit`):

| Format | Real endpoint | Test endpoint | Form fields |
|---|---|---|---|
| MPC 1992 | `/submit_obs` | `/submit_obs_test` | `source` only (AC2 is in the header) |
| ADES PSV | `/submit_psv` | `/submit_psv_test` | `source`, `ack`, `ac2`, `obj_type` |
| ADES XML | `/submit_xml` | `/submit_xml_test` | `source`, `ack`, `ac2`, `obj_type` |

Base URL `https://minorplanetcenter.net`; `source` is a multipart file field
carrying the report text. The MPC 1992 endpoint takes the batch alone.

5. **Response**: `ok = HTTP 200 and no "error" in the first 400 characters of the
   body`; the body (the CurlID or the error list) and the URL are returned and
   written to the dialog's log.

## 8. Errors and design notes

- No network is never a crash: a request failure returns
  `"Could not reach the MPC: …"` and is shown in the log.
- The email is **personally identifiable information**, so it never enters an
  ADES document (only the submission form). The MPC's own ADES page states it.
- A submission is a **POST** and cannot be cached, so it does **not** go through
  `core/db.py`; it lives in `core/sources/mpc_submit.py`, the only place allowed
  to import `requests` (AGENTS). Everything else (the report generation) is pure.
- Sending is never silent (ADR-080): the observer sees and chooses the email,
  the ACK, the target and the mode before anything leaves.

## 9. References

- MPC, *Specifying Observational Details*: `iau/info/ObsDetails.html` (the header
  keywords and the target words).
- MPC, *Format For Optical Astrometric Observations*: `iau/info/OpticalObs.html`
  (the 80-column field positions).
- MPC, *Information on How to Submit Observations From the Command Line*:
  `iau/info/commandlinesubmissions.html` (the endpoints and the form fields).
- MPC, *ADES Data Submission*: `mpcops/documentation/ades/` (the PSV/XML
  context and the PII rule).
