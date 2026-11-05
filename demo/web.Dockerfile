# Every hospital's web app and lab-order endpoint, and the one-shot prepare
# and train steps: the project with its training dependencies, and the web group.
FROM python:3.13-slim
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
COPY --chown=app . /app
RUN uv sync --frozen --no-dev --group web --no-install-package ray
