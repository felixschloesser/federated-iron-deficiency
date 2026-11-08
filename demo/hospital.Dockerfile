# The hospital's web app. It contains the hospital's and the shared Django
# apps, plus the training package (PyTorch) it uses to check and run
# screening models. No other party's code
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
# Install dependencies before copying code: editing code then reuses this
# layer. torch is the CPU-only build (pyproject.toml pins PyTorch's CPU index).
RUN --mount=type=cache,target=/tmp/.cache/uv,uid=1000,gid=1000 uv sync --locked --no-dev --group web --no-install-package ray --no-install-project
COPY --chown=app README.md LICENSE manage.py /app/
COPY --chown=app ml/ /app/ml/
COPY --chown=app buf/ /app/buf/
COPY --chown=app web/__init__.py /app/web/
COPY --chown=app web/shared/ /app/web/shared/
COPY --chown=app web/hospital/ /app/web/hospital/
RUN --mount=type=cache,target=/tmp/.cache/uv,uid=1000,gid=1000 uv sync --locked --no-dev --group web --no-install-package ray
# Empty folders for this party's data. compose mounts a new volume on /data,
# and Docker copies these folders into it, owned by app.
RUN mkdir -p /data/cohort /data/screening-models
# demo/party.py runs first: it creates the database and demo accounts from
# the NHANES extract, then runs the server command compose gives it.
COPY --chown=app demo/__init__.py demo/party.py demo/seed.py /app/demo/
COPY --chown=app demo/seeding/__init__.py demo/seeding/accounts.py demo/seeding/parties.py demo/seeding/names.py /app/demo/seeding/
ENTRYPOINT ["python", "-m", "demo.party"]
