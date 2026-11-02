# Browser check: patient-page-readable

A browser-check agent ran this check on 2026-11-02 against commit 9ccb0db. The
browser was Chrome with a 606px-wide viewport.

## Setup

- Server A on `127.0.0.1:8090`, run from the worktree with `uv run` and
  `DATABASE_NAME=patient-page-readable PARTY_COLOUR=green
  PRACTICE_NAME="Huisartsenpraktijk De Akker" DJANGO_DEBUG=1`. `PRACTICE_DIR`
  was unset. It was migrated and seeded with
  `manage.py seed_practice --patients 6`.
- The brief also asked for `MESSAGING_ADDRESS=127.0.0.1:1` on that server. The
  settings refuse this: "MESSAGING_ADDRESS needs PRACTICE_DIR", and
  `DATABASE_NAME` cannot be set together with `PRACTICE_DIR`. The reload hint
  was therefore checked on a second server, B, on `localhost:8091`. B ran with
  `PRACTICE_DIR=<scratchpad>/practice MESSAGING_ADDRESS=127.0.0.1:1
  REPORT_CHECK_SECONDS=5`, and was migrated and seeded the same way.
  Without `PRACTICE_DIR`, server A's header reads "Demo hospital" (the default
  party name). That is a setup artefact.
- The GP was logged in as doctor-a.
- Data states:
  - **Lien Willems** (A): no samples.
  - **Laura Peeters** (A), two samples, made through the shell with
    `collect_sample`/`place_order` and `LabReport` rows shaped like those in
    `tests/test_practice_views.py`:
    - The newer sample has a released CBC with 13 values and
      `ferritin_suggested=True`, which shows the Order ferritin button.
    - The older sample is closed. It has a released CBC with the suggestion and
      an awaiting ferritin order.
  - **Maria Goossens** (A): a released CBC with no suggestion, which shows the
    sample's outline "Order ferritin" button.
  - **Luc De Smet** (A), through the UI: Collect sample twice (one sample left
    empty), then a CBC with the indication "Other", awaiting.
  - **Laura Peeters** (B): Collect sample and a CBC through the UI. On B,
    placing the order raised a `FileNotFoundError` for the messaging CA
    certificate. The order row had already been saved, so the page showed it
    as awaiting. This is environmental and not a defect of this branch.
- 375px and 1440px: `resize_window` left `innerWidth` at 606. The pages were
  therefore loaded into a same-origin `<iframe srcdoc>` with a `<base>`, as in
  `slice-reports`. At 1440px the frame was scaled by 606/1440 to fit the
  screenshot.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Sex and age under the name, above Collect sample | Pass | "Female, aged 35" sits directly under the h1 (0px gap), at 17px in the muted colour rgb(100,107,121). Collect sample comes after it. Checked at 375, 606 and 1440 (`02`, `07`, `13`, `15`). |
| 2 | Sample heading smaller than the name | Pass, see defect 1 | The h1 is 34px and the summary h2 is 21.25px (1.25rem). However, the card's h3 ("CBC (other)") is 25.5px, which is **larger** than the sample heading above it (`02`). |
| 3 | The open sample does not repeat its tests; closed samples do | Pass | The open summary has the heading only. The closed one reads "CBC, ferritin · Ferritin suggested", or "No tests ordered yet" for an empty sample (`03`, `09`). A closed sample opened by the user keeps its test line, because the line is decided on the server (`04`). That is acceptable. |
| 4 | Each card leads with its status, then "· Ordered …"; the reload hint goes on a new line | Pass, see observation 1 | `<mark>Awaiting lab report</mark>` shows as an amber chip (`05`, `09`). `<ins>Lab report released …</ins>` shows as plain green text with no background (`02`). On B, the hint "New reports arrive within 5 seconds; reload to see them." is small text on its own line (`10`). There is no hint on A, which is correct without messaging. |
| 5 | Sample Order buttons are `secondary outline` and come after the cards; the primary Order ferritin beside a suggestion is unchanged | Pass, see defect 2 | The DOM order is summary > article(s) > `.action-row`, with class `secondary outline` (`06`, `09`). The suggestion's Order ferritin is a filled primary button inside the card (`02`). The empty sample's buttons come after "No tests ordered yet". |
| 6 | Visual hierarchy: the name dominates | Mostly pass | The name is the largest text on the page. Below it, the order of sizes is inverted (defect 1). |
| 7 | The details chevron | Fail, see defect 3 | Pico floats `summary::after` to the far right. At 1440px it sits about 540px from the end of the heading. On a closed sample it drops below the test line, on its own row (`14`, `16`). It is still easy to miss and does not clearly belong to the heading. |
| 8 | Keyboard focus order | Pass | Skip to content → Patients → Orders → Log out → Collect sample → sample summary → Order ferritin (sample) → … This is the reading order. The sample buttons' aria-label is "Order ferritin on sample 139264-1" (`11`). |
| 9 | Visible focus | Fail, see defect 4 | Links and buttons get a 2px solid ring in the text colour (`11`). The `<summary>` gets Pico's ring instead, rgba(71,164,23,0.5), which is about 1.7:1 on white (`12`). |
| 10 | 375px | Pass | `scrollWidth` 375 = `clientWidth` 375. The sample heading wraps to two lines and the chevron sits beside the second line. The open report table box measured 311/311 (`13`, `14`). |
| 11 | 1440px | Pass | 1440/1440. The content column is 1200px (`15`, `16`). |
| 12 | Other `index_header` pages unchanged | Pass | The Patients, Orders and Login hgroups contain only the h1 (no empty `<p>`), each 38.25px high (`17`, `18`, `01`). |

