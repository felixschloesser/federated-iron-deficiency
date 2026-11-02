# The startup's apps at run time: the ServerApp at the startup and each
# hospital's ClientApp (TB4). Flower's SuperExec, plus the app's dependencies,
# since runtime dependency installation stays off; the FAB brings the code.
FROM flwr/superexec:1.40.0
COPY --chown=app pyproject.toml uv.lock /tmp/lock/
USER root
RUN python -m pip install --no-cache-dir uv \
    && uv export --project /tmp/lock --frozen --no-dev --no-default-groups \
       --no-emit-project --no-hashes --no-emit-package ray --no-emit-package flwr \
       -o /tmp/lock/requirements.txt \
    # torch==…+cpu, as locked for Linux, lives on PyTorch's CPU index.
    && python -m pip install --no-cache-dir -r /tmp/lock/requirements.txt \
       --extra-index-url https://download.pytorch.org/whl/cpu \
    && python -m pip uninstall -y uv && rm -rf /tmp/lock
USER app
# The ClientApp installs each run's FAB here; the image's /app is not writable.
ENV FLWR_HOME=/tmp/flwr MPLCONFIGDIR=/tmp/matplotlib
