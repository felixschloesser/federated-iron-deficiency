# Browser check: no-timers

A browser-check agent ran this check on 2026-11-03 against commit 0024ea7. The
browser was headless Chrome 156, driven over the DevTools protocol by a small
script. The Claude-in-Chrome extension was not connected.

## Setup

- Server A, practice with messaging, `127.0.0.1:8613`:
  `PRACTICE_DIR=<worktree>/.ui-audit-practice MESSAGING_ADDRESS=127.0.0.1:1
  PARTY_COLOUR=green PRACTICE_NAME="Huisartsenpraktijk De Akker"
  DJANGO_DEBUG=1`, run with `uv run`. The certificates were made with
  `tools/certificates.py` (`make_authority`, `issue(..., server=False)`, plus
  `ca.crt` copied in). It was migrated, then seeded with
  `seed_practice --patients 4`. Nothing listens on 127.0.0.1:1, so the
  hospital is unreachable.
- Server B, the same practice without messaging, `127.0.0.1:8614`: the same
  `PRACTICE_DIR` and database, with `MESSAGING_ADDRESS` unset.
- Data, entered through the UI on A while logged in as `doctor`:
  - Lien Willems: a sample and a CBC (suspected anaemia). The send failed
    because the hospital was down. `Order.sent_at` was then set in
    `manage.py shell`, so the order is sent and awaiting a report.
  - Lotte Jacobs: a sample and a CBC (unexplained fatigue), not sent.
- Widths were set with `Emulation.setDeviceMetricsOverride`, which is a real
  viewport change, not an iframe copy. Keyboard input came from
  `Input.dispatchKeyEvent` (Tab, Enter).

## Checklist

| # | Item | Result | Note |
|---|------|--------|------|
| 1 | Sent order awaiting a report: chip, then the hint on its own line in small text, exact wording | Pass | The markup is `<mark>Awaiting lab report</mark> · Ordered 3 Nov 2026, 20:47<br><small>Check for reports on Orders to fetch it.</small>`. The hint is 16.67px under 20px body text, and its line starts 35px below the chip (`01`). |
| 2 | Order not sent yet: "Lab order not sent yet", no hint | Pass | `<mark>Lab order not sent yet</mark> · Ordered …`, with no `<small>` in `main` (`03`). |
| 3 | Without `MESSAGING_ADDRESS`: no hint, no Check for reports | Pass | On B, Lien's sent order shows "Awaiting lab report" with no hint (`09`). The Orders page on B has no form and no button in `main` (`10`). |
| 4 | Orders: Check for reports present, keyboard-reachable, sensible error with the hospital down | Pass | It is a POST form to `/practice/orders/check-for-reports/` (`04`). Tab order: Skip to content → Patients → Orders → Log out → **Check for reports** → Lotte Jacobs → Lien Willems. The button has a 2px solid ring in the text colour (`05`). Pressing Enter on it posts, gets a 302 and redirects to Orders, which shows the red alert "The hospital could not be reached. Try again later." above the h1. It answered in well under a second, with no 500 (`08`). |
| 5 | "Orders" in the hint matches the navigation label | Pass | The header nav reads "Patients", "Orders", "Log out", and the Orders page's h1 is "Orders". |
| 6 | 375px and 1400px: the hint wraps cleanly, with no horizontal scroll | Pass for the hint; see observation 1 for the page | At 1400: `scrollWidth` 1400 = `clientWidth` 1400 (`01`). At 375 the hint fits on one line (right edge 272px, card edge 359px), so it does not need to wrap (`02`). At 300px it wraps to two lines inside the card (right edge 257, card 284) (`07`). |

## Observations

1. **Pre-existing, not this branch: the header overflows at 375px.** On both the
   patient page and Orders, `scrollWidth` is 385 at 375px. The nav `ul`
   reaches 385px because "Log out" wraps and sticks out (`02`, `06`). The
   login-errors check reported the same overflow.
2. **The hint names Orders but does not link to it.** "Orders" is plain text.
   The nav link is one Tab away, so this works. A link would save the user a
   step, but it would add a second focus stop with the same target.
3. **Orders does not show which orders are sent.** After the hint sends the
   user to Orders, the "Lab report" column shows "—" for both the sent order
   and the unsent one (`08`). The user cannot tell from that page what Check
   for reports will fetch and what it will send. This predates the branch.
4. **The nav does not mark the current page.** No nav link has
   `aria-current`, so on Orders nothing shows that you are on Orders.
   This predates the branch.

## Defects

None found on this branch.

## Not checked

- A successful Check for reports, or a reachable hospital that refuses the
  message ("The hospital refused a message …"). No hospital was running.
- The hint after a report arrives. With no hospital, no report could be
  released. Its absence for a released report is covered by the template
  condition and the view tests, not by this check.
- Pressing Check for reports with Space, or with the mouse. Only Enter was
  used.
- Screen readers, dark mode, other browsers, and headed Chrome. The
  extension was offline, so every page was rendered in headless Chrome.
