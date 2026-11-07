# A hospital's or the startup's web app (PARTY=hospital or startup): its own
# Django apps and the shared ones, and the training package it reads or screens
# with. No other party's apps (tests/quality/security/test_running_containers.py).
FROM python:3.13-slim
ARG PARTY
RUN pip install --no-cache-dir uv \
    && useradd --create-home app
WORKDIR /app
RUN chown app /app
USER app
ENV UV_PROJECT_ENVIRONMENT=/home/app/venv PATH=/home/app/venv/bin:$PATH
# compose runs the image as the demo user (DEMO_USER), who may have no home here.
ENV HOME=/tmp
# Dependencies first, so a code change rebuilds only the last layers.
# The lock takes torch on Linux from PyTorch's CPU index (pyproject.toml).
COPY --chown=app pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --group web --no-install-package ray --no-install-project
COPY --chown=app README.md LICENSE manage.py /app/
COPY --chown=app ml/ /app/ml/
COPY --chown=app web/__init__.py /app/web/
COPY --chown=app web/shared/ /app/web/shared/
COPY --chown=app web/${PARTY}/ /app/web/${PARTY}/
RUN uv sync --frozen --no-dev --group web --no-install-package ray
