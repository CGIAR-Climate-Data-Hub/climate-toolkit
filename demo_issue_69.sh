#!/usr/bin/env bash
# Demo for issue #69: NEX-GDDP batch "Earth Engine project ID missing".
# Shows the failure (no project id) then a cold-start live fetch (project id set,
# cache refreshed, fresh cache dir => no cached data used).
#
# Usage:
#   ./demo_issue_69.sh <EE_PROJECT_ID>
#   ./demo_issue_69.sh ee-peetmate
#
# Requires: .venv with earthengine-api, and EE auth already done
# (~/.config/earthengine/credentials). If not authed:
#   .venv/bin/python -c "import ee; ee.Authenticate()"

set -u

PROJECT_ID="${1:-}"
PY=".venv/bin/python"
CACHE_DIR="/tmp/nexgddp_coldtest"

CMD_ARGS=(
  -m climate_tookit.fetch_data.nex_gddp_batch
  --variables precipitation,max_temperature,min_temperature
  --from 2050-01-01 --to 2050-01-10
  --lon 36.817 --lat -1.286
  --model GFDL-ESM4 --scenario ssp245
  --stage raw
)

echo "=============================================================="
echo " STEP 1: reproduce the bug — no project id set"
echo "=============================================================="
env -u GCP_PROJECT_ID -u GOOGLE_CLOUD_PROJECT -u EE_PROJECT_ID \
  "$PY" "${CMD_ARGS[@]}"
echo
echo "(expected: 'Error: Earth Engine project ID missing.')"
echo

if [ -z "$PROJECT_ID" ]; then
  echo "No EE project id passed. Re-run with:  ./demo_issue_69.sh <EE_PROJECT_ID>"
  exit 1
fi

echo "=============================================================="
echo " STEP 2: cold-start live fetch — project id set, cache wiped"
echo "=============================================================="
rm -rf "$CACHE_DIR"   # cold start: no cached data
GCP_PROJECT_ID="$PROJECT_ID" \
  "$PY" "${CMD_ARGS[@]}" --refresh-cache --cache-dir "$CACHE_DIR"
echo
echo "(expected: 'fetched' (not 'cache hit') + 10 rows of data)"
