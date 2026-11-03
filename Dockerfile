# Reproducible runtime image for climate-toolkit.
#
# Reproducibility comes from three pins:
#   1. the base image, pinned by digest (OS + CPython 3.10, matching CI);
#   2. uv, pinned to an exact release;
#   3. uv.lock, which fixes every Python dependency to an exact version + hash.
#
# Earth Engine credentials are NOT baked in (they are per-user OAuth). Mount
# them read-only at runtime and pass GCP_PROJECT_ID as an environment variable
# -- see README "Reproducible environment with Docker".

FROM python:3.10-slim@sha256:e5300dc020a26a34a19337a57602955a2510e22abeb176edd6de6cd2cc927dd4 AS runtime

# Pinned uv release: deterministic, lockfile-based installs.
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    MPLBACKEND=Agg \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 1) Dependency layer -- cached until pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project --no-dev

# 2) Project layer -- source changes do not invalidate the dependency layer.
COPY climate_toolkit ./climate_toolkit
RUN uv sync --locked --no-dev

# Run as non-root. Earth Engine credentials mount at
# /home/app/.config/earthengine; outputs/cache persist via /app/outputs.
RUN useradd --create-home app \
    && mkdir -p /app/outputs \
    && chown -R app:app /app
USER app

ENTRYPOINT ["climate-toolkit"]
CMD ["--help"]
