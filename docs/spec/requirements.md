# Hospital screening app: requirements

A server-rendered Django app that models the path of workflow for the
iron-deficiency screening in the PIA report (`report/report.typ`): a general
practitioner orders a blood test, the hospital's laboratory receives and
analyses the sample, the deployed model screens it, and the lab report reaches
the ordering general practitioner. The same code runs as two kinds of
deployment: each **hospital** (TB1: P5, P7–P9, DS1, DS5, DS6, DS8) and
each **general practitioner's own app** (TB3: P6, DS7), which exchange the
lab order (DF23) and the lab report (DF25) as messages (§10). It also covers
the hospital's side of DF8/DF16: which final model the hospital deploys.
Training itself (P2–P4) stays with Flower.

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
| laboratory staff | WHO LQMS, the handbook's word for the people who work in the laboratory (44 uses; e.g. ch. 5, Sample management) | Receive samples and run the analyser; one record per person (`LaboratoryStaffMember`) | lab technician ("technician" in WHO LQMS means equipment service only), technologist (a qualified grade), laboratorian, laboratory worker |
| patient | Report, Use case | The report's word | participant (NHANES word; data origin only) |
| order | Report, DF23 "lab order"; WHO glossary *path of workflow*, "physician's order" (p. 228) | Report and WHO agree | request, requisition (WHO), examination request (ISO 15189) |
| test | Report, Use case "ferritin test" | Order picks one: CBC or ferritin | examination (ISO 15189) |
| CBC (complete blood count) | Report, Use case | The report's word for the routine test | blood count (report uses both; one word only) |
| clinical indication | Report, Data table | The report's word; drives screening | reason for testing |
| non-specific complaint | Report, Data table and Use case | The one indication that is screened | fatigue work-up |
| registered sex | Report, Data table | Distinguishes the record from the person (report, Information at risk) | gender, sex |
| sample ID | Report, DF23 and Data table | The report's link between lab order, results and lab report; on the tube's label when the first test is ordered. In the demo it is the patient's NHANES number (one sample per patient) | laboratory identification number, accession number (WHO 5-4, p. 66) |
| stored sample | WHO LQMS 5-5, p. 68, "stored samples" | A sample the laboratory already holds: a later test is measured on it, without receiving it again | add-on test, retained sample |
| received | WHO 5-4, "date and time the sample was received in the laboratory" (p. 66) | Moment the sample crosses into the hospital | registered, accessioned |
| analysed | Report, P1 "Lab analysis" | The report's process name | examined, tested |
| screening | Report, P7 | The report's process name | scoring, classification |
| screening result | Report, DF32 "screening result", P9 | What screening records per CBC: one of the three below, with the reason when not screened (R5) and the final model when screened (R6) | flag, outcome, classification |
| ferritin suggested / ferritin not suggested / not screened | Report, Use case "a comment to the lab report suggesting ferritin"; "not screened" from Federated version | Names the action for the general practitioner; avoids the lab meaning of *flag* | flagged / not flagged (an earlier report draft; in a lab a *flag* marks an out-of-range value), possible iron deficiency (names a diagnosis) |
| final model | Report, DS4, DF8 "final model, threshold" | What one training run sends to every hospital; stored there with its run ID and local validation | release, model version |
| deploy | Report, Use case: the model "is then deployed to every hospital" | The laboratory director's decision that a final model screens this hospital's patients | activate, release, roll out |
| deployment (of a party) | Flower documentation, "Deployment Engine": running the federation on real nodes, not in simulation | One party's running copy of the code, in its own folder (§9); never a final model being deployed | installation, instance |
| deployed model | Report, DF30, DF31 "deployed final model" | The final model this hospital deployed last; the only one that screens | active release, fingerprint |
| laboratory director | WHO LQMS ch. 2, p. 21: the director assesses "all potential risks … including services to patients" (20 uses) | Decides which final model screens patients | clinical biologist (not in either source), quality manager (WHO: runs the quality system, does not decide), laboratory manager |
| local validation | Built from *validation* (report, DF10 "validation example count") | A final model on this hospital's own validation split: the confusion matrix at its threshold, as counts, then AUROC | local evaluation, shadow run, flag rate |
| threshold | Report, Design choices | The report's word | cutoff (reserved for ferritin's 15 ng/mL) |
| lab report | Report, DF25 | The report's word | test report (WHO p. 193) |
| comment | Report, Use case; WHO report contents "applicable comments" (p. 193) | Both sources | interpretive comment |
| CBC value names and units, e.g. *Hemoglobin*, g/dL | NHANES 2021–2023 CBC_L codebook, SAS labels (`sources/nhanes-2021-2023-CBC_L.htm`) | The values are NHANES's own, in its units; no conversion | Hb, Ht and other report abbreviations (no source; other units) |
| Ferritin, ng/mL | NHANES 2021–2023 FERTIN_L codebook (`sources/nhanes-2021-2023-FERTIN_L.htm`) | As above | µg/L (LBDFERSI) |

