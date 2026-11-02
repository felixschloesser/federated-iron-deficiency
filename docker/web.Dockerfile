# Every party's web app, the hospitals' lab-order endpoints, the practices'
# report checkers, and the one-shot prepare, register and train steps.
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssl openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv \
    && useradd --create-home app
WORKDIR /app
RUN chown app /app
USER app
ENV UV_PROJECT_ENVIRONMENT=/home/app/venv PATH=/home/app/venv/bin:$PATH
# Dependencies first, so a code change rebuilds only the last layers.
# shortcut: CPU torch from PyTorch's index; screening needs no GPU.
COPY --chown=app pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --group web --no-install-package ray --no-install-project \
    --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
COPY --chown=app . /app
RUN uv sync --frozen --no-dev --group web --no-install-package ray \
    --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
