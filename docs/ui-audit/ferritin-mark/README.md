# Browser check: ferritin-mark

A browser-check agent ran this check on 2026-11-04 against commit aa75411. The
browser was headless Chrome 156, driven over the DevTools protocol by a small
script. The Claude-in-Chrome extension was not connected.

## Setup

- Server: `127.0.0.1:8617`, run with `uv run` from the worktree, with
  `PRACTICE_DIR=<worktree>/.ui-audit-practice PARTY_COLOUR=green
  PRACTICE_NAME="Huisartsenpraktijk De Akker" DJANGO_DEBUG=1`. No
  `MESSAGING_ADDRESS`. It was migrated, then seeded with
  `seed_practice --patients 5`.
- Data, made in `manage.py shell`: for Lien Willems, `collect_sample`, then
  `place_order` for a CBC (suspected anaemia), then a `LabReport` with
  `results={}`, `ferritin_suggested=True` and `released_at` and `fetched_at`
  set to now. The other four patients have no samples.
- Logged in as `doctor`. Widths were set with
  `Emulation.setDeviceMetricsOverride`. Keyboard input came from
  `Input.dispatchKeyEvent` (Tab, Enter), and search text from
  `Input.insertText` into the search box.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Patients page: one table, the mark after the name in the same cell, readable, not part of the link; other rows unmarked | Pass | `main` has 1 table and no `h2`. Lien's cell is `<a href="/practice/patients/1/">Lien Willems</a> <mark>Ferritin suggested</mark>`. The mark is outside the `a`, in dark text (rgb 15,17,20) on a pale amber background, not underlined. The link is green and underlined, and there is a 5px gap between them at 1400. It has the same font size as the name. The other four rows have no mark (`01`). |
| 2 | Search by name works and keeps the mark | Pass | The search box was filled and submitted with Enter. `q=Lien` gives Lien only, with the mark (`04`). `q=willems` gives Lien with the mark. `q=Lotte` gives Lotte with no mark. `q=L` gives four rows, and only Lien has the mark (`05`). |
| 3 | Order ferritin on the patient's page beside the lab report; after ordering, the mark is gone | Pass | Lien's page shows the CBC, "Lab report released …", the suggestion comment and the **Order ferritin** button under it (`aria-label="Order ferritin on sample 135318-1"`) (`07`, `08` at 375). Enter on it opens "Order ferritin for Lien Willems" with a Place order button (`09`). Enter on Place order redirects to the patient page, which says "Ferritin ordered on sample 135318-1." and lists the ferritin order. Order ferritin is gone (`10`). Back on Patients, `main` has 0 `mark` elements (`11`). |
| 4 | Keyboard: Tab order through the list is sensible; the mark is not focusable | Pass | Tab order: Skip to content → Patients → Orders → Log out → search box → Search → Laura Peeters → **Lien Willems** → Lotte Jacobs → Luc De Smet → Sofie De Smet → (out of page). The mark has `tabIndex` -1 and is never focused. The focus ring wraps the name only, with the mark outside it (`06`). From Lien's page, Order ferritin is 7 Tabs from the top. |
| 5 | 375px and 1400px: name plus mark wraps cleanly, no horizontal scroll from it | Pass | At 1400, `scrollWidth` 1400 = `clientWidth` 1400 and everything is on one line (`01`). At 375 the Name cell is 158px wide, so the mark drops under the name onto two lines ("Ferritin" / "suggested"), all inside the cell. The table's `scrollWidth` 343 = its wrapper's 343 (`02`). At 320 the name wraps too, and the table is still 288 = 288 (`03`). The page's `scrollWidth` is 385 at 375 and at 320, which comes from the header (known, separate issue). |

## Observations

1. **The mark breaks inside itself at narrow widths.** At 375 and 320,
   "Ferritin suggested" splits across two lines. The amber background breaks
   with it: the first line has padding on its left edge and the second line
   does not, so the second line looks slightly offset (`02`, `03`). It is
   still readable and still inside the cell. Keeping the two words together
   on one line, for example with `white-space: nowrap` on the mark, would
   tidy it up, but that needs a class in `static/css/`. This is cosmetic,
   not a defect.
2. **The column widths shift when the mark goes away.** The table uses auto
   layout, so the wider Name cell with the mark pushes Registered sex
   rightwards (795px vs 595px at 1400, `01` vs `11`). This is harmless.
3. **Pre-existing: the header overflows at 375px.** `scrollWidth` is 385, as
   reported in earlier checks.

## Defects

None found on this branch.

## Not checked

- A screen reader. The mark has no extra text or role, so whether "Ferritin
  suggested" is announced as highlighted depends on the reader. The words are
  in the cell's text either way.
- A lab report that came from the hospital over messaging. The report was
  made in the shell, with empty results.
- Two or more marked patients, or a marked patient whose name is long.
- Dark mode, other browsers, headed Chrome, and the mouse.