## 2. Goal model

Notation: `Achieve[…]` (eventually true), `Maintain[…]` (always true),
`Avoid[…]` (never true). Requirements are goals assigned to a software agent;
expectations are goals assigned to a person, which the app cannot enforce.

```
G0 Achieve[Ferritin suggested to the general practitioner of a likely iron-deficient woman aged 18–49]   (report, Use case)
├── G1 Achieve[Order reaches the lab]
│   ├── E1 Expectation[general practitioner picks the true clinical indication]                         general practitioner
│   ├── R1 Achieve[Order carries patient's registered sex, age, test, indication]      General practitioner's app
│   ├── R22 Achieve[Lab order delivered to the general practitioner's hospital]       General practitioner's app + messaging
│   └── R26 Maintain[One sample per patient; each test ordered at most once]          General practitioner's app
├── G2 Achieve[Sample analysed]
│   ├── R2 Achieve[Sample received; a later test uses the stored sample]             Laboratory staff + Lab app
│   └── R3 Achieve[Analyser result recorded]                                         Laboratory staff + Analyser
├── G3 Achieve[Screening result recorded for every analysed CBC]
│   ├── R4 Maintain[Screened only if non-specific complaint, female, aged 18–49]       Lab app
│   ├── R5 Maintain[Not-screened reason recorded]                                    Lab app
│   ├── R6 Maintain[Result traceable to the final model that produced it]             Lab app
│   └── R7 Avoid[Score stored]                                                       Lab app
├── G4 Achieve[Lab report visible to the ordering general practitioner]
│   ├── R8 Achieve[Lab report released at once, screened or not]                     Lab app
│   └── R9 Maintain[Comment only when ferritin suggested]                            Practice app
└── G5 Achieve[Ferritin follow-up from a lab report]
    ├── R11 Achieve[Order ferritin offered when ferritin suggested and not yet ordered]  Practice app
    └── R12 Achieve[Ferritin result recorded, never screened]                         Lab app + Analyser

G6 Maintain[Only a final model the hospital deployed screens its patients]
├── R16 Achieve[Each final model stored at the hospital with run ID, threshold and local validation]  ClientApp
├── R17 Maintain[A final model that cannot be deployed shows why, and has no Deploy]  Deploy app
├── E2 Expectation[Laboratory director deploys only after comparing local validation]  Laboratory director
├── R18 Achieve[Deploying a final model makes it the deployed model; an older one rolls back]  Deploy app
└── R19 Maintain[Screening uses the deployed model only while its SHA-256 matches]   Lab app

P0 Maintain[Patient data seen only by those who need it]   (report, Part 2)
├── R13 Maintain[A general practitioner sees only their own patients, orders and lab reports]           Practice app
├── R14 Avoid[Patient name at the lab]                                               Lab app
├── R15 Avoid[Demo login outside development]                                        Settings + system check
├── R20 Avoid[A hospital learns another hospital's metrics]                          ClientApp
└── R21 Maintain[Each party's software and data stay inside its trust boundary]      Settings + audit + launcher
```

### Requirements

