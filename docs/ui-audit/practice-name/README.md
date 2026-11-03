# Browser check: practice-name

A browser-check agent ran this check on 2026-11-03 against commit 7e4700a.

## Setup

- The Claude-in-Chrome extension was not connected. The check therefore used
  the locally installed Chrome 156 headless (`--headless=new`, its own profile
  in the scratchpad), driven over the DevTools protocol from a small Node
  script. Widths are real viewport overrides (`Emulation.setDeviceMetricsOverride`,
  375 and 1440). Dark mode is the emulated `prefers-color-scheme: dark`, not
  Pico's `data-theme`. Keys are real `Input.dispatchKeyEvent` Tab presses.
- Certificates: `tools/certificates.py`. One hospital CA, a client certificate
  for "Huisartsenpraktijk De Akker" with `ca.crt` copied in, and a messaging
  server certificate.
- Hospital, `localhost:8291`: `HOSPITAL_DIR=<scratchpad>/hospital
  PARTY_COLOUR=violet DJANGO_DEBUG=1`, then `seed_hospital --patients 8 --seed 0`.
  Messaging endpoint: `serve_messages 127.0.0.1:8292`. No screening model was
  deployed.
- Practice, `127.0.0.1:8290`: `PRACTICE_DIR=<scratchpad>/practice
  MESSAGING_ADDRESS=localhost:8292 PARTY_COLOUR=green
  PRACTICE_NAME="Huisartsenpraktijk De Akker" REPORT_CHECK_SECONDS=5`, then
  `seed_practice --patients 8 --seed 0`.
- The databases live in the party folders. `DATABASE_NAME` cannot be set
  together with a party folder.
- End to end, as `doctor`: a sample was collected and a CBC ordered for
  patients 1–3, plus a ferritin on patient 1's sample. All four orders reached
  the hospital. As `lab-1`, the analyser was run on 139682-1 (by Tab and then
  activating the focused button) and on 135318-1. The practice's
  "Check for reports" button then fetched "2 new lab reports."

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | To analyse: columns, no general practitioner, fit | Pass | The headers are Sample ID, Test, (visually hidden) Action, Ordered. The page HTML has no "practitioner", "Dr. Demo" or "doctor" (`02`–`05`, `09`–`12`). At 1440 nothing scrolls (box 1200/1200). At 375 the page does not scroll (375/375). The table box scrolls 403/343, which is 60px. With the old general practitioner column put back in the DOM, it scrolled 524/343, so there is less sideways scrolling than before. At 375, "135318-1 · stored sample" wraps to three lines, "Run analyser" to two, and "Ordered" to three; the Ordered column is cut at the right edge until it is scrolled (`11`). |
| 2 | Analysed: columns, no general practitioner, long results | Pass | The headers are Sample ID, Test, Analysed, Screening result. No general practitioner appears. At 1440 "Not screened: no screening model deployed" stays on one line (`14`, `16`). At 375 it wraps one word per line, five lines, and the box scrolls 377/343, so the last 34px are cut until scrolled (`13`, `15`). |
| 3 | Keyboard on To analyse | Fail, see defect 1 | Tab order: Skip to content, To analyse, Analysed, Log out, then each Run analyser in row order, with accessible names "Run analyser for sample 135318-1", "…139682-1", "…138828-1", "…135318-1". The light-mode focus ring on the buttons is invisible (`06`, `07`). Dark mode shows it (`08`). |
| 4 | End to end | Pass | The orders arrived with no general practitioner name (`02`). The run gave "Sample 139682-1: CBC analysed, lab report released without screening: no screening model deployed. Tell the laboratory director." After the run, the ferritin row showed "· stored sample" (`09`). The practice patient page shows "Lab report released …" and the 13 CBC values (`17`, `18`). The practice pages name no general practitioner either. |

## Defects

1. **The focus ring on a primary button is white on white, so it is
   invisible in light mode.** `static/css/app.css:132-135` sets
   `outline: 2px solid var(--pico-color)`. Inside a button, `--pico-color` is
   the button's text colour, white, and with `outline-offset: 2px` the ring is
   drawn on the white page. The computed outline is rgb(255, 255, 255), and
   `:focus-visible` matches (`07`). In dark mode the same white ring shows on
   the dark page (`08`). This predates the branch, but it affects every
   Run analyser and every other primary button. Suggested fix: use a colour
   that does not depend on the element, e.g. `var(--pico-contrast)` (dark in
   light mode, light in dark mode), or set a separate
   `button:focus-visible { outline-color: var(--pico-contrast); }`.

## Observations

1. **The Run analyser button got wider.** At 1440 it is 333px wide, where it
   was 235px with the old column. Pico makes a submit button in a form 100%
   wide, and the action column took the freed space (`03`). The button also
   sits high in its cell, 12px above and 31px below, because of the form's
   bottom margin, so rows are about 104px tall for one line of text. Neither
   is a regression in function, but the rows read as unevenly padded. Removing
   the bottom margin and the full width for `td form` in the kit would
   tighten the rows.
2. **Not this branch:** with no model deployed, the practice shows "No
   ferritin suggestion. This does not rule out iron deficiency." for a report
   the hospital released "without screening" (`17`).
3. **Not this branch:** the test label "ferritin" is lower case, next to "CBC".

## Not checked

- A real headed window, the Claude-in-Chrome extension, and Pico's
  `data-theme` toggle. Dark mode was the emulated media query.
- Screen readers.
- Screening results other than "no screening model deployed" (no model was
  deployed), and the sex and age "Not screened" reasons.
- The empty states ("Nothing to analyse.", "Nothing analysed yet.").
- Other browsers.

## Fixed on the branch after this check

- Defect 1, invisible focus ring on buttons in light mode: the focus rules in
  `static/css/app.css` use `--pico-contrast` (#181c25 light, #dfe3eb dark)
  instead of `--pico-color`, which inside a button is its own white text.
  This was not re-checked in the browser.
- Not changed: the wider Run analyser button and the tall rows. Those are an
  observation, not a defect.
