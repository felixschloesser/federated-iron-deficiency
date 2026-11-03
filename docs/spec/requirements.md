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

The PIA report is the first source, the WHO *Laboratory Quality Management
System Handbook* (2011, ISBN 9789241548274, `sources/9789241548274_eng.pdf`) the
second. The report was drafted with AI help, so a word that reads badly to lab
staff is replaced and the report's word moves to the rejected column.

| Term | Source | Why chosen | Rejected terms |
|---|---|---|---|
| general practitioner | Report, Stakeholders table ("GP", spelled out) | The report's orderer and reader of the lab report; spelled out everywhere in the app | GP (abbreviation), requester, ordering physician (WHO 5-4, p. 66) |
| laboratory staff | WHO LQMS, the handbook's word for the people who work in the laboratory (44 uses; e.g. ch. 5, Sample management) | Run the analyser; one record per person (`LaboratoryStaffMember`) | lab technician ("technician" in WHO LQMS means equipment service only), technologist (a qualified grade), laboratorian, laboratory worker |
| patient | Report, Use case | The report's word | participant (NHANES word; data origin only) |
| order | Report, DF23 "lab order"; WHO glossary *path of workflow*, "physician's order" (p. 228) | Report and WHO agree | request, requisition (WHO), examination request (ISO 15189) |
| test | Report, Use case "ferritin test" | Order picks one: CBC or ferritin | examination (ISO 15189) |
| CBC (complete blood count) | Report, Use case | The report's word for the routine test | blood count (report uses both; one word only) |
| clinical indication | Report, Data table | The report's word; decides screening (R4). One of the six below, in the guidelines' words | reason for testing |
| suspected anaemia | Domus Medica, *Aanvraag van laboratoriumtests door huisartsen*, key messages, Huisarts Nu 2012;41(4), S6: "Bepaal Hb om de diagnose van anemie te stellen"; NHG-Standaard Anemie 2014, H&W 57(10) p. 528: Hb for "moeheid, duizeligheid, algemene malaise, bleekheid of hevig menstrueel bloedverlies" | Screened: ferritin follows only once anaemia is found (Domus S6), so a woman who is iron deficient without anaemia is missed | anaemia work-up |
| suspected irritable bowel syndrome | Domus Medica, *Aanvraag van laboratoriumtests door huisartsen*, key messages, Huisarts Nu 2012;41(4), S8: "rode bloedcellen, hematocriet, hemoglobine, witte bloedcellen, sedimentatie, CRP" | Screened: a CBC without ferritin | IBS (abbreviation) |
| unexplained fatigue | Domus Medica, *Aanvraag van laboratoriumtests door huisartsen*, key messages, Huisarts Nu 2012;41(4), S8: lab tests "wanneer de moeheid meer dan een maand aanhoudt … Bepaal ook ferritine bij vrouwen op vruchtbare leeftijd" | Screened, though the guideline already adds ferritin for women of childbearing age: the suggestion helps only where ferritin was left out | non-specific complaint (no source; the report's earlier word), fatigue work-up |
| start of pregnancy | Domus Medica, *Aanvraag van laboratoriumtests door huisartsen*, key messages, Huisarts Nu 2012;41(4), S9: "Bepaal Hb, RBC en Hct … bij Hb <9,5 g/100 ml … ferritinebepaling" | Not screened: pregnancy has its own Hb rule, and the cohort was not checked for pregnancy | pregnancy check |
| chronic kidney disease follow-up | WOREL, *Aanvraag van laboratoriumtests (deel 1)*, 2026, p. 42: "Bepaal minstens jaarlijks het hemoglobinegehalte … om te screenen op renale anemie" | Not screened: monitoring a known disease, whose anaemia has another cause | CKD (abbreviation) |
| other | User decision, 2026-11-01: the guidelines are organised by indication and name no catch-all | Not screened | — |
| registered sex | Report, Data table | Distinguishes the record from the person (report, Information at risk) | gender, sex |
| sample ID | Report, DF23 and Data table | The report's link between lab order, results and lab report; on the sample's label. In the demo the patient's NHANES number and the sample's number for that patient, e.g. 135318-2 | laboratory identification number, accession number (WHO 5-4, p. 66) |
| stored sample | WHO LQMS 5-5, p. 68, "stored samples" | A sample the laboratory already holds: a later test is measured on it | add-on test, retained sample |
| sample | WHO LQMS ch. 5, *Sample management* (the handbook's word throughout) | Blood collected from one patient at one time; each order is on one sample, and one sample may carry a CBC and a later ferritin | specimen (ISO 15189), tube (the container), blood draw |
| collected | WHO LQMS 5-3, p. 64: "the health care provider may collect a sample in a clinic setting"; 5-4, p. 66, register field "date and time of collection" | When the general practitioner's practice takes the blood; recorded on the sample | drawn, taken, venipuncture |
| analysed | Report, P1 "Lab analysis" | The report's process name | examined, tested |
| screening | Report, P7 | The report's process name | scoring, classification |
| screening result | Report, DF31 "screening result", P10 | What screening records per CBC: one of the three below, with the reason when not screened (R5) and the screening model when screened (R6) | flag, outcome, classification |
| ferritin suggested / ferritin not suggested / not screened | Report, Use case "a comment to the lab report suggesting ferritin"; "not screened" from Federated version | Names the action for the general practitioner; avoids the lab meaning of *flag* | flagged / not flagged (an earlier report draft; in a lab a *flag* marks an out-of-range value), possible iron deficiency (names a diagnosis) |
| final model | Report, DS4, DF8 "final model, threshold" | What one training run sends to every hospital; stored there with its run ID and local validation | release, model version |
| screening model | Built from the report's words: P10 *Screening* and "the model" (Use case) | Named after its purpose at the hospital: a model that can screen this hospital's CBCs. What the laboratory director compares and deploys, named by when it arrived ("Screening model of 30 Oct 2026, 14:02") with its run ID as a detail. A final model becomes a screening model when it reaches the hospital | model (too generic; Django's `Model`), final model (kept for training code and the report's DFD), release, model version |
| deploy | Report, Use case: the model "is then deployed to every hospital" | The laboratory director's decision that a screening model screens this hospital's patients | activate, release, roll out |
| deployment (of a party) | Flower documentation, "Deployment Engine": running the federation on real nodes, not in simulation | One party's running copy of the code, in its own folder (§9); never a final model being deployed | installation, instance |
| deployed model | Report, DF29, DF30 "deployed final model" | The screening model this hospital deployed last; the only one that screens | active release, fingerprint |
| laboratory director | WHO LQMS ch. 2, p. 21: the director assesses "all potential risks … including services to patients" (20 uses) | Decides which screening model screens patients | clinical biologist (not in either source), quality manager (WHO: runs the quality system, does not decide), laboratory manager |
| local validation | Built from *validation* (report, DF10 "validation example count") | A screening model on this hospital's own validation split: the confusion matrix at its threshold, as counts, then AUROC | local evaluation, shadow run, flag rate |
| sensitivity | WHO LQMS 3-3, p. 40: test methods are "evaluated for the ability to detect disease (sensitivity, specificity, positive and negative predictive value)" | Iron-deficient women of the local validation whom the screening model suggests ferritin for, shown as counts and a percentage | recall (machine learning, not a laboratory word), true positive rate |
| specificity | WHO LQMS 3-3, p. 40: test methods are "evaluated for the ability to detect disease (sensitivity, specificity, positive and negative predictive value)" | Women without iron deficiency whom it does not suggest ferritin for | true negative rate |
| positive predictive value | WHO LQMS 3-3, p. 40: test methods are "evaluated for the ability to detect disease (sensitivity, specificity, positive and negative predictive value)" | Ferritin suggestions that were right: what a suggestion is worth to the general practitioner | precision (in the laboratory: how much repeated measurements vary, WHO LQMS p. 82), unnecessary suggestions (its complement, shown inside it) |
| negative predictive value | WHO LQMS 3-3, p. 40: test methods are "evaluated for the ability to detect disease (sensitivity, specificity, positive and negative predictive value)" | Women without a suggestion who were not iron deficient: what a silent lab report is worth (R9) | — |
| threshold | Report, Design choices | The report's word | cutoff (reserved for ferritin's 15 ng/mL) |
| lab report | Report, DF25 | The report's word | test report (WHO p. 193) |
| comment | Report, Use case; WHO report contents "applicable comments" (p. 193) | Both sources. The only comment is the suggestion: "Ferritin suggested by the hospital's screening of this CBC. Likely iron deficiency; not a diagnosis." ("likely iron deficient": report, Use case) | interpretive comment |
| CBC value names and units, e.g. *Hemoglobin*, g/dL | NHANES 2021–2023 CBC_L codebook, SAS labels (`sources/nhanes-2021-2023-CBC_L.htm`) | The values are NHANES's own, in its units; no conversion | Hb, Ht and other report abbreviations (no source; other units) |
| Ferritin, ng/mL | NHANES 2021–2023 FERTIN_L codebook (`sources/nhanes-2021-2023-FERTIN_L.htm`) | As above | µg/L (LBDFERSI) |
| Ferritin (made up for the demo), ng/mL | User decision, 2026-11-01: NHANES has no ferritin for men and women outside 12–49 | Tells the general practitioner the value is not a measurement; kept apart from ferritin so it never feeds a suggestion or a label | ferritin (would pass a made-up value as measured), synthetic ferritin |

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
├── R13 Maintain[A general practitioner sees only their own patients, orders and lab reports]           Practice app
├── R14 Avoid[Patient name at the lab]                                               Lab app
├── R15 Avoid[Demo login outside development]                                        Settings + system check
├── R20 Avoid[A hospital learns another hospital's metrics]                          ClientApp
├── R21 Maintain[Each party's software and data stay inside its trust boundary]      Settings + audit + launcher
├── R27 Avoid[A node other than a hospital's SuperNode joins the federation]        Compose + SuperLink
├── R28 Maintain[The startup's code at a hospital sees only the cohort and final models]  Compose
└── R29 Maintain[Every web app serves HTTPS with Django's deploy settings]          Compose + settings
```

### Requirements

| ID | Requirement | Scenarios |
|---|---|---|
| R1 | An order is on one sample of the patient and records the test (CBC or ferritin) and, for a CBC only, the clinical indication. It copies the patient's registered sex and age, which is all the lab learns about the patient besides the sample ID. Ferritin orders have no indication (`None`). | `ordering.feature` |
| R2 | A sample arrives with its lab order: its tests are ready to analyse at once, with no receiving step. A later test on the same sample is measured on the stored sample. | `lab.feature` |
| R3 | Running the analyser on a sample records the patient's NHANES values: the 13 CBC values for a CBC, ferritin in ng/mL for ferritin, else the made-up ferritin (§8), else *not available in the demo data*. A sample is analysed at most once. | `lab.feature` |
| R4 | A CBC is screened only when the clinical indication is screened (suspected anaemia, suspected irritable bowel syndrome, unexplained fatigue: where the guidelines order a CBC without ferritin), registered sex is female and age is 18–49. Each condition is its own branch. | `screening.feature` |
| R5 | A CBC that is not screened records why: the first failing condition, in the order indication, registered sex, age; else that there is no usable deployed model (none deployed, or changed on disk). | `screening.feature` |
| R6 | A screening result records the screening model that produced it (run ID, SHA-256, threshold). | `screening.feature` |
| R7 | No score, probability or standardized input is stored or shown. | `screening.feature` |
| R8 | Running the analyser on a CBC screens it at once, and its lab report is released at once. Without a usable deployed model (R19) a CBC that meets R4 is *not screened* with that reason: the general practitioner's CBC never waits for the startup's model, and is not screened again later. Screening runs in the same transaction as the analysis, so an analysed lab order is a released lab report; there is no separate release step. | `screening.feature` |
| R9 | The lab report shows the values under NHANES's names and units, without reference ranges or any mark; the comment *Ferritin suggested.* appears only for *ferritin suggested*. The hospital sends one bit, *ferritin suggested*, so *ferritin not suggested* and *not screened* look the same at the practice and show nothing about screening. Under a CBC lab report without a suggestion, whatever the reason, the same note: "No ferritin suggestion. This does not rule out iron deficiency." Under the values: "Reference intervals are not shown: the demo has no laboratory's intervals." (ISO 15189 lists them, WHO LQMS p. 193; no laboratory's intervals are sourced). | `screening.feature` (the bit the hospital sends), `messaging.feature`, `reports.feature` |
| R11 | *Order ferritin* is offered beside the comment of a lab report with *ferritin suggested* while that lab report's sample has no ferritin order (R26); it opens the ferritin order page on that sample, so the laboratory measures ferritin on the stored sample (R2). It is never offered without a suggestion: ferritin is ordered on suspicion (report, Use case). A ferritin order from the patient page collects a new sample and does not count. | `reports.feature` |
| R12 | A ferritin sample is never screened; its lab report is visible once analysed. | `lab.feature`, `screening.feature`, `reports.feature` |
| R13 | Every general practitioner query is scoped to the general practitioner's own patients; another general practitioner's order or lab report returns 404. | `access.feature` |
| R14 | Lab queries select only sample ID, ordering general practitioner, registered sex, age, test, indication and results; never the patient's name. | `access.feature` |
| R15 | `DEMO_LOGIN` (default off) shows one POST login button per seeded user. A deploy check fails when `DEMO_LOGIN` is on and `DEBUG` is off. | `access.feature` |
| R22 | Placing an order sends a lab order (DF23) to the general practitioner's one hospital; the hospital records it once, however often the same message arrives. | `messaging.feature` |
| R23 | The general practitioner's app fetches its new lab reports (DF25) from its hospital every `REPORT_CHECK_SECONDS` (60; the demo 5) and on *Check for reports*, and a lab report it is still waiting for says within how many seconds new ones arrive; it is always the client, the hospital never connects to it. | `messaging.feature` |
| R24 | The hospital's messaging endpoint accepts only a client certificate issued by that hospital's own certificate authority, for its general practitioner's app; any other client, the startup's included, is refused before a message is read. The hospital tells apps apart by their certificate's name: a sample is known by app and sample ID, and an app fetches and acknowledges only the lab reports of its own lab orders. The app stores each lab report on its own: one it cannot match to an order stays unacknowledged and holds back no other. | `messaging.feature` |
| R25 | DF23 and DF25 carry exactly the fields of `web/messaging/messages.proto` (§10): no patient name, no blood values in DF1. | `messaging.feature`, `tests/test_messages.py` |
| R26 | *Collect sample* records blood collected from the patient, at `now`, with the patient's next sample ID; a patient may give any number of samples, and nothing reaches the hospital until a test is ordered. Tests are ordered on a sample afterwards; a test is ordered at most once per sample (`already_ordered`). Drawing first and choosing the tests afterwards simplifies WHO LQMS 5-3 (p. 64), where the request comes first: a sample here stands for one blood draw into the standard tubes. | `ordering.feature` |
| R16 | The ClientApp's deploy handler writes each final model as a new file named after its Flower run ID into the node's `final-models-path`, never overwriting one, with the threshold, the federated metrics the ServerApp sends, and its local validation on this hospital's validation split: the confusion matrix at the final model's threshold, as counts, and AUROC. Training results are unchanged. | `tests/test_final_models.py` |
| R17 | The Screening models page lists every screening model; one that is unreadable, trained on other features than `FEATURES`, or lacks a threshold or standardization is shown as *cannot be deployed* with the reason, and deploying it is refused with that reason's code. | `deployment.feature` |
| R18 | The laboratory director deploys any screening model that can be deployed, including an older one (rollback). The app keeps the deployment history (screening model, deployed at) and nothing else: no account, no reason. Past screening results are never re-screened. | `deployment.feature` |
| R19 | Before each screening the deployed model's file is hashed; if it no longer matches the SHA-256 recorded at deployment, there is no usable deployed model (R8). | `deployment.feature`, `screening.feature` |
| R20 | A final model's metadata holds only this hospital's local validation and the federated aggregate the ServerApp computed; never another hospital's metrics. | `tests/test_final_models.py` |
| R21 | Each party has its own folder (§9); a hospital's web app reads only its own (`HOSPITAL_DIR`), a practice's only its own (`PRACTICE_DIR`), and each installs, migrates and serves only its own party's apps: a hospital's database has no table for patients, a practice's none for lab orders, analyser values or final models (test and audit check), and code under `web/` imports from the training package only `iron_deficiency.screening` and `iron_deficiency.dataset` (audit check). | `tests/test_settings.py`, `tools/audit.py` |
| R27 | The SuperLink admits only SuperNodes registered with it (Flower's SuperNode authentication, which needs TLS). Each hospital makes its own key pair in its own folder and hands the startup only the public key; the startup registers each hospital's public key before any SuperNode starts. A node with another key, or none, is refused and gets no global model, no final model and no run configuration (DF7, DF8). | `tests/test_supernode_auth.py`, `tests/test_containers.py` |
| R28 | The ClientApp, the startup's code at each hospital (DF7, TB4), runs in a container of its own that mounts only the hospital's `cohort/` (read-only) and `final-models/`, on a network it shares only with its hospital's SuperNode: it sees no database, no key and no other party's folder, and reaches neither the hospital's web app nor anything outside the deployment, so what it sends leaves only through DF9 and DF10. | `tests/test_compose.py`, `tests/test_containers.py` |
| R29 | Each of the six web apps runs gunicorn with `DEBUG` off, so Django's deploy settings apply (HTTPS redirect, secure cookies, HSTS), serving HTTPS with a certificate from the demo's one browser CA, which names `<party>.localhost`, `localhost` and `127.0.0.1` and may name nothing outside `localhost` and `127.0.0.1` (X.509 name constraints), so trusting it lends its key no power over real sites; WhiteNoise serves the stylesheets. The browser CA's key stays in `demo/browser-ca/`, in no party's folder; the person running the demo trusts it once with `CAROOT=demo/browser-ca mkcert -install`, on macOS, Arch and Ubuntu alike; mkcert finds `rootCA.pem` but no key, so it installs and never issues. Only `prepare`, which seeds the demo accounts, runs with `DJANGO_DEBUG` (R15). | `tests/test_compose.py`, `tests/test_containers.py`, `tests/test_demo.py` |

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
| Deployment (`compose.yaml`, `tools/demo.py`) | Software | Runs each process in its own container, one network per trust boundary and per crossing (§9, R21, R28); registers each hospital's SuperNode key before the SuperNodes start (R27) |
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
| O17 | Someone other than the general practitioner's app sends orders or reads lab reports | P0 | R24; the hospital is its own CA, so the startup cannot issue a certificate |
| O18 | A lab order is sent twice (retry after a lost reply) | R22 | Recorded once by sample ID and test; the repeat is acknowledged |
| O19 | The laboratory links tests of the same patient | P0 | Accepted: only through the shared sample ID; real laboratories link through the national register number |
| O20 | A node that is not a hospital connects to the SuperLink and receives every round's global model, the final model and the run configuration | P0 | R27 |
| O21 | The startup's ClientApp reads what the hospital's process can read, such as the laboratory's records, and returns it in its model update | P0 | R28 |

## 5. Operations

All are POSTs that redirect on success; model and manager methods take `now`.

| Operation | Actor | Precondition | Postcondition | Requirements |
|---|---|---|---|---|
| Fetch lab reports | General practitioner's app | Every `REPORT_CHECK_SECONDS`, or *Check for reports* | New lab reports stored at the general practitioner's app | R23 |
| Collect sample | general practitioner | Patient is the general practitioner's | A sample with the patient's next sample ID, collected at `now`; nothing sent; then the sample's CBC order page | R13, R26 |
| Place order | general practitioner | Sample is one of the general practitioner's patient's; indication given iff test is CBC; the test not yet on the sample | The order on the sample, sex and age copied; its lab order sent | R1, R13, R26 |
| Run analyser | Laboratory staff | Lab order arrived, not analysed | Values recorded; a CBC screened, or not screened with its reason; lab report released | R3, R8, R12 |
| Deploy | Laboratory director | Screening model can be deployed (R17) | It is the deployed model from `now` | R18 |
| Log in as (demo) | Anyone | `DEMO_LOGIN` on | Session for that seeded user | R15 |

## 6. Pages

| Page | Role | Content |
|---|---|---|
| Log in | Anyone | Django login form; refuses an account without a role; demo buttons when `DEMO_LOGIN`. Afterwards, and at `/`, the start page of the user's role |
| Patients (start page) | general practitioner | *Ferritin suggested (n)*: lab reports suggesting ferritin whose sample has no ferritin order yet, newest first, each with patient, sample ID, release time and *Order ferritin*; then a search by name (contains, any case) and own patients: name, registered sex, age. Served by the general practitioner's app, not the hospital's |
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

## 8. Data

- Patients: NHANES 2021–2023 (`iron_deficiency.dataset.load_new_samples`), all sexes and ages, seeded at the general practitioner's app (`--patients`, default 12, shared by the seeding groups; the demo seeds De Akker 40, De Berk 24, De Ceder 12, the same number at each practice's hospital; doctor-a gets two for every one of doctor-b's); each has a fictional Flemish name matching their registered sex (common Flemish first names, the ten most common family names of the Flemish Region, Statbel); each patient is one NHANES participant, whose number starts each of their sample IDs.
- The hospital's analyser stand-in holds the same cycle's values (13 CBC values, ferritin from `load_ferritin`), looked up by the NHANES number in the sample ID: what the samples in its laboratory would measure. Every sample of one patient measures the same values, as NHANES measured each participant once. No values travel in a message.
- NHANES measured ferritin only for women aged 12–49 (FERTIN_L, eligible sample). The demo seeds no woman aged 18–49 whom it did not measure; for men and other women the hospital's stand-in holds a made-up ferritin, the measured ferritin of an eligible woman at or above the cutoff picked by sample ID, reported as *Ferritin (made up for the demo)*, never as ferritin. A participant with neither gets *not available in the demo data*.
- Age is the NHANES age at the survey and does not change.
- Registered sex has the two NHANES values, female and male.

## 9. Demo deployment: one container per process, one network per trust boundary

`compose.yaml` runs the demo: one container per process, one Docker network
per trust boundary of the report's DFDs and one per crossing, and in each
container only the folders its process needs, mounted at the same path under
`/demo` as on the host. Everything lives under `demo/` (gitignored):

```
demo/
├── startup/                     TB2
│   ├── certificates/            the startup's CA and the SuperLink's certificate
│   ├── trust/                   the startup's CA certificate alone, for its clients
│   ├── superlink/               DS3 run state, configuration, messages, registered SuperNodes
│   ├── supernodes/              each hospital's SuperNode public key, as handed over (R27)
│   └── final-models/            DS4 the startup's copy of every final model, one per run (DF13)
└── hospitals/
    ├── uz-leuven/               TB1
    │   ├── cohort/              DS2 training cohort (2005–2006)
    │   ├── web-tls/             the web app's certificate from the browser CA (R29)
    │   ├── supernode/           the SuperNode's key pair; the private key never leaves (R27)
    │   ├── final-models/        DS5 one file per training run (R16)
    │   ├── ca/, messaging/      its CA; the lab-order endpoint's certificate
    │   └── web.sqlite3          DS8 screening records, DS6 deployment history
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

| Container | Image | Network | Mounts |
|---|---|---|---|
| `superlink` | `flwr/superlink` | `startup`, `model-updates` | `startup/superlink`, `startup/certificates` (read-only) |
| `serverapp` | built: SuperExec with the app's dependencies | `startup` | `startup/trust`, `startup/final-models` |
| `<hospital>-supernode` | `flwr/supernode` | `model-updates`, `<hospital>-clientapp` | its `certificates/` and `supernode/` (read-only) |
| `<hospital>-clientapp` | built: SuperExec with the app's dependencies | `<hospital>-clientapp` | its `cohort/` (read-only), `final-models/` (R28) |
| `<hospital>-web`, `<hospital>-lab-orders` | built: the project | `<hospital>`; the endpoint also `<hospital>-lab-orders` | its folder, with `cohort/` and `supernode/` masked and `final-models/` read-only |
| `<practice>-web`, `<practice>-reports` | built: the project | `<practice>`, its hospital's `<hospital>-lab-orders` | its folder |
| `proxy` | `nginx` (`docker/sni-proxy.conf`) | every `<hospital>` and `<practice>` network | none |

`startup`, `model-updates` (DF7–DF10), each `<hospital>-clientapp` (TB4) and
each `<hospital>-lab-orders` (DF23, DF25) are internal networks: nothing on
them reaches outside the deployment. Only the `proxy` is published, on
`127.0.0.1:443` (`DEMO_HTTPS_PORT`): it routes each `<party>.localhost`
(RFC 6761) to that party's web app by the name in the TLS handshake, without
decrypting, so it sees names, never content. The SuperLink admits
only the registered SuperNodes (R27); a SuperNode runs no app itself
(`--isolation process`): its hospital's ClientApp container fetches the run
from it, and the ServerApp container likewise from the SuperLink.

Three one-shot containers stand outside the DFDs. `prepare` is out-of-band
setup, the one container that sees every party's folder: certificates, keys,
cohorts, the NHANES data, migrated and seeded databases. `register` registers
each hospital's public key once the SuperLink answers, before any SuperNode
starts. `train` is the data scientist (E1), submitting a run from inside TB2:
`docker compose run --rm train`. Every container runs as `DEMO_USER` (default
`1000:1000`), so on Linux `demo/` belongs to one user. The web apps run gunicorn with `DEBUG` off
and HTTPS (R29), each with a certificate under its folder's `web-tls/` from
the browser CA in `demo/browser-ca/`, which belongs to no party.

`python tools/demo.py reset`, with the demo stopped, removes the six web databases so the next `docker compose up` migrates and seeds afresh; certificates, cohorts, final models and NHANES data stay.

Each web app takes a Pico colour theme from `PARTY_COLOUR` (vendored themes only; absent: Pico's default), so the parties' pages are told apart at a glance: UZ Leuven jade and De Akker green, Heilig Hart Leuven pumpkin and De Berk amber, AZ Diest violet and De Ceder purple.

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
