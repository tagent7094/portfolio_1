#!/usr/bin/env bash
# One-time VPS bootstrap for tagent.club.
# Run as root after fresh Hostinger VPS provisioning.
# Assumes Ubuntu 22.04+ and that *.tagent.club DNS already points here.

set -euo pipefail

APP_DIR=/opt/tagent
APP_USER=tagent
REPO_URL="${REPO_URL:-https://github.com/YOUR_USER/digital-dna.git}"

echo "==> Installing system packages"
apt-get update
apt-get install -y python3.11 python3.11-venv python3-pip nginx certbot \
    git curl ca-certificates build-essential

echo "==> Installing Node.js 20 (for build only)"
if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi

echo "==> Creating service user"
if ! id "$APP_USER" >/dev/null 2>&1; then
    useradd -r -m -d "$APP_DIR" -s /bin/bash "$APP_USER"
fi

echo "==> Cloning repo"
if [ ! -d "$APP_DIR/.git" ]; then
    sudo -u "$APP_USER" git clone "$REPO_URL" "$APP_DIR"
else
    sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
fi

echo "==> Creating Python venv"
if [ ! -d "$APP_DIR/venv" ]; then
    sudo -u "$APP_USER" python3.11 -m venv "$APP_DIR/venv"
fi
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -e "$APP_DIR"

echo "==> Building frontend"
sudo -u "$APP_USER" bash -c "cd $APP_DIR/webapp-react && npm ci && npm run build"

echo "==> Generating JWT secret"
mkdir -p /etc/tagent
if [ ! -s /etc/tagent/jwt-secret ]; then
    openssl rand -base64 48 > /etc/tagent/jwt-secret
    chmod 600 /etc/tagent/jwt-secret
    chown "$APP_USER":"$APP_USER" /etc/tagent/jwt-secret
fi

echo "==> Copying founder-auth.yaml.example if none exists"
if [ ! -f "$APP_DIR/config/founder-auth.yaml" ]; then
    cp "$APP_DIR/config/founder-auth.yaml.example" "$APP_DIR/config/founder-auth.yaml"
    chown "$APP_USER":"$APP_USER" "$APP_DIR/config/founder-auth.yaml"
    chmod 600 "$APP_DIR/config/founder-auth.yaml"
    echo "    ⚠  Run 'digital-dna auth set <slug>' to create real credentials"
fi

echo "==> Installing systemd unit"
cp "$APP_DIR/deploy/tagent.service" /etc/systemd/system/tagent.service
systemctl daemon-reload
systemctl enable tagent
systemctl restart tagent

echo "==> Installing nginx config"
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/tagent
ln -sf /etc/nginx/sites-available/tagent /etc/nginx/sites-enabled/tagent
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo ""
echo "==> Next steps:"
echo "  1. Get wildcard cert:"
echo "     certbot certonly --manual --preferred-challenges=dns \\"
echo "       -d tagent.club -d '*.tagent.club' --agree-tos -m you@example.com"
echo "  2. Reload nginx:  systemctl reload nginx"
echo "  3. Mint credentials:"
echo "     sudo -u $APP_USER $APP_DIR/venv/bin/digital-dna auth set sharath"
echo "  4. Test:  curl -i https://sharath.tagent.club/api/auth/me"
