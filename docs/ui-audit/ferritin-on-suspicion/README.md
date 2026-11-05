# Browser check: ferritin-on-suspicion

A browser-check agent ran this check on 2026-11-05 against commit 549be7e. The
browser was headless Chrome 156, driven over the DevTools protocol by a small
script. The Claude-in-Chrome extension was not connected.

## Setup

- Server: `127.0.0.1:8621`, run with `uv run` from the worktree, with
  `PRACTICE_DIR=<worktree>/.ui-audit-fos/practice PARTY_COLOUR=green
  PRACTICE_NAME="Huisartsenpraktijk De Akker" DJANGO_DEBUG=1`. It was
  migrated, then seeded with `seed_practice --patients 4`. No laboratory was
  set up, because the change does not depend on one.
- Data, made in `manage.py shell` with `collect_sample` and `place_order`:
  - Lien Willems (sample 1): a sample, nothing ordered.
  - Lotte Jacobs (sample 2): a CBC (suspected anaemia), `sent_at` set, no lab
    report.
  - Luc De Smet (sample 3): a CBC, sent, with a `LabReport`
    (`results={}`, `ferritin_suggested=True`).
  - Sofie De Smet (sample 4): a CBC, sent, with a `LabReport`
    (`results={}`, `ferritin_suggested=False`).
- Logged in as `doctor`. Widths were set with
  `Emulation.setDeviceMetricsOverride`. Links and buttons were pressed with
  Enter on the focused element (`Input.dispatchKeyEvent`).

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | New sample, nothing ordered: the row offers only "Order CBC" | Pass | Lien's sample row has one link, "Order CBC", which goes to `/practice/patients/1/samples/1/orders/new/cbc/`. `main` has only Collect sample and Order CBC (`02`). |
| 2 | CBC awaiting its report: no order buttons in the row, no Order ferritin anywhere | Pass | Lotte's sample has no `.action-row` at all, not even an empty one. The only control in `main` is Collect sample. The CBC reads "Awaiting lab report · Ordered …" (`03`). |
| 3 | Suggestion: Order ferritin beside the comment; it opens the ferritin page; confirming orders it and returns; the button is gone | Pass | Order ferritin sits directly under the bold suggestion comment, in its own action row inside the CBC article (`04`). Enter opens `/practice/patients/3/samples/3/orders/new/ferritin/`, "Order ferritin for Luc De Smet", which has one Place order button (`06`). Enter on that button gets a 302 back to `/practice/patients/3/`. The page shows the success alert "Ferritin ordered on sample 134314-1." and a new Ferritin article ("Lab order not sent yet"). Order ferritin is gone, and Collect sample is the only control left (`07`). |
| 4 | Lab report without a suggestion: no Order ferritin | Pass | Sofie's CBC shows "No ferritin suggestion. This does not rule out iron deficiency." There is no action row on the sample, and Collect sample is the only control (`05`, `11-p4-375`). |
| 5 | Direct ferritin URL without a suggestion: the refusal in the error summary; no order created | Pass | GET of the URL renders the order page with no hint, the same as a suggested one. On POST the page re-renders (200, no redirect) with `<article role="alert" data-level="error"><p>Ferritin is ordered only beside a lab report suggesting it.</p></article>`. The alert sits between the sample line and Place order, in error styling, and is easy to read (`09`). This was tried on sample 1, which has no CBC, and on sample 4, which has a CBC report without a suggestion (`10`); both show the same refusal. Landmarks are header, nav, main and footer, and the alert is inside main. After the reload, focus is on the body, as on any full-page load. The database afterwards holds four orders: three CBCs and the one ferritin from item 3, so neither refusal created an order. |
| 6 | Patients page: "Ferritin suggested" shows for case 3 before ordering and disappears after | Pass | Before: "Luc De Smet" followed by `<mark>Ferritin suggested</mark>`, and no other patient has the mark. Sofie, whose report has no suggestion, has none (`01`). After the ferritin order, no patient has the mark (`08`). |
| 7 | 375 and 1400: nothing broken by the fewer buttons | Pass | No sample renders an empty `.action-row`; the row is left out when there are no actions. The space between a sample's last child and the bottom of its `details` is the same whether that child is the action row (Lien) or an article (the other three): 41px at 1400 and 33px at 375. `main`'s `scrollWidth` equals its `clientWidth` at both widths. At 1400 the page `scrollWidth` is 1400. At 375 it is 385, which comes from the header (pre-existing, see below) (`11-*`). |

## Observations

1. **The ferritin page does not warn before you confirm.** When the URL is
   opened directly for a sample without a suggestion, the page looks like the
   allowed case, and the refusal only appears after Place order. Only a typed
   or stale URL reaches this page, so this is acceptable. Showing the refusal
   on GET would be a possible refinement.
2. **The refusal is an alert, not a field error.** The order page has no
   visible field, so the `test` field error shows as the page's only alert. It
   reads well.
3. **Pre-existing: the header overflows at 375px.** `scrollWidth` is 385
   because "Log out" wraps. The previous check recorded the same.

## Defects

None found on this branch.

## Not checked

- A laboratory set up: Check for reports, and the "for <laboratory>" sample
  line.
- A real fetched lab report with values (`results={}` was used, so the page
  shows "Not available in the demo data.").
- A patient with several samples, one of them suggested.
- Tab order on the refusal page beyond the focus after load. Screen reader,
  dark mode, other browsers, headed Chrome and the mouse were not checked.
- 320px width.
