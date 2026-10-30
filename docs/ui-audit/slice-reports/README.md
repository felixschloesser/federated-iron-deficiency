# Browser check: slice-reports

A browser-check agent ran this check on 2026-10-30 against commit ddaad59. It
used the full multi-party demo that was already running from the slice-reports
worktree: the hospitals UZ Leuven (8001), Heilig Hart Leuven (8002) and AZ Diest
(8003), and the practices De Akker (8011), De Berk (8012) and De Ceder (8013).
The browser was Chrome with a 1280px viewport. Cookies on one host are shared
across ports, so the hospitals were opened as `127.0.0.1` and the practices as
`localhost`.

The Chrome window could not be resized (`resize_window` left `innerWidth` at
1280). The 606px and 1400px checks therefore loaded each page's HTML into a
same-origin `<iframe srcdoc>` of that width, with a `<base>` pointing at the
app. Inside the frame, `innerWidth` was 606 or 1400 and the app's CSS applied.

Before the check, no hospital had a deployed model. As director-1, final model
8964046695433038449 was deployed at UZ Leuven and at AZ Diest. Heilig Hart
Leuven was left without one for item B.

Orders were placed as doctor-a. The first order and the ferritin order were
placed by real clicks; the rest went through `fetch` POSTs of the same forms.
Receiving and analysing were done as lab-1: the first sample at each hospital
by a real click, the rest by POSTing the same forms. Every order used the
indication "Non-specific complaint".

| Hospital | Sample | Practice patient | Sex, age | Screening result | Run message |
|----------|--------|------------------|----------|------------------|-------------|
| UZ Leuven | 139881 | De Akker Test Patient 3 | F 19 | Ferritin not suggested | "Sample 139881: CBC analysed." |
| UZ Leuven | 139264 | De Akker Test Patient 5 | F 34 | Ferritin not suggested | same, success |
| UZ Leuven | 136426 | De Akker Test Patient 7 | F 20 | Ferritin not suggested | same, success |
| UZ Leuven | 137989 | De Akker Test Patient 9 | F 43 | Ferritin not suggested | same, success |
| UZ Leuven | 135318 | De Akker Test Patient 1 (already had a ferritin order) | F 28 | Ferritin suggested | same, success |
| AZ Diest | 140478 | De Ceder Test Patient 1 | F 43 | Ferritin suggested | success |
| AZ Diest | 131615, 134235, 132411, 134982 | De Ceder Test Patients 3, 5, 7, 9 | F 35/44/45/36 | Ferritin not suggested | success |
| AZ Diest | 140478 (ferritin) | De Ceder Test Patient 1 | | — | "Sample 140478: ferritin analysed." |
| Heilig Hart | 137814 | De Berk Test Patient 5 | F 38 | Not screened: no model deployed | warning (item B) |
| Heilig Hart | 137297 | De Berk Test Patient 11 | M 12 | Not screened: registered sex not female | "Sample 137297: CBC analysed.", success |

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| A | End to end, ferritin suggested | Pass | On the patient page, each released CBC showed "CBC lab report", "Released <date>" and 13 rows with names and units (e.g. "Hemoglobin 11.7 g/dL"). There were no reference ranges or flags. "Ferritin suggested." appeared in bold for exactly the two samples the hospitals listed as "Ferritin suggested": 135318 and 140478. None of the other eight patient pages contains "suggest" or "screen". De Ceder Patient 1 had no ferritin order, and an "Order ferritin" link showed under the comment. De Akker Patient 1 already had a ferritin order, and the comment showed with no button, as specified. Order ferritin opened `/practice/patients/1/orders/new/ferritin/` ("Order ferritin for Test Patient 1"). Place order returned to the patient page with "Order placed.", and both Order ferritin controls were gone. The Lab report column of the patient's orders table and of the Orders index read "Released <date>" or "—". Check for reports said "5 new lab reports." / "1 new lab report." / "0 new lab reports.". (`01`–`06`, `13`, `14`) |
| B | Warning for a model fault | Pass, see defect 1 | At Heilig Hart, 137814 gave `<article role="status" data-level="warning">` with the text "Sample 137814: CBC analysed and released not screened: no model deployed. Tell the laboratory director." The male sample 137297 gave the normal success message "Sample 137297: CBC analysed.". The warning has the warning styling, but its colour is barely visible (defect 1). (`16`–`18`) |
| C | Ferritin through to the patient page | Pass | De Ceder Patient 1 had a "ferritin lab report" with "Ferritin 11.4 ng/mL". The order rows read "Released 30 Oct 2026, 14:22". "Not available in the demo data." was not seen, because no ferritin sample without a value was found. (`15`) |
| D | Widths | Pass | Patient page with a CBC report at 606px: `scrollWidth` 606 = `clientWidth` 606, and both `.overflow-auto` boxes are 510/510, so nothing scrolls sideways. "Million cells/µL" and "Mean cell hemoglobin concentration" wrap to two lines (`08`–`10`). At 1400px: 1400/1400, boxes 1200/1200 (`12`). Orders index at 606px: 606/606, box 510/510. Cells wrap to three or four lines, e.g. "Released / 30 Oct / 2026, / 14:20" (`11`). |
| E | Keyboard | Pass | Tab order from the top: Skip to content, Patients, Orders, Log out, Order ferritin (header), Order ferritin (under the comment), then back to Skip to content. The focus ring is visible (`07`). Enter on the second Order ferritin opened the ferritin order page (`13`). |
| F | Wording | See observations | |

