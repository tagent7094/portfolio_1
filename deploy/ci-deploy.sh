#!/usr/bin/env bash
# Triggered by the /api/deploy webhook (via sudo).
# Pulls latest code, builds the frontend, runs provision, restarts service.
set -eo pipefail

APP_DIR=/opt/tagent
APP_USER=tagent

echo "=== [ci-deploy] Start ==="

cd "$APP_DIR"
git config --global --add safe.directory "$APP_DIR" || true
sudo -u "$APP_USER" git fetch origin main
sudo -u "$APP_USER" git reset --hard origin/main
chown -R "$APP_USER":"$APP_USER" "$APP_DIR/config/founder-permissions.yaml" || true

echo "=== [ci-deploy] Installing Python deps ==="
"$APP_DIR/venv/bin/pip" install --quiet openpyxl

echo "=== [ci-deploy] Building frontend ==="
cd "$APP_DIR/webapp-react"
npm ci --prefer-offline
npm run build

echo "=== [ci-deploy] Restarting service ==="
systemctl restart tagent

echo "=== [ci-deploy] Running provision ==="
bash "$APP_DIR/deploy/provision.sh"

echo "=== [ci-deploy] Done ==="
