# A general practitioner's practice's web app and its report checker. A
# practice screens nothing: only the web dependency group, so no PyTorch,
# Flower or W&B, and not the training package's dependencies.
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
RUN uv sync --frozen --only-group web
COPY --chown=app . /app