## Defects

1. **The warning colour is barely visible** (Samples page, all widths).
   `article[role="status"][data-level="warning"]` uses
   `--pico-mark-background-color`, which is rgb(253, 231, 192) on white. The
   left bar and border are much fainter than the dark green success bar
   (rgb(29, 106, 84)). The message meant to stand out therefore looks weaker
   than an ordinary success (`16` next to `17`). Its contrast is well under the
   3:1 needed for non-text indicators. Recommendation: use a darker amber for
   the border.

## Observations

1. **"Beside" is below.** At every width, the second Order ferritin sits under
   "Ferritin suggested." as a full button, not on the same line (`06`, `09`).
   This is fine visually. It is noted because the brief says "beside".
2. **Two identical "Order ferritin" controls.** When ferritin is suggested,
   the header and the report each show "Order ferritin", both with the same
   target. A screen-reader user tabbing through hears the same link twice
   with no context. This could be acceptable, but the second control could
   name its reason (e.g. "Order ferritin (suggested)").
3. **Warning wording.** "CBC analysed and released not screened: no model
   deployed" needs a comma: "analysed and released, not screened: no model
   deployed." It reads as if "released not screened" were one status. The
   message is `role="status"` (polite), the same as success; `role="alert"`
   was not considered.
4. **"0 new lab reports."** reads mechanically. "No new lab reports." would
   read better. "1 new lab report." is correctly singular.
5. **Lower-case "ferritin"** starts the heading "ferritin lab report",
   next to "CBC lab report". The `Test.FERRITIN` label
   predates this branch, but a lower-case heading is new here.
6. **Report layout.** The report heading follows the orders table with no
   gap (`05`). A CBC report and a ferritin report are separate sections below
   the table and do not point back to their order row. With several orders,
   the reader matches them by date.
7. Results are shown with one decimal even where it adds nothing ("280.0",
   "7.0"). Units come from NHANES ("1000 cells/µL"). A Belgian GP may expect SI units
   (10^9/L, g/L). That is a demo-data choice, not a
   defect.
8. Models page (predates the branch): "found 8 of 10 deficient, 1 unnecessary
   suggestions" should use the singular for 1.
9. After a CBC is ordered, the header no longer offers "Order CBC" even once
   the report is released (De Akker Patient 3). This behaviour predates the
   branch and was not looked into.

## Not checked

- "Not available in the demo data." for a ferritin value: no such sample was
  hit.
- The "deployed model file changed" warning path: no files were touched.
- The 60 s automatic fetch: De Akker's reports had arrived before Check for
  reports was clicked, so it appears to work, but it was not timed.
- A real window resize. The widths were checked in a fixed-width iframe (see
  above).
- Other browsers, screen readers, dark mode.

## Screenshots

