# Browser check: link-buttons

A browser-check agent ran this check on 2026-11-05 against commit db79499. It
compared the branch with main's code, a `git archive main` export served the
same way. Since the branch point, main's only changes are in `CLAUDE.md` and
`.gitignore`, so the export shows the old `role="button"` markup. The browser
was headless Chrome 156, driven over the DevTools protocol by a small script.
The Claude-in-Chrome extension was not used.

## Setup

- Servers: branch on `127.0.0.1:8629` and main on `127.0.0.1:8630`, both over
  plain HTTP. Each had its own fresh untracked practice folder and ran with
  `PARTY_COLOUR=green PRACTICE_NAME="Huisartsenpraktijk De Akker"
  DJANGO_DEBUG=1`. Each was migrated, then seeded with `seed_practice
  --patients 4`, then given two laboratories with `add_laboratory "UZ Leuven"
  127.0.0.1:1` and `add_laboratory "AZ Groeninge" 127.0.0.1:1`. With two
  laboratories, Collect sample is a link.
- Data, made in `manage.py shell` with `collect_sample` and `place_order`:
  - Lien Willems (patient 1, sample 1, UZ Leuven): nothing ordered, so the
    sample's row has the link "Order CBC" (`secondary outline`).
  - Lotte Jacobs (patient 2, sample 2): a CBC, sent, with a `LabReport`
    (`results={}`, `ferritin_suggested=True`), so the page shows "Order
    ferritin".
- Logged in as `doctor`. Widths were set with
  `Emulation.setDeviceMetricsOverride`. Hover came from `Input.dispatchMouseEvent`.
  Tab and Enter came from `Input.dispatchKeyEvent`. Roles were read with
  `Accessibility.getPartialAXTree`. Styles are computed values after the
  0.2s transition.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Each link looks like the same button as before and lines up with the real buttons | Pass | At rest, every computed property matches main for Collect sample, Order CBC and Order ferritin on both patients, at 1400 and 375. That covers background, text and border colour, 1px border, 5px radius, 15/20px padding, font family, 20px size, weight 400, 30px line height, no underline and the pointer cursor. Only `role` and `class` differ. Collect sample (172×62 at y 277) and Check for reports (195×62 at y 277) have the same height and top edge, with the same fill `rgb(57,135,18)` (`*-p1-collect-rest`). |
| 2 | Hover and keyboard focus: hover changes colour, focus shows the same ring as a real button, no underline | **Fail (focus ring)** | Hover matches main: the fill goes to `rgb(51,121,15)` with no underline (`*-collect-hover`, `*-ferritin-hover`). **On keyboard focus the 2px contrast outline is missing.** On main, and on the real Check for reports button, `:focus-visible` gives `outline: 2px solid rgb(24,28,37)` with a 2px offset. On the branch the links have `outline: none`, and only Pico's faint box-shadow ring remains: `rgba(71,164,23,0.5)` 2.5px on green links and `rgba(93,107,137,0.25)` on Order CBC. Compare `main-p1-collect-focus` with `branch-p1-collect-focus`, and see `branch-p1-cbc-focus`. That faint ring is below 3:1 against white, which is why `app.css` adds the contrast outline. See Defect 1. |
| 3 | Secondary outline "Order CBC" in its states | Pass, except focus | At rest it has a transparent fill, with text and border `rgb(93,107,137)`. On hover both go to `rgb(72,83,107)` and the fill stays transparent. These match main (`*-p1-cbc-rest`, `*-p1-cbc-hover`). Focus has the same missing outline as item 2. |
| 4 | Keyboard: Tab reaches each link, Enter follows it, the role is "link" | Pass | Tab order on patient 1 is the same as on main: Skip to content, Patients, Orders, Log out, Collect sample, Check for reports, the sample's summary, Order CBC. On patient 2 it is the same, ending with Order ferritin. Enter on each focused link navigates. The accessibility tree reports `link` for "Collect sample", "Order CBC on sample 135318-1" and "Order ferritin on sample 138828-1". Main reports `button` for all three. Check for reports stays `button`. |
| 5 | Each link leads to the right page | Pass | Collect sample goes to `/practice/patients/{1,2}/samples/collect/` ("Collect sample"). Order CBC goes to `/practice/patients/1/samples/1/orders/new/cbc/` ("Order CBC for Lien Willems"). Order ferritin goes to `/practice/patients/2/samples/2/orders/new/ferritin/` ("Order ferritin for Lotte Jacobs"). Each matches main. The server log has no 4xx or 5xx response apart from the browser's `/favicon.ico` 404. |
| 6 | 375px and 1400px: wrapping and gaps unchanged | Pass | Each action row's item positions and sizes are identical to main. At 1400 the gap is 20px (Collect sample 100–272, Check for reports 292–487). At 375 the gap is 16px, both header items are 50px high on one line (16–157 and 173–334), Order CBC is 112×50, and Order ferritin is 127×50 inside its card. Each row's `scrollWidth` equals its `clientWidth`, and `main` does not overflow (`*-p1-375`, `*-p2-375`, `*-1400`). |

