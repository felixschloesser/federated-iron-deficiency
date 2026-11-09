# Glossary

The domain's words, what each means, and where it comes from. Models, forms,
templates and copy use them. Sources: the privacy impact assessment report
("Report"), the WHO *Laboratory Quality
Management System Handbook* (2011, "WHO LQMS"), the clinical guidelines named,
and "project decision" where none of them has a word.

Each party speaks its own language: the practice *orders*, the wire carries a
*lab order*, the laboratory works on a *test request*.

## Shared

| Term | Meaning | Source |
|---|---|---|
| practice | A general practitioner's practice; it orders tests at a hospital through its own app and has one general practitioner. | Report, "Federated version" |
| laboratory | A hospital's laboratory that a practice sends samples to; every test on a sample goes where the sample went. | Report, "Federated version" |
| startup | The company that trains the model with the hospitals and keeps the final models. | Report, Stakeholders table |
| name | A party's own name, shown on its pages; a practice or hospital calls another party as the name's slug, which the receiving party must know. | Project decision; stands for the certificate name of the report's mutual TLS |
| lab order | What travels from practice to hospital: sample ID, test, clinical indication, registered sex and age; no name, no values. | Report |
| lab report | What the hospital returns for one test: the results, and whether ferritin is suggested. | Report |
| acknowledgement | The practice's word that a lab report arrived; the laboratory then sends it no more. | HL7 v2, ch. 2 (ACK) |
| rejection | The laboratory refuses a lab order whose information is insufficient, with a reason per field; the general practitioner collects a new sample to order again. | WHO LQMS 5-4, p. 66 |
| test | What an order asks the laboratory to measure: a CBC or ferritin. | Report, Use case |
| CBC (complete blood count) | The routine blood test the hospital screens: 13 values such as haemoglobin and red cell size. | Report, Use case |
| sample | Blood collected from one patient at one time; it may carry a CBC and a later ferritin. | WHO LQMS ch. 5 |
| sample ID | The number on a sample's label that links its lab order, results and lab report; each sample has its own. | Report; WHO LQMS 5-3, p. 64 |
| registered sex | The sex in the patient's record, which may differ from the person's; the screening covers women. | Report, Data table |
| clinical indication | Why the general practitioner orders a CBC; the hospital decides from it whether the CBC is screened. | Report, Data table |
| suspected anaemia | Screened: ferritin follows only once anaemia is found, so iron deficiency without anaemia is missed. | Domus Medica 2012, S6; NHG Anemie 2014 |
| suspected irritable bowel syndrome | Screened: the guideline orders a CBC without ferritin. | Domus Medica 2012, S8 |
| unexplained fatigue | Screened: the guideline adds ferritin for women of childbearing age, so the suggestion helps only where it was left out. | Domus Medica 2012, S8 |
| start of pregnancy | Not screened: pregnancy has its own haemoglobin rule. | Domus Medica 2012, S9 |
| chronic kidney disease follow-up | Not screened: its anaemia has another cause. | WOREL 2026, p. 42 |
| other | Not screened: any reason not listed. | Project decision |
| screening model | A released final model as a hospital holds it, with this hospital's standardization and local validation; named by when it arrived. | Report, Use case |
| result names and units (*Hemoglobin*, g/dL; *Ferritin*, ng/mL) | NHANES's own names and units, unconverted. | NHANES 2021–2023 CBC_L and FERTIN_L codebooks |
| Flower container (`flower-` prefix) | A compose service that is a Flower component, not a party's own app. | Flower docs, *Flower Architecture* |

## Hospital

