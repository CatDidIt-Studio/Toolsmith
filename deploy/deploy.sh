#!/usr/bin/env bash
# Deploy the sandbox worker to Cloud Run.
#
# The sandbox is the only component that must run somewhere disposable, so it
# is the one that has to be deployed for the architecture to be real rather
# than described. Everything else could run anywhere; this cannot run in the
# agent's process without giving up the property it exists to provide.
set -euo pipefail

GCLOUD="${GCLOUD:-$HOME/google-cloud-sdk/bin/gcloud}"
REGION="${TOOLSMITH_SANDBOX_REGION:-us-central1}"
SERVICE="${TOOLSMITH_SANDBOX_SERVICE:-toolsmith-sandbox}"
REPO="${TOOLSMITH_AR_REPO:-toolsmith}"
PROJECT="$($GCLOUD config get-value project 2>/dev/null)"

if [[ -z "$PROJECT" || "$PROJECT" == "(unset)" ]]; then
  echo "No project set. Run: $GCLOUD config set project <PROJECT_ID>" >&2
  exit 1
fi

IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/sandbox:latest"

echo "project : $PROJECT"
echo "region  : $REGION"
echo "image   : $IMAGE"

$GCLOUD services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com --project "$PROJECT" --quiet

$GCLOUD artifacts repositories describe "$REPO" --location "$REGION" \
  --project "$PROJECT" >/dev/null 2>&1 || \
  $GCLOUD artifacts repositories create "$REPO" --repository-format=docker \
    --location "$REGION" --project "$PROJECT" --quiet

# Built from the repo root so the worker can import the probe module, but with
# a Dockerfile that copies only the probe path in.
$GCLOUD builds submit --config cloudbuild.yaml \
  --substitutions "_IMAGE=${IMAGE}" --project "$PROJECT" --quiet

$GCLOUD run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --project "$PROJECT" \
  --allow-unauthenticated \
  --memory 512Mi --cpu 1 --timeout 60 --max-instances 10 --port 8080 \
  --quiet

URL="$($GCLOUD run services describe "$SERVICE" --region "$REGION" \
       --project "$PROJECT" --format='value(status.url)')"

echo
echo "deployed: $URL"
echo "export TOOLSMITH_SANDBOX_URL=$URL"