| ID | Requirement | Scenarios |
|---|---|---|
| R1 | An order records the patient, the sample ID, the test (CBC or ferritin), and, for a CBC only, the clinical indication. It copies the patient's registered sex and age, which is all the lab learns about the patient. Ferritin orders have no indication (`None`). | `ordering.feature` |
| R2 | Receiving registers that a sample's tube arrived; a sample is received at most once. A test ordered for a stored sample needs no receiving and can be analysed at once. | `lab.feature` |
| R3 | Running the analyser on a received sample records the patient's NHANES values: the 13 CBC values for a CBC, ferritin in ng/mL for ferritin, or *not available in the demo data* when NHANES has none. A sample is analysed at most once. | `lab.feature` |
| R4 | A CBC is screened only when the indication is non-specific complaint, registered sex is female and age is 18–49. Each condition is its own branch. | `screening.feature` |
| R5 | A CBC that is not screened records why: the first failing condition, in the order indication, registered sex, age; else that there is no usable deployed model (none deployed, or changed on disk). | `screening.feature` |
| R6 | A screening result records the final model that produced it (run ID, SHA-256, threshold). | `screening.feature` |
| R7 | No score, probability or standardized input is stored or shown. | `screening.feature` |
| R8 | Running the analyser on a CBC screens it at once, and its lab report is released at once. Without a usable deployed model (R19) a CBC that meets R4 is *not screened* with that reason: the general practitioner's CBC never waits for the startup's model, and is not screened again later. Screening runs in the same transaction as the analysis, so an analysed lab order is a released lab report; there is no separate release step. | `screening.feature` |
| R9 | The lab report shows the values under NHANES's names and units, without reference ranges or any mark; the comment *Ferritin suggested.* appears only for *ferritin suggested*. The hospital sends one bit, *ferritin suggested*, so *ferritin not suggested* and *not screened* look the same at the practice and show nothing about screening. | `screening.feature` (the bit the hospital sends), `messaging.feature`, `reports.feature` |
| R11 | *Order ferritin* is offered beside the comment of a lab report with *ferritin suggested* while the patient has no ferritin order (R26: at most one); it opens the ferritin order page for the patient. It is never offered without a suggestion: ferritin is ordered on suspicion (report, Use case). | `reports.feature` |
| R12 | A ferritin sample is never screened; its lab report is visible once analysed. | `lab.feature`, `screening.feature`, `reports.feature` |
| R13 | Every general practitioner query is scoped to the general practitioner's own patients; another general practitioner's order or lab report returns 404. | `access.feature` |
| R14 | Lab queries select only sample ID, ordering general practitioner, registered sex, age, test, indication and results; never the patient's name. | `access.feature` |
| R15 | `DEMO_LOGIN` (default off) shows one POST login button per seeded user. A deploy check fails when `DEMO_LOGIN` is on and `DEBUG` is off. | `access.feature` |
| R22 | Placing an order sends a lab order (DF23) to the general practitioner's one hospital; the hospital records it once, however often the same message arrives. | `messaging.feature` |
| R23 | The general practitioner's app fetches its new lab reports (DF25) from its hospital every 60 seconds and on *Check for reports*; it is always the client, the hospital never connects to it. | `messaging.feature` |
| R24 | The hospital's messaging endpoint accepts only a client certificate issued by that hospital's own certificate authority, for its general practitioner's app; any other client, the startup's included, is refused before a message is read. The hospital tells apps apart by their certificate's name: a sample is known by app and sample ID, and an app fetches and acknowledges only the lab reports of its own lab orders. The app stores each lab report on its own: one it cannot match to an order stays unacknowledged and holds back no other. | `messaging.feature` |
| R25 | DF23 and DF25 carry exactly the fields of `web/messaging/messages.proto` (§10): no patient name, no blood values in DF1. | `messaging.feature`, `tests/test_messages.py` |
| R26 | A patient has one sample; ordering a test the patient already has is refused (`already_ordered`). | `ordering.feature` |
| R16 | The ClientApp's deploy handler writes each final model as a new file named after its Flower run ID into the node's `final-models-path`, never overwriting one, with the threshold, the federated metrics the ServerApp sends, and its local validation on this hospital's validation split: the confusion matrix at the final model's threshold, as counts, and AUROC. Training results are unchanged. | `tests/test_final_models.py` |
| R17 | The Models page lists every final model; one that is unreadable, trained on other features than `FEATURES`, or lacks a threshold or standardization is shown as *cannot be deployed* with the reason, and deploying it is refused with that reason's code. | `deployment.feature` |
| R18 | The laboratory director deploys any final model that can be deployed, including an older one (rollback). The app keeps the deployment history (final model, deployed at) and nothing else: no account, no reason. Past screening results are never re-screened. | `deployment.feature` |
| R19 | Before each screening the deployed model's file is hashed; if it no longer matches the SHA-256 recorded at deployment, there is no usable deployed model (R8). | `deployment.feature`, `screening.feature` |
| R20 | A final model's metadata holds only this hospital's local validation and the federated aggregate the ServerApp computed; never another hospital's metrics. | `tests/test_final_models.py` |
| R21 | Each party has its own folder (§9); a hospital's web app reads only its own (`HOSPITAL_DIR`), a practice's only its own (`PRACTICE_DIR`), and each installs, migrates and serves only its own party's apps: a hospital's database has no table for patients, a practice's none for lab orders, analyser values or final models (test and audit check), and code under `web/` imports from the training package only `iron_deficiency.screening` and `iron_deficiency.dataset` (audit check). | `tests/test_settings.py`, `tools/audit.py` |

