# nhanes-download: the one container that reaches the internet. It writes the
# public NHANES extracts each party seeds from (demo/nhanes.py). Only the
# `nhanes` dependency group and the modules that choose the extracts, so a
# change anywhere else never rebuilds it.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/
RUN useradd --create-home app && install -d -o app /app
WORKDIR /app
USER app
# HOME: compose runs the image as the demo user (DEMO_USER), who may have no home here.
# Bytecode compiled once here, not by every new container.
ENV UV_PROJECT_ENVIRONMENT=/home/app/venv PATH=/home/app/venv/bin:$PATH HOME=/tmp \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --chown=app pyproject.toml uv.lock /app/
RUN --mount=type=cache,target=/tmp/.cache/uv,uid=1000,gid=1000 uv sync --frozen --only-group nhanes
COPY --chown=app ml/__init__.py ml/cohort.py ml/dataset.py /app/ml/
COPY --chown=app demo/__init__.py demo/nhanes.py /app/demo/
COPY --chown=app demo/seeding/__init__.py demo/seeding/participants.py /app/demo/seeding/
