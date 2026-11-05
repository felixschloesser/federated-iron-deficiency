# Hospital screening app: requirements

A server-rendered Django app that models the path of workflow for the
iron-deficiency screening in the PIA report (`report/report.typ`): a general
practitioner orders a blood test, the hospital's laboratory analyses the
sample, the deployed model screens it, and the lab report reaches
the ordering general practitioner. The same code runs as two kinds of
deployment: each **hospital** (TB1: P6, P8–P10, DS5, DS6, DS8) and
each **general practitioner's own app** (TB3: P7, DS7), which exchange the
lab order (DF23) and the lab report (DF25) as messages (§10). It also covers
the hospital's side of DF8/DF17: which final model the hospital deploys.
Training itself (P2–P4) stays with Flower.

Method: KAOS goal model (goals, agents, obstacles, operations), refined into
the Gherkin scenarios under `features/`. Each requirement names the scenarios
that cover it.

## 1. Vocabulary

In `glossary.toml` at the repository root: each term with its source, why it
was chosen, and the words it replaces.

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
│   └── R26 Maintain[Each order on one sample; each test at most once per sample]      General practitioner's app
├── G2 Achieve[Sample analysed]
│   ├── R2 Achieve[Sample arrives with its lab order; a later test uses the stored sample]  Lab app
│   └── R3 Achieve[Analyser result recorded]                                         Laboratory staff + Analyser
├── G3 Achieve[Screening result recorded for every analysed CBC]
│   ├── R4 Maintain[Screened only for a screened indication, female, aged 18–49]       Lab app
│   ├── R5 Maintain[Not-screened reason recorded]                                    Lab app
│   ├── R6 Maintain[Result traceable to the screening model that produced it]             Lab app
│   └── R7 Avoid[Score stored]                                                       Lab app
├── G4 Achieve[Lab report visible to the ordering general practitioner]
│   ├── R8 Achieve[Lab report released at once, screened or not]                     Lab app
│   └── R9 Maintain[Comment only when ferritin suggested]                            Practice app
└── G5 Achieve[Ferritin follow-up from a lab report]
    ├── R11 Achieve[Order ferritin offered when ferritin suggested and not yet ordered]  Practice app
    └── R12 Achieve[Ferritin result recorded, never screened]                         Lab app + Analyser

G6 Maintain[Only a screening model the hospital deployed screens its patients]
├── R16 Achieve[Each final model stored at the hospital with run ID, threshold and local validation]  ClientApp
├── R17 Maintain[A screening model that cannot be deployed shows why, and has no Deploy]  Deploy app
├── E2 Expectation[Laboratory director deploys only after comparing local validation]  Laboratory director
├── R18 Achieve[Deploying a screening model makes it the deployed model; an older one rolls back]  Deploy app
└── R19 Maintain[Screening uses the deployed model only while its SHA-256 matches]   Lab app