## 3. Agents

| Agent | Kind | Responsible for |
|---|---|---|
| general practitioner | Person | E1; uses R1, R9, R11 |
| Laboratory staff | Person | Triggers R2, R3 (and with it R4–R8) |
| Laboratory director | Person | E2; triggers R18 (*Deploy*) |
| ClientApp (deploy handler) | Software, startup's code at each hospital | R16, R20 |
| Deploy app (`deployment`) | Software | R17, R18 |
| General practitioner's app (`practice`, its own deployment) | Software, outside TB1 | R1, R9–R11, R13, R22, R23, R26 |
| Messaging endpoint (gRPC with mutual TLS, per hospital) | Software | R22–R25 |
| Hospital's certificate authority | Software, the hospital's | Issues the hospital's server and its general practitioner's client certificate (R24) |
| Lab app (`lab`) | Software | R2–R8, R12, R14 |
| Analyser | Software, stand-in | Returns the patient's NHANES 2021–2023 values (R3, R12) |
| Final models | Environment | Written by the ClientApp (R16) into the hospital's `final-models/` folder (§9) |
| Launcher (`tools/demo.py`) | Software | Starts each party as its own process (§9, R21) |
| Seed commands (`seed_hospital`, `seed_practice`) | Software | Each party's demo accounts from the same NHANES 2021–2023 participants: laboratory staff, a laboratory director and the analyser stand-in's values at the hospital; general practitioners and patients with obviously synthetic names at the practice |

## 4. Obstacles

| ID | Obstacle | Obstructs | Resolution |
|---|---|---|---|
| O1 | general practitioner picks the wrong clinical indication | E1, R4 | Accepted: the app cannot know the complaint (report, Assumptions) |
| O2 | Threshold 0.5 has no clinical basis, so suggestions are wrong | G0 | Accepted. Owner: the startup sets the threshold per final model with clinical input; the laboratory director can refuse to deploy (E2). Not tuned per hospital: AZ Diest's validation split holds about 52 patients, about 10 deficient. Ferritin follow-up (G5) makes errors visible |
| O3 | No usable deployed model when a CBC is analysed | G0 | Accepted, R8: the CBC is released *not screened*, with the reason; the suggestion is lost for that patient rather than delaying the CBC |
| O4 | Model screens people it was not trained on | G0 | R4 |
| O5 | A general practitioner opens another general practitioner's lab report by URL | P0 | R13 |
| O6 | Lab sees who the patient is | P0 | R14, R1 (the order copies only sex and age) |
| O7 | A new final model is deployed between screenings | R6 | R6, R18 (history) |
| O8 | NHANES has no ferritin for the patient | R12 | R3: *not available in the demo data* |
| O9 | Demo login shipped to a deployment | P0 | R15 |
| O10 | The score reveals more than the result | P0 | R7 |
| O11 | A final model screens before anyone at the hospital looked at it | G6 | R18: only a deployed model screens |
| O12 | A bad final model is deployed | G0 | R18: deploy an older one; no re-screening of past results |
| O13 | A final model was trained on other features | G6 | R17 |
| O14 | The deployed model's file is replaced on disk | G6 | R19 |
| O15 | A hospital learns another hospital's metrics through the final model's metadata | P0 | R20 |
| O16 | Hospital software reads another party's data, or carries startup code paths | P0 | R21 |
| O17 | Someone other than the general practitioner's app sends orders or reads lab reports | P0 | R24; the hospital is its own CA, so the startup cannot issue a certificate |
| O18 | A lab order is sent twice (retry after a lost reply) | R22 | Recorded once by sample ID and test; the repeat is acknowledged |
| O19 | The laboratory links tests of the same patient | P0 | Accepted: only through the shared sample ID; real laboratories link through the national register number |

