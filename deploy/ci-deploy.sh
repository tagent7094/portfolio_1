#!/usr/bin/env bash
# Triggered by the /api/deploy webhook (via sudo).
# Pulls latest code, builds the frontend, runs provision, restarts service.
set -eo pipefail

export HOME=/root

APP_DIR=/opt/tagent
APP_USER=tagent

echo "=== [ci-deploy] Start ==="

cd "$APP_DIR"
git config --global --add safe.directory "$APP_DIR" || true

# Preserve VPS-generated data and config before hard reset
if [ -d "$APP_DIR/data/founders" ]; then
    echo "=== [ci-deploy] Backing up VPS data ==="
    cp -a "$APP_DIR/data" /tmp/tagent-data-backup
fi
if [ -f "$APP_DIR/config/llm-config.yaml" ]; then
    cp -a "$APP_DIR/config/llm-config.yaml" /tmp/tagent-llm-config-backup
fi

git fetch origin main
git reset --hard origin/main

# Restore VPS-generated files that may not be in git
if [ -d /tmp/tagent-data-backup/founders ]; then
    echo "=== [ci-deploy] Restoring VPS data ==="
    for slug_dir in /tmp/tagent-data-backup/founders/*/; do
        slug=$(basename "$slug_dir")
        for subdir in post-data knowledge-graph; do
            src="$slug_dir$subdir"
            dst="$APP_DIR/data/founders/$slug/$subdir"
            if [ -d "$src" ]; then
                mkdir -p "$dst"
                cp -an "$src"/. "$dst"/ 2>/dev/null || true
            fi
        done
    done
    rm -rf /tmp/tagent-data-backup
fi

# Restore config if it was wiped
if [ -f /tmp/tagent-llm-config-backup ] && [ ! -f "$APP_DIR/config/llm-config.yaml" ]; then
    echo "=== [ci-deploy] Restoring llm-config.yaml ==="
    mkdir -p "$APP_DIR/config"
    cp -a /tmp/tagent-llm-config-backup "$APP_DIR/config/llm-config.yaml"
fi
rm -f /tmp/tagent-llm-config-backup

chown -R "$APP_USER":"$APP_USER" "$APP_DIR/.git"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR/data" || true
chown -R "$APP_USER":"$APP_USER" "$APP_DIR/config" || true

echo "=== [ci-deploy] Installing Python deps ==="
"$APP_DIR/venv/bin/pip" install --quiet openpyxl anthropic python-multipart

echo "=== [ci-deploy] Building frontend ==="
cd "$APP_DIR/webapp-react"
npm ci --prefer-offline
npm run build

echo "=== [ci-deploy] Installing poll timer ==="
cp "$APP_DIR/deploy/tagent-poll.service" /etc/systemd/system/ 2>/dev/null || true
cp "$APP_DIR/deploy/tagent-poll.timer" /etc/systemd/system/ 2>/dev/null || true
systemctl daemon-reload
systemctl enable --now tagent-poll.timer 2>/dev/null || true

echo "=== [ci-deploy] Restarting service ==="
systemctl restart tagent

echo "=== [ci-deploy] Running provision ==="
bash "$APP_DIR/deploy/provision.sh"

echo "=== [ci-deploy] Indexing RAG for AskSharath ==="
cd "$APP_DIR"
"$APP_DIR/venv/bin/python" scripts/index_sharath_rag.py || echo "[ci-deploy] RAG indexing failed (non-fatal)"

echo "=== [ci-deploy] Done ==="
