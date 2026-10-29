# Browser check: slice-ordering

## 1. Agent check, stopped partway (c98a33e, 2026-10-29)

A browser agent ran the checklist against the first version of the slice and
was stopped after placing orders; it wrote no item-by-item record. Its one
screenshot, `01-login-error.jpg`, shows the only defect it left evidence of:

1. A form-wide error (wrong password) appeared twice: in the error summary
   and again above the fields. Fixed in b51e919, with a view test.

## 2. Manual check (5c233a7, 2026-10-29)

Checked by hand by the project owner, `DJANGO_DEBUG=1`, `seed_demo` data,
after the later changes: class-based views, messages, kit error pages, one
order page per test, patient first, start page per role.

Checklist: login and refusal of a wrong password; Patients as start page and
header navigation; patient page with Order CBC / Order ferritin; CBC refused
without an indication, placed with one; ferritin as a confirmation; "Order
placed." message with its border; another general practitioner's patient not
found; account without a role refused at login; log out; keyboard (skip link,
tab order, focus ring); narrow and wide widths.

Result: reported as looking good, no defects. Item-by-item results were not
recorded.

Not checked: screen readers; browsers other than the owner's.
