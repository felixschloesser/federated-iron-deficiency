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
each hospital screens new blood counts locally with `iron_deficiency.screening`.

## Changes from `@javier/iron-deficiency`

This app extends [`@javier/iron-deficiency`](https://flower.ai/apps/javier/iron-deficiency/)
v1.3.0 for a privacy impact assessment of a hypothetical deployment: a startup
and three Belgian hospitals.

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
- **Final models.** The original app stops after training. Here the ServerApp
  sends the final model, the `screening-threshold` and the aggregated
  evaluation metrics to every hospital. Each stores it as a new file named
  after the run ID in its `final-models-path`, with its own standardization
  and a local validation on its validation split: the confusion matrix at the
  threshold, and AUROC (`iron_deficiency/final_models.py`). A hospital decides
  itself which final model to deploy. The startup keeps a copy of every final
  model in `<demo-dir>/startup/final-models/`, so the assessment can cover how
  the model is used, not only how it is trained.
- **Local screening** (`iron_deficiency/screening.py`). Only registered women
  aged 18–49 are scored, as the model was trained on them alone. Only each
  sample ID and its decision leave the screening, with no scores or other input
  columns.
- **Seeded training.** The initial weights and dropout are seeded, so repeated
  runs give the same flags.
- **Evaluation scripts** (`scripts/`). They check flags against ferritin, which
  the screening never sees, and train a centralized baseline to compare against.
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
python -m iron_deficiency.dataset --out-dir demo_data
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
then stores its final model in `<demo-dir>/hospitals/<hospital>/final-models/`,
where the hospitals are `uz-leuven`, `heilig-hart-leuven` and `az-diest`
(partitions 0, 1 and 2). `demo-dir` must be absolute; it defaults to
`~/.cache/iron-deficiency`:

```shell
flwr run . --federation-config "num-supernodes=3" --run-config "demo-dir='$PWD/demo'" --stream
```

`flwr run` starts a local SuperLink in the background and reuses it for later
runs, from any checkout: its simulation imports `iron_deficiency` from the
environment it was started in. Stop it (`pkill -f flower-superlink`) before
running the simulation from another checkout.

## Run the demo deployment

The demo runs the whole scenario on your machine: the startup, three
hospitals and each hospital's general practitioner's practice. Each party
runs in its own containers, which see only that party's folder under `demo/`
(gitignored), on Docker networks that follow the report's trust boundaries.
So "UZ Leuven's data never reaches the startup" holds because no network or
mount connects them, not merely because the code is careful. Who the parties
are, and each one's colour and number of seeded patients, is declared in
`demo.toml`.

### 1. Install Docker

On a Mac, [OrbStack](https://orbstack.dev) or Docker Desktop; on Linux,
Docker Engine with the compose plugin (`docker compose version` should
answer). Docker is what keeps the parties apart: every trust boundary gets its
own network, and each party runs in containers of its own. Each container is
one compose *service*: one long-running command, such as gunicorn serving a
hospital's web app, which may start child processes of its own. A service is
not a process of the report's DFDs:

| DFD element | Where it runs |
|---|---|
| P1 Cohort extraction | not built: `prepare` stands in, saving each hospital's cohort |
| P2 SuperNode, ClientApp | two containers: `<hospital>-supernode`, and `<hospital>-clientapp` for the startup's code (TB4) |
| P3 SuperLink | `superlink` |
| P4 ServerApp | `serverapp` |
| P5 Model sale, E3 Other hospitals | not built |
| P6 Model deployment, P9 Lab analysis, P10 Screening | one container, `<hospital>-web`: one Django app, which screens a CBC as it records the analysis |
| P7 Practice app | two containers: `<practice>-web`, and `<practice>-reports`, which fetches lab reports |
| P8 Messaging endpoint | `<hospital>-lab-orders` |
| E1 Data scientist | `train`, run by hand |

Two containers have no DFD element: `register`, part of setup, and `proxy`,
which stands for the network between your browser and the parties.

### 2. On Linux: tell compose who you are

```shell
id -u   # if this prints 1000, skip this step
echo "DEMO_USER=$(id -u):$(id -g)" > .env
```

Every container writes `demo/` as one user, by default `1000:1000`, the first
account on most Linux machines. On Linux a mounted folder keeps numeric user
IDs, so without this your own account could not edit or delete `demo/`. On a
Mac, Docker maps IDs for you.

### 3. Start everything

```shell
docker compose up --build --abort-on-container-failure
```

The first start takes a while. It builds two images (the web apps, and the
startup's Flower app with PyTorch, CPU only), then runs these steps in order:

1. **prepare** creates what each party needs and the DFDs do not draw:
   certificates, keys, the hospitals' training cohorts and the 2021–2023
   blood counts (downloaded from Hugging Face; set `HF_TOKEN` in `.env` if
   it refuses), and each party's database with its demo accounts. It is the
   only container that sees every party's folder: setup done once, out of
   band, like a hospital's IT handing a public key to the startup.
2. **register** gives the startup's SuperLink each hospital's SuperNode
   public key. Any other node is refused, so no stranger receives a model.
3. Everything else starts: the startup's SuperLink and ServerApp; per
   hospital a SuperNode, the startup's ClientApp (in a container that sees
   only the cohort and the final models and reaches only its SuperNode), the
   web app and the endpoint that receives lab orders; per practice its web
   app and a process that fetches lab reports.

`--abort-on-container-failure` stops every party when one fails, so a broken
setup never looks half alive. Ctrl-C stops them all.

Later starts reuse what `prepare` made and are quick.

### 4. Trust the demo's certificate authority, once

The web apps run with Django's production settings, so they speak only HTTPS.
Their certificates come from the demo's own certificate authority in
`demo/browser-ca/`, which is allowed to vouch only for `localhost` and
`127.0.0.1` (an X.509 name constraint that browsers enforce). Trusting it
therefore lends it no power over any real website, even if someone copies its
key. [mkcert](https://github.com/FiloSottile/mkcert) puts it into the system
store, Firefox and Chrome in one step; it is given the certificate but not the
key, so mkcert itself can never issue anything with it.

```shell
brew install mkcert nss                # macOS
sudo pacman -S mkcert nss              # Arch
sudo apt install mkcert libnss3-tools  # Ubuntu
CAROOT=$PWD/demo/browser-ca mkcert -install
```

### 5. Open the parties

| Party | Web app |
|---|---|
| UZ Leuven | https://uz-leuven.localhost |
| Heilig Hart Leuven | https://heilig-hart-leuven.localhost |
| AZ Diest | https://az-diest.localhost |
| Huisartsenpraktijk De Akker → UZ Leuven | https://huisartsenpraktijk-de-akker.localhost |
| Huisartsenpraktijk De Berk → Heilig Hart Leuven | https://huisartsenpraktijk-de-berk.localhost |
| Huisartsenpraktijk De Ceder → AZ Diest | https://huisartsenpraktijk-de-ceder.localhost |

Hospitals have `lab-1` (laboratory staff) and `director-1` (laboratory
director); each practice has one general practitioner, `doctor`; the password is
`demo-pass-2026`. A practice's patients are the same NHANES participants whose
tubes its hospital's analyser stand-in measures.

One proxy on `127.0.0.1:443` routes each name to its party's web app by the
name in the TLS handshake, without decrypting: like the internet between your
browser and six organisations, it sees names, never content. `*.localhost`
always means your own machine (RFC 6761); Chrome, Firefox and Linux with
systemd-resolved find these names by themselves. Safari needs one line per
party in `/etc/hosts`, for example `127.0.0.1 uz-leuven.localhost`. If port
443 is taken, put `DEMO_HTTPS_PORT=8443` in `.env` and add `:8443` to the
addresses.

### 6. Train, deploy, order

```shell
docker compose run --rm train   # in a second terminal
```

This is the startup's data scientist submitting a training run. It runs in a
container inside the startup's network because that is where the data
scientist sits in the report's DFD; the SuperLink's control API is never
published to your machine. Each hospital receives the final model; log in as
`director-1` to compare it on local validation and deploy it. Then order a
CBC as `doctor`, analyse it as `lab-1`, and the lab report with its
screening comes back to the practice.

### Stop, reset, clean up

- Ctrl-C in the first terminal stops every container.
- With the demo stopped, `docker compose run --rm --no-deps prepare python
  tools/demo.py reset --demo-dir /demo` deletes the six databases, so the
  next start seeds them afresh; certificates, cohorts and final models stay.
  Deleting `demo/` starts over completely.
- `CAROOT=$PWD/demo/browser-ca mkcert -uninstall` removes the trust again.

A `demo/` from before the containers keeps its data; its certificates are
reissued for the containers' host names. The migrations were restarted from
one `0001_initial` per app on 2026-11-03: a `demo/` with older databases needs
the reset above once.

### Without Docker

Each party installs only its own apps: a hospital's database has no table
for patients, a practice's none for lab orders, analyser values or final
models. A development checkout (neither `HOSPITAL_DIR` nor `PRACTICE_DIR`)
serves both parties from one database; seed it with
`DJANGO_DEBUG=1 uv run python manage.py seed_hospital` and `seed_practice`.

## Screen new blood counts

Each hospital screens a lab export of new blood counts with its deployed model.
The export is a CSV with `sample_id`, registered `sex`, `age`, and the 13
blood-count variables; other columns are ignored. Only women aged 18–49 are
screened, as the model was trained on them alone:

```shell
python -m iron_deficiency.screening \
  --model ~/.cache/iron-deficiency/hospitals/az-diest/final-models/<run-id>.pt \
  --input demo_data/new_samples.csv \
  --output flags.csv
```

The output holds only each `sample_id` and its result: `flagged`, `not flagged`,
or `not screened`. The flag threshold is the `screening-threshold` run config
value, which the ServerApp sends with the deployed model.

## Evaluate a screening

The screening never sees ferritin. To check a deployed model against the
women's actual ferritin, print its AUROC and the confusion matrix of its flags:

```shell
python scripts/evaluate_screening.py \
  --model ~/.cache/iron-deficiency/hospitals/az-diest/final-models/<run-id>.pt \
  --input demo_data/new_samples.csv
```

Training is seeded with the `model-seed` run config value, so repeated runs give
the same flags. To see how much the results depend on the seed, and how
federated training compares with a centralized baseline, train both once per
seed and evaluate every hospital's deployment:

```shell
python scripts/seed_sweep.py --seeds 10  # writes seed_sweep.csv
```

The centralized baseline (`scripts/train_centralized.py`) trains on the union of
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