Screenshots: `{branch,main}-p{1,2}-{1400,375}` show the full pages.
`{branch,main}-p1-{collect,check,cbc}-{rest,hover,focus}` and
`{branch,main}-p2-{collect,ferritin}-{rest,hover,focus}` show each action row
in its three states at 1400.

## Defects

1. **Keyboard focus on a `button-link` loses the 2px contrast outline.** In
   `static/css/app.css`, `a.button-link { … outline: 0; … }` (specificity
   0,1,1) overrides the house rule `:where(a, button, …):focus-visible {
   outline: 2px solid var(--pico-contrast); outline-offset: 2px }`, whose
   specificity is 0. Pico's `[role=button]` rule did not override it, so main
   showed the outline. Recommendation: delete `outline: 0;` from
   `a.button-link`. In the browser, removing that one declaration from the
   CSSOM brought back `rgb(24,28,37) solid 2px` on Collect sample and Order
   CBC, the same as Check for reports. `:focus-visible` keeps the outline off
   after a mouse click, as on main. A test that the rule has no `outline`
   would keep this from coming back.

## Observations

- On focus, Order CBC's box-shadow is one shadow instead of main's two (main
  adds a transparent zero shadow first). It looks the same.
- Pre-existing: at 375 the header overflows ("Log out" wraps).

## Not checked

- Fixing and rechecking the defect. Only the CSSOM experiment above was done.
- The active (pressed) state, a real screen reader, dark mode, other browsers,
  headed Chrome, and 320px width.
- Space on a link. As a link, it scrolls the page, which is expected.

## Recheck

I rechecked items 2 and 3 against commit b6a174e, which removes
`outline: 0` from `a.button-link`. The branch ran alone on `127.0.0.1:8629`
with a fresh practice folder. The seed, the two laboratories and the data were
the same as in the first run.

| # | Item | Result | Note |
|---|------|--------|------|
| 2 | Keyboard focus shows the same ring as a real button; hover unchanged | Pass | At 1400 and 375, Tab onto Collect sample and Order ferritin gives `outline: 2px solid rgb(24,28,37)` with a 2px offset and `:focus-visible` true. That is identical to Check for reports, including the focused fill `rgb(51,121,15)` and Pico's box-shadow (`recheck-{collect-sample,order-ferritin,check-for}-focus-{1400,375}`). Hover gives the same values as the first run: fill `rgb(51,121,15)`, no outline and no underline. |
| 3 | Secondary outline Order CBC | Pass | On keyboard focus it gets the same 2px contrast outline with a 2px offset, a transparent fill and grey `rgb(72,83,107)` text and border (`recheck-order-cbc-focus-{1400,375}`). Hover is unchanged: transparent fill, `rgb(72,83,107)` text and border, no outline. A mouse click focuses it without the outline (`:focus-visible` false), as on main. |

The defect above is fixed. The server log has no 5xx response.
