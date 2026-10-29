# Hospital screening app: requirements

A server-rendered Django app that models one hospital's path of workflow for
the iron-deficiency screening in the PIA report (`report/report.typ`): a general practitioner
orders a blood test, the lab receives and analyses the sample, the deployed
model screens it, and the lab report reaches the ordering general practitioner. It implements
P7 (Screening) and P8 (Reporting) of the federated DFD and stands in for DF1,
DF16–DF20. Training (P3–P6) stays with Flower and is out of scope.

Method: KAOS goal model (goals, agents, obstacles, operations), refined into
the Gherkin scenarios under `features/`. Each requirement names the scenarios
that cover it.

## 1. Vocabulary

The PIA report is the first source, the WHO *Laboratory Quality Management
System Handbook* (2011, ISBN 9789241548274, `sources/9789241548274_eng.pdf`) the
second. The report was drafted with AI help, so a word that reads badly to lab
staff is replaced and the report's word moves to the rejected column.

| Term | Source | Why chosen | Rejected terms |
|---|---|---|---|
| general practitioner | Report, Stakeholders table ("GP", spelled out) | The report's orderer and reader of the lab report; spelled out everywhere in the app | GP (abbreviation), requester, ordering physician (WHO 5-4, p. 66) |
| patient | Report, Use case | The report's word | participant (NHANES word; data origin only) |
| order | Report, DF1 "lab order"; WHO glossary *path of workflow*, "physician's order" (p. 228) | Report and WHO agree | request, requisition (WHO), examination request (ISO 15189) |
| test | Report, Use case "ferritin test" | Order picks one: CBC or ferritin | examination (ISO 15189) |
| CBC (complete blood count) | Report, Use case | The report's word for the routine test | blood count (report uses both; one word only) |
| clinical indication | Report, Data table | The report's word; drives screening | reason for testing |
| non-specific complaint | Report, Data table and Use case | The one indication that is screened | fatigue work-up |
| registered sex | Report, Data table | Distinguishes the record from the person (report, Information at risk) | gender, sex |
| sample ID | Report, DF16 and Data table | The report's link between flag and lab report | laboratory identification number, accession number (WHO 5-4, p. 66) |
| received | WHO 5-4, "date and time the sample was received in the laboratory" (p. 66) | Moment the sample crosses into the hospital | registered, accessioned |
| analysed | Report, P1 "Lab analysis" | The report's process name | examined, tested |
| screening | Report, P7 | The report's process name | scoring, classification |
| ferritin suggested / ferritin not suggested / not screened | Report, Use case "a comment to the lab report suggesting ferritin"; "not screened" from DF18 | Names the action for the general practitioner; avoids the lab meaning of *flag* | flagged / not flagged (report, DF18; in a lab a *flag* marks an out-of-range value), possible iron deficiency (names a diagnosis) |
| awaiting screening | Built from *screening* (report, P7) | A sample analysed while no model is deployed | held, pending |
| deployed model | Report, DS5 | Model, threshold and standardization the hospital screens with | fingerprint, model version |
| threshold | Report, Design choices | The report's word | cutoff (reserved for ferritin's 15 ng/mL) |
| lab report | Report, DF20 | The report's word | test report (WHO p. 193) |
| comment | Report, Use case; WHO report contents "applicable comments" (p. 193) | Both sources | interpretive comment |
| read | — **unsourced** | A general practitioner marks a lab report as read | seen, acknowledged |

Open: *read* has no source. It stays flagged until one is found or the term is
replaced.

## 2. Goal model

Notation: `Achieve[…]` (eventually true), `Maintain[…]` (always true),
`Avoid[…]` (never true). Requirements are goals assigned to a software agent;
expectations are goals assigned to a person, which the app cannot enforce.