## 5. Operations

All are POSTs that redirect on success; services take `now`.

| Operation | Actor | Precondition | Postcondition | Requirements |
|---|---|---|---|---|
| Fetch lab reports | General practitioner's app | Every 60 s, or *Check for reports* | New lab reports stored at the general practitioner's app | R23 |
| Place order | general practitioner | Patient is the general practitioner's; indication given iff test is CBC | Order with sex and age copied | R1, R13 |
| Receive | Laboratory staff | Order not received | Sample with sample ID, received at `now` | R2 |
| Run analyser | Laboratory staff | Sample received, not analysed | Values recorded; a CBC screened, or not screened with its reason; lab report released | R3, R8, R12 |
| Deploy | Laboratory director | Final model can be deployed (R17) | It is the deployed model from `now` | R18 |
| Log in as (demo) | Anyone | `DEMO_LOGIN` on | Session for that seeded user | R15 |

## 6. Pages

| Page | Role | Content |
|---|---|---|
| Log in | Anyone | Django login form; refuses an account without a role; demo buttons when `DEMO_LOGIN`. Afterwards, and at `/`, the start page of the user's role |
| Patients (start page) | general practitioner | Own patients: name, registered sex, age. Served by the general practitioner's app, not the hospital's |
| Patient | general practitioner | Registered sex, age, the patient's orders, each with its lab report once fetched: values (R9), comment, *Order ferritin* beside a suggestion (R11); *Order CBC*, *Order ferritin* |
| Order CBC / Order ferritin for a patient | general practitioner | The clinical indication only for a test that takes one; ferritin is a confirmation |
| Orders | general practitioner | Own orders, newest first, linked to their patient, with when their lab report was released; *Check for reports* |
| Models (start page) | Laboratory director | Every final model: run ID, received, threshold, local confusion matrix (counts) and AUROC, federated AUROC; the deployed one marked; *Deploy* or *cannot be deployed: reason* |
| Samples (lab index) | Laboratory staff | Orders to receive, samples to analyse, analysed with their screening result; *Receive*, *Run analyser*. A CBC not screened because of the model (none deployed, or its file changed) gives a warning to tell the laboratory director (O3) |

Index pages assert their query count. Conditional controls (*Order ferritin*,
*Deploy* and its refusal) are decided in query functions and tested there.

## 7. Out of scope

