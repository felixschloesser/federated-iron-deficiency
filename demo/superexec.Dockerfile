# The startup's apps at run time: the ServerApp at the startup and each
# hospital's ClientApp (TB4). Flower's SuperExec, plus the app's dependencies,
# since runtime dependency installation stays off; the FAB brings the code.
FROM flwr/superexec:1.40.0
USER root
# uv and the lock are mounted for this step only: neither stays in the image.
# torch==…+cpu, as locked for Linux, lives on PyTorch's CPU index.
RUN --mount=from=ghcr.io/astral-sh/uv:0.13.6,source=/uv,target=/usr/local/bin/uv \
    --mount=type=bind,source=pyproject.toml,target=/tmp/lock/pyproject.toml \
    --mount=type=bind,source=uv.lock,target=/tmp/lock/uv.lock \
    --mount=type=cache,target=/root/.cache/pip \
    uv export --project /tmp/lock --frozen --no-dev --no-default-groups \
       --no-emit-project --no-hashes --no-emit-package ray --no-emit-package flwr \
       -o /tmp/requirements.txt \
    && python -m pip install -r /tmp/requirements.txt \
       --extra-index-url https://download.pytorch.org/whl/cpu \
    && rm /tmp/requirements.txt
USER app
# The ClientApp installs each run's FAB here; the image's /app is not writable.
ENV FLWR_HOME=/tmp/flwr MPLCONFIGDIR=/tmp/matplotlib
