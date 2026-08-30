#!/usr/bin/env bash
# Pin the Cloud Run services warm, or let them scale to zero.
#
#   scripts/cloud.sh warm    before recording -- no cold starts, costs per idle hour
#   scripts/cloud.sh idle    afterwards -- free when unused, first call is slow
#
# Cold starts are why this matters: a scaled-to-zero instance takes longer to
# wake than the MCP session was willing to wait, which is a failure that only
# appears on the take.
set -uo pipefail

MODE="${1:-status}"
GCLOUD="${GCLOUD:-$HOME/google-cloud-sdk/bin/gcloud}"
PROJECT="${TOOLSMITH_GCP_PROJECT:-toolsmith-505815}"
REGION="${TOOLSMITH_SANDBOX_REGION:-us-central1}"
SERVICES=(toolsmith-sandbox toolsmith-github toolsmith-injected)

case "$MODE" in
  warm) MIN=1 ;;
  idle) MIN=0 ;;
  status)
    for s in "${SERVICES[@]}"; do
      min=$($GCLOUD run services describe "$s" --region "$REGION" --project "$PROJECT" \
            --format='value(spec.template.metadata.annotations."autoscaling.knative.dev/minScale")' 2>/dev/null)
      printf "  %-20s min-instances=%s\n" "$s" "${min:-0}"
    done
    exit 0 ;;
  *) echo "usage: $0 [warm|idle|status]" >&2; exit 1 ;;
esac

for s in "${SERVICES[@]}"; do
  $GCLOUD run services update "$s" --region "$REGION" --project "$PROJECT" \
    --min-instances=$MIN --quiet >/dev/null 2>&1 \
    && echo "  $s -> min-instances=$MIN" \
    || echo "  $s -> FAILED"
done

if [[ "$MODE" == "idle" ]]; then
  echo
  echo "  Services stay deployed and reachable; the first call after an idle"
  echo "  period just takes longer. Run 'scripts/cloud.sh warm' before filming."
fi
