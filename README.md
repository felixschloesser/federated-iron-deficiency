# Federated Iron-Deficiency Classification

This [Flower](https://flower.ai/) app trains a
[PyTorch](https://pytorch.org/) binary classifier to identify iron deficiency
from routine complete blood count measurements and age. Iron deficiency is
defined as ferritin below 15 ng/mL.

The federation has four clients, each representing a different
[NHANES](https://www.cdc.gov/nchs/nhanes/) survey cycle: 2005–2006, 2015–2016,
2017–2018, and 2021–2023. Each client trains on its own locally standardized
data.

## Run on SuperGrid

The app is designed for a SuperGrid deployment federation with four SuperNodes.
Before connecting a SuperNode, first register its public key with SuperGrid and
then add the registered SuperNode to the deployment federation of interest. See
[Create and Manage Federations on SuperGrid](https://flower.ai/docs/framework/how-to-create-and-manage-federations.html)
and
[Connect SuperNodes to SuperGrid](https://flower.ai/docs/framework/how-to-connect-supernodes-to-supergrid.html).

Each SuperNode loads one survey cycle from its own disk. To generate demo
partitions, download the cohorts and save one partition per cycle
(`demo_data/2005-2006`, `demo_data/2015-2016`, ...):

```shell
python -m iron_deficiency.dataset --out-dir demo_data
```

Then pass each SuperNode the path to its partition through its node
configuration. For example:

```shell
flower-supernode \
  --superlink fleet-supergrid.flower.ai:443 \
  --auth-supernode-private-key ~/path/to/supernode/private/key \
  --node-config "data-path='/path/to/demo_data/2005-2006'" \
  --allow-runtime-dependency-installation # optional
```

Launch the other three SuperNodes in the same way, pointing `data-path` to the
`2015-2016`, `2017-2018`, and `2021-2023` partitions, respectively.

Once the four SuperNodes are online and part of the federation, follow
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
280 MB; set `HF_TOKEN` for faster downloads. Use four virtual SuperNodes, one
per cycle, and submit the app to the simulation federation:

```shell
flwr federation simulation-config @<username>/<federation-name> supergrid --num-supernodes 4
flwr run . supergrid --federation @<username>/<federation-name>
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
  four NHANES cohorts.

After making your changes, submit the app to your SuperGrid federation:

```shell
cd iron-deficiency
flwr run . --federation @<username>/<federation-name> supergrid
```
