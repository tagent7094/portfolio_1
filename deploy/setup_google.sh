#!/usr/bin/env bash
# One-time setup: creates a GCP project + service account for Google Sheets export.
# Run this once on the VPS as root or a user with sudo.
# After this script completes, /etc/tagent/google-sa.json will exist and
# the Sheets export button in the admin panel will work.

set -eo pipefail

PROJECT_ID="tagent-sheets-$(head -c4 /dev/urandom | xxd -p)"
SA_NAME="tagent-sheets-bot"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SA_KEY_FILE="/etc/tagent/google-sa.json"
SHARE_EMAIL="content@tagent.club"

echo "=== [setup_google] Starting Google Sheets setup ==="
echo "Project: $PROJECT_ID"

# ── 1. Install gcloud if not present ──────────────────────────────────────────
if ! command -v gcloud &>/dev/null; then
  echo "Installing gcloud CLI..."
  curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir=/opt/gcloud
  export PATH="/opt/gcloud/google-cloud-sdk/bin:$PATH"
  echo 'export PATH="/opt/gcloud/google-cloud-sdk/bin:$PATH"' >> /etc/profile.d/gcloud.sh
fi

# ── 2. Authenticate (device flow — user clicks a URL once) ────────────────────
echo ""
echo "=== ACTION REQUIRED ==="
echo "You need to authorize gcloud with your Google account."
echo "Run the URL shown below in any browser (phone is fine)."
echo ""
gcloud auth login --no-launch-browser --quiet

# ── 3. Create project ─────────────────────────────────────────────────────────
echo "Creating GCP project: $PROJECT_ID"
gcloud projects create "$PROJECT_ID" --name="tagent Sheets" --quiet

# Billing must be enabled for the Sheets API; skip if on free tier
# gcloud beta billing projects link "$PROJECT_ID" --billing-account=XXXXX

gcloud config set project "$PROJECT_ID" --quiet

# ── 4. Enable APIs ────────────────────────────────────────────────────────────
echo "Enabling Sheets and Drive APIs..."
gcloud services enable sheets.googleapis.com drive.googleapis.com --quiet

# ── 5. Create service account + key ──────────────────────────────────────────
echo "Creating service account: $SA_NAME"
gcloud iam service-accounts create "$SA_NAME" \
  --display-name="tagent Sheets Bot" --quiet

mkdir -p /etc/tagent
gcloud iam service-accounts keys create "$SA_KEY_FILE" \
  --iam-account="$SA_EMAIL" --quiet

chmod 600 "$SA_KEY_FILE"
chown tagent:tagent "$SA_KEY_FILE" 2>/dev/null || true

# ── 6. Install Python dependencies ───────────────────────────────────────────
echo "Installing Python packages..."
/opt/tagent/venv/bin/pip install --quiet "google-auth>=2.0" "google-api-python-client>=2.0"

echo ""
echo "=== [setup_google] Done! ==="
echo "Service account key: $SA_KEY_FILE"
echo "Sheets will be shared with: $SHARE_EMAIL"
echo "Restart tagent: sudo systemctl restart tagent"
