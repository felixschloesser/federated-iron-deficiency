# Browser check: narrow-header

A browser-check agent ran this check on 2026-11-05 against commit 42a744d. It
compared the branch with main's code, a `git archive main` export served the
same way. The browser was headless Chrome 156, driven over the DevTools
protocol by a small Node script. The Claude-in-Chrome extension was not used.

## Setup

- Servers, each with its own fresh untracked party folder, `DJANGO_DEBUG=1`,
  migrated, then seeded:
  - branch practice on `127.0.0.1:8631` and main practice on `127.0.0.1:8632`:
    `PRACTICE_DIR=… PARTY_COLOUR=green PRACTICE_NAME="Huisartsenpraktijk De
    Akker"`, `seed_practice --patients 5`.
  - branch hospital on `127.0.0.1:8633`: `HOSPITAL_DIR=… PARTY_COLOUR=violet
    HOSPITAL_NAME="Heilig Hart Leuven"`, `seed_hospital --patients 3`. No
    orders, so its pages are empty lists.
- Data, made in `manage.py shell` with `collect_sample` and `place_order`, the
  same on both practices:
  - Lien Willems (patient 1): a CBC with `sent_at` set and a `LabReport`
    (`results={}`, `ferritin_suggested=True`), so the Patients list shows
    "Ferritin suggested".
  - Laura Peeters (patient 2): sample 1 with a sent CBC ("Awaiting lab
    report") and sample 2 with an unsent CBC ("Lab order not sent yet").
- Practice pages as `doctor`: Patients, patient 1, patient 2, Orders. Hospital
  pages as `lab-1`: To analyse, Analysed. Logged out: the login page on all
  three servers.
- Widths 320, 375 and 1400 via `Emulation.setDeviceMetricsOverride`
  (`mobile` below 500). On each page the script read
  `document.documentElement.scrollWidth`, the box of every header item (name,
  links, Log out), whether any item leaves the viewport, wraps inside itself
  or overlaps another, and for each `<mark>` its line count and its
  paragraph's or cell's `scrollWidth`/`clientWidth`. Closed `<details>` were
  opened first so every mark was measured. Tab came from
  `Input.dispatchKeyEvent`.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | No sideways scroll at 320/375/1400; the header wraps cleanly | Pass | On every practice and hospital page, `scrollWidth` equals the viewport at all three widths. On main it was 385 at 320 and 375, with Log out at x 316–377 past the edge and the name broken over two lines. On the branch at 320 and 375 the name is one line on the first row (y 35–53). Patients and Orders (or To analyse and Analysed) and Log out share the second row, starting at x 16, the same left edge as the name. Nothing leaves the viewport, wraps inside itself or overlaps (`branch-*-{320,375}-top`, `hospital-*-{320,375}-top`, compared with `main-*-{320,375}-top`). The header is 186px high there, against 154 on main. |
| 2 | 1400px: header as before, one row | Pass | Every header item has the same box as on main, to the pixel. Practice: name 100–364, Patients 1011–1102, Orders 1102–1182, Log out 1192–1300. The header is 162px on both (`{branch,main}-*-1400-top`). The hospital header is one row too (`hospital-*-1400-top`). |
| 3 | Logged out: login page at all three widths | Pass | The header holds only the name, on one line, and `scrollWidth` equals the viewport at 320, 375 and 1400 for both parties. It is identical to main (`*-login-*-top`). |
| 4 | Marks stay one line; the row or paragraph wraps instead; nothing overflows | **Fail (Patients table at 320)** | Each mark is one line at every width: "Ferritin suggested" (140px), "Lab order not sent yet" and "Awaiting lab report". On main, "Ferritin suggested" broke over two lines at 320 and 375. On the patient page, the paragraph wraps after the mark ("· Ordered 5 Nov 2026, / 15:22"), and the paragraph's `scrollWidth` equals its `clientWidth` (256/256 at 320, 311/311 at 375) (`branch-practice_patients_2-{320,375}`). In the Patients list the mark stays inside its cell (172/172), under the name. **But the nowrap mark sets the Name column's minimum width, so the table no longer fits.** The table's `overflow-auto` wrapper scrolls 348/288 at 320, so the Age column is cut off until scrolled. At 375 it scrolls 348/343, and only the cell's right padding is lost. On main it was 288/288 and 343/343 (`branch-practice_patients-320` vs `main-practice_patients-320`). See Defect 1. Orders scrolls 560/288 and 560/343 on both branch and main, so that is not from this branch. |
| 5 | Keyboard: Tab order in the header unchanged, focus visible | Pass | Practice, at 1400 and at 375: Skip to content, Patients, Orders, Log out, then the search box. Main has the same order. Hospital: Skip to content, To analyse, Analysed, Log out. Each stop matches `:focus-visible` with `outline: 2px solid rgb(24,28,37)`. Log out's ring shows whole on the wrapped second row (`branch-tab4-375`, `hospital-tab4-375`, `branch-tab4-1400`). |

## Defects

1. **At 320px the Patients table scrolls sideways again, because of the
   marked patient.** `mark { white-space: nowrap; }` makes "Ferritin
   suggested" 140px wide that cannot shrink. With the cell's padding, that is
   the Name column's minimum width. Registered sex and Age no longer fit in
   288px, so the table's wrapper scrolls by 60px and Age sits off-screen. The
   page itself does not scroll, so item 1 still passes. Only one marked row
   is needed to cause this. The branch owner should choose between two
   options:
   - Accept a table that scrolls on the narrowest phones, as Orders already
     does.
   - Let the mark wrap between words and keep each line a whole chip:
     `mark { -webkit-box-decoration-break: clone; box-decoration-break:
     clone; }` instead of `white-space: nowrap`. Put in the live page as a
     test, this rule gives every line of the mark its own padding, which was
     the cosmetic problem from ferritin-mark. The wrapper then scrolls
     292/288 at 320, 4px instead of 60px with Age visible, and 343/343 at
     375 (`experiment-clone-patients-{320,375}`). The mark is no longer "one
     chip", so the branch's scenario would change.

## Observations

- In the header, Log out sits about 8–10px higher than the links' midline:
  its centre is at y 113, the links' at y 121 at 375. At 1400 the gap is
  71 vs 81. Main has the same offset at 1400, so it is not from this branch.
- At 320 and 375 the gap between the name row and the link row is about 35px,
  from Pico's nav padding. It reads as one header, but it is roomy for a
  phone.

## Not checked

- Fixing and rechecking the defect. Only the in-page style experiment was
  done.
- A hospital page with rows in it, the director's pages and a laboratory
  chooser. The hospital pages were empty lists.
- Widths between 375 and 1400 where the header first wraps. Longer party
  names. Dark mode, zoom or text-size changes, other browsers, headed Chrome,
  a screen reader.

## Recheck

I rechecked item 4, and spot-checked item 1, against commit 2073f23. In that
commit `mark` has `-webkit-box-decoration-break: clone;
box-decoration-break: clone` and no `white-space: nowrap`. Only the branch
practice ran, on `127.0.0.1:8631`, with a fresh practice folder. The seed and
the data were the same as in the first run. Screenshots are at
`deviceScaleFactor` 2.

| # | Item | Result | Note |
|---|------|--------|------|
| 4 | Patients list with "Ferritin suggested": table fits, Age visible | Pass | At 320 the table's wrapper scrolls 292/288. The 4px is the right padding of the Age cell: Age's header ends at x 308 and the wrapper at 304. The text "Age" and every age are in view (`recheck-patients-320`). This is 60px less than the first run's 348/288. At 375 the wrapper is 343/343 and at 1400 it is 1200/1200 (`recheck-patients-{375,1400}`). |
| 4 | The mark's look when wrapped | Pass | At 320 and 375 "Ferritin suggested" wraps between the words onto two lines (fragments 32–91 and 32–117). The computed `box-decoration-break` is `clone`, so each line has its own 4px padding on both sides, and the two lines share the same left edge. The second line is no longer offset (`recheck-mark-{320,375}`, at 3× zoom). At 1400 it is one line (235–404). The mark stays inside its cell (117/117 at 320, 159/159 at 375). |
| 4 | Patient page: "Lab order not sent yet", "Awaiting lab report" | Pass | Both marks are short enough to stay on one line at 320, 375 and 1400, with no change from the first run. Their paragraph wraps after the mark and does not overflow (256/256 at 320, 311/311 at 375, 1160/1160 at 1400) (`recheck-patient2-*`). |
| 1 | Spot-check: no page-level sideways scroll | Pass | On Patients, patients 1 and 2, and Orders at 320, 375 and 1400, the page's `scrollWidth` equals the viewport width. Orders' table still scrolls inside its own wrapper (560/288, 560/343), as it does on main. |

Defect 1 is fixed. The server log has no 5xx response.
