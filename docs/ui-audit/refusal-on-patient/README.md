# Browser check: refusal-on-patient

A browser-check agent ran this check on 2026-11-05 against commit a14f106. The
browser was headless Chrome 156, driven over the DevTools protocol by a small
script. The Claude-in-Chrome extension was not used.

## Setup

- Server: `127.0.0.1:8627`, run with `uv run` from the worktree, with
  `PRACTICE_DIR=<worktree>/.ui-audit-rop/practice PARTY_COLOUR=green
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
  `Input.dispatchKeyEvent`. Two tabs of one browser were used for the stale form.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Typed ferritin URL without a suggestion: the patient page, with the reason as an error message; nothing ordered | Pass | A GET of `/orders/new/ferritin/` was tried on samples 1 (no CBC), 2 (CBC awaiting its report) and 4 (report without a suggestion). Each answers 302 to that patient's page, which shows one `<article data-level="error">` at the top of `main`, above the patient's name: "Ferritin is ordered only beside a lab report suggesting it." (`01`, `02`, `03`). |
| 2 | Typed CBC URL on a sample that has a CBC: the patient page with "This sample already has this test." | Pass | Sample 2: 302 to `/practice/patients/2/`, with the message in the same place (`04`). |
| 3 | Stale form: ferritin page opened in tab A, placed in tab B, then A submitted | Pass | Both tabs show "Order ferritin for Luc De Smet" and Place order (`07`). Enter on Place order in B returns to `/practice/patients/3/` with "Ferritin ordered on sample 134314-1." (`08`). Enter on Place order in A then returns to the same page with "This sample already has this test." and a single Ferritin article (`09`). Afterwards the database holds four orders: CBCs on samples 2, 3 and 4 and one ferritin on sample 3. So no refusal created an order. |
| 4 | The message is announced (`role="alert"`) and readable, gone on the next load; focus and Tab order on arrival | **Fail (announcement)** | Readable: body-colour text on pale red with a dark red bar and border, at both widths. It is gone on the next load of the patient page (`05`). Focus on arrival is on the document. Tab goes Skip to content, Patients, Orders, Log out, Collect sample, the sample's summary, then the order links and buttons. That order is sensible. **However, the message has `role="status"`, not `role="alert"`.** `templates/kit/base.html` passes `role="status"` for every flash message, errors included, so the refusal renders as `<article role="status" data-level="error">`. The old refusal page used `role="alert"`. A polite live region that is already in the page when it loads is usually not read out, so a screen-reader user may land on the patient page without hearing why. The kit's own comment in `kit/alert.html` says to use `alert` "for an error the reader must act on now". |
| 5 | Normal cases unchanged | Pass | CBC on the fresh sample 1 shows "Order CBC for Lien Willems", six indication radios and Place order (`06`). On Luc's page, "Order ferritin" links to `/samples/3/orders/new/ferritin/`, which shows its confirmation with no message and one Place order button (`07`). Place order places the ferritin (`08`). The server log has no 4xx or 5xx response apart from the browser's own `/favicon.ico` 404. |
| 6 | 375px and 1400px: the message lays out cleanly | Pass | At 1400 the message is 1200px wide, on one line and 72px high. At 375 it is 343px wide: the ferritin message wraps to two lines (82px) and the already-ordered message fits on one line (58px). The padding stays even, nothing is clipped, and the name heading sits just below the message. `main`'s `scrollWidth` equals its `clientWidth` at both widths. At 375 the page is 385px wide because of the header, which is known and separate (`*-375`, `10`). |

Screenshots: `01-ferritin-no-cbc-{1400,375}`, `02-ferritin-cbc-awaiting-{1400,375}`,
`03-ferritin-not-suggested-{1400,375}`, `04-cbc-already-{1400,375}`,
`05-reloaded-1400`, `06-cbc-fresh-1400`, `07-ferritin-suggested-tab-a-1400`,
`08-after-ferritin-tab-b-1400`, `09-stale-ferritin-1400`,
`10-ferritin-now-ordered-375`.

## Defects

1. **The refusal is not announced as an alert.** All flash messages render
   with `role="status"` (`templates/kit/base.html`, the `messages` loop), so
   an error message after a redirect is a polite status region that already
   exists when the page loads, and a screen reader may not read it out.
   Recommendation: choose the role from the level in the kit, `alert` for
   `error` and `status` otherwise, as `kit/alert.html` already describes. This
   affects every error flash message, not only this branch's, but this branch
   is what moved the refusal from an alert to a flash message.

## Observations

- Pre-existing: the header overflows at 375px ("Log out" wraps, page 385px).

## Not checked

- A real screen reader. Only the markup was checked, and the defect above
  follows from the markup.
- A refusal with more than one message. None of the reachable cases produce
  two.
- Dark mode, other browsers, headed Chrome, the mouse, and 320px width.