P0 Maintain[Patient data seen only by those who need it]   (report, Part 2)
├── R13 Maintain[A practice has one general practitioner, who sees its patients, orders and lab reports]  Practice app
├── R14 Avoid[Patient name at the lab]                                               Lab app
├── R15 Avoid[Demo login outside development]                                        Settings + system check
├── R20 Avoid[A hospital learns another hospital's metrics]                          ClientApp
├── R21 Maintain[Each party's software and data stay inside its trust boundary]      Settings + audit + launcher
├── R27 (not in the demo) SuperNode authentication: the report's control              —
├── R28 Maintain[The startup's code at a hospital sees only the cohort and final models]  Compose
└── R29 Maintain[Every web app runs with DEBUG off; plain HTTP in the demo]          Compose + settings
```

### Requirements

| ID | Requirement | Scenarios |
|---|---|---|
| R1 | An order is on one sample of the patient and records the test (CBC or ferritin) and, for a CBC only, the clinical indication. It copies the patient's registered sex and age, which is all the lab learns about the patient besides the sample ID and whether the indication is screened (R25). Ferritin orders have no indication (`None`). | `ordering.feature` |
| R2 | A sample arrives with its lab order: its tests are ready to analyse at once, with no receiving step. A later test on the same sample is measured on the stored sample. | `lab.feature` |
| R3 | Running the analyser on a sample records the patient's NHANES values: the 13 CBC values for a CBC, ferritin in ng/mL for ferritin, else the made-up ferritin (§8), else *not available in the demo data*. A sample is analysed at most once. | `lab.feature` |
| R4 | A CBC is screened only when its lab order says the indication is screened (`screened_indication`: suspected anaemia, suspected irritable bowel syndrome, unexplained fatigue, where the guidelines order a CBC without ferritin), registered sex is female and age is 18–49. The general practitioner's app decides only whether its indication is screened (`Order.screened_indication`); the laboratory checks all three conditions. | `screening.feature`, `messaging.feature` |
| R5 | A CBC that is not screened records why, as far as someone acts on it: `not eligible` when R4 excludes it, never which condition (lab staff act on none of them, and the laboratory holds sex and age anyway); else that there is no usable deployed model (none deployed, or changed on disk), which lab staff report to the laboratory director (O3). | `screening.feature` |
| R6 | A screening result records the screening model that produced it (run ID, SHA-256, threshold). | `screening.feature` |
| R7 | No score, probability or standardized input is stored or shown. | `screening.feature` |
| R8 | Running the analyser on a CBC screens it at once, and its lab report is released at once. Without a usable deployed model (R19) a CBC that meets R4 is *not screened* with that reason: the general practitioner's CBC never waits for the startup's model, and is not screened again later. Screening runs in the same transaction as the analysis, so an analysed lab order is a released lab report; there is no separate release step. | `screening.feature` |
| R9 | The lab report shows the values under NHANES's names and units, without reference ranges or any mark; the comment *Ferritin suggested.* appears only for *ferritin suggested*. The hospital sends one bit, *ferritin suggested*, so *ferritin not suggested* and *not screened* look the same at the practice and show nothing about screening. Under a CBC lab report without a suggestion, whatever the reason, the same note: "No ferritin suggestion. This does not rule out iron deficiency." Under the values: "Reference intervals are not shown: the demo has no laboratory's intervals." (ISO 15189 lists them, WHO LQMS p. 193; no laboratory's intervals are sourced). | `screening.feature` (the bit the hospital sends), `messaging.feature`, `reports.feature` |
| R11 | *Order ferritin* is offered beside the comment of a lab report with *ferritin suggested* while that lab report's sample has no ferritin order (R26); it opens the ferritin order page on that sample, so the laboratory measures ferritin on the stored sample (R2). It is never offered without a suggestion: ferritin is ordered on suspicion (report, Use case), so a sample's own order buttons never offer it, and ferritin on a sample without a lab report suggesting it is refused (`ferritin_not_suggested`, on the test). | `reports.feature`, `ordering.feature` |
| R12 | A ferritin sample is never screened; its lab report is visible once analysed. | `lab.feature`, `screening.feature`, `reports.feature` |
| R13 | A practice has exactly one general practitioner: a second is refused (`one_general_practitioner`), by the database too. The practice's patients, orders and lab reports are that general practitioner's. | `access.feature` |
| R14 | Lab queries select only sample ID, registered sex, age, test, whether the indication is screened and results, by the sample's practice; never the patient's name, the general practitioner's name or the clinical indication. | `access.feature` |
| R15 | `DEMO_LOGIN` (default off) shows one POST login button per seeded user. A deploy check fails when `DEMO_LOGIN` is on and `DEBUG` is off. | `access.feature` |
| R22 | A practice works with one or more laboratories; *Collect sample* records the one the sample goes to, chosen by the general practitioner when there are several (`laboratory_required`); the primary laboratory, if the practice names one (`add_laboratory --primary`, at most one: `one_primary_laboratory`), is preselected. Placing an order sends its lab order (DF23) to its sample's laboratory only, waiting at most 2 seconds; if that laboratory does not answer, the next check for reports (R23) sends it. The hospital records it once, however often the same message arrives. | `messaging.feature` |
| R23 | The general practitioner's app fetches its new lab reports (DF25) from each of its laboratories only on *Check for reports*, which also sends lab orders still unsent; a laboratory that cannot be reached is named and holds back no other; a lab report it is still waiting for says so; no timer fetches them. It is always the client, the hospital never connects to it. | `messaging.feature` |
| R24 | Every message from a general practitioner's app names its practice (practice name); a message without one is refused (`practice_required`) before anything is read or recorded. The hospital tells apps apart by that name: a sample is known by practice and sample ID, and an app fetches and acknowledges only the lab reports of its own lab orders. The app stores each lab report on its own, and only for a sample it sent to that laboratory: one it cannot match stays unacknowledged and holds back no other. The report's mutual TLS, each hospital its own CA, is left out of the demo for simplicity, so the name is trusted as sent. | `messaging.feature` |
| R25 | DF23 and DF25 carry exactly the fields of `web/messaging/messages.proto` (§10): no patient name, no blood values, and no clinical indication, only whether it is screened (R4). | `messaging.feature`, `tests/tools/test_messages.py` |
| R26 | *Collect sample* records blood collected from the patient, at `now`, with the patient's next sample ID; a patient may give any number of samples, and nothing reaches the hospital until a test is ordered. Tests are ordered on a sample afterwards; a test is ordered at most once per sample (`already_ordered`). Drawing first and choosing the tests afterwards simplifies WHO LQMS 5-3 (p. 64), where the request comes first: a sample here stands for one blood draw into the standard tubes. | `ordering.feature` |
| R16 | The ClientApp's deploy handler writes each final model as a new file named after its Flower run ID into the node's `final-models-path`, never overwriting one, with the threshold, the federated metrics the ServerApp sends, and its local validation on this hospital's validation split: the confusion matrix at the final model's threshold, as counts, and AUROC. Training results are unchanged. | `tests/ml/test_final_models.py` |
| R17 | The Screening models page lists every screening model; one that is unreadable, trained on other features than `FEATURES`, or lacks a threshold or standardization is shown as *cannot be deployed* with the reason, and deploying it is refused with that reason's code. | `deployment.feature` |
| R18 | The laboratory director deploys any screening model that can be deployed, including an older one (rollback). The app keeps the deployment history (screening model, deployed at) and nothing else: no account, no reason. Past screening results are never re-screened. | `deployment.feature` |
| R19 | Before each screening the deployed model's file is hashed; if it no longer matches the SHA-256 recorded at deployment, there is no usable deployed model (R8). | `deployment.feature`, `screening.feature` |
| R20 | A final model's metadata holds only this hospital's local validation and the federated aggregate the ServerApp computed; never another hospital's metrics. | `tests/ml/test_final_models.py` |
| R21 | Each party has its own folder (§9); a hospital's web app reads only its own (`HOSPITAL_DIR`), a practice's only its own (`PRACTICE_DIR`), and each installs, migrates and serves only its own party's apps: a hospital's database has no table for patients, a practice's none for lab orders, analyser values or final models (test and audit check), and code under `web/` imports from the training package only `iron_deficiency.screening`, `iron_deficiency.cohort` and `iron_deficiency.dataset` (audit check). | `tests/web/test_settings.py`, `tools/audit.py` |
| R27 | Not in the demo. The report's control: the SuperLink admits only SuperNodes whose public key the startup registered (Flower's SuperNode authentication, over TLS). The demo runs every Flower connection with `--insecure` and admits any node, for simplicity. | `tests/demo/test_compose.py` (every Flower connection runs without TLS) |
| R28 | The ClientApp, the startup's code at each hospital (DF7, TB4), runs in a container of its own that mounts only the hospital's `cohort/` (read-only) and `final-models/`, on a network it shares only with its hospital's SuperNode: it sees no database, no key and no other party's folder, and reaches neither the hospital's web app nor anything outside the deployment, so what it sends leaves only through DF9 and DF10. | `tests/demo/test_compose.py`, `tests/demo/test_containers.py` |
| R29 | Each of the six web apps runs gunicorn with `DEBUG` off; WhiteNoise serves the stylesheets. The demo serves plain HTTP: the report's TLS (HTTPS, secure cookies, HSTS) is left out for simplicity. Only `prepare`, which seeds the demo accounts, runs with `DJANGO_DEBUG` (R15). | `tests/demo/test_compose.py`, `tests/demo/test_containers.py` |

## 3. Agents

| Agent | Kind | Responsible for |
|---|---|---|
| general practitioner | Person | E1; uses R1, R9, R11 |
| Laboratory staff | Person | Triggers R2, R3 (and with it R4–R8) |
| Laboratory director | Person | E2; triggers R18 (*Deploy*) |
| ClientApp (deploy handler) | Software, startup's code at each hospital | R16, R20 |
| Deploy app (`deployment`) | Software | R17, R18 |
| General practitioner's app (`practice`, its own deployment) | Software, outside TB1 | R1, R9–R11, R13, R22, R23, R26 |
| Messaging endpoint (gRPC, plaintext in the demo, per hospital) | Software | R22–R25 |
| Lab app (`lab`) | Software | R2–R8, R12, R14 |
| Analyser | Software, stand-in | Returns the patient's NHANES 2021–2023 values (R3, R12) |
| Final models | Environment | Written by the ClientApp (R16) into the hospital's `final-models/` folder (§9) |
| Deployment (`compose.yaml`, `tools/demo.py`) | Software | Runs each process in its own container, one network per trust boundary and per crossing (§9, R21, R28) |
| Seed commands (`seed_hospital`, `seed_practice`) | Software | Each party's demo accounts from the same NHANES 2021–2023 participants: laboratory staff, a laboratory director and the analyser stand-in's values at the hospital; general practitioners and patients with obviously synthetic names at the practice |

## 4. Obstacles

| ID | Obstacle | Obstructs | Resolution |
|---|---|---|---|
| O1 | general practitioner picks the wrong clinical indication | E1, R4 | Accepted: the app cannot know the complaint (report, Assumptions) |
| O2 | Threshold 0.5 has no clinical basis, so suggestions are wrong | G0 | Accepted. Owner: the startup sets the threshold per final model with clinical input; the laboratory director can refuse to deploy (E2). Not tuned per hospital: AZ Diest's validation split holds about 52 patients, about 10 deficient. Ferritin follow-up (G5) makes errors visible |
| O3 | No usable deployed model when a CBC is analysed | G0 | Accepted, R8: the CBC is released *not screened*, with the reason; the suggestion is lost for that patient rather than delaying the CBC |
| O4 | Model screens people it was not trained on | G0 | R4 |
| O5 | A general practitioner opens another general practitioner's lab report by URL | P0 | R13: another general practitioner's lab reports are at another practice's app |
| O6 | Lab sees who the patient is | P0 | R14, R1 (the order copies only sex and age) |
| O7 | A new screening model is deployed between screenings | R6 | R6, R18 (history) |
| O8 | NHANES has no ferritin for the patient | R12 | R3: *not available in the demo data* |
| O9 | Demo login shipped to a deployment | P0 | R15 |
| O10 | The score reveals more than the result | P0 | R7 |
| O11 | A final model screens before anyone at the hospital looked at it | G6 | R18: only a deployed model screens |
| O12 | A bad final model is deployed | G0 | R18: deploy an older one; no re-screening of past results |
| O13 | A screening model was trained on other features | G6 | R17 |
| O14 | The deployed model's file is replaced on disk | G6 | R19 |
| O15 | A hospital learns another hospital's metrics through the final model's metadata | P0 | R20 |
| O16 | Hospital software reads another party's data, or carries startup code paths | P0 | R21 |
| O17 | Someone other than the general practitioner's app sends orders or reads lab reports | P0 | Report: mutual TLS, each hospital its own CA. Not in the demo, which trusts the practice name as sent (R24) |
| O18 | A lab order is sent twice (retry after a lost reply) | R22 | Recorded once by sample ID and test; the repeat is acknowledged |
| O19 | The laboratory links tests of the same patient | P0 | Accepted: only through the shared sample ID; real laboratories link through the national register number |
| O20 | A node that is not a hospital connects to the SuperLink and receives every round's global model, the final model and the run configuration | P0 | Report: SuperNode authentication (R27). Not in the demo |
| O21 | The startup's ClientApp reads what the hospital's process can read, such as the laboratory's records, and returns it in its model update | P0 | R28 |
| O22 | The laboratory learns why a CBC was ordered (start of pregnancy, suspected IBS, …), which it needs only to decide whether to screen | P0 | R25: the lab order says only whether the indication is screened |

## 5. Operations

All are POSTs that redirect on success; model and manager methods take `now`.

| Operation | Actor | Precondition | Postcondition | Requirements |
|---|---|---|---|---|
| Fetch lab reports | General practitioner's app | *Check for reports*, on Orders or a patient's page | New lab reports stored at the general practitioner's app, from each of its laboratories | R23 |
| Collect sample | general practitioner | Patient is the practice's; a laboratory chosen if the practice works with several, the primary one preselected | A sample with the patient's next sample ID, for that laboratory, collected at `now`; nothing sent; then the sample's CBC order page | R13, R22, R26 |
| Place order | general practitioner | Sample is one of the practice's patient's; indication given iff test is CBC; the test not yet on the sample | The order on the sample, sex and age copied; its lab order sent, else with the next check (R22) | R1, R13, R22, R26 |
| Run analyser | Laboratory staff | Lab order arrived, not analysed | Values recorded; a CBC screened, or not screened with its reason; lab report released | R3, R8, R12 |
| Deploy | Laboratory director | Screening model can be deployed (R17) | It is the deployed model from `now` | R18 |
| Log in as (demo) | Anyone | `DEMO_LOGIN` on | Session for that seeded user | R15 |

## 6. Pages

| Page | Role | Content |
|---|---|---|
| Log in | Anyone | Django login form; refuses an account without a role; demo buttons when `DEMO_LOGIN`. Afterwards, and at `/`, the start page of the user's role |
| Patients (start page) | general practitioner | A search by name (contains, any case) and own patients: name, registered sex, age; *Ferritin suggested* beside the name of a patient with a lab report suggesting ferritin whose sample has no ferritin order yet (its *Order ferritin* is on the patient's page, R11). Served by the general practitioner's app, not the hospital's |
| Patient | general practitioner | Registered sex, age, *Collect sample*, then one collapsible section per sample, newest first and only the newest open (summary: sample ID, collected, its tests or *No tests ordered yet*, *Ferritin suggested* if a lab report in it says so). In each: each test in the order placed, with its clinical indication, its status (*Awaiting lab report* or *Lab report released*) and its lab report once fetched (values, R9; comment; *Order ferritin* beside a suggestion, R11); then *Order CBC* / *Order ferritin* for tests the sample does not have (ferritin not while it is offered beside a suggestion) |
| Order CBC / Order ferritin on a sample | general practitioner | The sample and when it was collected; the clinical indication only for a test that takes one; ferritin is a confirmation |
| Orders | general practitioner | Own orders, newest first, linked to their patient, with when their lab report was released; *Check for reports* |
| Screening models (start page) | Laboratory director | One card per screening model, newest first: its name, then as a description list its sensitivity, specificity, positive and negative predictive value on the local validation (each as counts and a percentage), AUROC here and across hospitals and threshold, and its run ID; *Deployed*, *Deploy* or *Cannot be deployed: reason*. Deployment history: when, which model |
| To analyse (start page) | Laboratory staff | Lab orders not yet analysed, oldest first: sample ID (marked *stored sample* when another test on it was analysed), test, *Run analyser*, ordered, general practitioner; nothing else of the patient. A CBC not screened because of the model (none deployed, or its file changed) gives a warning to tell the laboratory director (O3) |
| Analysed | Laboratory staff | Analysed lab orders, newest first, with their screening result |

Index pages assert their query count. Conditional controls (*Order ferritin*,
*Deploy* and its refusal) are decided in query functions and tested there.

## 7. Out of scope

- Clinical-biologist review before release (O2 accepted)
- Reference intervals and high/low marks on lab reports: no laboratory's intervals are sourced, and R9 keeps the report uninterpreted
- Abbreviated value names (Hb, MCV): neither WHO LQMS nor the NHANES CBC_L codebook gives them
- Receiving and rejecting samples (WHO 5-4): a sample arrives with its lab order, and nothing in the demo would make the laboratory refuse one
- Access log of who viewed what (the report's adversaries attack the model, not this app)
- Email or other notification outside the app
- More than one test per order
- Free-text clinical notes
- Several hospitals in one deployment
- The report's security controls: TLS for Flower and the web apps, SuperNode authentication, mutual TLS for lab orders (each hospital its own CA). The report keeps them; the demo leaves them out for simplicity
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

## 8. Data

- Patients: NHANES 2021–2023 (`iron_deficiency.dataset.load_new_samples`), all sexes and ages, seeded at the general practitioner's app (`--patients`, default 12, shared by the seeding groups; the demo seeds De Akker 40, De Berk 24, De Ceder 12, sized like each practice's paired hospital, its primary laboratory; all are the practice's one general practitioner's, `doctor`); each has a fictional Flemish name matching their registered sex (common Flemish first names, the ten most common family names of the Flemish Region, Statbel); each patient is one NHANES participant, whose number starts each of their sample IDs.
- The hospital's analyser stand-in holds the same cycle's values (13 CBC values, ferritin from `load_ferritin`), looked up by the NHANES number in the sample ID: what the samples in its laboratory would measure. Every hospital holds every practice's participants, as any practice may send it a sample (R22). Every sample of one patient measures the same values, as NHANES measured each participant once. No values travel in a message.
- NHANES measured ferritin only for women aged 12–49 (FERTIN_L, eligible sample). The demo seeds no woman aged 18–49 whom it did not measure; for men and other women the hospital's stand-in holds a made-up ferritin, the measured ferritin of an eligible woman at or above the cutoff picked by sample ID, reported as *Ferritin (made up for the demo)*, never as ferritin. A participant with neither gets *not available in the demo data*.
- Age is the NHANES age at the survey and does not change.
- Registered sex has the two NHANES values, female and male.

## 9. Demo deployment: one container per service, one network per trust boundary

`compose.yaml` runs the demo: one container per service (one long-running command, such as gunicorn for a hospital's web app), one Docker network
per trust boundary of the report's DFDs and one per crossing, and one Docker
volume per party, holding its folder (`startup`, each `<hospital>`, each
`<practice>`). Each container mounts only the parts of its own party's volume
its process needs, at the path under `/demo` that `prepare` wrote them to.
On the host, `demo/` (gitignored) keeps only what a reset must not delete:
`huggingface/` (`HF_HOME`, and the NHANES 2021–2023 cycle the seed commands pick participants from), which only `prepare` mounts. Each party's folder holds only its DFD stores and the Django secret key.

```
/demo/
├── startup/                     TB2
│   ├── superlink/               DS3 run state, configuration, messages
│   └── final-models/            DS4 the startup's copy of every final model, one per run (DF13)
└── hospitals/
    ├── uz-leuven/               TB1
    │   ├── cohort/              DS2 training cohort (2005–2006)
    │   ├── final-models/        DS5 one file per training run (R16)
    │   └── web.sqlite3          DS8 screening records, DS6 deployment history
    ├── heilig-hart-leuven/      TB1 (2015–2016, 50%)
    └── az-diest/                TB1 (2017–2018, 25%)
└── practices/                   TB3: each general practitioner's own app
    ├── huisartsenpraktijk-de-akker/  Heverlee; sends samples to every hospital (R22)
    │   └── web.sqlite3          DS7 patients, orders, fetched lab reports, its laboratories
    ├── huisartsenpraktijk-de-berk/   Kessel-Lo
    └── huisartsenpraktijk-de-ceder/  Diest
```

The three practices are fictional; a real practice may share a name. `demo.toml`
declares the parties: each hospital, keyed as `iron_deficiency.dataset` names it,
with its practice, both colours and its number of seeded patients; a test holds
it to exactly the hospitals training knows. How a hospital trains (cycle,
sample) stays in the startup's app, and `demo.toml` never reaches the FAB.

Services are not the DFDs' processes; README.md maps one
onto the other (P6 and P8–P10 share the hospital's container; P2 is two
containers; P1 and P5 are not built).

| Container | Image | Network | Mounts |
|---|---|---|---|
| `flower-superlink` | `flwr/superlink` | `startup`, `model-updates` | `startup/superlink` |
| `flower-server-app` | built: SuperExec with the app's dependencies | `startup` | `startup/final-models` |
| `<hospital>-flower-supernode` | `flwr/supernode` | `model-updates`, `<hospital>-flower-client-app` | none |
| `<hospital>-flower-client-app` | built: SuperExec with the app's dependencies | `<hospital>-flower-client-app` | its `cohort/` (read-only), `final-models/` (R28) |
| `<hospital>-web` | built: the project | `<hospital>`, where its pages listen (`<hospital>-pages:8000`), and `lab-orders`, where only its messaging endpoint listens (`<hospital>-lab-orders:8441`) | its folder, with `cohort/` masked and `final-models/` read-only |
| `<practice>-web` | built: the project | `<practice>`, and `lab-orders`, reaching every hospital's endpoint (R22) | its folder |
| `proxy` | `nginx` (`docker/proxy.conf`) | every `<hospital>` and `<practice>` network | none |

`startup`, `model-updates` (DF7–DF10), each `<hospital>-flower-client-app` (TB4) and
`lab-orders` (DF23, DF25), where every practice reaches every hospital's endpoint and so could reach the other practices too, are internal networks: nothing on
them reaches outside the deployment. Only the `proxy` is published, on
`127.0.0.1:80` (`DEMO_HTTP_PORT`): it routes each `<party>.localhost`
(RFC 6761) to that party's web app by its Host header, in plain HTTP. The
SuperLink admits any node (R27 is not in the demo); a SuperNode runs no app itself
(`--isolation process`): its hospital's ClientApp container fetches the run
from it, and the ServerApp container likewise from the SuperLink.

Two one-shot containers stand outside the DFDs. `prepare` is out-of-band
setup, the one container that sees every party's folder: cohorts, the NHANES
data, migrated and seeded databases. `train` is the data scientist (E1), submitting a run from inside TB2:
`docker compose run --rm train`. Every container runs as `DEMO_USER` (default
`1000:1000`), so the volumes and, on Linux, `demo/` belong to one user;
`prepare` alone starts as root, hands the fresh volumes to that user and drops
to it (`setpriv`). The web apps run gunicorn with `DEBUG` off, in plain HTTP
(R29).

`docker compose down -v` deletes every party's volume, so the next `docker compose up` prepares everything afresh; the Hugging Face downloads in `demo/` stay.

Each web app takes a Pico colour theme from `PARTY_COLOUR` (vendored themes only; absent: Pico's default), so the parties' pages are told apart at a glance: UZ Leuven jade and De Akker green, Heilig Hart Leuven pumpkin and De Berk amber, AZ Diest violet and De Ceder purple.

## 10. Messages between the general practitioner and the hospital (DF23, DF25)

A practice's laboratories are rows in its own database, added with
`manage.py add_laboratory "<name>" <host:port> [--primary]` (R22). In the demo every
practice works with every hospital, and its paired hospital's laboratory is its primary one. A laboratory's suggestions come from its own deployed model, so
the same CBC may get a different one at another laboratory.

The general practitioner's app is always the client (R23): it sends lab orders
and fetches lab reports over gRPC, plaintext in the demo, naming its practice in every message (R24). `web/messaging/messages.proto`
is the contract; its generated code and typed stubs are committed and a test
fails if they drift from it. Its choices are proto enums with one value per
vocabulary member (`web.messaging.choices`), and its times are
`google.protobuf.Timestamp`; the hospital's form still checks every field.

| Message | Fields | Never |
|---|---|---|
| Lab order (DF23) | sample ID, test, whether the indication is screened (CBC only), registered sex, age; the sending practice's name | patient name, blood values, clinical indication, general practitioner's name |
| Lab report (DF25) | sample ID, test, results, *ferritin suggested* (one bit), released at | score, screening result beyond that bit, not-screened reason, free text |

The tube itself is not a message: the hospital's analyser stand-in looks up
what a sample ID's tube would measure (§8).
