#!/usr/bin/env bash
# Run from any directory: bash server/scripts/deploy_cloudrun.sh https://YOUR-APP.vercel.app
set -euo pipefail

PROJECT="${PROJECT:-forgehackathon}"
REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-adhikaar-api}"
CLIENT_ORIGIN="${1:-${CLIENT_ORIGIN:-}}"
DATABASE_SECRET="${DATABASE_SECRET:-adhikaar-database-url}"
SARVAM_SECRET="${SARVAM_SECRET:-adhikaar-sarvam-api-key}"
PROFILE_SECRET_NAME="${PROFILE_SECRET_NAME:-adhikaar-profile-secret}"
GCLOUD="${GCLOUD:-gcloud}"

# Codex/PowerShell may have started before the Google SDK was added to PATH.
if ! command -v "$GCLOUD" >/dev/null 2>&1 && [[ -n "${LOCALAPPDATA:-}" ]]; then
    sdk="$(cygpath -u "$LOCALAPPDATA")/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"
    if [[ -f "$sdk" ]]; then GCLOUD="$sdk"; fi
fi
if ! command -v "$GCLOUD" >/dev/null 2>&1; then
    echo "gcloud not found; set GCLOUD to its executable path." >&2
    exit 1
fi
if [[ -z "$CLIENT_ORIGIN" ]]; then
    echo "Usage: bash $0 https://YOUR-APP.vercel.app (comma-separated exact origins allowed)" >&2
    exit 1
fi
IFS=',' read -r -a origins <<< "$CLIENT_ORIGIN"
for origin in "${origins[@]}"; do
    if [[ ! "$origin" =~ ^https?://[[:alnum:].-]+(:[0-9]+)?$ ]]; then
        echo "Use exact HTTP(S) origins without paths, spaces, or trailing slashes." >&2
        exit 1
    fi
done
server_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

"$GCLOUD" services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com secretmanager.googleapis.com \
    aiplatform.googleapis.com iam.googleapis.com --project="$PROJECT" --quiet

if [[ -z "${SERVICE_ACCOUNT:-}" ]]; then
    SERVICE_ACCOUNT="$("$GCLOUD" iam service-accounts list --project="$PROJECT" \
        --filter='displayName=ForgeHackathon-backend' --format='value(email)' | tr -d '\r')"
fi
if [[ -z "$SERVICE_ACCOUNT" || "$SERVICE_ACCOUNT" == *$'\n'* ]]; then
    echo "Expected one existing ForgeHackathon-backend service account; set SERVICE_ACCOUNT to its email." >&2
    exit 1
fi
for role in roles/aiplatform.user roles/secretmanager.secretAccessor; do
    "$GCLOUD" projects add-iam-policy-binding "$PROJECT" \
        --member="serviceAccount:$SERVICE_ACCOUNT" --role="$role" --condition=None --quiet \
        --format='value(version)' >/dev/null
done

# Check metadata only. Secret values never enter shell arguments, logs, or source.
for secret in "$DATABASE_SECRET" "$SARVAM_SECRET" "$PROFILE_SECRET_NAME"; do
    state="$("$GCLOUD" secrets versions describe latest --secret="$secret" \
        --project="$PROJECT" --format='value(state)' | tr -d '\r')"
    if [[ "$state" != ENABLED ]]; then
        echo "Secret $secret needs an enabled version. Create it in Secret Manager first." >&2
        exit 1
    fi
done

# A YAML file also preserves comma-separated origins through Windows gcloud.cmd.
env_file="$(mktemp)"
trap 'rm -f -- "$env_file"' EXIT
cat > "$env_file" <<EOF
GEMINI_BACKEND: vertex
GCP_PROJECT: "$PROJECT"
GCP_LOCATION: global
GEMINI_RPM: "60"
AGENT_HEADLESS: "true"
DATABASE_TRANSPORT: tcp
STORAGE_DIR: /tmp/adhikaar
CLIENT_ORIGIN: "$CLIENT_ORIGIN"
EOF

"$GCLOUD" run deploy "$SERVICE" --project="$PROJECT" --region="$REGION" \
    --source="$server_dir" --service-account="$SERVICE_ACCOUNT" \
    --cpu=2 --memory=4Gi --min-instances=1 --max-instances=1 --max=1 \
    --no-cpu-throttling --timeout=3600 --session-affinity --port=8080 \
    --no-invoker-iam-check --ingress=all \
    --env-vars-file="$env_file" \
    --set-secrets="DATABASE_URL=$DATABASE_SECRET:latest,SARVAM_API_KEY=$SARVAM_SECRET:latest,PROFILE_SECRET=$PROFILE_SECRET_NAME:latest" \
    --quiet

"$GCLOUD" run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" \
    --format='value(status.url)'
