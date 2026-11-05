# Browser check: order-refused-early

A browser-check agent ran this check on 2026-11-05 against commit c364a39. The
browser was headless Chrome 156, driven over the DevTools protocol by a small
script. The Claude-in-Chrome extension was not used.

## Setup

- Server: `127.0.0.1:8623`, run with `uv run` from the worktree, with
  `PRACTICE_DIR=<worktree>/.ui-audit-ore/practice PARTY_COLOUR=green
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
| 1 | Ferritin URL on a sample without a suggestion: the alert at once, no form, no Place order; heading and sample line kept | Pass | A plain GET of `/orders/new/ferritin/` was tried on three samples: one with no CBC (sample 1), one with a CBC awaiting its report (sample 2), and one with a report that has no suggestion (sample 4). Each page shows the heading "Order ferritin for …", the line "On sample …, collected …", and directly below it one `<article role="alert" data-level="error">` that reads "Ferritin is ordered only beside a lab report suggesting it." `main` has no `<form>`, no button and no input (`01`, `02`, `03`). |
| 2 | CBC URL on a sample that has a CBC: the already-ordered alert at once, no button | Pass | Sample 2 shows "This sample already has this test." in the same error alert, with no form and no button (`04`). The same alert appears for sample 1 after its CBC was placed in item 3 (`07`), and for ferritin on sample 3 after the ferritin was placed (`10`). |
| 3 | Normal cases unchanged | Pass | CBC on the fresh sample 1 shows the six clinical-indication radios and Place order, as before (`05`). With an indication chosen, Enter on Place order goes back to `/practice/patients/1/` (`06`). On Luc's patient page, Enter on the focused "Order ferritin" link opens `/practice/patients/3/samples/3/orders/new/ferritin/`. That page has no alert and one Place order button (`08`). Enter on the button goes back to `/practice/patients/3/`, which shows "Ferritin ordered on sample 134314-1." and a new Ferritin article (`09`). Afterwards the database holds five orders: four CBCs and one ferritin, so none of the refusal pages created an order. The server log has no 5xx response and no 4xx apart from the browser's own `/favicon.ico` 404. |
| 4 | The alert is announced and readable; Tab order sensible, nothing focusable that does nothing | Pass | The alert has `role="alert"` and sits inside `main`, between the sample line and the footer. Its text is the theme's body colour on a pale red background, with a dark red left bar and border. It reads clearly at both widths. On every refusal page Tab goes: Skip to content, Patients, Orders, Log out, then back to the body. The alert is not focusable, and the page has no other focusable element. On the allowed pages Tab goes: Skip to content, Patients, Orders, Log out, the indication radio group (CBC only), then Place order. |
| 5 | 375px and 1400px: the alert wraps cleanly | Pass | At 1400 the alert is 1200px wide and on one line (72px high). At 375 it is 343px wide. The ferritin message wraps to two lines (82px) and the already-ordered message stays on one line (58px). The padding stays even and nothing is clipped. `main`'s `scrollWidth` equals its `clientWidth` at both widths. At 375 the page `scrollWidth` is 385, which comes from the header (pre-existing, see below) (`*-375`). |

Screenshots: `01-ferritin-no-cbc-{1400,375}`, `02-ferritin-cbc-awaiting-{1400,375}`,
`03-ferritin-not-suggested-{1400,375}`, `04-cbc-already-{1400,375}`,
`05-cbc-fresh-1400`, `06-after-cbc-1400`, `07-cbc-now-ordered-1400`,
`08-ferritin-suggested-1400`, `09-after-ferritin-1400`,
`10-ferritin-now-ordered-1400`.

## Observations

1. **The refusal page offers no way back to the patient.** Once the form is
   gone, the only controls are the site navigation, so getting back to the
   patient takes Patients and then the patient's name. Only a typed or stale
   URL reaches this page, so this is acceptable. A link back to the patient
   would be a possible refinement, and it would belong in the kit.
2. **Pre-existing: the header overflows at 375px.** "Log out" wraps and the
   page is 385px wide. Earlier checks recorded the same.

## Defects

None found on this branch.

## Not checked

- A screen reader actually announcing the alert. Only the markup was checked.
- A refusal with more than one message. None of the reachable cases produce
  two messages.
- A POST of a stale form, when the page was opened before another tab placed
  the same order. The tests cover this path.
- Dark mode, other browsers, headed Chrome, the mouse, and 320px width.
