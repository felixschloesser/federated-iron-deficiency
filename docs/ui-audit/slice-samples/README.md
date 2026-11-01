# Browser check: slice-samples

A browser-check agent ran this check on 2026-11-01. It started at commit 102e380.
During the run the branch gained cb26e34, which only changes citations. The
browser was Chrome with a 1440×813 viewport.

## Setup

- Development checkout: one database (`DATABASE_NAME=slice-samples-ui`,
  `DJANGO_DEBUG=1`), every app, no messaging between parties.
- `runserver 127.0.0.1:8061`, opened as `http://samples.localhost:8061`
  (`DJANGO_ALLOWED_HOSTS=samples.localhost,127.0.0.1,localhost`). Cookies are
  shared across ports on one host name, and the user's demo on 8001–8013 uses
  `127.0.0.1` and `localhost`. A separate host name kept this check from
  logging the demo out.
- Accounts: `doctor-a` (GP) and `lab-1` (laboratory staff). The checker logged
  out between roles.
- Relay between parties by hand with the scratchpad helper `ui_relay.py`:
  `deliver()` after GP orders, and `release(suggest=True)` after the analyser.
  The helper marks CBC lab reports "ferritin suggested", because no model is
  deployed.
- Patient: Test Patient 5 (female, 34, NHANES number 139264). Every CBC used the
  indication "Non-specific complaint".
- `resize_window` did not change the viewport (`innerWidth` stayed 1440). The
  375px and 1400px checks follow the slice-reports method. Each page's HTML was
  fetched and loaded into an `<iframe srcdoc>` of that width, with a `<base>`
  pointing at the app. Framing the URL directly is blocked by X-Frame-Options.
  Inside the frame, `innerWidth` was 375 or 1400 and the app's CSS applied.
- Screenshots are JPEG for full-viewport captures and PNG for zoomed 375px
  regions. The capture tool gives no other format.

## Checklist

| # | Check | Result | Screenshot |
|---|-------|--------|------------|
| A1 | Patient page offers both "Order CBC" and "Order ferritin" | Pass | 01-patient-both-orders-offered.jpg |
| A2 | Order CBC page says "Collects a new sample." | Pass | 02-order-cbc-collects-new-sample.jpg |
| A3 | After placing, the Orders table shows sample ID 139264-1 | Pass | 03-first-cbc-placed-sample-id.jpg |
| A4 | Ferritin from the patient page also says "Collects a new sample." | Pass | 04-order-ferritin-new-sample.jpg |
| A5 | Second CBC gets 139264-2 and the ferritin gets 139264-3, all different | Pass | 05-three-orders-three-samples.jpg |
| A6 | (extra) Practice "Orders" index shows the sample | **Fail**, see D1 | 06-practice-orders-no-sample-id.jpg |
| B1 | lab-1 login lands on "To analyse" (/lab/lab-orders/); header links "To analyse" and "Analysed" | Pass | 07-lab-login-to-analyse.jpg |
| B2 | Rows show sample IDs and no patient names (checked in page text) | Pass | 07-lab-login-to-analyse.jpg |
| B3 | Run analyser on CBC 139264-1 by keyboard (Enter) gives the expected warning "…not screened: no model deployed. Tell the laboratory director." | Pass | 08-keyboard-focus-run-analyser.jpg, 09-analyser-warning-no-model.jpg |
| B4 | Run analyser on CBC 139264-2 (same warning) and on ferritin 139264-3 ("Sample 139264-3: ferritin analysed."); To analyse then shows "Nothing to analyse." | Pass | 10-ferritin-analysed-nothing-left.jpg |
| B5 | Analysed lists all three with screening result ("Not screened: no model deployed" for CBCs, "—" for ferritin) | Pass | 11-lab-analysed.jpg |
| C1 | Patient page: headings "Ferritin lab report, sample 139264-3" and "CBC lab report, sample 139264-2/-1" | Pass | 13-patient-reports-released.jpg |
| C2 | Each CBC report shows "Ferritin suggested." with an "Order ferritin" button | Pass | 14-cbc-report-ferritin-suggested.jpg |
| C3 | That button opens a page that says "On sample 139264-2, which the laboratory holds." | Pass | 15-order-ferritin-on-held-sample.jpg |
| C4 | After placing, a new ferritin row carries sample ID 139264-2 | Pass | 16-ferritin-order-same-sample-row.jpg |
| C5 | Report 139264-2 no longer offers Order ferritin; 139264-1 still does | Pass | 17-cbc-report-button-gone.jpg, 21-patient-keyboard-focus-report-button.jpg |
| D1 | After deliver(), To analyse shows ferritin on existing sample 139264-2 | Pass | 22-lab-ferritin-on-existing-sample.jpg |
| E1 | Keyboard, lab: Tab order is Skip to content → To analyse → Analysed → Log out → Run analyser (row 1…). Focus ring visible. | Pass | 08-keyboard-focus-run-analyser.jpg |
| E2 | Keyboard, patient page: Skip to content → Patients → Orders → Log out → Order CBC → Order ferritin → Order ferritin (report 139264-1). Focus ring visible, order logical. | Pass | 21-patient-keyboard-focus-report-button.jpg |
| E3 | 375px: no horizontal page scroll on Analysed, To analyse, the patient page or the order-on-sample page (`scrollWidth` = 375). Tables scroll inside their own container. | Pass | 12, 18, 20, 23 |
| E4 | 375px: sample IDs stay on one line in table cells | **Fail**, see D2 | 12-analysed-375-sample-id-wraps.png, 18-patient-375-sample-id-wraps.png |
| E5 | 375px: report heading "CBC lab report, sample 139264-2" wraps between words, not inside the ID | Pass | 19-patient-375-report-heading.png |
| E6 | 1400px: no page scroll; tables fill the 1200px container (patient page, Analysed) | Pass | (measured: `scrollWidth` 1400, tables 1200/1200) |
| E7 | Heading hierarchy: one H1 per page. Patient page: H1 patient, then H2 "Orders" and one H2 per lab report. Lab pages have only an H1. | Pass | 13-patient-reports-released.jpg |
| E8 | Wording "Collects a new sample." / "On sample …, which the laboratory holds." | Pass. The two pages read differently and the held-sample line names the sample. See note N2. | 02, 15 |
| E9 | 375px: Run analyser reachable on To analyse | Minor, see D3 | 23-to-analyse-375-button-offscreen.png |

