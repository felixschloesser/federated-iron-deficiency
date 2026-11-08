# A general practitioner's practice's web app. A practice screens nothing:
# only the web dependency group, so no PyTorch, Flower or W&B, and only its own
# Django apps and the shared ones (tests/quality/security/test_running_containers.py).
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/
RUN useradd --create-home app && install -d -o app /app /data /opt/venv
WORKDIR /app
USER app
# HOME: compose runs the image as the demo user (DEMO_USER), who may have no home here.
# Bytecode compiled once here, not by every new container.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH HOME=/tmp \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --chown=app pyproject.toml uv.lock /app/
RUN --mount=type=cache,target=/tmp/.cache/uv,uid=1000,gid=1000 uv sync --locked --only-group web
COPY --chown=app manage.py /app/
COPY --chown=app ml/__init__.py ml/cohort.py /app/ml/
COPY --chown=app buf/ /app/buf/
COPY --chown=app web/__init__.py /app/web/
COPY --chown=app web/shared/ /app/web/shared/
COPY --chown=app web/practice/ /app/web/practice/
# Its start (demo/party.py): it sets itself up from its NHANES extract, then
# starts the servers its command names.
COPY --chown=app demo/__init__.py demo/party.py demo/seed.py /app/demo/
COPY --chown=app demo/seeding/__init__.py demo/seeding/accounts.py demo/seeding/parties.py demo/seeding/names.py /app/demo/seeding/
ENTRYPOINT ["python", "-m", "demo.party"]