```
G0 Achieve[Ferritin suggested to the general practitioner of a likely iron-deficient woman aged 18–49]   (report, Use case)
├── G1 Achieve[Order reaches the lab]
│   ├── E1 Expectation[general practitioner picks the true clinical indication]                         general practitioner
│   └── R1 Achieve[Order carries patient's registered sex, age, test, indication]      Practice app
├── G2 Achieve[Sample analysed]
│   ├── R2 Achieve[Sample received, sample ID assigned]                              Lab technician + Lab app
│   └── R3 Achieve[Analyser result recorded]                                         Lab technician + Analyser
├── G3 Achieve[Screening result recorded for every analysed CBC]
│   ├── R4 Maintain[Screened only if non-specific complaint, female, aged 18–49]       Lab app
│   ├── R5 Maintain[Not-screened reason recorded]                                    Lab app
│   ├── R6 Maintain[Result traceable to the deployed model]                           Lab app
│   └── R7 Avoid[Score stored]                                                       Lab app
├── G4 Achieve[Lab report visible to the ordering general practitioner]
│   ├── R8 Avoid[Lab report of a CBC visible before screening]                       Practice app
│   ├── R9 Maintain[Comment only when ferritin suggested]                            Practice app
│   └── R10 Achieve[general practitioner can mark a lab report as read]                                Practice app
└── G5 Achieve[Ferritin follow-up from a lab report]
    ├── R11 Achieve[Order ferritin offered when ferritin suggested and not yet ordered]  Practice app
    └── R12 Achieve[Ferritin result recorded, never screened]                         Lab app + Analyser

P0 Maintain[Patient data seen only by those who need it]   (report, Part 2)
├── R13 Maintain[A general practitioner sees only their own patients, orders and lab reports]           Practice app
├── R14 Avoid[Patient name at the lab]                                               Lab app
└── R15 Avoid[Demo login outside development]                                        Settings + system check
```

### Requirements

| ID | Requirement | Scenarios |
|---|---|---|
| R1 | An order records the patient, the test (CBC or ferritin), and, for a CBC only, the clinical indication. It copies the patient's registered sex and age, which is all the lab learns about the patient. Ferritin orders have no indication (`None`). | `ordering.feature` |
| R2 | Receiving an order creates its sample and assigns a sample ID. An order is received at most once. | `lab.feature` |
| R3 | Running the analyser on a received sample records the patient's NHANES values: the 13 CBC values for a CBC, ferritin in ng/mL for ferritin, or *not available in the demo data* when NHANES has none. A sample is analysed at most once. | `lab.feature` |
| R4 | A CBC is screened only when the indication is non-specific complaint, registered sex is female and age is 18–49. Each condition is its own branch. | `screening.feature` |
| R5 | A CBC that is not screened records the first failing condition, in the order indication, registered sex, age. | `screening.feature` |
| R6 | A screening result records the deployed model's SHA-256 and threshold. | `screening.feature` |
| R7 | No score, probability or standardized input is stored or shown. | `screening.feature` |
| R8 | With no deployed model, an analysed CBC is *awaiting screening*; its lab report is not visible and *Screen* is refused beside the action. Once a model is deployed, *Screen* records the result. | `screening.feature` |
| R9 | The lab report shows the results; the comment appears only for *ferritin suggested*. *Ferritin not suggested* and *not screened* show nothing about screening. | `reports.feature` |
| R10 | A general practitioner marks a lab report as read with a POST; the reports index shows unread ones. | `reports.feature` |
| R11 | *Order ferritin* is offered on a lab report with *ferritin suggested* when the patient has no ferritin order after it; it opens the ferritin order page with the patient filled in. | `reports.feature` |
| R12 | A ferritin sample is never screened; its lab report is visible once analysed. | `lab.feature` |
| R13 | Every general practitioner query is scoped to the general practitioner's own patients; another general practitioner's order or lab report returns 404. | `access.feature` |
| R14 | Lab queries select only sample ID, ordering general practitioner, registered sex, age, test, indication and results; never the patient's name. | `access.feature` |
| R15 | `DEMO_LOGIN` (default off) shows one POST login button per seeded user. A deploy check fails when `DEMO_LOGIN` is on and `DEBUG` is off. | `access.feature` |

## 3. Agents