- `01-uz-leuven-analysed.jpg`: UZ Leuven Analysed table, 135318 Ferritin suggested
- `02-patient1-suggested-has-ferritin.jpg`: De Akker Patient 1, comment without button (ferritin already ordered)
- `03-az-diest-analysed.jpg`: AZ Diest Analysed table, 140478 Ferritin suggested
- `04-de-ceder-check-for-reports.jpg`: "5 new lab reports." and the Lab report column
- `05-patient-suggested-top-1280.jpg`: De Ceder Patient 1, header with Order ferritin
- `06-patient-suggested-report-1280.jpg`: CBC report with comment and Order ferritin
- `07-order-ferritin-focused.jpg`: Order ferritin under the comment, keyboard focus
- `08-patient-606-top.jpg`, `09-patient-606-report.jpg`, `10-patient-606-report-end.jpg`: patient page at 606px
- `11-orders-606.jpg`: Orders index at 606px
- `12-patient-1400-report.jpg`: CBC report at 1400px
- `13-order-ferritin-page.jpg`: ferritin order page reached by Enter
- `14-ferritin-placed-buttons-gone.jpg`: after placing it, no Order ferritin
- `15-ferritin-report.jpg`: ferritin lab report, 11.4 ng/mL
- `16-warning-no-model.jpg`: warning message at Heilig Hart, no model deployed
- `17-success-male.jpg`: success message for the male sample
- `18-heilig-hart-analysed.jpg`: Heilig Hart Analysed table

## Re-check (ac95294)

This re-check ran after the demo was restarted from the same worktree. The
data and ports were unchanged, and app.css was fetched fresh.

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Warning border | Pass | At Heilig Hart, with still no model, sample 134306 was a CBC for "Non-specific complaint" (De Berk Test Patient 1, F 19). The stored sample went straight to To analyse. Run analyser (real click) gave "Sample 134306: CBC analysed and released, not screened: no model deployed. Tell the laboratory director." with `data-level="warning"` and a computed `border-left-color` of rgb(184, 110, 0), which is clearly amber (`19`). |
| 2 | "No new lab reports." | Pass | De Berk Orders: the first Check for reports said "1 new lab report." and the second "No new lab reports.". |
| 3 | "Ferritin lab report" and no trailing ".0" | **Fail** | The heading now reads "Ferritin lab report" (pass). But every value with decimals now shows three of them: "7.100", "4.160", "12.700", "37.100", "13.200", and the ferritin value "10.700 ng/mL", which was "10.7" before. Only whole numbers lost the ".0" ("363"). Cause: `templates/practice/patient.html` uses `{{ value.value\|floatformat:"-3" }}`, and `-3` pads to three decimals unless the value is a whole number. `floatformat:"-1"` would round "4.16" to "4.2", so the fix belongs in the view, for example `f"{value:g}"` or `Decimal(str(value)).normalize()`, with a test on "7.0" → "7" and "4.16" → "4.16" (`20`). |
| 4 | "1 unnecessary suggestion" | Pass | AZ Diest Models: both final models read "found 8 of 10 deficient, 1 unnecessary suggestion". |

- `19-recheck-warning-amber.jpg`: amber warning border with the comma wording
- `20-recheck-values-three-decimals.jpg`: CBC values padded to three decimals

## Re-check (99dbe9f)

This re-check covered only the lab report values, after the demo was
restarted from the same worktree.

| Page | Result | Values seen |
|------|--------|-------------|
| De Berk Test Patient 1 (CBC 134306 and ferritin) | Pass | 7.1, 4.16, 12.7, 37.1, 89.2, 34.1, 30.4, 13.2, 363, 7.2, 1.7, 4.7, 0.4; Ferritin 10.7 ng/mL |
| De Ceder Test Patient 1 (CBC 140478 and ferritin) | Pass | WBC 7 (was "7.0"), platelets 280 (was "280.0"), 4.51, 11.7; Ferritin 11.4 ng/mL |

No cell on either page matches a trailing zero after a decimal point
(`^\d+\.\d*0$`). Headings read "CBC lab report" and "Ferritin lab report".

- `21-recheck-values-plain.jpg`: De Berk CBC values without padding

## Follow-up (branch author)

- Fixed after the first check: warning border (amber #b86e00, 3.99:1 on white, 4.5:1 dark), the comma in the warning, "No new lab reports.", "Ferritin lab report", "1 unnecessary suggestion"; after the second, values shown as measured (`ResultValue.shown`, with a test). Both re-checked above.
- Not changed: two "Order ferritin" links on a patient with a suggestion (header and beside the comment; the header one is ordinary ordering, the other answers the comment); no gap or back-link between the orders table and the reports; the warning keeps `role="status"`; wrapping on the Orders index at 606px.
