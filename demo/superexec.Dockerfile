# Runs the startup's training code: the ServerApp at the startup and the
# ClientApp at each hospital (TB4). This is Flower's own SuperExec image plus
# our locked dependencies: Flower installs nothing at run time, and the code
# itself arrives with each run (the FAB).
FROM flwr/superexec:1.40.0
USER root
# uv and the lock are mounted for this one step, so neither stays in the
# image; --no-cache-dir keeps pip's cache out too. torch is the CPU-only build.
RUN --mount=from=ghcr.io/astral-sh/uv:0.13.6,source=/uv,target=/usr/local/bin/uv \
    --mount=type=bind,source=pyproject.toml,target=/tmp/lock/pyproject.toml \
    --mount=type=bind,source=uv.lock,target=/tmp/lock/uv.lock \
    uv export --project /tmp/lock --locked --no-dev --no-default-groups \
       --no-emit-project --no-hashes --no-emit-package ray --no-emit-package flwr \
       -o /tmp/requirements.txt \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt \
       --extra-index-url https://download.pytorch.org/whl/cpu \
    && rm /tmp/requirements.txt
USER app
# Each run's FAB is unpacked here, because /app is not writable.
ENV FLWR_HOME=/tmp/flwr MPLCONFIGDIR=/tmp/matplotlib
