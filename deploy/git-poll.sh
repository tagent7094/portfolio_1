#!/usr/bin/env bash
# Polls origin/main every run. If new commits are found, runs ci-deploy.sh.
# Called by systemd timer (tagent-poll.timer) every 60 seconds.
set -eo pipefail

APP_DIR=/opt/tagent
LOG_TAG="tagent-poll"

cd "$APP_DIR"
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true

# Fetch latest without changing working tree
git fetch origin main --quiet 2>/dev/null || {
    echo "[$LOG_TAG] git fetch failed — skipping this cycle"
    exit 0
}

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0
fi

echo "[$LOG_TAG] New commits detected: $LOCAL -> $REMOTE"
echo "[$LOG_TAG] Running ci-deploy.sh..."
bash "$APP_DIR/deploy/ci-deploy.sh"
