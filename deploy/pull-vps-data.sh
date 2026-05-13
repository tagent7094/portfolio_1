#!/usr/bin/env bash
# Pull post-packs and knowledge-graph data from VPS to local.
# Usage: bash deploy/pull-vps-data.sh [--dry-run]
set -eo pipefail

VPS_HOST="${TAGENT_VPS_HOST:-root@147.93.20.156}"
VPS_DIR="/opt/tagent"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

RSYNC_OPTS="-avz --progress"
[ "$1" = "--dry-run" ] && RSYNC_OPTS="$RSYNC_OPTS --dry-run"

echo "=== Pulling VPS data to local ==="
echo "    VPS:   $VPS_HOST:$VPS_DIR"
echo "    Local: $LOCAL_DIR"

rsync $RSYNC_OPTS \
    "$VPS_HOST:$VPS_DIR/data/founders/*/post-data/" \
    --include="*/" --include="*.json" --include="*.xlsx" --exclude="*" \
    "$LOCAL_DIR/data/founders/" \
    --relative

rsync $RSYNC_OPTS \
    "$VPS_HOST:$VPS_DIR/data/founders/" \
    --include="*/" --include="*/post-data/***" --include="*/knowledge-graph/***" --exclude="*" \
    "$LOCAL_DIR/data/founders/"

echo "=== Done ==="
