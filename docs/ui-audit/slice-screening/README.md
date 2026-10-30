# Browser check: slice-screening

A browser-check agent ran this check on 2026-10-30 against commit 420b78f. The
app ran with `runserver` on 127.0.0.1:8031 from the slice-screening worktree,
using its own database (`slice-screening.sqlite3`, freshly migrated, then
`seed_hospital` and `seed_practice`) with `DJANGO_DEBUG=1`. `FINAL_MODELS_DIR`
pointed at a scratch copy of Heilig Hart Leuven's two final models from the
slice-deploy demo. The browser was Chrome. Its viewport was 1659px, and two
extra tabs were opened at 1400px and 606px.

Dev mode has no messaging, so the eight lab orders were recorded in
`manage.py shell` with `web.lab.services.record_lab_order`, from client
`practice-browser-check` and GP "Dr. Demo A". The sample IDs are seeded
practice patients. The test, indication, sex and age were set per row:

| Sample | Test | Indication | Sex | Age | Purpose |
|--------|------|------------|-----|-----|---------|
| 139682 | CBC | Non-specific complaint | Female | 30 | Analysed before any model is deployed |
| 135318 | CBC | Non-specific complaint | Female | 30 | Eligible |
| 136426 | CBC | Non-specific complaint | Female | 42 | Eligible |
| 139881 | CBC | Non-specific complaint | Male | 30 | Sex |
| 138828 | CBC | Non-specific complaint | Female | 55 | Age |
| 139264 | CBC | Other | Female | 30 | Indication |
| 139450 | ferritin | — | Female | 30 | Ferritin gets no result |
| 141462 | CBC | Non-specific complaint | Female | 25 | Deployed model file changed on disk (one byte appended, restored afterwards) |

All receiving and analysing was done as lab-1 on the Samples page. For the
first sample of each kind it was a real click or keyboard Enter. The rest went
through a JS `button.click()` on the same form buttons, which sends the same
form POST. Final model 8964046695433038449 was deployed as director-1 on the
Models page after sample 139682 had been analysed.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Message and Analysed row after each Run analyser | Pass | Each run gave "Sample N: CBC analysed." (ferritin: "Sample 139450: ferritin analysed."). The Analysed rows read: 139682 "Not screened: no final model is deployed"; 135318 "Ferritin suggested"; 136426 "Ferritin not suggested"; 139881 "Not screened: registered sex"; 138828 "Not screened: age"; 139264 "Not screened: clinical indication"; 139450 "—"; 141462 "Not screened: the deployed model changed on disk". All match the expected results. (`01`, `02`, `04`) |
| 2a | Analysed table at 606px | Pass, see observation 2 | `scrollWidth` 606 = `clientWidth` 606, so the page does not scroll sideways. The `.overflow-auto` box is 510px wide with a 526px scroll width, so the table scrolls inside its box by 16px. (`06`) |
| 2b | Analysed table at 1400px | Pass | No stray scrollbar: the box is 1200/1200 and the page is 1400/1400. Every row fits on one line. Column widths are Sample ID 138, Test 100, Analysed 220, Screening result 509 and General practitioner 232. (`05`) |
| 3 | Keyboard order | Pass | Tab from the top: Skip to content, Samples, Log out, then Receive for 139682, 135318, 136426, 139881, 138828, 139264, 139450 in row order, then back to Skip to content. With the samples received: Run analyser for 135318, 136426, 139881, 138828, 139264, 139450 in row order. Pressing Enter on the focused Run analyser ran it for 135318. The Analysed table has no focusable elements. (`03`) |
| 4 | No screening wording on practice pages | Pass | As doctor-a, the page text of `/practice/patients/`, `/practice/orders/` and every patient detail page of doctor-a's eight patients was searched for "screen", "ferritin suggested" and "not suggested". There were no hits. doctor-b's patients return 404, as expected. (`07`) |

## Observations

1. **Wording.** "Not screened: registered sex", "…: age" and "…: clinical
   indication" name only the field, not what was wrong with it. Lab staff can
   see the sex, age and indication in To analyse before running, but once a
   row is in Analysed those columns are gone, so "Not screened: age" does not
   say why. Wording such as "Not screened: age outside 18–49", "…: male" or
   "…: indication not non-specific complaint" would explain it without a
   lookup. "Not screened: the deployed model changed on disk" reads oddly in
   a table (the article, "on disk"), and it describes a fault rather than a
   patient reason.
2. **The run message hides a fault.** When the deployed model was missing
   (139682) or changed on disk (141462), Run analyser still showed the same
   green "Sample N: CBC analysed." success message. A tampered or missing
   model only shows up in the Screening result cell. A warning-style message,
   or a note for the director, would make it visible. That is a product
   decision, so it is reported here, not filed as a defect.
3. **Screening result is squeezed at 606px.** The table overflows its box by
   only 16px, but the auto layout shrinks Screening result to 114px. "Not
   screened: the deployed model changed on disk" then wraps over seven lines
   and "Not screened: clinical indication" over four, while each date wraps
   over three (`06`). A `white-space: nowrap` on that column, or a wider
   minimum width, would trade more horizontal scrolling for readable rows.
4. **The 1659px viewport wraps rows that fit at 1400px.** At 1659px Pico
   raises the root font size, but the container stays 1200px. "Sample ID",
   "General practitioner" and every date then wrap to two lines, and the long
   reason wraps too (`04`). At 1400px everything fits on one line (`05`).
   This is cosmetic.
5. The ferritin row's "Test" cell reads lower-case "ferritin" next to "CBC".
   This was already the case before this branch (`Test.FERRITIN` label).

No defects that block merge.

## Not checked

- The practice receiving a lab report with its comment ("Ferritin
  suggested."). No practice page lists fetched lab reports yet, and dev mode
  has no messaging. The practice had no `Order` rows for these samples
  because the lab orders were injected at the hospital.
- The screening result through the real demo (separate hospital and practice
  processes, model files from training).
- Focus ring visibility on Run analyser: it was focused (`03`) but not
  inspected closely.
- Other browsers, screen readers, widths other than 606, 1400 and 1659px.

## Screenshots

- `01-no-model-analysed-message.jpg`: success message after analysing 139682 with no model deployed
- `02-not-screened-no-model.jpg`: Analysed row "Not screened: no final model is deployed"
- `03-run-analyser-focused.jpg`: To analyse table, Run analyser for 135318 focused by keyboard
- `04-analysed-all-results-1659.jpg`: all eight results at 1659px (wrapping)
- `05-analysed-1400.jpg`: all eight results at 1400px
- `06-analysed-606.jpg`: Analysed table at 606px
- `07-practice-patients.jpg`: practice Patients page as doctor-a

## Follow-up (branch author)

- Reasons now say what was wrong: "not a non-specific complaint", "registered sex not female", "age outside 18–49", "no model deployed", "deployed model file changed". Text-only change in the same cells; not re-checked in a browser.
- Not changed: Run analyser shows the same success message when the CBC was not screened because of a model fault (product decision, left to the user); the squeezed column at 606px (shorter labels help); wrapping at 1659px; lower-case "ferritin" (predates the branch).