| Term | Meaning | Source |
|---|---|---|
| laboratory staff | The people who run the analyser on test requests. | WHO LQMS |
| laboratory director | Decides which screening model screens the hospital's patients, and provides its training cohort. | WHO LQMS ch. 2, p. 21 |
| analyser | The instrument that measures a sample; outside the laboratory's software, simulated in the demo by NHANES 2021–2023 women aged 18–49, whose numbers are the practices' sample IDs. | Report |
| test request | One test on a sample, as the laboratory received it from a lab order. | WHO LQMS |
| stored sample | A sample the laboratory already holds; a later test is measured on it. | WHO LQMS 5-5, p. 68 |
| analysed | A test request the analyser has measured. | Report |
| screening | Running the deployed screening model on an analysed CBC to decide whether to suggest ferritin. | Report |
| inference | The training code's word for the same step (`ml.inference`). | PyTorch docs |
| screened indication | A clinical indication the hospital screens a CBC for. | Report, Data table |
| not eligible | A CBC the screening does not cover: indication not screened, not female, or not aged 18–49. | Report, Use case |
| screening result | Ferritin suggested, ferritin not suggested, not screened, or screening failed (no usable deployed screening model). | Report; "screening failed": project decision 2026-11-08 |
| deploy | The laboratory director's decision that a screening model screens, at a threshold they choose. | Report, Use case |
| deployed screening model | A screening model as deployed, with its threshold and its file's hash; the latest is the one that screens. | Report |
| threshold | The score at or above which the deployed screening model suggests ferritin. | Report, Design choices |
| fetch | The laboratory director's request for new screening models; none enters the hospital otherwise. | Report |
| lab record | What the laboratory holds of a past patient; what the training cohort is extracted from. | Report |
| past patient | An eligible woman with a complete CBC for a screened indication, a ferritin and a CRP in the lab records. | Report |
| training cohort | The 13 CBC values, age and label per past patient, which the startup's code at the hospital trains on. | Report |
| provide / withdraw | The laboratory director lets the startup's code at the hospital train on the training cohort, or takes it back. | Project decision |
| local validation | A screening model on this hospital's held-out split: the confusion matrix at each threshold, and AUROC. | Report |
| sensitivity, specificity, positive and negative predictive value | How well a screening model finds iron deficiency at a threshold, shown as counts. | WHO LQMS 3-3, p. 40 |
| 95% confidence interval | The range a measure would likely fall in on other past patients like these. | WHO ferritin guideline 2020, p. 38 |
| inflammation | A CRP above 5 mg/L; with it, ferritin below 70 ng/mL counts as iron deficient instead of below 15. | WHO ferritin guideline 2020, rec. 1.2 |
| CRP, mg/L | The result that says whether a past patient had inflammation. | WHO ferritin guideline 2020; NHANES HSCRP |

## Practice

| Term | Meaning | Source |
|---|---|---|
| general practitioner | The doctor who orders tests and reads lab reports; one per practice. | Report, Stakeholders table |
| patient | A person the general practitioner orders a test for; known by name only at the practice. | Report, Use case |
| order | What the general practitioner places for a test on a sample. | WHO glossary, "physician's order" |
| collected | When the practice takes the blood. | WHO LQMS 5-3, p. 64 |
| primary laboratory | The laboratory preselected for a new sample. | Project decision |
| comment | The text beside a suggestion: "Ferritin suggested by the hospital's screening of this CBC. Likely iron deficiency; not a diagnosis." | Report, Use case |

## Startup

| Term | Meaning | Source |
|---|---|---|
| data scientist | The startup's one person: submits training runs and releases final models. | Report |
| training run | One federated training, from submission to the final model the startup keeps. | Report; `flwr run` |
| submit / stop | Start a training run, or end one in progress. | Report; `flwr run`, `flwr stop` |
| run status | Pending, Starting, Running, Completed, Failed or Stopped, in Flower's words. | `flwr ls` |
| run configuration | The training parameters chosen at submission and kept with the final model. | `flwr run --run-config`; Report |
| rounds, local epochs, learning rate, weight decay, batch size, seed | The training parameters. | Flower run configuration; PyTorch |
| final model | The model one training run ends with, kept at the startup. | Report |
| release | The data scientist's act that lets recipient hospitals fetch a final model. | Report |
| recipient hospital | A hospital the startup registers; it may fetch every released final model. | Report, "Federated version" |