## Defects

1. **The card heading is larger than the sample heading.** In `static/css/app.css:108-112`, the summary h2 is set to 1.25rem (21.25px). Pico's default h3 inside each `article` is 25.5px. "CBC (other)" therefore outranks "Sample …, collected …", the heading it sits under (`02`, `16`). Fix: also size the card heading below the sample heading, e.g. `details article h3 { font-size: 1.0625rem; }` (or 1.125rem), or raise the h2 to about 1.5rem while keeping it under the 34px h1.
2. **The sample's Order buttons float halfway between two samples.** From `templates/practice/patient.html:37`, the `.action-row` sits 20px below its sample's last card and 20px above the next sample's summary (measured at 1440). Nothing marks it as part of the sample above, so on a page with several samples it can read as belonging to the next sample (`09`, `14`, `16`). Fix: separate samples, e.g. `details { padding-bottom: var(--pico-spacing); border-bottom: 1px solid var(--pico-muted-border-color); }` in `app.css`. Alternatively, give the action row a smaller top margin than the gap between samples.
3. **The chevron is far from the heading and on the wrong line when closed.** Pico floats `details summary::after` right (vendored Pico, styled in `static/css/app.css:107-117`). Because `small` is `display: block`, the floated chevron of a closed sample lands after the test line, below the heading (`14`, `16`). Fix: make the summary a flex row (`details > summary { display: flex; align-items: baseline; gap: .5rem; } details > summary::after { order: -1; float: none; }`) so the chevron leads the heading, as a disclosure triangle usually does. At minimum, set `margin-inline-start: auto` and drop the float so that it aligns with the first line.
4. **The summary's focus ring is too faint.** In `static/css/app.css:102`, the house focus rule covers `a, button, input, select, textarea, [role="button"]` but not `summary`. The summary keeps Pico's 50%-alpha theme ring, about 1.7:1 on white, which is below the 3:1 for focus indicators (`12`). This rule predates the branch, but the summary is now the main control on this page. Fix: add `summary` to the `:where(...)` list.

## Observations

1. **The two status labels carry different weight.** "Awaiting" is a filled amber chip. "Released" is plain green text in the body weight and is easy to read as ordinary text (`02` next to `05`). If the status should lead visually in both cases, give `ins` a matching chip, for example a pale green background with the same padding as `mark`.
2. **"CBC, ferritin"**: the lower-case "ferritin" in the closed summary and on the Orders index comes from the `Test.FERRITIN` label, as noted in slice-reports.
3. **A male patient (Luc, 38) is offered "Order ferritin" on his sample.** This is outside the scope of this branch and is noted only because it is visible in `09`.
4. **Placing an order with `MESSAGING_ADDRESS` set and no certificates** gives a 500, but the order row stays saved, and the next page showed the "CBC ordered" flash. This is outside this branch's scope, but the order should probably not persist when sending fails.

## Not checked

- A real window resize. The widths were checked in an iframe.
- Other browsers, screen readers, dark mode.
- The reload hint together with a released report on the same sample.

## Fixes after the check

The branch author fixed every defect in `static/css/app.css` and checked each fix in Chrome at 606px. That check used a static copy of the page with the new stylesheet, not the full app.

1. Defect 1: `details article h3` is now 1.0625rem, below the 1.25rem sample heading.
2. Defect 2: each sample's `details` ends with a padded bottom rule, so its Order buttons stay with it.
3. Defect 3: the chevron is placed absolutely in the summary's left padding. It sits beside the heading's first line, both open and closed, also when a test line follows. The flex version was not used because it would have put the heading and the test line on one row.
4. Defect 4: the house focus rule (a `:where()` list) has no specificity, so adding `summary` to it would lose to Pico's `summary:focus-visible:not([role])`. A separate rule, `details > summary:focus-visible:not([role])`, gives the summary the same 2px ring in the text colour.
5. Observation 1: `ins` inside a card has a thin border chip, so "Lab report released …" reads as a status like "Awaiting lab report".

Observations 2–4 are outside this branch and still open.
