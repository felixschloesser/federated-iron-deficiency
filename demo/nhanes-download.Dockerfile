# Downloads the public NHANES data and writes one extract per party, which
# each party's web app then loads (demo/nhanes.py). The only container with
# internet access. It holds just the `nhanes` dependency group and the few
# modules it needs, so changes elsewhere never rebuild it.
FROM python:3.13.18-slim
RUN useradd --uid 1000 --create-home app && install -d -o app /app
WORKDIR /app
USER app
# HOME=/tmp: compose runs this image as DEMO_USER, who has no home folder here.
# UV_COMPILE_BYTECODE: compile .pyc files now, so containers start faster.
ENV PATH=/app/.venv/bin:$PATH HOME=/tmp \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --chown=app pyproject.toml uv.lock /app/
# uv is mounted for this one step, so it stays out of the image.
RUN --mount=from=ghcr.io/astral-sh/uv:0.13.6,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/tmp/.cache/uv,uid=1000,gid=1000 \
    uv sync --locked --only-group nhanes
COPY --chown=app ml/__init__.py ml/cohort.py ml/dataset.py /app/ml/
COPY --chown=app demo/__init__.py demo/nhanes.py /app/demo/
COPY --chown=app demo/seeding/__init__.py demo/seeding/participants.py /app/demo/seeding/
