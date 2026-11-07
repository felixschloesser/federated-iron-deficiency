# The demo

Run every command here from the repository root. The demo runs the whole scenario on your machine: the startup, three
hospitals and each hospital's general practitioner's practice. Each party
runs in its own containers, which see only that party's folder under `.demo/`
(gitignored), on Docker networks that follow the report's trust boundaries.
So "UZ Leuven's data never reaches the startup" holds because no network or
mount connects them, not merely because the code is careful. Who the parties
are, and each one's colour and number of seeded patients, is declared in
`demo/demo.toml`. `demo/compose.yaml` and `demo/proxy.conf` are generated from it:
after editing it, run `uv run python -m demo.topology`.

## 1. Install Docker

On a Mac, [OrbStack](https://orbstack.dev) or Docker Desktop; on Linux,
Docker Engine with the compose plugin (`docker compose version` should
answer). Docker is what keeps the parties apart: every trust boundary gets its
own network, and each party runs in containers of its own. Each container is
one compose *service*: one long-running command, such as gunicorn serving a
hospital's web app, which may start child processes of its own. A service is
not a process of the report's DFDs:

| DFD element | Where it runs |
|---|---|
| DS1 Lab records | each hospital's NHANES cycle, which `prepare` seeds into its database |
| P1 Extract training cohort | *Provide the training cohort* on `<hospital>-web`, by its laboratory director; *Withdraw* takes it back |
| P2 Train locally | two containers: `<hospital>-flower-supernode`, and `<hospital>-flower-client-app` for the startup's code (TB4) |
| P3 Relay messages | `flower-superlink` |
| P4 Average weights (FedAvg) | `flower-server-app` |
| P5 Release final models | `startup-web`: its pages, where the data scientist releases, and a second server beside them, on the `final-models` network only the hospitals' web apps join |
| P6 Validate and deploy model, P8 Receive lab orders, P9 Analyse samples, P10 Screen CBC, P12 Send lab reports | one container, `<hospital>-web`: one Django app, which screens a CBC as it records the analysis, and its messaging endpoint, each server on its own network |
| P7 Order tests, P11 Show lab reports | one container, `<practice>-web`; it fetches lab reports on *Check for reports* |
| E1 Data scientist | `startup-web`, the startup's web app, where the data scientist sees the final models (DS4) and submits a training run; or `train`, run by hand |

One container has no DFD element: `proxy`, which stands for the network
between your browser and the parties.

## 2. On Linux: tell compose who you are

```shell
id -u   # if this prints 1000, skip this step
echo "DEMO_USER=$(id -u):$(id -g)" > .env
```

Every container writes `.demo/` as one user, by default `1000:1000`, the first
account on most Linux machines. On Linux a mounted folder keeps numeric user
IDs, so without this your own account could not edit or delete `.demo/`. On a
Mac, Docker maps IDs for you.

## 3. Start everything

```shell
docker compose up --build --abort-on-container-failure
```

The first start takes a while. It builds three images (the hospitals'
web apps, the practices' leaner ones without PyTorch or Flower, and the
startup's Flower app with PyTorch, CPU only), then runs these steps in order:

1. **prepare** creates what each party needs and the DFDs do not draw:
   each hospital's lab records (its NHANES cycle) and the 2021–2023
   blood counts (downloaded from Hugging Face; set `HF_TOKEN` in `.env` if
   it refuses), and each party's database with its demo accounts. It is the
   only container that sees every party's folder: setup done once, out of
   band.
2. Everything else starts: the startup's SuperLink and ServerApp; per
   hospital a SuperNode, the startup's ClientApp (in a container that sees
   only the cohort and the final models and reaches only its SuperNode), the
   web app and the endpoint that receives lab orders; per practice its web
   app and a process that fetches lab reports.

`--abort-on-container-failure` stops every party when one fails, so a broken
setup never looks half alive. Ctrl-C stops them all.

Later starts reuse what `prepare` made and are quick.

The demo has no TLS, SuperNode authentication or mutual TLS: every connection
is plaintext and the SuperLink admits any node. The report describes these
security controls; the demo leaves them out for simplicity.

## 4. Open the parties

| Party | Web app |
|---|---|
| The startup | http://startup.localhost |
| UZ Leuven | http://uz-leuven.localhost |
| Heilig Hart Leuven | http://heilig-hart-leuven.localhost |
| AZ Diest | http://az-diest.localhost |
| Huisartsenpraktijk De Akker → UZ Leuven | http://huisartsenpraktijk-de-akker.localhost |
| Huisartsenpraktijk De Berk → Heilig Hart Leuven | http://huisartsenpraktijk-de-berk.localhost |
| Huisartsenpraktijk De Ceder → AZ Diest | http://huisartsenpraktijk-de-ceder.localhost |

The startup has `data-scientist`; hospitals have `staff` (laboratory staff) and `director` (their one laboratory
director); each practice has one general practitioner, `doctor`; the password is
`demo-pass-2026`. A practice's patients are NHANES participants whose tubes
every hospital's analyser stand-in measures, as any hospital may receive their
samples.

One proxy on `127.0.0.1:80` routes each name to its party's web app by its
Host header, like the internet between your browser and seven organisations. `*.localhost`
always means your own machine (RFC 6761); Chrome, Firefox and Linux with
systemd-resolved find these names by themselves. Safari needs one line per
party in `/etc/hosts`, for example `127.0.0.1 uz-leuven.localhost`. If port
80 is taken, put `DEMO_HTTP_PORT=8080` in `.env` and add `:8080` to the
addresses.

## 5. Train, deploy, order

UZ Leuven's and Heilig Hart Leuven's laboratory directors have provided
their training cohorts; AZ Diest's has not, so it takes no part in a
training run (its SuperNode answers each round with an error, which FedAvg
leaves out) until you log in there as `director` and provide it on the
*Training cohort* page. Until then, transmitting a final model fails at AZ
Diest, as its ClientApp has no cohort to validate the model on.

Log in to http://startup.localhost as `data-scientist` and submit a training
run, or from a second terminal:

```shell
docker compose run --rm train
```

This is the startup's data scientist submitting a training run. Both run in a
container inside the startup's network because that is where the data
scientist sits in the report's DFD; the SuperLink's control API is never
published to your machine, and the proxy reaches the startup's web app on a
network of its own, `startup-web`, never the SuperLink. When the run
finishes, its final model appears on the startup's Final models page; release
it there. Then log in to a hospital as `director`, fetch new final models, compare
its local validation at each threshold and deploy it at one. Then order a
CBC as `doctor`, analyse it as `staff`, and the lab report with its
screening comes back to the practice.

## Stop, reset, clean up

- Ctrl-C in the first terminal stops every container; `up` again carries on
  where it stopped.
- Each party's data is a Docker volume of its own:
  training cohorts, final models, the SuperLink's state and the databases.
  `docker compose down -v` deletes them all, so the next `up` starts over;
  `.demo/` on your machine keeps only what that must not cost you: the
  Hugging Face downloads (`.demo/huggingface/`), with the NHANES 2021–2023
  cycle the seeded patients come from; no party's folder holds that cycle.
  `prepare` still asks Hugging Face, but downloads nothing twice.
- When a change to `demo.toml` or the topology renames or drops a network,
  `docker compose down --remove-orphans` leaves the old one behind, and Docker
  has room for only about 30 networks. With the demo stopped,
  `docker network prune --filter label=com.docker.compose.project=iron-deficiency`
  removes this demo's networks that no container uses; the next `up` creates
  the ones it needs again.
- To look into a party's database while the demo runs:
  `docker compose exec uz-leuven-web python -m sqlite3 /demo/hospitals/uz-leuven/web.sqlite3`.

The demo's output folder was `demo/` until 2026-11-05; `demo/` now holds the
demo's source. Move what you have once:

```shell
mkdir -p .demo && mv demo/browser-ca demo/huggingface .demo/
```

A `demo/` from before the volumes (2026-11-03) also still holds `startup/`,
`hospitals/` and `practices/`; nothing reads them any more, so delete those
three once. The first `up` downloads the NHANES data again.
A demo from before 2026-11-05 left a browser CA in `demo/browser-ca/`; if
you trusted it, run `CAROOT=$PWD/.demo/browser-ca mkcert -uninstall` after the
move, then delete the folder. Your browser may also remember HSTS for the `*.localhost`
names and insist on HTTPS: clear it for those sites.

## Without Docker

Each party installs only its own apps: a hospital's database has no table
for patients, a practice's none for test requests, analyser values or final
models. Without Docker, run each party as its own web app, each on a port of its
own; its data goes to `.data/<party>/` in the checkout:

    export DJANGO_DEBUG=1
    DJANGO_SETTINGS_MODULE=hospital.settings uv run python manage.py migrate
    DJANGO_SETTINGS_MODULE=hospital.settings uv run python -m demo.seed hospital
    DJANGO_SETTINGS_MODULE=hospital.settings uv run python manage.py runserver 8001
    DJANGO_SETTINGS_MODULE=practice.settings uv run python manage.py migrate
    DJANGO_SETTINGS_MODULE=practice.settings uv run python -m demo.seed practice
    DJANGO_SETTINGS_MODULE=practice.settings uv run python manage.py runserver 8002
