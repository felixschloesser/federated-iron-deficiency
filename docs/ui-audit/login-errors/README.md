# Browser check: login-errors

A browser-check agent ran this check on 2026-11-03 against commit 92e37ec, in
Chrome (window viewport 1400px wide).

## Setup

- Server A, practice, `127.0.0.1:8190`: `PRACTICE_DIR=<scratchpad>/practice
  MESSAGING_ADDRESS=127.0.0.1:1 PARTY_COLOUR=green REPORT_CHECK_SECONDS=5
  PRACTICE_NAME="Huisartsenpraktijk De Akker" DJANGO_DEBUG=1`. Its
  certificates were made with `tools/certificates.py` (`make_authority`,
  `issue(..., server=False)`, plus `ca.crt` copied in). Migrated, then
  `seed_practice --patients 4`.
- Server B, hospital, `127.0.0.1:8191`: `DATABASE_NAME=login-errors-check-hospital
  PARTY_COLOUR=violet DJANGO_DEBUG=1`. Migrated, then `seed_hospital`. The NHANES
  data downloaded without trouble.
- The account without a role is the seeded `no-role` (both seed commands create
  it: a plain `User` with a password). No extra account was made in the shell.
- To mark the order as sent, `Order.sent_at` was set in `manage.py shell`.
- Widths and dark mode: `resize_window` did not change `innerWidth` (it stayed
  at 1400). Each page was therefore copied into a same-origin
  `<iframe srcdoc>` with a `<base>`, 375px or 1440px wide (1440 scaled to fit),
  as in earlier reports. Dark mode is Pico's `data-theme="dark"` on that copy,
  not the OS setting.
- Contrast is the WCAG ratio of computed colours, which were resolved through a
  canvas because `color-mix()` computes to `color(srgb …)`.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Kit alert: card, coloured 0.5rem left edge, faint tint, heading in colour | Pass | Success, warning and error look as described (`10`, `13`). Edge against the page: success 6.48 / 6.94, warning 3.99 / 4.50, error 7.83 / 5.89 (light / dark), all at least 3:1. Body text on the tint is 8.85 to 10.07. |
| 2a | Login, wrong password | Pass | Red "There is a problem" alert between the h1 and the form, 16px gaps at 375 and 20px at 1440. Both inputs have `aria-invalid="true"` and are drawn red (`01`–`04`). No horizontal scroll at 375. |
| 2b | Login, account without a role | Pass | The same alert, "Your account has no role in this app. Ask the administrator."; neither input has `aria-invalid` (`05`). |
| 2c | Keyboard after a failed login | Pass | `autofocus` puts focus on Username. Tab → Password → Log in. Shift+Tab goes back to Skip to content. The summary has no link for the non-field error, so there is nothing to tab to in it. |
| 3a | Order placed, hospital unreachable | Pass | Green "CBC ordered on sample …", then the amber warning "The hospital could not be reached, so the lab order is not sent yet." (`08`, `09`). The page answered after about 2 s. |
| 3b | Check for reports, hospital unreachable | Pass | Red "The hospital could not be reached. Try again later." above the Orders h1 (`11`). |
| 3c | Success message | Pass | "Sample … collected." in the success alert, light and dark (`06`). |
| 4 | Patient page, sent and not sent | Pass | Not sent: `<mark>Lab order not sent yet</mark>` and no reload hint (`08`). After `sent_at` was set: "Awaiting lab report" and "New reports arrive within 5 seconds; reload to see them." (`12`). |
| 5 | Deployment page, no usable model | Pass | "No screening model is deployed." in the error alert, under the h1 (`14`, `15`). |
| 6 | Party themes | Pass | Green (A) and violet (B). The alert colours come from Pico's `ins`/`del` and the fixed amber, so they are the same in every theme. Theme links on the tints: green 4.76–5.80, violet 4.64–5.87. |
| — | Heading contrast on the tint | Pass for the headings in use, see defect 1 | Error 6.88 light / 5.01 dark, success 5.77 / 5.81. Warning 3.62 / 3.93. |

## Defects

1. **A warning heading would fail text contrast.** `static/css/app.css:42-44`
   colours a warning alert's heading #b86e00. On the warning tint this measures
   3.62:1 (light) and 3.93:1 (dark), below 4.5:1. At 375px the heading is 16px
   bold, which is not large text (`10`, `13`, injected test headings). No page
   shows a warning with a heading yet, so nothing visible fails today, but the
   kit offers one. Fix: keep #b86e00 for the edge and give the heading its own
   colour, e.g. `article[data-level="warning"] > :is(h2, h3) { color: #8a5300; }`
   (about 5.7:1 on the light tint), with a lighter amber under
   `[data-theme="dark"]` and the dark media query. Alternatively, colour the
   heading only for success and error.
2. **Pre-existing, seen on this branch: the error summary links a radio
   group to `#`.** In `templates/kit/form.html:10`, `field.id_for_label` is
   empty for a `RadioSelect`. The CBC order's "Clinical indication: A CBC
   needs a clinical indication." therefore links to `#` and jumps to the top
   instead of the field (`07`). Fix: fall back to the first option,
   `#{{ field.auto_id }}_0`, when `id_for_label` is empty.

## Observations

1. **Two identical chips for two different states.** "Lab order not sent yet"
   and "Awaiting lab report" are both Pico's amber `mark` (`08`, `12`). Only
   the text tells them apart.
2. **Success and warning together.** After an order with the hospital down,
   the page shows a green "CBC ordered" directly above the amber "not sent
   yet" (`08`). This reads acceptably, but the green may suggest that all is
   well.
3. **Link colour inside the error alert.** Links in the summary keep the theme
   colour (green or violet) inside the red card (`07`). The contrast is fine.
4. **Not this branch:** the practice header overflows at 375px.
   `scrollWidth` is 385, because the nav's "Log out" button wraps and sticks
   out (`06`, `12`).
5. **Messages use `role="status"` at every level**, including the error "The
   hospital could not be reached" (`templates/kit/base.html:32`). That is
   probably right after a redirect, and is noted only to make the choice
   explicit.

## Not checked

- A real window resize, and the OS dark-mode setting: both were checked on an
  iframe copy (see Setup).
- Screen-reader announcements of `role="alert"`/`role="status"`.
- The "hospital refused" texts. They need a reachable endpoint that rejects
  the message.
- The reload hint together with a released report.
- The default (unthemed) Pico colours. They were not needed for the alert
  colours, which are the same in every theme.
- Other browsers.

## Fixed on the branch after this check

- Defect 1, warning heading contrast: warning headings now have their own
  colour (`static/css/app.css`). They are #8a5300 in light (5.74:1 on the
  warning tint) and #e09a3a in dark (6.6:1), computed against Pico's card
  backgrounds (#ffffff, #181c25) with the tint at 8%. The edge keeps #b86e00.
  These were measured by script, not in the browser.
- Defect 2, radio group linked to `#`: the error summary now falls back to
  `#{{ field.auto_id }}_0` (`templates/kit/form.html`). A view test asserts
  `<a href="#id_indication_0">`.
- Not changed: the two chips share one amber, and the practice header
  overflows at 375px. Both are older than this branch.
