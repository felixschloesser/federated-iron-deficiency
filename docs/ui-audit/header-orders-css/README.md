# Browser check: header-orders-css

A browser-check agent ran this check on 2026-11-05 against commit 6f14d00. It
compared the branch with main (3865d80), using a `git archive main` export
served the same way. The browser was headless Chrome 156, driven over the
DevTools protocol by a small Node script. The Claude-in-Chrome extension was
not used.

The change under test: in `templates/kit/base.html`, the header's Log out
button no longer has `type="submit"`. Pico's `nav li button` rule now applies
to it, which sets `margin-bottom: 0`. Before the change, Pico's form-button
margin made Log out's list item taller than the links' items. The nav row
centres each item, so Log out sat 10px above the links' centre at 1400 and
8px above at 375.

## Setup

- Four servers, each with a fresh untracked party folder and `DJANGO_DEBUG=1`.
  Each was migrated, then seeded:
  - Practices: branch on `127.0.0.1:8635`, main on `127.0.0.1:8637`.
    `PRACTICE_DIR=… PARTY_COLOUR=green PRACTICE_NAME="Huisartsenpraktijk De
    Akker"`, seeded with `seed_practice --patients 5`. Each practice also got
    one primary `Laboratory`, added in `manage.py shell`, so that Collect
    sample and Check for reports show.
  - Hospitals: branch on `127.0.0.1:8636`, main on `127.0.0.1:8638`.
    `HOSPITAL_DIR=… PARTY_COLOUR=violet HOSPITAL_NAME="Heilig Hart Leuven"`,
    seeded with `seed_hospital --patients 3`.
- Pages:
  - Practice, as `doctor`: Patients, patient 1, Orders.
  - Hospital, as `staff`: To analyse and Analysed.
  - Hospital, as `director`: Screening models.
- Widths 1400, 375 and 320, set with `Emulation.setDeviceMetricsOverride`
  (`mobile` below 500). On each page the script read:
  - `document.documentElement.scrollWidth` and the header's height;
  - the bounding box of the party name, each nav link and Log out;
  - Log out's `type` and computed `margin-bottom`;
  - for the index header's action row: each button's box and
    `margin-bottom`, and the gap from the row to the next element.

  Δ means Log out's vertical centre minus the links' centre. Tab and Enter
  were sent with `Input.dispatchKeyEvent`. Screenshots are at
  `deviceScaleFactor` 2.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | 1400px: Log out's centre matches the links', one row | Pass | **Δ = 0** on every practice and hospital page. On main, Δ = −10. Log out's `margin-bottom` is 0 (20px on main). Its box is y 40–87 and the links' are y 39–89. Everything is on one row (`branch-practice-patients-1400`, `branch-hospital-to-analyse-1400`, `branch-director-models-1400`, compared with `main-*-1400`). |
| 2 | 375 and 320px: clean wrap, Log out lines up on the wrapped row, no sideways scroll | Pass | **Δ = 0** on every page at both widths; on main, Δ = −8. The name is one line on the first row (y 35–53, the same as on main). The links and Log out share the second row from x 16, with no overlap. `scrollWidth` equals the viewport on every page at 1400, 375 and 320 (`branch-*-{375,320}`). |
| 3 | Keyboard: Tab, Enter logs out, visible focus | Pass | Practice, at 1400 and 375: Skip to content, Patients, Orders, Log out. Hospital (staff): Skip to content, To analyse, Analysed, Log out. Every stop matches `:focus-visible`, with `outline: 2px solid rgb(24,28,37)`, and the ring around Log out shows whole on the wrapped row. The button's `type` still computes to `submit`, which is a button's default in a form. Enter on Log out sends the POST and lands on `/login/` ("Log in"), with no Log out in the header (`branch-*-tab-logout-*`, `branch-practice-after-logout-1400`). |
| 4 | Index header's action row unchanged against main | Pass | Patient 1 has Collect sample and Check for reports; Orders has Check for reports. Branch and main agree at 1400, 375 and 320:<br>• every button's x position, width and height;<br>• `margin-bottom` 0 on each button;<br>• the wrap onto two rows at 320, with 16px between them;<br>• the gap below the row: 20px at 1400, 16px at 375 and 320.<br>Only the whole row sits higher, by as much as the header got shorter: 35px at 1400, 28px at 375 and 320 (`{branch,main}-patient1-{1400,320}`, `{branch,main}-practice-orders-1400`). |

## Changes against main, beyond the alignment

Pico's nav button rule also gives Log out the compact nav padding, so the
button is smaller and the header is shorter:

| | Main | Branch |
|---|---|---|
| Log out at 1400 | 108 × 62 | 88 × 47 |
| Log out at 375 | 89 × 50 | 73 × 38 |
| Header height, 1400 / 375 / 320 | 162 / 186 / 186 | 127 / 158 / 158 |

At 1400 the links shift 20px right, because Log out is narrower and the row
is right-aligned. Practice: Patients 1031–1122 and Orders 1122–1202, against
1011–1102 and 1102–1182 on main. Log out's right edge stays at 1300. The
name stays at x 100–364 and moves up from y 69–92 to y 52–75. At 375 and
320 the name does not move. Log out's label still has room, and it reads
like the other header items (`branch-practice-tab-logout-375`). These
changes are not defects. They come from using Pico's own styling for a
button in a nav.

No defects found. The server logs have no 5xx response.

## Not checked

- Widths between 375 and 1400, longer party names.
- Dark mode, zoom, other browsers, headed Chrome, a screen reader.
- Hospital pages with rows in them. The hospital lists were empty.
