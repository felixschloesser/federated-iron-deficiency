# Federated Iron-Deficiency Classification

A worked example for a privacy impact assessment: a startup and three Belgian
hospitals train a model together with [Flower](https://flower.ai/), without
any hospital's patient data leaving it, and the hospitals then use the model to
screen routine blood counts for iron deficiency.

The model is a [PyTorch](https://pytorch.org/) binary classifier on the 13
values of a complete blood count (CBC) and age. Iron deficiency is ferritin
below 15 ng/mL, or below 70 ng/mL with inflammation (CRP above 5 mg/L), as the
WHO ferritin guideline (2020) defines it for adults. The data is
[NHANES](https://www.cdc.gov/nchs/nhanes/): each hospital holds one survey
cycle (2005–2006, 2015–2016, 2017–2018, about 5:2:1 in size), and the 2021–2023
cycle, which never trains, stands in for new patients. The app extends
[`@javier/iron-deficiency`](https://flower.ai/apps/javier/iron-deficiency/)
(see [Changes from upstream](#changes-from-upstream)).

## Parties and what crosses between them

Three kinds of party, each with a web app of its own: the general
practitioner's **practice**, the **hospital** (its laboratory), and the
**startup**. `GLOSSARY.md` defines the words.

| From → to | What | Carries | Over |
|---|---|---|---|
| practice → hospital | lab order | sample ID, test, clinical indication, registered sex, age; no name, no values | gRPC, `SendLabOrder` |
| hospital → practice | lab report | sample ID, test, results, whether ferritin is suggested; never the score | gRPC, `FetchNewLabReports` |
| practice → hospital | acknowledgement | sample ID and test of each lab report received | gRPC, `AcknowledgeLabReports` |
| startup → SuperLink | training run | the app and its run configuration | `flwr run` |
| startup ↔ hospital | each round | the global model's weights and learning rate; back, the updated weights, training loss, validation loss and AUROC, and example counts | Flower |
| startup → hospital | screening model | a released final model's weights and its AUROC across hospitals; never its run configuration | gRPC, `FetchNewScreeningModels` |

The messages are defined in `web/shared/grpc/messages.proto`; the Flower ones
in `ml/server_app.py` and `ml/client_app.py`. Every gRPC call is made by the
practice or the hospital, which names itself by its name's slug; the demo
leaves out mutual TLS.

Inside the hospital, the laboratory director provides the training cohort to
the startup's ClientApp, fetches screening models, validates each on the
hospital's own held-out past patients, and deploys one at a threshold of their
choosing. When laboratory staff analyse a CBC for a screened indication in a
woman aged 18–49, the deployed screening model decides whether the lab report
suggests ferritin.

## Layout

- `web/`: the three parties' web apps, each a Django project of its own
  (`DJANGO_SETTINGS_MODULE=web.<party>.settings`):
  - `web/hospital/`: the laboratory, its training cohort, the screening models
    it deploys, and its analyser stand-in;
  - `web/practice/`: the general practitioner's patients, samples and orders;
  - `web/startup/`: training runs and the final models the data scientist
    releases;
  - `web/shared/`: what all three use: accounts, the gRPC messages, the page
    templates and stylesheet.
- `ml/`: the Flower app: the ServerApp at the startup, the ClientApp at each
  hospital, and the model.
- `demo/`: the whole scenario in containers, one per server (`demo/README.md`).
- `features/`: the requirements as Gherkin scenarios, one folder per party, the
  ones crossing parties at the top.
- `tests/`: the scenarios' steps and the other tests (see [Tests](#tests)).
- `GLOSSARY.md`: each party's words, what each means and where it comes from.

## Run the demo

The whole scenario, every party in its own containers: see `demo/README.md`.

## Run in simulation

Each virtual SuperNode loads the cycle matching its `partition-id` from a
pinned revision of the
[`gracemyu/nhanes-merged`](https://huggingface.co/datasets/gracemyu/nhanes-merged)
dataset (CC0). The first run downloads about 280 MB; set `HF_TOKEN` for faster
downloads. On your machine, keeping each final model as
`<run-id>.pt` in the absolute folder `FINAL_MODELS_DIR` names, which must exist;
the startup's web app reads `.data/startup/final-models` and creates it. Without
`FINAL_MODELS_DIR`, a run keeps no final model, as on SuperGrid:

```shell
FINAL_MODELS_DIR=$PWD/.data/startup/final-models flwr run . --federation-config "num-supernodes=3" --stream
```

`flwr run` starts a local SuperLink in the background and reuses it for later
runs, from any checkout: its simulation imports `ml`, and reads
`FINAL_MODELS_DIR`, from the environment it was started in. Stop it
(`pkill -f flower-superlink`) before running from another checkout or with
another `FINAL_MODELS_DIR`.

On SuperGrid's simulation federation instead, with three virtual SuperNodes:

```shell
flwr federation simulation-config @<username>/<federation-name> supergrid --num-supernodes 3
flwr run . supergrid --federation @<username>/<federation-name>
```

## Run on SuperGrid

The app is designed for a SuperGrid deployment federation with three
SuperNodes. Register each SuperNode's public key with SuperGrid and add it to
the federation first: see
[Create and Manage Federations on SuperGrid](https://flower.ai/docs/framework/how-to-create-and-manage-federations.html)
and
[Connect SuperNodes to SuperGrid](https://flower.ai/docs/framework/how-to-connect-supernodes-to-supergrid.html).

Each SuperNode reads the training cohort in its `data-path`, as a hospital's
web app writes it when its laboratory director provides one. To write one per
cycle from NHANES instead (`demo_data/2005-2006`, `demo_data/2015-2016`, ...):

```shell
python -m ml.dataset --out-dir demo_data
```

Then start each SuperNode with its folder:

```shell
flower-supernode \
  --superlink fleet-supergrid.flower.ai:443 \
  --auth-supernode-private-key ~/path/to/supernode/private/key \
  --node-config "data-path='/path/to/demo_data/2005-2006'" \
  --allow-runtime-dependency-installation # optional
```

and the other two with `2015-2016` and `2017-2018`. Once all three are online,
submit the app as
[Run Flower Apps on SuperGrid](https://flower.ai/docs/framework/how-to-run-flower-apps-on-supergrid.html)
describes.

The cohorts hold women aged 18–49 with complete measurements: 13 blood-count
variables plus age as features.

### Weights & Biases

To upload the aggregated metrics after a run, pass your W&B API key when you
submit; without it, W&B logging is off. The ServerApp runs on SuperGrid, so it
cannot read your environment, and the key must not go in `pyproject.toml`,
which is packaged with the app:

```shell
flwr run . supergrid --federation @<username>/<federation-name> \
  -c "wandb-api-key='$WANDB_API_KEY'"
```

## Tests

```shell
uv run pytest                                          # the tests outside the party folders
for party in hospital practice startup; do uv run pytest --ds=web.$party.settings; done   # each party's
uv run pytest -m "not containers and not subprocess and not privacy_issue"   # the quick loop
uv run pytest -m containers                            # against the running demo (Docker)
uv run pytest -m privacy_issue                         # the report's open privacy issues: red until fixed
uv run pytest -m privacy_issue --ds=web.hospital.settings   # and the hospital's
```

Each party's web app is its own Django project, so each party's tests run under
its own settings: a folder named after the party, anywhere under `tests/`,
holds them (`tests/hospital/`, `tests/quality/privacy/hospital/`). Plain
`uv run pytest` leaves them out and says so.

- `tests/<party>/`: each party's scenarios and views.
- `tests/e2e/`: flows through the running demo.
- `tests/quality/security/` and `tests/quality/privacy/`: one test per threat;
  the privacy folder's `conftest.py` says how to write one.

## Changes from upstream

What differs from [`@javier/iron-deficiency`](https://flower.ai/apps/javier/iron-deficiency/)
v1.3.0:

- **Package `ml/`** instead of `iron_deficiency/`, beside the web apps in
  `web/` and the demo in `demo/`.
- **Data from Hugging Face.** The cohorts come from a pinned revision of
  `gracemyu/nhanes-merged` through Flower Datasets instead of the CDC, so the
  app also runs in simulation; a SuperNode reads its partition from the
  `data-path` in its node config instead of a `CYCLES` name.
- **No evaluation on other hospitals' data.** The original ClientApp also
  evaluated on a global test set built from every cycle, so each client loaded
  the others' data. Each client now evaluates on its own validation split only.
- **W&B key at submit time**, with `-c`, not in `pyproject.toml`.
- **Three hospitals instead of four cycles.** The 2015–2016 and 2017–2018
  cycles keep fixed 50% and 25% samples, giving a large, a medium and a small
  hospital. The 2021–2023 cycle no longer trains, so it can stand in for new
  blood counts.
- **Final models.** The original stops after training. Here the startup keeps
  each final model and its data scientist releases one. A hospital's laboratory
  director fetches it as a screening model over gRPC, never through Flower, so
  the startup's code at a hospital writes nothing there. The hospital stores it
  with its own standardization and a local validation on its held-out split:
  the confusion matrix at each threshold from 0.05 to 0.95, and AUROC. Each
  hospital decides which screening model to deploy, and at which threshold.
- **Screening at the hospital.** `ml/inference.py` gives a CBC's probability of
  iron deficiency, which the hospital compares with its threshold. Only
  registered women aged 18–49 are scored, as the model was trained on them
  alone; the lab report says only whether ferritin is suggested.
- **The analyser stand-in.** Each hospital's analyser holds real 2021–2023
  CBCs of women aged 18–49; a practice's sample IDs are their NHANES numbers,
  so every sample carries real held-out blood.
- **Seeded training.** The initial weights and dropout are seeded, so repeated
  runs give the same flags.