- Clinical-biologist review before release (O2 accepted)
- Access log of who viewed what (the report's adversaries attack the model, not this app)
- Email or other notification outside the app
- More than one test per order
- Free-text clinical notes
- Several hospitals in one deployment; a general practitioner sending samples to more than one laboratory (one laboratory each; the report can note that the same CBC may get a different suggestion at another hospital)
- A national certificate authority such as the Belgian eHealth platform (each hospital is its own CA, a simplification)
- Encrypting lab reports at rest at the general practitioner's app; retention of stored samples (WHO 5-5)
- Retention and deletion of samples and lab reports
- Training and federation (Flower, report P3–P6); the hospital's side of model distribution is in scope (G6)
- Withdrawing the deployed model without deploying another (unsourced term; deploy an older final model instead)
- Recording who deployed a final model, or why; application logging beyond Django's defaults (the PIA leaves logs aside)
- Re-screening past results with a newly deployed model, or CBCs released not screened; recalling lab reports
- Holding a lab report until a deployed model is usable
- Falling back automatically to another final model
- Shadow runs of an undeployed final model on patients' samples, and more than one deployed model at a time
- Tuning the threshold per hospital (O2)
- Deleting old final models (the hospital's IT, on the folder)
- Containers

## 8. Data

- Patients: NHANES 2021–2023 (`iron_deficiency.dataset.load_new_samples`), all sexes and ages, seeded at the general practitioner's app; each patient's NHANES number is their sample ID.
- The hospital's analyser stand-in holds the same cycle's values (13 CBC values, ferritin from `load_ferritin`), looked up by sample ID: what the tubes in its laboratory would measure. No values travel in a message.
- Ferritin exists in NHANES mainly for women aged 12–49; others get *not available in the demo data*.
- Age is the NHANES age at the survey and does not change.
- Registered sex has the two NHANES values, female and male.

## 9. Demo deployment: one folder and one process per party

The trust boundaries of the report's DFD (TB1 per hospital, TB2 the startup, TB3 per practice)
are visible on disk and as processes. Everything lives under `demo/`
(gitignored):

```
demo/
├── startup/                     TB2
│   ├── superlink/               DS3 run state, configuration, messages
│   └── final-models/            DS4 the startup's copy of every final model, one per run (DF13)
└── hospitals/
    ├── uz-leuven/               TB1
    │   ├── cohort/              DS2 training cohort (2005–2006)
    │   ├── final-models/        DS5 one file per training run (R16)
    │   └── web.sqlite3          DS1 lab records, DS6 deployment history
    ├── heilig-hart-leuven/      TB1 (2015–2016, 50%)
    └── az-diest/                TB1 (2017–2018, 25%)
└── practices/                   TB3: each general practitioner's own app
    ├── huisartsenpraktijk-de-akker/  Heverlee → UZ Leuven
    │   ├── certificates/        client certificate from UZ Leuven's CA, and that CA's certificate
    │   └── web.sqlite3          DS7 patients, orders, fetched lab reports
    ├── huisartsenpraktijk-de-berk/   Kessel-Lo → Heilig Hart Leuven
    └── huisartsenpraktijk-de-ceder/  Diest → AZ Diest
```

The three practices are fictional; a real practice may share a name.

`tools/demo.py` starts, as separate processes: one `flower-superlink` (the
startup); three `flower-supernode`s, each given only its hospital's `cohort/`
and `final-models/` in its node config; and three web apps, one port per
hospital, each with `HOSPITAL_DIR` set to its folder. Training is submitted
with `flwr run` to this local deployment, not the simulation, so the only data
crossing a boundary is Flower's messages (DF7–DF10). The web app refuses to
start if its database or final models lie outside `HOSPITAL_DIR`.

Each hospital also runs a messaging endpoint (UZ Leuven 8441, Heilig Hart
Leuven 8442, AZ Diest 8443) next to its staff app (8001–8003), and each
general practitioner's app runs on its own port (De Akker 8011, De Berk 8012,
De Ceder 8013) with `PRACTICE_DIR` set to its folder and `MESSAGING_ADDRESS`
to its hospital's endpoint, next to a process that checks for lab reports
every 60 seconds (`check_for_lab_reports --every 60`). Each hospital folder
gains `ca/` (DS8, its certificate authority) and `messaging/` (the endpoint's
server certificate, served by `serve_messages`). Without either folder set,
a development checkout serves every party's pages from one database.

## 10. Messages between the general practitioner and the hospital (DF23, DF25)

The general practitioner's app is always the client (R23): it sends lab orders
and fetches lab reports over gRPC with mutual TLS (R24). `web/messaging/messages.proto`
is the contract; its generated code and typed stubs are committed and a test
fails if they drift from it.

| Message | Fields | Never |
|---|---|---|
| Lab order (DF23) | sample ID, test, clinical indication (CBC only), registered sex, age, ordering general practitioner's name | patient name, blood values |
| Lab report (DF25) | sample ID, test, results, *ferritin suggested* (one bit), released at | score, screening result beyond that bit, not-screened reason, free text |

The tube itself is not a message: the hospital's analyser stand-in looks up
what a sample ID's tube would measure (§8).