| Agent | Kind | Responsible for |
|---|---|---|
| general practitioner | Person | E1; uses R1, R10, R11 |
| Lab technician | Person | Triggers R2, R3, R8 (*Screen*) |
| Practice app (`practice`) | Software | R1, R8 (visibility), R9–R11, R13 |
| Lab app (`lab`) | Software | R2–R8, R12, R14 |
| Analyser | Software, stand-in | Returns the patient's NHANES 2021–2023 values (R3, R12) |
| Deployed model | Environment | Produced by Flower training (report, DF15); read from `DEPLOYED_MODEL_PATH` |
| Seed command (`seed_demo`) | Software | Creates general practitioners, lab technicians and patients from NHANES 2021–2023 with obviously synthetic names |

## 4. Obstacles

| ID | Obstacle | Obstructs | Resolution |
|---|---|---|---|
| O1 | general practitioner picks the wrong clinical indication | E1, R4 | Accepted: the app cannot know the complaint (report, Assumptions) |
| O2 | Threshold 0.5 has no clinical basis, so suggestions are wrong | G0 | Accepted; no clinical-biologist review in scope. Ferritin follow-up (G5) makes errors visible |
| O3 | No deployed model when a CBC is analysed | G3 | R8: awaiting screening, report not visible, *Screen* later |
| O4 | Model screens people it was not trained on | G0 | R4 |
| O5 | A general practitioner opens another general practitioner's lab report by URL | P0 | R13 |
| O6 | Lab sees who the patient is | P0 | R14, R1 (the order copies only sex and age) |
| O7 | Model retrained between screenings | R6 | R6 |
| O8 | NHANES has no ferritin for the patient | R12 | R3: *not available in the demo data* |
| O9 | Demo login shipped to a deployment | P0 | R15 |
| O10 | The score reveals more than the result | P0 | R7 |

## 5. Operations

All are POSTs that redirect on success; services take `now`.

| Operation | Actor | Precondition | Postcondition | Requirements |
|---|---|---|---|---|
| Place order | general practitioner | Patient is the general practitioner's; indication given iff test is CBC | Order with sex and age copied | R1, R13 |
| Receive | Lab technician | Order not received | Sample with sample ID, received at `now` | R2 |
| Run analyser | Lab technician | Sample received, not analysed | Values recorded; CBC screened at once if a model is deployed, else awaiting screening | R3, R8, R12 |
| Screen | Lab technician | CBC awaiting screening; model deployed | Screening result with model SHA-256 and threshold | R4–R8 |
| Mark as read | general practitioner | Lab report visible to this general practitioner, unread | Read at `now` | R10, R13 |
| Log in as (demo) | Anyone | `DEMO_LOGIN` on | Session for that seeded user | R15 |

## 6. Pages

| Page | Role | Content |
|---|---|---|
| Log in | Anyone | Django login form; demo buttons when `DEMO_LOGIN` |
| Lab reports (general practitioner index) | general practitioner | Own lab reports, newest first, unread marked; pending orders |
| Lab report | general practitioner | Results, comment (R9), *Mark as read*, *Order ferritin* (R11) |
| Order CBC, Order ferritin | general practitioner | One page per test: patient, and the clinical indication only for a test that takes one |
| Samples (lab index) | Lab technician | Orders to receive, samples to analyse, awaiting screening, screened; *Receive*, *Run analyser*, *Screen* |

Index pages assert their query count. Conditional controls (*Order ferritin*,
*Screen* and its refusal) are decided in query functions and tested there.

## 7. Out of scope

- Clinical-biologist review before release (O2 accepted)
- Access log of who viewed what (the report's adversaries attack the model, not this app)
- Email or other notification outside the app
- More than one test per order
- Free-text clinical notes
- Several hospitals in one deployment (one deployment per hospital; the general practitioner side sits inside the hospital's deployment, unlike the DFD)
- Retention and deletion of samples and lab reports
- Training, federation and model distribution (Flower, report P3–P6)

## 8. Data

- Patients: NHANES 2021–2023 (`iron_deficiency.dataset.load_new_samples`), all sexes and ages. `load_new_samples` must also return ferritin (`LBXFER`), which the analyser alone reads.
- Ferritin exists in NHANES mainly for women aged 12–49; others get *not available in the demo data*.
- Age is the NHANES age at the survey and does not change.
- Registered sex has the two NHANES values, female and male.
