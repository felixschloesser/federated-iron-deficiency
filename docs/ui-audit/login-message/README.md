# Browser check: login-message

A browser-check agent ran this check on 2026-11-03 against commit 6edc53a.

## Setup

- Chrome headless (`--headless=new`, its own profile, DevTools port 8591),
  driven over the DevTools protocol from a small Node script. Widths are
  viewport overrides (375, 1440). Dark mode is the emulated
  `prefers-color-scheme: dark`.
- Practice only: `DATABASE_NAME=lm-check DJANGO_DEBUG=1 PARTY_COLOUR=green`,
  `runserver 127.0.0.1:8590`, `seed_practice --patients 6 --seed 0`. The CBC
  order page was reached with the *Collect sample* button on patient 2's page.
- Positions are `getBoundingClientRect()` values in CSS px.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Login, wrong password | Pass | The alert is `<article role="alert" data-level="error"><p>Wrong username or password.</p></article>`, with no heading, no list and no `aria-labelledby`. Both inputs have `aria-invalid="true"` and a red border (`rgb(184,106,107)` light, `rgb(150,74,80)` dark). No sideways scrolling at 375 (`01`–`04`). |
| 2 | Login as `no-role` | Pass | The alert holds only "Your account has no role in this app. Ask the administrator." as a `<p>`. Neither input has `aria-invalid`, and their borders are Pico's normal colours (`05`–`08`). At 375 the sentence wraps to two lines and the padding stays even. |
| 3 | CBC order, no indication | Pass | The alert keeps the "There is a problem" heading (`aria-labelledby="error-summary-title"`), followed by one line, a link to `#id_indication_0`: "Clinical indication: A CBC needs a clinical indication." The `li` has `list-style: none` and the `ul` has `padding-left: 0`. The line's left edge is level with the heading (40 at 375, 150 at 1440) (`09`–`12`). Keyboard check: Tab from the top reaches the link, and Enter focuses the first radio ("Suspected anaemia") and scrolls it into view (`13`). |
| 4 | Spacing | Pass | In the sentence-only alert the `<p>` has margin 0 top and bottom. Padding is 16/16 at 375 and 20/20 at 1440, and the text sits centred in the box: at 375 the alert spans 156–214 and the text 173–197, which leaves 17 above and 17 below (border included). The h1 does not move on either page. The form moves down by exactly the alert's height plus its margin (login 156 → 230 at 375; order 297 → 437 at 1440). `scrollWidth` equals the viewport at every width and theme. |

## Defects

None.

## Not checked

- A side-by-side comparison with `main`. Item 4 rests on comparing the layout
  before and after the error on this branch.
- Screen-reader output itself: only the `role="alert"` markup was checked.
  Also not checked: Pico's `data-theme` toggle, other browsers, and a form
  with both a form-wide error and a field error.
