# The startup's web app. It contains the startup's and the shared Django
# apps, plus the training package (PyTorch) whose final models it keeps.
# No other party's code
# (tests/quality/security/test_running_containers.py checks this).
FROM python:3.13.18-slim
# Empty folders for this party's data. compose mounts a new volume on /data,
# and Docker copies these folders into it, owned by app.
RUN useradd --uid 1000 --create-home app \
    && install -d -o app /app /data /data/final-models /data/superlink /data/flwr-home
WORKDIR /app
USER app
# UV_COMPILE_BYTECODE: compile .pyc files now, so containers start faster.
ENV PATH=/app/.venv/bin:$PATH UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --chown=app pyproject.toml uv.lock /app/
# Install dependencies before copying code: editing code then reuses this
# layer. torch is the CPU-only build (pyproject.toml pins PyTorch's CPU index).
# uv is mounted for this one step, so it stays out of the image.
RUN --mount=from=ghcr.io/astral-sh/uv:0.13.6,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/home/app/.cache/uv,uid=1000,gid=1000 \
    uv sync --locked --no-dev --group web --no-install-package ray --no-install-project
# The FAB the data scientist's flwr builds from /app includes these two
# (pyproject.toml's fab-include).
COPY --chown=app README.md LICENSE manage.py /app/
COPY --chown=app ml/ /app/ml/
COPY --chown=app web/__init__.py /app/web/
COPY --chown=app web/shared/ /app/web/shared/
COPY --chown=app web/startup/ /app/web/startup/
# The setup job's seeding (compose.yaml): the demo accounts and NHANES records.
COPY --chown=app demo/__init__.py demo/seed.py /app/demo/
COPY --chown=app demo/seeding/__init__.py demo/seeding/accounts.py demo/seeding/parties.py demo/seeding/names.py /app/demo/seeding/
# The data scientist's flwr reaches the SuperLink with this (demo/flwr-home/).
COPY --chown=app demo/flwr-home/config.toml /data/flwr-home/config.toml
