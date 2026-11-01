# Browser check: slice-colours

A browser-check agent ran this check on 2026-11-01 at commit 707f06d. The
browser was Chrome with a 1440×757 viewport.

The branch builds on slice-samples (checked in `docs/ui-audit/slice-samples/`)
and adds:

1. six clinical indications;
2. the "Screening models" page;
3. party colours (`PARTY_COLOUR`);
4. fixes for the slice-samples defects: a Sample ID column on Orders, `.sample-id`
   no-wrap, and aria-labels that name the sample.

## Setup

- Development checkout: one database (`DATABASE_NAME=slice-colours-ui`,
  `DJANGO_DEBUG=1`), every app, no messaging between parties. Real final models
  from `FINAL_MODELS_DIR=…/scratchpad/ui-models` (two runs).
- `runserver 127.0.0.1:8062`, opened as `http://colours.localhost:8062`. A
  separate host name keeps this check away from the user's demo cookies on
  `127.0.0.1`.
- `PARTY_COLOUR=jade` for checks A to D. For check E the server was restarted
  with pumpkin, violet, green, amber, purple and no `PARTY_COLOUR`. Each time the
  served stylesheet was confirmed (`pico.<colour>.min.css`, or `pico.min.css`
  without a colour).
- Accounts: `director-1`, `doctor-a` and `lab-1`. The checker logged out between
  roles.
- Relay by hand with the scratchpad helper `ui_relay.py`: `deliver()` after the
  GP orders, and `release()` without `suggest` after the analyser.
  - **Relay caveat:** `release()` writes `ferritin_suggested = suggest and
    test == CBC`. Without `suggest` every report comes out "not suggested"
    whatever the model decided.
  - The checker then copied each lab order's `ferritin_suggested` onto its
    released lab report in the shell: 135318-1 True, 137989-1 False. That is
    what real messaging would carry.
  - This is a defect in the test helper, not in the app. The helper should copy
    `lab_order.ferritin_suggested` when it is used again.
- Patients: Test Patient 1 (female, 28) had a CBC for "Unexplained fatigue",
  sample 135318-1. Test Patient 9 (female, 43) had a CBC for "Start of
  pregnancy", sample 137989-1.
- The 375px and 1400px checks used the slice-samples method, because
  `resize_window` does not change the viewport. Each page's HTML was fetched and
  loaded into an `<iframe srcdoc>` of that width, with a `<base>` pointing at the
  app. `innerWidth` inside the frame was 375 or 1400.
- In the colour runs, the login page was framed the same way while logged in as
  `doctor-a`, so its header shows the GP nav. Jade also has a logged-out
  capture (E01).
- The success, warning and error message boxes in E02–E15 are **synthetic**.
  Three `article[role=status][data-level=…]` elements were inserted in the DOM,
  with the same markup as `templates/kit/base.html`. Real ones need a POST for
  each level.
- Contrast ratios were computed in the page from computed styles (WCAG relative
  luminance) against the white page background.

## Checklist

| # | Check | Result | Screenshot |
|---|-------|--------|------------|
| A1 | Director nav says "Screening models". Page `<title>` is "Screening models · Demo hospital" and the H1 is "Screening models". | Pass | A01 |
| A2 | Two cards (`<article>`), newest first: 29 Oct 2026 20:55 above 20:49 | Pass | A01, A06 |
| A3 | 1440px card header: title left, Deploy right, vertically centred | Pass | A01 |
| A4 | 375px card header: Deploy wraps under the title and sits on the left. No page scroll (`scrollWidth` 375). | Pass. The title breaks between "29" and "Oct", see N1. | A02 |
| A5 | Card body: "Finds 8 of 10 iron-deficient women", "1 unnecessary ferritin suggestion" (singular is right), "AUROC 0.97 here, 0.87 across hospitals". Footer shows "threshold 0.5 · run …" in small print. | Pass | A01 |
| A6 | Before deploying, the error box "No screening model is deployed." shows under the H1 | Pass | A01 |
| A7 | Deploy the 20:55 model: message "Screening model of 29 Oct 2026, 20:55 deployed.", card shows "Deployed" on the right, the other card keeps Deploy, and the history row is "1 Nov 2026, 15:28 · Screening model of 29 Oct 2026, 20:55". The error box is gone. | Pass | A05, A06 |
| A8 | Keyboard: Tab order Skip to content → Screening models → Log out → Deploy (card 1) → Deploy (card 2). Focus ring visible (jade). | Pass | A03, A04 |
| A9 | Accessible names of the two Deploy buttons | **Fail**, see D1 | (read_page: `button "Deploy"` ×2) |
| B1 | Order CBC page: "This order collects a new sample." and six radios in a fieldset with legend "Clinical indication:". The labels are Suspected anaemia, Suspected irritable bowel syndrome, Unexplained fatigue, Start of pregnancy, Chronic kidney disease follow-up and Other. | Pass | B01 |
| B2 | (extra) Submit with no radio selected: the error summary "Clinical indication: A CBC needs a clinical indication." and the field error appear, and radios show an invalid outline | Pass | B03 |
| B3 | Order CBC with "Unexplained fatigue" (Patient 1) and with "Start of pregnancy" (Patient 9): "Order placed.", and each row shows sample ID and indication | Pass | B02, B04 |
| B4 | Practice Orders index has a Sample ID column (fixes slice-samples D1) | Pass | B04 |
| B5 | 375px Orders index: IDs on one line (`white-space: nowrap`, one client rect each), table scrolls in its own box (547 in 343), page `scrollWidth` 375 | Pass | B05 |
| C1 | To analyse lists both samples with indication | Pass | C01 |
| C2 | 375px To analyse: IDs unbroken, page `scrollWidth` 375. The table scrolls inside (711 in 343). | Pass. The Run analyser column is off-screen until scrolled, as in slice-samples. | C02 |
| C3 | Run analyser accessible names: "Run analyser for sample 135318-1" and "Run analyser for sample 137989-1" | Pass | (read_page) |
| C4 | Run analyser on both: "Sample …: CBC analysed." Analysed shows 135318-1 "Ferritin suggested" (the model decided) and 137989-1 "Not screened: clinical indication not screened". | Pass | C03, C04 |
| D1 | After release (see the relay caveat), Patient 1 has the report "CBC lab report, sample 135318-1" with "Ferritin suggested." and an Order ferritin button | Pass | D01, D02 |
| D2 | That button's accessible name is "Order ferritin on sample 135318-1" | Pass | (read_page) |
| D3 | The Patient 9 report (not screened) shows results only, with no suggestion line | Pass | D03 |
| E1 | Each colour serves its own Pico theme. Primary buttons, links, focused inputs and the focus ring take the theme colour. | Pass | E01–E16 |
| E2 | Primary button text contrast. White text: jade 5.39, violet 6.48, purple 6.39, green 4.52, default 5.23. Pico switches to black text on amber (12.7) and pumpkin (9.55). | Pass (green is just over 4.5) | E02–E15 |
| E3 | Link contrast on white: jade 5.39, pumpkin 5.47, violet 5.28, green 5.41, amber 5.45, purple 5.01, default 5.23 | Pass | same |
| E4 | Message borders keep the same colours in every theme: success `#1d6a54` (6.48:1), warning `#b86e00` (3.99:1), error `#883935` (7.83:1). The three are distinguishable from each other in every theme. | Pass. In jade the success green is close to the primary colour, and in amber and pumpkin the warning amber is close to the primary. They still read as different levels. | E02, E11 |
| E5 | Focus visibility on amber and pumpkin | **Fail (minor)**, see D2 | E05, E11, E12 |
| F1 | No horizontal page scroll at 375 and 1400: Orders index, patient pages 1 and 9, Order CBC, To analyse, Analysed (`scrollWidth` equals `innerWidth`). Screening models was checked at 375 and at the 1440 viewport. | Pass | measured |
| F2 | Heading order. Screening models: H1, H2 for each card, H2 Deployment history. Patient page: H1, H2 Orders, H2 for each report. Order CBC, Orders, To analyse and Analysed have only an H1. | Pass | measured |

