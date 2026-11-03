# Browser check: form-errors

A browser-check agent ran this check on 2026-11-03 against commit c8258d6.

## Setup

- Chrome headless (`--headless=new`, its own profile, DevTools port 8491),
  driven over the DevTools protocol from a small Node script, as in
  `docs/ui-audit/choose-laboratory/`. Widths are viewport overrides (375, 1440).
  Dark mode is the emulated `prefers-color-scheme: dark`.
- Practice only: `DATABASE_NAME=fe-check DJANGO_DEBUG=1 PARTY_COLOUR=green`,
  `runserver 127.0.0.1:8490`, `seed_practice --patients 6 --seed 0`, logged in
  as `doctor`. The sample was collected with the patient page's *Collect
  sample* button, which led straight to the CBC order page.
- Contrast is the WCAG ratio of the computed colours, resolved through a canvas,
  against the nearest ancestor with a background (here `html`).

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Login, wrong password | Pass | The labels read "Username" and "Password", with no colon. The red alert "There is a problem" sits above the form. Both inputs have `aria-invalid="true"` and the red border `rgb(184,106,107)`. There is no `ul.errorlist` on the page (`01`–`04`). Nothing scrolls sideways at 375. |
| 2 | CBC order, no indication | Pass | The legend reads "Clinical indication", with no colon. Under it is `<ul class="errorlist" id="id_indication_error">` in red, with `list-style: none`, `padding-left: 0` and its left edge at the legend's x (120 at 1440, 16 at 375). The gaps are even: legend → error 10px, error → first radio 10px, the same gap as legend → first radio before the error (`05`–`11`). The alert link `#id_indication_0`, when clicked, focuses the first radio ("Suspected anaemia") and scrolls it into view (`12`). |
| 3 | Contrast of the error text | Pass | Light: `rgb(136,57,53)` on `#fff` = **7.83:1**. Dark: `rgb(206,126,123)` on `rgb(19,23,31)` = **5.89:1**. Both are above 4.5:1. The text is 16px at 375 and 20px at 1440, weight 400. |
| 4 | Nothing else shifted | Pass | The header, h1 and Log out button sit at the same positions before and after the error. Only the content below the error line moves down, by the alert's height plus the 40px error line, which is expected. `scrollWidth` equals the viewport at every width and theme. |

## Defects

None.

## Observations

1. The alert summary still reads "Clinical indication: A CBC needs a clinical
   indication." There the colon separates the field from the message; it is not
   a label suffix.
2. The alert's own list keeps Pico's square bullet (`06`, `07`). That is the
   kit alert, which this branch did not change.

## Not checked

- A side-by-side comparison with `main` (this check stayed in this worktree). Item 4
  rests on comparing the layout before and after the error on this branch.
- Keyboard-only use of the summary link (it was clicked with a mouse event), Pico's
  `data-theme` toggle, screen readers, other browsers, and fields with more than
  one error.
