# Browser check: slice-lab

Manual check by the project owner of 1f84dad, 2026-10-29, with `DJANGO_DEBUG=1`
and `seed_demo` data (NHANES patients).

Checklist: a general practitioner orders a CBC and a ferritin; laboratory
staff land on Samples and see both orders to receive with no patient name;
Receive moves an order to "Samples to analyse" with "Sample … received.";
Run analyser moves it to "Analysed"; a laboratory staff member opening a
general practitioner's page lands on Samples with "That page is for general
practitioners.", and the reverse; keyboard; action buttons in table rows at
narrow and wide widths.

Result: reported as all good, no defects. Item-by-item results were not
recorded.

Not checked: screen readers; browsers other than the owner's.