## Defects

**D1 (moderate, accessibility).** Both Deploy buttons on Screening models have
the accessible name "Deploy".
- Location: `/deployment/models/`, the card header button.
- Screen-reader users who tab or list buttons hear "Deploy, Deploy" and cannot
  tell which model each one deploys. This is the same problem the branch fixed
  for Run analyser and Order ferritin.
- Suggested fix: name the model, for example
  `aria-label="Deploy screening model of 29 Oct 2026, 20:55"`.

**D2 (minor, accessibility, amber and pumpkin only).** The keyboard focus
indicator and control edges are weak on the light themes.
- Location: every page under `PARTY_COLOUR=amber` or `pumpkin`.
- A focused text input gets a border in the primary colour: 1.65:1 against
  white on amber, about 2.2:1 on pumpkin. Both are below the 3:1 that WCAG
  1.4.11 asks of a focus indicator.
- Pico's 50% focus halo is about 1.7:1 in every theme, default blue included.
  On the dark themes the solid primary border (≥4.5:1) carries the focus state.
  On amber and pumpkin nothing does.
- A focused button only gets a slightly darker fill.
- Primary button fills against white are 1.65 (amber) and about 2.2 (pumpkin).
  The black labels stay highly readable.
- Suggested fix: in `static/css/app.css`, give these themes a darker
  `--pico-primary-border`/`--pico-primary-focus` or a solid focus outline, or
  avoid amber and pumpkin for any party.

## Notes (not defects)

- **N1.** At 375px the card title "Screening model of 29 Oct 2026, 20:55" breaks
  between "29" and "Oct" (A02). It is readable. A no-wrap span on the date would
  keep the date together.
- **N2.** The page error "No screening model is deployed." sits below the H1.
  Flash messages such as "… deployed." sit above it (A01 vs A05). The kit places
  the two differently. This is consistent with the other pages.
- **N3.** A card showing "Deployed" has a shorter header than a card with a
  Deploy button: the button is taller than the text (A05). This is cosmetic.
- **N4.** In this development checkout every party shares one `PARTY_COLOUR`, so
  the practice and the lab are also jade. The rule that a practice takes its
  hospital's family was not visible here.

## Not checked

- Dark mode (`prefers-color-scheme: dark`) in any of the seven themes.
- Separate per-party deployments: hospital and practice with different
  `PARTY_COLOUR`, and the "practice in its hospital's family" pairing.
- The "Cannot be deployed: reason" state. Both available models were
  deployable.
- Clinical indications other than Unexplained fatigue and Start of pregnancy at
  the analyser. "Suspected anaemia" and "Suspected IBS" are expected to be
  screened, and "CKD follow-up" and "Other" not screened.
- Real success, warning and error messages in each colour. The E-series
  messages are synthetic DOM inserts. Only real success messages were seen, in
  jade.
- Screening models at exactly 1400px (seen at the 1440 viewport and at 375).
  Analysed was not photographed at 375 (it was measured).
- Screen-reader output. Accessible names come from the Chrome accessibility
  tree, not from VoiceOver.
