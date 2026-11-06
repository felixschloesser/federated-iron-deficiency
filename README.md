# Federated Iron-Deficiency Classification

This [Flower](https://flower.ai/) app trains a
[PyTorch](https://pytorch.org/) binary classifier to identify iron deficiency
from routine complete blood count measurements and age. Iron deficiency is
defined as ferritin below 15 ng/mL.

The federation has three clients, standing in for a large, a medium, and a
small hospital. Each holds a different
[NHANES](https://www.cdc.gov/nchs/nhanes/) survey cycle: 2005–2006, 2015–2016,
and 2017–2018, keeping fixed 50% and 25% samples for the medium and small
hospitals. Each client trains on its own locally standardized data.

After training, the ServerApp deploys the final model to every hospital, and
each hospital screens new blood counts locally with `ml.screening`.

## Changes from `@javier/iron-deficiency`

This app extends [`@javier/iron-deficiency`](https://flower.ai/apps/javier/iron-deficiency/)
v1.3.0 for a privacy impact assessment of a hypothetical deployment: a startup
and three Belgian hospitals.

- **Package `ml/`.** The original's package is `iron_deficiency/`; here the
  Flower app is `ml/`, beside the web app in `web/` and the demo in `demo/`.
- **Data from Hugging Face.** The original downloads the NHANES files from the
  CDC on each client. Here the cohorts come from a pinned revision of
  `gracemyu/nhanes-merged` through Flower Datasets, so the app also runs in
  simulation, and a SuperNode reads its partition from the `data-path` in its
  node config instead of a `CYCLES` name.
- **No evaluation on other hospitals' data.** The original ClientApp also
  evaluated on a global test set built from every cycle, so each client loaded
  the other clients' data. Each client now evaluates on its own validation
  split only.
- **W&B key at submit time.** The key is passed with `-c` instead of being set
  in `pyproject.toml`, which is packaged with the app.
- **Three hospitals instead of four cycles.** The 2015–2016 and 2017–2018
  cycles keep fixed 50% and 25% samples, giving a large, a medium, and a small
  hospital (about 5:2:1). The latest cycle, 2021–2023, no longer trains, so it
  can stand in for new blood counts screened after training.
- **Final models.** The original app stops after training. Here the startup
  keeps each final model, and its data scientist transmits one to every
  connected hospital in a run of its own (`transmit-final-model=<run ID>`),
  with the aggregated evaluation metrics; the run fails unless every connected
  hospital acknowledges it. Each stores it as a new file named after the training run ID in its
  `final-models-path`, with its own standardization and a local validation on
  its validation split: the confusion matrix at each threshold from 0.05 to
  0.95 in steps of 0.05, and AUROC (`ml/final_models.py`). A
  hospital decides itself which final model to deploy, and at which threshold. The startup keeps a copy of every final
  model in `<demo-dir>/startup/final-models/`, so the assessment can cover how
  the model is used, not only how it is trained.
- **Local screening** (`ml/screening.py`). Only registered women
  aged 18–49 are scored, as the model was trained on them alone. Only each
  sample ID and its decision leave the screening, with no scores or other input
  columns.
- **Seeded training.** The initial weights and dropout are seeded, so repeated
  runs give the same flags.
- **Evaluation scripts** (`analysis/`, run from a checkout; not in the FAB).
  They check flags against ferritin, which the screening never sees, and train
  a centralized baseline to compare against.
- **Tests** for the screening, run with `pytest`.

## Run on SuperGrid

The app is designed for a SuperGrid deployment federation with three SuperNodes.
Before connecting a SuperNode, first register its public key with SuperGrid and
then add the registered SuperNode to the deployment federation of interest. See
[Create and Manage Federations on SuperGrid](https://flower.ai/docs/framework/how-to-create-and-manage-federations.html)
and
[Connect SuperNodes to SuperGrid](https://flower.ai/docs/framework/how-to-connect-supernodes-to-supergrid.html).

Each SuperNode loads one survey cycle from its own disk. To generate demo
partitions, download the cohorts and save one partition per cycle
(`demo_data/2005-2006`, `demo_data/2015-2016`, ...), plus new blood counts to
screen (`demo_data/new_samples.csv`, from the unused 2021–2023 cycle):

```shell
python -m ml.dataset --out-dir demo_data
```

Then pass each SuperNode the path to its partition, and where to store the
deployed model, through its node configuration. For example:

```shell
flower-supernode \
  --superlink fleet-supergrid.flower.ai:443 \
  --auth-supernode-private-key ~/path/to/supernode/private/key \
  --node-config "data-path='/path/to/demo_data/2005-2006' final-models-path='/path/to/final-models'" \
  --allow-runtime-dependency-installation # optional
```

Launch the other two SuperNodes in the same way, pointing `data-path` to the
`2015-2016` and `2017-2018` partitions and `final-models-path` to their own
folders.

Once the three SuperNodes are online and part of the federation, follow
[Run Flower Apps on SuperGrid](https://flower.ai/docs/framework/how-to-run-flower-apps-on-supergrid.html)
to submit the app.

The dataset is built from the NHANES demographics, complete blood count, and
ferritin components, read from the
[`gracemyu/nhanes-merged`](https://huggingface.co/datasets/gracemyu/nhanes-merged)
dataset (CC0) at a pinned revision. It includes women aged 18–49 with complete
measurements, using 13 blood-count variables plus age as model features.

## Run in simulation

In simulation, each virtual SuperNode loads the cycle matching its
`partition-id` from the Hugging Face dataset. The first run downloads about
280 MB; set `HF_TOKEN` for faster downloads. Use three virtual SuperNodes, one
per cycle, and submit the app to the simulation federation:

```shell
flwr federation simulation-config @<username>/<federation-name> supergrid --num-supernodes 3
flwr run . supergrid --federation @<username>/<federation-name>
```

On SuperGrid, the final models stay with the virtual SuperNodes. To screen
with them, run the simulation on your machine instead. Each virtual SuperNode
then stores its final model in `<demo-dir>/hospitals/<hospital>/screening-models/`,
where the hospitals are `uz-leuven`, `heilig-hart-leuven` and `az-diest`
(partitions 0, 1 and 2). `demo-dir` must be absolute; it defaults to
`~/.cache/iron-deficiency`:

```shell
flwr run . --federation-config "num-supernodes=3" --run-config "demo-dir='$PWD/.demo'" --stream
```

`flwr run` starts a local SuperLink in the background and reuses it for later
runs, from any checkout: its simulation imports `ml` from the
environment it was started in. Stop it (`pkill -f flower-superlink`) before
running the simulation from another checkout.

## Run the demo deployment

The whole scenario in containers, one network per trust boundary: see
`demo/README.md` in the repository.

## Screen new blood counts

Each hospital screens a lab export of new blood counts with its deployed model.
The export is a CSV with `sample_id`, registered `sex`, `age`, and the 13
blood-count variables; other columns are ignored. Only women aged 18–49 are
screened, as the model was trained on them alone:

```shell
python -m ml.screening \
  --model ~/.cache/iron-deficiency/hospitals/az-diest/screening-models/<run-id>.pt \
  --input demo_data/new_samples.csv \
  --threshold 0.5 \
  --output screening-results.csv
```

The output holds only each `sample_id` and its screening result: `ferritin
suggested`, `ferritin not suggested`, or `not screened`. The threshold is the one the hospital deploys the model
at; a training run sets none.

## Evaluate a screening

The screening never sees ferritin. To check a deployed model against the
women's actual ferritin, print its AUROC and the confusion matrix of its flags:

```shell
python -m analysis.evaluate_screening \
  --model ~/.cache/iron-deficiency/hospitals/az-diest/screening-models/<run-id>.pt \
  --input demo_data/new_samples.csv \
  --threshold 0.5
```

Training is seeded with the `model-seed` run config value, so repeated runs give
the same flags. To see how much the results depend on the seed, and how
federated training compares with a centralized baseline, train both once per
seed and evaluate every hospital's deployment:

```shell
python -m analysis.seed_sweep --seeds 10  # writes seed_sweep.csv
```

The centralized baseline (`analysis/train_centralized.py`) trains on the union of
the hospitals' training splits, with each row standardized by its own hospital
and the same seed, hyperparameters, and epochs. Pooling the training instead of
averaging updates is the only difference. The sweep reports the federated minus
centralized AUROC per hospital, paired by seed, and whether it lies within ±0.01.

## Tests

```shell
uv run pytest
```

## Weights & Biases

To upload the aggregated strategy metrics after a run, export your W&B API key
and pass it when you submit the app. Without it, W&B logging is disabled:

```shell
export WANDB_API_KEY=<your-key>
flwr run . supergrid --federation @<username>/<federation-name> \
  -c "wandb-api-key='$WANDB_API_KEY'"
```

The ServerApp runs on SuperGrid, so it cannot read your local environment. Do
not put the key in `pyproject.toml`, since that file is packaged with the app.

## Ways to improve the app

For background and step-by-step guidance, follow the Flower tutorial series:
[Get started with Flower](https://flower.ai/docs/framework/tutorial-series-get-started-with-flower.html),
[Write your first Flower App](https://flower.ai/docs/framework/tutorial-series-write-your-first-flower-app.html),
[Write your first Flower App with PyTorch](https://flower.ai/docs/framework/tutorial-series-write-your-first-flower-app-pytorch.html),
[Use a federated learning strategy](https://flower.ai/docs/framework/tutorial-series-use-a-federated-learning-strategy-pytorch.html),
[Customize a Flower Strategy](https://flower.ai/docs/framework/tutorial-series-build-a-strategy-from-scratch-pytorch.html),
and
[Communicate custom Messages](https://flower.ai/docs/framework/tutorial-series-customize-the-client-pytorch.html).

Fetch the app into a local directory so you can modify and experiment with it:

```shell
flwr new @javier/iron-deficiency
```

Possible next steps for experimenting with and improving the app include:

- Tune hyperparameters such as the learning rate, weight decay, batch size, and
  number of training rounds.
- Change the model architecture or compare it with other models suitable for
  tabular clinical data.
- Try a different built-in federated aggregation strategy.
- Create a custom aggregation strategy tailored to differences between the
  three NHANES cohorts.

After making your changes, submit the app to your SuperGrid federation:

```shell
cd iron-deficiency
flwr run . --federation @<username>/<federation-name> supergrid
```
