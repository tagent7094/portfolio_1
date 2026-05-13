#!/usr/bin/env bash
# Push local post-packs and knowledge-graph data to VPS.
# Usage: bash deploy/push-local-data.sh [--dry-run]
set -eo pipefail

VPS_HOST="${TAGENT_VPS_HOST:-root@147.93.20.156}"
VPS_DIR="/opt/tagent"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

RSYNC_OPTS="-avz --progress"
[ "$1" = "--dry-run" ] && RSYNC_OPTS="$RSYNC_OPTS --dry-run"

echo "=== Pushing local data to VPS ==="
echo "    Local: $LOCAL_DIR"
echo "    VPS:   $VPS_HOST:$VPS_DIR"

rsync $RSYNC_OPTS \
    "$LOCAL_DIR/data/founders/" \
    --include="*/" --include="*/post-data/***" --include="*/knowledge-graph/***" --exclude="*" \
    "$VPS_HOST:$VPS_DIR/data/founders/"

echo "=== Done ==="