## Defects

**D1. Medium: the practice "Orders" index has no Sample ID column.**
Page `/practice/orders/` (`templates/practice/orders.html`). The patient page
now lists a Sample ID for every order, but the practice-wide index still shows
only Ordered / Patient / Test / Clinical indication / Lab report. Repeat CBCs
are now allowed, so two CBCs for one patient on the same day show as identical
rows (screenshot 06). The GP cannot tell from the index which order a lab
report belongs to. The index also leaves out the one identifier the laboratory
uses.

**D2. Low to medium: sample IDs break at the hyphen in narrow table cells.**
Pages `/lab/lab-orders/`, `/lab/lab-orders/analysed/` and
`/practice/patients/<id>/`, in the Sample ID cells (orders table and lab
tables). At 375px, "139264-2" renders as "139264-" on one line and "2" on the
next (screenshots 12, 18, 23). The browser breaks after the hyphen. An ID
split over two lines is easy to misread or mis-copy, and it is the identifier
that matches a tube to a lab report. Old bare-number IDs had no hyphen, so
this branch introduces the problem. Wide screens are unaffected.

**D3. Low: at 375px the Run analyser button is outside the visible part of the To analyse table.**
Page `/lab/lab-orders/`. The table is 704px wide inside a 343px scroll
container, so the row's only action sits off-screen to the right
(screenshot 23). The user has to scroll the table sideways to find it. Lab
staff probably work on desktop screens, so this is low severity. The same
layout existed before this branch.

## Notes (not defects; for the branch owner to decide)

- **N1. Duplicate button names.** The patient page can show three links named
  "Order ferritin". One sits at the top and orders on a new sample. The others
  sit in each CBC report and order on that report's sample. They are visually
  separated by section, but a screen-reader links list or voice control
  ("click Order ferritin") cannot tell them apart. An accessible name such as
  "Order ferritin on sample 139264-1" (visible or `aria-label`) would fix it.
  Likewise the To analyse page has one "Run analyser" per row with no sample in
  its name.
- **N2. Wording.** "Collects a new sample." and "On sample X, which the
  laboratory holds." are clear in context. The first is a fragment with no
  subject; "This order collects a new sample." would read better on its own.
  Wording should follow the glossary/domain experts.
- **N3. After ordering ferritin from a report**, report 139264-2 still says
  "Ferritin suggested." with no button and no note that ferritin was ordered on
  that sample (screenshot 17). The new ferritin row in the Orders table is the
  only trace.
- **N4. The lab's To analyse row does not mark a stored sample.** The ferritin
  on stored sample 139264-2 looks the same as a newly arrived sample
  (screenshot 22). Only the page intro mentions "a later test on a stored
  sample". If staff must fetch stored samples from storage, a cue in the row may
  help. This is a question for the domain experts.
- **N5. Success messages differ.** The CBC message says "analysed and
  released"; the ferritin message says only "analysed". Neither "Order placed."
  message names the new sample ID.
- **N6. Placement.** On the patient page the order actions sit between the H1
  and the patient facts ("Female, aged 34"). This placement existed before this
  branch and was not changed.

## Not checked

- Old demo samples with bare NHANES numbers. This database had none in the
  practice or lab lists, so their display next to `<n>-<k>` IDs was not seen.
- A real deployed model. Screening results other than "Not screened: no model
  deployed" were not exercised.
- The director pages. They were not changed by this branch.
- Real window resizing. Narrow and wide widths were simulated with `srcdoc`
  iframes, so browser zoom, touch, and the real mobile viewport meta behaviour
  were not exercised.
- Screen-reader output itself. Only accessible names and DOM order were
  inspected.
- Multi-party messaging. Relay was done by the helper script, not by the
  real exchange between practice and hospital.
