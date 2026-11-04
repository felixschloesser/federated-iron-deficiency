# Browser check: patient-check-reports-2

A browser-check agent ran this check on 2026-11-04 against commit 522cf4b. The
browser was headless Chrome 156, driven over the DevTools protocol by a small
script. The Claude-in-Chrome extension was not connected.

## Setup

- Server: `127.0.0.1:8619`, run with `uv run` from the worktree, with
  `PRACTICE_DIR=<worktree>/.ui-audit-pcr2/practice PARTY_COLOUR=green
  PRACTICE_NAME="Huisartsenpraktijk De Akker" DJANGO_DEBUG=1`. It was
  migrated, then seeded with `seed_practice --patients 4`.
- Laboratories were added in three phases on the same server and database:
  1. No laboratory.
  2. One laboratory: `add_laboratory "UZ Leuven" 127.0.0.1:1`.
  3. Two laboratories: `add_laboratory "AZ Groeninge" 127.0.0.1:1`.

  The certificates for both came from `tools/certificates.py`
  (`make_authority`, `issue(..., server=False)`, plus `ca.crt` copied in).
  Nothing listens on 127.0.0.1:1, so every laboratory is unreachable.
- Data, made in `manage.py shell` after phase 2:
  - Lien Willems: a sample for UZ Leuven and a CBC (suspected anaemia), with
    `sent_at` set, so the order is sent and awaiting a report.
  - Lotte Jacobs: a sample for UZ Leuven and a CBC (unexplained fatigue), not
    sent.
- Logged in as `doctor`. Widths were set with
  `Emulation.setDeviceMetricsOverride`. Keyboard input came from
  `Input.dispatchKeyEvent` (Tab, Enter). Every press of Check for reports
  below was Enter on the focused button.

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | One laboratory: both buttons in one row with a visible gap; Tab reaches both; focus visible | Pass | The `.action-row` is `display: flex; flex-wrap: wrap; gap: 20px` at 1400. It holds two POST forms: `/practice/patients/1/samples/collect/` and `/practice/patients/1/check-for-reports/`. Collect sample is at x 100–272 and Check for reports at x 292–487, so the gap is 20px. Both are 62px tall and sit on the same top edge (`03`). Tab order: Skip to content → Patients → Orders → Log out → **Collect sample** → **Check for reports**. Each focused button has a 2px solid outline in the text colour (`04`, `05`). |
| 2 | Several laboratories: the Collect sample link and the Check for reports button sit together cleanly; the link still opens the choice page | Pass | Collect sample is now an `a`, and the row has one form (check-for-reports). The link and the button have the same size (172×62 and 195×62), the same fill and the same vertical centre (308). The gap is 20px, and the two look the same (`10-…-1400`). Tab order is the same as in item 1, and the link has the same 2px focus outline (`11`, `12`). Enter on the link opens `/practice/patients/1/samples/collect/`, which is titled "Collect sample" and offers AZ Groeninge and UZ Leuven (`13`). |
| 3 | Check for reports on the patient page returns to that patient with one error per unreachable laboratory; no crash | Pass | With one laboratory, the POST gets a 302 back to `/practice/patients/1/`, which shows "UZ Leuven could not be reached. Try again later." in a `role="status"` alert above the h1 (`06`). With two, it shows two separate alerts, "AZ Groeninge could not be reached. Try again later." and "UZ Leuven …", in name order (`14`). It answered in about 0.1s. The server log has no 500 and no traceback. |
| 4 | The hint is worded exactly under a sent, awaited order; there is none under an unsent one | Pass | Lien's markup is `<mark>Awaiting lab report</mark> · Ordered 4 Nov 2026, 10:06<br><small>Check for reports to fetch it.</small>` (`03`). Lotte's reads "Lab order not sent yet · Ordered …", and `main` has no `small` (`07`). |
| 5 | No laboratory: no Check for reports on the patient page or on Orders | Pass | In phase 1, Lien's page has only the Collect sample form in `main` (`01`). Orders has no form and no button in `main` (`02`). |
| 6 | Orders: its button still works and returns to Orders | Pass | It is the only button in the action row, a POST to `/practice/orders/check-for-reports/`, and it comes after Log out in Tab order. Enter gets a 302 back to `/practice/orders/` with the error for UZ Leuven (`09`), and with two laboratories the errors for both (`15`). |
| 7 | 375, 1400 and 320: the buttons wrap with an even gap; they cause no horizontal scroll | Pass | At 1400 the page `scrollWidth` 1400 = `clientWidth` 1400. At 375 the gap is 16px and both items fit on one line (16–157 and 173–334, row 343) (`08-…-375`, `10-…-375`). At 320, Check for reports wraps under Collect sample, left-aligned, 16px below it, which matches the 16px column gap (`08-…-320`, `10-…-320`). The row's `scrollWidth` equals its `clientWidth` at every width, and so does `main`'s. The page `scrollWidth` is 385 at 375 and at 320, which comes from the header (known, separate). |

## Observations

1. **The two-laboratory row looks the same as the one-laboratory row.** The
   link and the button cannot be told apart by look, which is what was
   intended. A screen reader announces one as a link and the other as a
   button.
2. **The errors stack as one alert per laboratory.** With two laboratories,
   two full-width alerts push the patient's name about 90px down (`14`). The
   alerts are still readable, but with many laboratories they would crowd the
   top of the page. This is not a defect at two.
3. **Order ferritin shows under a CBC that has no report yet.** This happens
   on Lien's page. It comes from earlier work, not from this branch, and was
   not examined.
4. **Pre-existing: the header overflows at 375px.** `scrollWidth` is 385
   because "Log out" wraps.

## Defects

None found on this branch.

## Not checked

- A laboratory that answers. No report was fetched, so the success message
  ("fetched"/"sent") was not seen.
- A laboratory that refuses a message ("… refused a message. Tell the
  administrator.").
- A practice that has a laboratory but no `PRACTICE_DIR`.
- A screen reader, dark mode, other browsers, headed Chrome, and the mouse.
- Where focus lands after the redirect. The page reloads, so focus starts at
  the top of the document, as on any full-page load.
