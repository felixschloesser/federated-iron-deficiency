# Browser check: slice-deploy

Checked by a browser-check agent on 2026-10-30, against commit db8d251 running
as the demo deployment via `tools/demo.py` (`DJANGO_DEBUG=1`). The practice was
Huisartsenpraktijk De Berk (127.0.0.1:8012) and the hospital was Heilig Hart
Leuven (localhost:8002). Using a different host for each party kept their
session cookies apart. The browser was Chrome with a 1280px viewport.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Title and header name the party | Pass | Titles seen: "Patients · Huisartsenpraktijk De Berk", "Orders · …", "Order CBC for Test Patient 3 · …", "Samples · Heilig Hart Leuven", "Models · Heilig Hart Leuven", "Log in · …". The header shows the party name. "Iron-deficiency screening" never appeared on these ports. (`01`, `05`) |
| 2 | No foreign pages | Pass, with a caveat | Practice `/lab/samples/` and hospital `/practice/patients/` both return 404. The URLconf lists only the party's own apps. Because the demo runs with `DJANGO_DEBUG=1`, Django's debug 404 page appears, not the kit's `templates/404.html`, so the kit 404 page could not be seen. (`02`) |
| 3 | Order a CBC | Pass | Test Patient 3, CBC, "Non-specific complaint". The page showed "Order placed." in a success box and no warning. Order CBC disappears from the patient's actions afterwards. (`03`) |
| 4 | Orders page: order and Check for reports | Partial, see defect 1 | The order is listed and the button sits between the heading and the table. The button is full-width (1200px), unlike every other page-level action. Narrow width was not checked: `resize_window` did not change the viewport, which stayed at 1280px. (`04`) |
| 5 | Hospital receives and analyses | Pass, see defect 2 | Under "Samples to receive": sample ID 141795, CBC, "Dr. Demo A", and no patient name. Receive gave "Sample 141795 received.". Run analyser gave "141795 cbc analysed.". (`05`, `06`) |
| 6 | Check for reports | Pass | The first press gave "1 new lab report." (the background check had not fetched it yet), and the second gave "0 new lab reports.". (`07`) |
| 7 | Warning message style | Skipped | A warning needs a stopped hospital, which was not allowed here. |
| 8 | Director Models page | Pass | Shows "No final model is deployed." in a red error-bordered box, deliberate since 0e8ee03. "Final models" lists two runs (8964046695433038449, 2918031829985066058), each with Deploy. "Deployment history" shows "Nothing deployed yet." The Stored column wraps the date onto three lines. (`11`) |
| 9 | Keyboard on Orders | Pass | Tab order: Skip to content, Patients, Orders, Log out, Check for reports, Test Patient 3. The skip link is visible on focus but overlaps the party name (`08`). The focus ring on Check for reports is visible but faint, a light-blue outline on dark blue (`09`). |
| 10 | Wrong role | Pass | lab-1 opening `/deployment/models/` lands on Samples with "That page is for laboratory directors." in an error box. (`10`) |

## Defects

1. **Check for reports is a full-width button.** Repro: log in as doctor-a at
   127.0.0.1:8012 and open Orders. The button spans the whole content column
   (computed width 1200px at a 1280px viewport). Page-level actions elsewhere
   (Order CBC and Order ferritin on a patient) are inline buttons. Cause:
   `templates/kit/action_button.html` wraps the button in a `<form>`, and Pico
   makes form buttons `width: 100%`. In table rows (Receive, Run analyser,
   Deploy) the column limits the width. On a page it does not. The kit needs
   an inline variant for page-level POST actions, for example placed in the
   index header's action row.
2. **"141795 cbc analysed."** (pre-existing, from `LabOrder.__str__` in
   3e4b56f, not introduced by this branch). Repro: as lab-1 at :8002, receive
   a sample and press Run analyser. The message shows the raw choice value
   `cbc` instead of "CBC" and drops "Sample". The Receive message reads
   "Sample 141795 received.", so for consistency this should read something
   like "Sample 141795: CBC analysed.". The text comes from
   `messages.success(request, f"{lab_order} analysed.")` in
   `web/lab/views.py:53`.

