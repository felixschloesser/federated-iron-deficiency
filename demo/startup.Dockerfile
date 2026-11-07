# The startup's web app: its own Django apps and the shared ones, and the
# training package whose final models it keeps. No other party's apps
# (tests/quality/security/test_running_containers.py).
FROM python:3.13-slim
RUN pip install --no-cache-dir uv \
    && useradd --create-home app
WORKDIR /app
RUN chown app /app
# The party's folder and its layout: Docker copies them, owned by app, into a
# fresh volume mounted here, before any of its subfolders is mounted.
RUN mkdir -p /data/final-models /data/superlink /data/flwr-home && chown -R app /data
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
COPY --chown=app web/startup/ /app/web/startup/
RUN uv sync --frozen --no-dev --group web --no-install-package ray
# Its start (demo/party.py): it sets itself up from its NHANES extract, then
# starts the servers its command names.
COPY --chown=app demo/__init__.py demo/party.py demo/seed.py /app/demo/
COPY --chown=app demo/seeding/__init__.py demo/seeding/accounts.py demo/seeding/parties.py demo/seeding/names.py /app/demo/seeding/
ENTRYPOINT ["python", "-m", "demo.party"]
