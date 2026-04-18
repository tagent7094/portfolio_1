#!/usr/bin/env bash
# Auto-provisioning for new founders on the Hostinger VPS.
#
# Run after a git pull detects new data/founders/<slug>/ directories.
# Idempotent — safe to run on every deploy.
#
# What it does:
#   1. Scans data/founders/*/founder-data/ for slugs not yet in llm-config.yaml
#   2. Registers each new slug in llm-config.yaml with default paths
#   3. Adds each new slug to founder-permissions.yaml (default: graph only)
#   4. Expands the TLS cert via certbot --expand to cover new subdomains
#   5. Reloads nginx + restarts tagent service
#
# Password minting is NOT done here — the admin sets passwords via
# /admin → Reset Password button (which reveals the plaintext once).

set -euo pipefail

APP_DIR=/opt/tagent
APP_USER=tagent
DOMAIN_APEX=tagent.club
CERT_EMAIL="${CERT_EMAIL:-admin@tagent.club}"

cd "$APP_DIR"

echo "=== [provision] Scanning for new founders ==="

# Run a Python one-liner inside the venv to register any new founders.
# Reads data/founders/*/founder-data/ and updates llm-config.yaml +
# founder-permissions.yaml. Prints a JSON list of newly-registered slugs.
NEW_SLUGS=$(sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" - <<'PY'
import json
import sys
from pathlib import Path

import yaml

ROOT = Path("/opt/tagent")
CONFIG = ROOT / "config" / "llm-config.yaml"
PERMS = ROOT / "config" / "founder-permissions.yaml"
FOUNDERS_DIR = ROOT / "data" / "founders"

# Load current config
with open(CONFIG) as f:
    config = yaml.safe_load(f) or {}

registry = config.setdefault("founders", {}).setdefault("registry", {})

# Load current permissions
if PERMS.exists():
    with open(PERMS) as f:
        perms = yaml.safe_load(f) or {}
else:
    perms = {"defaults": {"pages": ["graph"]}, "founders": {}, "admin": {"password_hash": ""}}
perms.setdefault("defaults", {"pages": ["graph"]})
perms.setdefault("founders", {})
perms.setdefault("admin", {"password_hash": ""})

new_slugs = []

for folder in sorted(FOUNDERS_DIR.iterdir()):
    if not folder.is_dir():
        continue
    fd = folder / "founder-data"
    if not fd.is_dir():
        continue

    slug = folder.name.lower().replace(" ", "_").replace("-", "_")
    if slug in registry:
        continue

    display_name = folder.name.replace("_", " ").title()
    rel_folder = f"data/founders/{folder.name}"
    registry[slug] = {
        "display_name": display_name,
        "data_dir": f"{rel_folder}/founder-data",
        "graph_path": f"{rel_folder}/knowledge-graph/graph.json",
        "personality_card_path": f"{rel_folder}/knowledge-graph/personality-card.md",
        "vectors_path": f"{rel_folder}/knowledge-graph/chroma",
    }
    perms["founders"].setdefault(slug, {"pages": list(perms["defaults"]["pages"])})
    new_slugs.append(slug)

if new_slugs:
    with open(CONFIG, "w") as f:
        yaml.safe_dump(config, f, sort_keys=False, default_flow_style=False)
    with open(PERMS, "w") as f:
        yaml.safe_dump(perms, f, sort_keys=False, default_flow_style=False)

print(json.dumps(new_slugs))
PY
)

echo "[provision] New slugs: $NEW_SLUGS"

# Collect ALL known subdomains for the cert — always expand idempotently
ALL_SUBDOMAINS=$(sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" - <<'PY'
import yaml
from pathlib import Path

CONFIG = Path("/opt/tagent/config/llm-config.yaml")
with open(CONFIG) as f:
    config = yaml.safe_load(f) or {}

registry = (config.get("founders", {}) or {}).get("registry", {}) or {}
slugs = sorted(registry.keys())
# Let's Encrypt rejects underscores → swap to hyphens
subdomains = [slug.replace("_", "-") for slug in slugs]
print(" ".join(f"-d {sub}.tagent.club" for sub in subdomains))
PY
)

echo "[provision] Subdomains for cert: $ALL_SUBDOMAINS"

# Expand cert (idempotent — certbot is a no-op when nothing new needs adding)
certbot certonly --webroot -w /var/www/certbot \
    --non-interactive --agree-tos --no-eff-email \
    -m "$CERT_EMAIL" \
    --cert-name tagent.club \
    --expand \
    -d "$DOMAIN_APEX" \
    $ALL_SUBDOMAINS 2>&1 | tail -5 || {
        echo "[provision] certbot failed — continuing without cert expansion"
    }

# Reload nginx, restart tagent
sudo systemctl reload nginx
sudo systemctl restart tagent

if [ "$NEW_SLUGS" != "[]" ]; then
    echo ""
    echo "=== [provision] Registered new founders: $NEW_SLUGS ==="
    echo "=== Go to https://tagent.club/admin and click 'Reset Password' on each row to mint credentials. ==="
fi

echo "[provision] Done."
