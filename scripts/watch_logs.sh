#!/usr/bin/env bash
# Follow a Cloud Run service's logs in a terminal pane.
#
# `gcloud beta logging tail` is the documented way to stream and it produced
# nothing here, so this polls instead. Polling is duller and it works, which
# is the right trade for something that has to run during a take.
#
#   scripts/watch_logs.sh toolsmith-sandbox
#   scripts/watch_logs.sh toolsmith-github
set -uo pipefail

SERVICE="${1:-toolsmith-sandbox}"
PROJECT="${TOOLSMITH_GCP_PROJECT:-toolsmith-505815}"
GCLOUD="${GCLOUD:-$HOME/google-cloud-sdk/bin/gcloud}"

echo "── $SERVICE ─────────────────────────────────────────────"
# Start from now, so the pane opens empty and everything in it belongs to the
# run being filmed rather than to whatever happened earlier today.
SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)

while true; do
  LINES=$($GCLOUD logging read \
    "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE AND timestamp>\"$SINCE\" AND textPayload:*" \
    --project "$PROJECT" --limit 20 --order=asc \
    --format='value(textPayload)' 2>/dev/null | grep -v '^$')

  if [[ -n "$LINES" ]]; then
    echo "$LINES"
    SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  fi
  sleep 3
done
