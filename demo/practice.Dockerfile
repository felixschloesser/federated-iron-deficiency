# The web app of a general practitioner's practice. A practice runs no
# screening model, so it gets only the `web` dependency group (no PyTorch,
# Flower or W&B) and only the practice's and the shared Django apps
# (tests/quality/security/test_running_containers.py checks this).
FROM python:3.13.18-slim
RUN useradd --uid 1000 --create-home app && install -d -o app /app /data
WORKDIR /app
USER app
# UV_COMPILE_BYTECODE: compile .pyc files now, so containers start faster.
ENV PATH=/app/.venv/bin:$PATH UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --chown=app pyproject.toml uv.lock /app/
# uv is mounted for this one step, so it stays out of the image.
RUN --mount=from=ghcr.io/astral-sh/uv:0.13.6,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/home/app/.cache/uv,uid=1000,gid=1000 \
    uv sync --locked --only-group web
COPY --chown=app manage.py /app/
COPY --chown=app ml/__init__.py ml/cohort.py /app/ml/
COPY --chown=app web/__init__.py /app/web/
COPY --chown=app web/shared/ /app/web/shared/
COPY --chown=app web/practice/ /app/web/practice/
# The setup job's seeding (compose.yaml): the demo accounts and NHANES records.
COPY --chown=app demo/__init__.py demo/seed.py /app/demo/
COPY --chown=app demo/seeding/__init__.py demo/seeding/accounts.py demo/seeding/parties.py demo/seeding/names.py /app/demo/seeding/
