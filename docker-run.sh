#!/usr/bin/env bash
#
# Recommended way to run climate-toolkit in Docker.
#
# Every invocation first deletes stale containers left by previous runs
# (exited / created / dead), then starts a fresh container with --rm so it
# cleans up after itself on exit too. Running containers are never touched, so
# concurrent runs are safe.
#
# Usage:
#   ./docker-run.sh --help
#   GCP_PROJECT_ID=your-project ./docker-run.sh fetch --source nasa_power \
#       --lat -1.286 --lon 36.817 --from 2020-01-01 --to 2020-12-31
#
# Override the image name with CLIMATE_TOOLKIT_IMAGE if you tagged it yourself.

set -euo pipefail

IMAGE="${CLIMATE_TOOLKIT_IMAGE:-climate-toolkit}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Build on first use if the image is missing.
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Image '$IMAGE' not found; building..." >&2
  docker build -t "$IMAGE" "$SCRIPT_DIR"
fi

# Delete stale containers from previous runs before starting. Different filter
# keys are ANDed (this image) while repeated status filters are ORed, so this
# matches only non-running containers built from this image.
stale="$(docker ps -aq \
  --filter "ancestor=$IMAGE" \
  --filter "status=exited" \
  --filter "status=created" \
  --filter "status=dead")"
if [ -n "$stale" ]; then
  echo "Removing stale climate-toolkit containers..." >&2
  # shellcheck disable=SC2086
  docker rm -f $stale >/dev/null
fi

# Create the outputs dir up front so it is owned by the current user. Docker
# would otherwise create a missing bind-mount source as root, and the non-root
# container (uid 1000) could not then write cache into it on Linux.
mkdir -p "$PWD/outputs"

run_args=(--rm -e GCP_PROJECT_ID="${GCP_PROJECT_ID:-}" -v "$PWD/outputs:/app/outputs")

# Mount Earth Engine credentials read-only only if they exist — otherwise Docker
# would create an empty root-owned ~/.config/earthengine on the host. Not needed
# for NASA POWER or the offline surface.
if [ -d "$HOME/.config/earthengine" ]; then
  run_args+=(-v "$HOME/.config/earthengine:/home/app/.config/earthengine:ro")
fi

exec docker run "${run_args[@]}" "$IMAGE" "$@"