## Not checked

- Narrow (~375px) and wide (~1400px) widths: the window could not be resized,
  so only 1280px was seen.
- The kit 404 page, because the demo runs with DEBUG on.
- The warning message style (item 7).
- Whether the fetched report shows on the practice's patient page (not on the
  checklist).
- Other practices and hospitals beyond De Berk and Heilig Hart Leuven, screen
  readers, and other browsers.

## Screenshots

`01`–`11` `.jpg` in this folder, captured at half scale except `04`.

## Re-check after fixes (24c03d4)

A browser-check agent re-checked this on 2026-10-30 against the same demo
ports. This time the Chrome viewport was 606px wide, not 1280px, so the
content column was 510px.

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Check for reports is inline | Pass, defect 1 fixed | Button width 169px in a 510px `div.action-row`, `display: inline-block`. The DOM is `div.action-row > form.inline-form > button`, with no `<p>` ancestor. The row sits directly under the `<hgroup>` holding "Orders" (h1 bottom 193px, row top 210px), and the table starts 17px below the row. (`12`) |
| 2 | Patient action row | Pass | On Test Patient 1, "Order CBC" (118px) and "Order ferritin" (134px) sit in one `div.action-row` at the same top (210px), with about 4px between them. "Female, aged 19" follows 17px below the row (margin-bottom 17px), the same gap as on Orders. After the ferritin order only "Order CBC" is left. (`13`) |
| 3 | Analysed message | Pass for ferritin, defect 2 fixed | Ordered ferritin for Test Patient 1. At the hospital the sample showed as 134306. Receive gave "Sample 134306 received." and Run analyser gave "Sample 134306: ferritin analysed.". The CBC wording was not exercised in the browser. |
| 4 | Check for reports at the practice | Pass, 0 | It gave "0 new lab reports.". About 20–30 s passed between Run analyser and the press, which was enough for the 60 s background check (`REPORT_CHECK_SECONDS` in `tools/demo.py`) to fetch the report first. The UI could not confirm this, because no practice page shows a received report. |

### New observations

- **The hospital "To analyse" table overflows at a 606px viewport.** With one
  row, the table measured 735px wide in a 510px `main.container`
  (`overflow-x: visible`), and the document `scrollWidth` was 783px, so the
  page scrolls horizontally and the "General practitioner" header was cut off
  at the right edge. It has six columns plus the Run analyser button. The
  1280px check could not see this. This is a defect for narrow widths, and the
  kit table probably needs a horizontal-scroll wrapper.
- The ferritin order form has no fields, just "Place order". The Orders table
  shows "—" under Clinical indication for ferritin. This looks deliberate
  (screening only), but it should be confirmed.
- No practice page (Orders or patient) shows whether a report has arrived, so
  a doctor cannot tell what "N new lab reports" refers to. This was already
  listed under Not checked above.
- The demo still runs with DEBUG on (an unknown URL shows the Django debug
  404).

Screenshots `12`, `13` (0.6 scale). Not checked: keyboard and focus again,
a narrow width for the practice pages beyond 606px, and the CBC analysed
message.

## Follow-up (after the re-check)

- The table overflow at 606px: every table is now wrapped in Pico's
  `overflow-auto`, so a wide table scrolls inside the page instead of the
  page scrolling sideways. Not re-checked in a browser.
- The ferritin order without fields and "—" as its indication are
  deliberate: ferritin takes no clinical indication (R1).
- No page shows a fetched lab report yet: that is the reports slice.
- The demo runs with `DJANGO_DEBUG=1` (demo accounts share a password), so
  unknown URLs show Django's debug 404; the kit's 404 is covered by
  `test_missing_page_comes_from_the_kit`.
