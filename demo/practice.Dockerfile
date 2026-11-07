# The web app of a general practitioner's practice. A practice runs no
# screening model, so it gets only the `web` dependency group (no PyTorch,
# Flower or W&B) and only the practice's and the shared Django apps
# (tests/quality/security/test_running_containers.py checks this).
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/
RUN useradd --create-home app && install -d -o app /app /data /opt/venv
WORKDIR /app
USER app
# HOME=/tmp: a home folder any user can write to.
# UV_COMPILE_BYTECODE: compile .pyc files now, so containers start faster.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH HOME=/tmp \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --chown=app pyproject.toml uv.lock /app/
RUN --mount=type=cache,target=/tmp/.cache/uv,uid=1000,gid=1000 uv sync --locked --only-group web
COPY --chown=app manage.py /app/
COPY --chown=app ml/__init__.py ml/cohort.py /app/ml/
COPY --chown=app web/__init__.py /app/web/
COPY --chown=app web/shared/ /app/web/shared/
COPY --chown=app web/practice/ /app/web/practice/
# demo/party.py runs first: it creates the database and demo accounts from
# the NHANES extract, then runs the server command compose gives it.
COPY --chown=app demo/__init__.py demo/party.py demo/seed.py /app/demo/
COPY --chown=app demo/seeding/__init__.py demo/seeding/accounts.py demo/seeding/parties.py demo/seeding/names.py /app/demo/seeding/
ENTRYPOINT ["python", "-m", "demo.party"]
