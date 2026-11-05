# Browser check: refusal-back-link

A browser-check agent ran this check on 2026-11-05 against commit 1dcde8c. The
browser was headless Chrome 156, driven over the DevTools protocol by a small
Node script. The Claude-in-Chrome extension was not used.

## Setup

- Server: `127.0.0.1:8625`, run with `uv run` from the worktree, with
  `PRACTICE_DIR=<worktree>/.ui-audit-rbl/practice PARTY_COLOUR=green
  PRACTICE_NAME="Huisartsenpraktijk De Akker" DJANGO_DEBUG=1`. It was
  migrated, then seeded with `seed_practice --patients 4`. No laboratory was
  set up.
- Data, made in `manage.py shell` with `collect_sample` and `place_order`:
  - Lien Willems (patient 1, sample 1): a sample with nothing ordered.
  - Lotte Jacobs (2, sample 2): a CBC (suspected anaemia), sent, with no lab
    report.
  - Luc De Smet (3, sample 3): a CBC, sent, with a `LabReport`
    (`results={}`, `ferritin_suggested=True`).
  - Sofie De Smet (4, sample 4): a CBC, sent, with a `LabReport`
    (`results={}`, `ferritin_suggested=False`).
- Logged in as `doctor`. Widths were set with
  `Emulation.setDeviceMetricsOverride`. Tab and Enter were sent with
  `Input.dispatchKeyEvent`.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Refused ferritin page: "Back to <name>" under the heading, above the alert; Enter opens the patient's page | Pass | Tried on three samples: no CBC (sample 1), a CBC awaiting its report (sample 2), and a report with no suggestion (sample 4). Each page shows, in order: the heading, one `<a role="button">` "Back to <name>" inside `div.action-row`, the line "On sample …", then the error alert. At 1400 the heading ends at y=227, the button spans 247–309, and the alert starts at 379. `main` has no `<form>` and no input. The button is its only link and its only button (`01`, `02`, `03`). Tab to the button, then Enter, opens `/practice/patients/<pk>/` with that patient's name as the heading, for all three. |
| 2 | Refused already-ordered page: same | Pass | The CBC page on sample 2 shows "Back to Lotte Jacobs" in the same place, above "This sample already has this test." Enter opens `/practice/patients/2/` (`04`). |
| 3 | Normal CBC order page and ferritin confirmation beside a suggestion: no Back action, form unchanged | Pass | CBC on sample 1 has no Back link and no alert. It shows one form with the six clinical-indication radios and Place order, as before (`05`). Ferritin on Luc's sample 3 has no Back link and no alert. It shows one form with only Place order (`06`). Neither page has a link inside `main`. |
| 4 | Tab order on a refused page: Skip, Patients, Orders, Log out, Back to <name>; visible focus | Pass | On all four refused pages Tab goes: Skip to content, Patients, Orders, Log out, Back to <name>, then the document, then Skip again. The focused button gets a solid 2px dark outline around the green fill (`*-focus-back`). The alert is not focusable. On the allowed pages the order is unchanged: Skip, Patients, Orders, Log out, the radio group (CBC only), then Place order. |
| 5 | 375px and 1400px: button and alert lay out cleanly | Pass | At 1400 the button is 223–237px wide and 62px high, left-aligned with the heading, and the alert is 1200px wide. At 375 the button is 184–196px wide and 50px high. Each label stays on one line. The alert is 343px wide: the ferritin message wraps to two lines (82px) and the already-ordered message stays on one line (58px). `main`'s `scrollWidth` equals its `clientWidth` at both widths. At 375 the page `scrollWidth` is 385, which comes from the header (known, separate). |

Screenshots: `01-ferritin-no-cbc-{1400,375}`, `02-ferritin-cbc-awaiting-{1400,375}`,
`03-ferritin-not-suggested-{1400,375}`, `04-cbc-already-{1400,375}`,
`0{1,2,3,4}-*-focus-back` (1400, Back focused before Enter),
`05-cbc-fresh-{1400,375}`, `06-ferritin-suggested-{1400,375}`.

The database held three orders before the run and three after, so no page
created an order. The server log has no 5xx response. The only 4xx responses
are the browser's own `/favicon.ico` request and one probe of a wrong login
URL sent by the agent with curl.

## Observations

1. **The Back action is a filled, primary-styled button.** On a refused page
   it is the only control in `main`, so it is the obvious next step and the
   emphasis reads as intended. If refusal pages ever get a second action,
   compare the two. Not a defect.
2. **The sample line sits between the button and the alert.** The kit puts
   the action row directly under the heading, so "On sample …" comes after
   the button. That is the same order as other pages that have header
   actions. Not a defect.
3. **Pre-existing kit pattern: Space does not activate the Back link.** The
   kit's `index_header.html` renders every header action as
   `<a role="button">`, which Pico styles as a button. A screen reader
   announces it as a button, but Space does nothing (tried: the page stayed on
   the order URL), and only Enter follows the link. This holds for every
   header action in the app, not only this one. One fix would be to drop
   `role="button"` and give the kit link a button-like class in `static/css/`.
   It belongs in the kit, not in this branch.
4. **Pre-existing: the header overflows at 375px.** "Log out" wraps and the
   page is 385px wide. Earlier checks recorded the same.

## Defects

None found on this branch.

## Not checked

- A screen reader announcing the alert or the `role="button"` link. Only the
  markup was checked.
- Reaching a refused page from a stale tab after another tab placed the
  order. The tests cover that path.
- Dark mode, other browsers, headed Chrome, the mouse, and 320px width.
