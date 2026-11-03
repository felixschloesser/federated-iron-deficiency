# Browser check: choose-laboratory

A browser-check agent ran this check on 2026-11-03 against commit c527ffc.

## Setup

- Chrome 156 headless (`--headless=new`, its own profile, DevTools port 8391),
  driven over the DevTools protocol from a small Node script, as in
  `docs/ui-audit/practice-name/`. Widths are viewport overrides (375, 1440).
  Dark mode is the emulated `prefers-color-scheme: dark`. Keys are real
  `Input.dispatchKeyEvent` presses (Tab, ArrowDown, ArrowUp).
- Practice only, no PRACTICE_DIR: `DATABASE_NAME=cl-check DJANGO_DEBUG=1
  PARTY_COLOUR=green`, `runserver 127.0.0.1:8390`, `seed_practice --patients 4
  --seed 0`, logged in as `doctor`. Without PRACTICE_NAME the brand reads
  "Demo hospital".
- Laboratories were created in the shell, `Laboratory.objects.create(name=…,
  address="127.0.0.1:1")`: none for item 1, "UZ Leuven" for item 2, then
  "AZ Diest" as well for items 3 and 4.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | No laboratory | Pass | *Collect sample* is one `<button>` in a POST form to `…/samples/collect/` (`01`–`04`). |
| 2 | One laboratory | Pass | Still one button. Pressing it led straight to the CBC order page ("Sample 135318-1 collected."). The heading reads "Sample 135318-1, collected 3 Nov 2026, 20:30, for UZ Leuven" (`05`–`08`). At 375 it wraps to two lines and does not overflow (`05`, `07`). |
| 3 | Two laboratories | Pass | *Collect sample* is a link (`<a role="button">`) to `/practice/patients/2/samples/collect/` (`09`). The page title is "Collect sample · Lotte Jacobs"; the heading is "Collect sample" with "Lotte Jacobs" under it, followed by a "Laboratory:" fieldset with the radios AZ Diest and UZ Leuven, sorted by name and none preselected (`10`–`13`). Submitting with no choice re-rendered the page with the red error alert "There is a problem" and the link "Laboratory: Choose the laboratory the sample goes to." The same message appears in the fieldset, and both radios get `aria-invalid` (`14`–`17`). The summary link goes to `#id_laboratory_0`, and clicking it focuses the first radio (`18`). Choosing AZ Diest led to the CBC order page for sample 138828-1 (`19`). The patient page heading reads "…, for AZ Diest" (`20`–`23`). At 375 the heading takes 2 lines (46px) inside the 375px page, which does not scroll sideways (`20`, `22`). |
| 4 | Keyboard | Pass | Tab order: Skip to content, Patients, Orders, Log out, AZ Diest (the group stop), Collect sample, then the body. ArrowDown moves to UZ Leuven and selects it; ArrowUp moves back. Every stop matches `:focus-visible` with a 2px solid outline, #181c25 in light and #dfe3eb in dark mode (`24`–`31`). In `25`, `27` and `29` the checked radio is still in Pico's transition (grey); `30` and `31` show it settled, green. |
| 5 | Unreachable laboratory warning | Not checked | This needs a PRACTICE_DIR with certificates. Creating it in the scratchpad was refused by the session's permission rules, so I skipped it. |

## Defects

None on this branch.

## Observations

1. **The field error is plain text in a bulleted list.** In the fieldset,
   "Choose the laboratory the sample goes to." is a Django `ul.errorlist`
   with Pico's list bullet, in body colour, not red (`14`, `17`). Only the
   radio borders turn red. `static/css/app.css` has no `.errorlist` rule, so
   this affects every kit form, not only this page. Suggested fix: style
   `.errorlist` in `app.css` (no bullet, `padding-left: 0`, colour
   `var(--pico-del-color)`), or render the errors through the kit.
2. The legend reads "Laboratory:", with the colon from Django's default label
   suffix, and the summary repeats it as "Laboratory: Choose …". The other
   kit forms work the same way.
3. The full-width primary submit button sits right under two short radios at
   1440 (`11`). This is Pico's default for a submit button in a form, the same
   as on the order page.

## Not checked

- Item 5: no PRACTICE_DIR or certificates (see above).
- A headed window, the Claude-in-Chrome extension, Pico's `data-theme` toggle
  (dark mode was only the emulated media query), screen readers, other
  browsers.
- A laboratory name long enough to wrap the heading to three lines.
