# nhanes-download: the one container that reaches the internet. It writes the
# public NHANES extracts each party seeds from (demo/nhanes.py). Only the
# `nhanes` dependency group and the modules that choose the extracts, so a
# change anywhere else never rebuilds it.
FROM python:3.13-slim
RUN pip install --no-cache-dir uv \
    && useradd --create-home app
WORKDIR /app
RUN chown app /app
USER app
ENV UV_PROJECT_ENVIRONMENT=/home/app/venv PATH=/home/app/venv/bin:$PATH
# compose runs the image as the demo user (DEMO_USER), who may have no home here.
ENV HOME=/tmp
COPY --chown=app pyproject.toml uv.lock /app/
RUN uv sync --frozen --only-group nhanes
COPY --chown=app ml/__init__.py ml/cohort.py ml/dataset.py /app/ml/
COPY --chown=app demo/__init__.py demo/nhanes.py /app/demo/
COPY --chown=app demo/seeding/__init__.py demo/seeding/participants.py /app/demo/seeding/
