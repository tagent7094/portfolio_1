# tagent.club Deployment Runbook

End-to-end steps to deploy Digital DNA to `*.tagent.club` on a Hostinger VPS,
with DNS kept at your current registrar (Option A).

---

## Prerequisites

- [ ] Hostinger VPS purchased (KVM 1 minimum, Ubuntu 22.04 LTS recommended)
- [ ] VPS root password (or your SSH public key uploaded)
- [ ] Access to the DNS panel of whatever registrar holds `tagent.club`
- [ ] GitHub repo for this code (already has `.github/workflows/deploy.yml`)

---

## Phase 1 — DNS (at your registrar)

At the registrar where `tagent.club` is registered, add **two A records** pointing at your VPS IP:

| Type | Name      | Value            | TTL  |
|------|-----------|------------------|------|
| A    | `@`       | `<VPS_IP>`       | 3600 |
| A    | `*`       | `<VPS_IP>`       | 3600 |

The wildcard (`*`) is what makes `sharath.tagent.club`, `anish.tagent.club`, etc. all resolve to the same VPS. The middleware in `webapp/auth_middleware.py` reads the `Host` header to decide which founder the request belongs to.

**Verify with:**
```bash
dig +short sharath.tagent.club   # should return <VPS_IP>
dig +short tagent.club           # should return <VPS_IP>
```

Wait for propagation (usually a few minutes, up to 1 hour).

---

## Phase 2 — VPS bootstrap (one-time)

SSH into the VPS as root:

```bash
ssh root@<VPS_IP>
```

Clone the repo and run the bootstrap script:

```bash
# Set your repo URL
export REPO_URL=https://github.com/<you>/digital-dna.git

# Fetch the bootstrap script from the repo
curl -fsSL https://raw.githubusercontent.com/<you>/digital-dna/main/deploy/bootstrap.sh -o /tmp/bootstrap.sh
chmod +x /tmp/bootstrap.sh
REPO_URL=$REPO_URL bash /tmp/bootstrap.sh
```

What it does (see `deploy/bootstrap.sh`):
- Installs Python 3.11, Node 20, nginx, certbot, git
- Creates a `tagent` service user
- Clones the repo to `/opt/tagent`, creates venv, installs the package
- Builds the React frontend
- Generates a random JWT secret at `/etc/tagent/jwt-secret`
- Copies `founder-auth.yaml.example` → `founder-auth.yaml` (empty placeholders)
- Installs the systemd unit and nginx config
- Starts `tagent.service`

---

## Phase 3 — TLS certificate (wildcard, one-time)

Wildcard certs require **DNS-01 challenge**, which means manually adding a TXT record at your registrar.

```bash
certbot certonly --manual --preferred-challenges=dns \
  -d tagent.club -d '*.tagent.club' \
  --agree-tos --no-eff-email \
  -m you@example.com
```

Certbot will print something like:
```
Please deploy a DNS TXT record under the name:
_acme-challenge.tagent.club.
with the following value:
<long-random-string>
```

Add that TXT record at your registrar, wait ~2 min for propagation, press Enter. Certbot fetches the cert to `/etc/letsencrypt/live/tagent.club/`. Then reload nginx:

```bash
systemctl reload nginx
```

**Renewal note:** Wildcard certs don't auto-renew via webroot. You'll need to re-run the same certbot command every ~80 days, or script it with a DNS plugin if your registrar has one. Set a calendar reminder.

---

## Phase 4 — Mint founder credentials

For each founder you want to give access to:

```bash
sudo -u tagent /opt/tagent/venv/bin/digital-dna auth set sharath
# (prompts for password + confirmation)
```

Repeat for `anish_popli`, `deepinder`, `manisha`. Passwords are stored as bcrypt hashes in `/opt/tagent/config/founder-auth.yaml`.

**Verify:**
```bash
sudo -u tagent /opt/tagent/venv/bin/digital-dna auth list
```

---

## Phase 5 — Smoke test

```bash
# Should return 401 (no cookie yet)
curl -i https://sharath.tagent.club/api/auth/me

# Login
curl -c /tmp/jar -X POST https://sharath.tagent.club/api/auth/login \
  -H 'content-type: application/json' \
  -d '{"slug":"sharath","password":"<THE_PASSWORD>"}'

# Should return 200 + sharath's display name
curl -b /tmp/jar https://sharath.tagent.club/api/auth/me

# Should return sharath's graph stats
curl -b /tmp/jar https://sharath.tagent.club/api/graph/stats

# Cross-scope check: cookie for sharath should NOT work on anish subdomain
curl -b /tmp/jar https://anish.tagent.club/api/graph/stats
# → 403 (subdomain mismatch)
```

Open `https://sharath.tagent.club` in a browser → should redirect to `/login` with the slug field prefilled to `sharath` and read-only. Enter the password → lands on the dashboard showing only sharath's graph.

---

## Phase 6 — GitHub Actions (optional, for future pushes)

Repository **Settings → Secrets and variables → Actions**:

**Secrets:**
- `VPS_HOST` — VPS IP or hostname
- `VPS_USER` — `root` (or a deploy user with sudo)
- `VPS_SSH_KEY` — private key contents (generate a deploy key, put the pubkey in `~/.ssh/authorized_keys` on the VPS)

**Variables:**
- `DEPLOY_ENABLED` — set to `true`

After that, any `git push origin main` will build the frontend, SCP the `dist/` folder to the VPS, pull backend code, and restart the `tagent` systemd service.

**The workflow is gated behind `DEPLOY_ENABLED=true`, so pushes are safe until you flip that variable.**

---

## Troubleshooting

**`401` on /api/auth/me after login**
Cookie probably didn't get set. Check the `Set-Cookie` response header on login. If missing `Secure` but served over HTTPS, set `TAGENT_COOKIE_SECURE=1` in `/etc/systemd/system/tagent.service` (already done in the unit file).

**`403 subdomain mismatch`**
The cookie's `sub` claim doesn't match the subdomain. Log out and re-login on the correct subdomain.

**`502 Bad Gateway` on /api/***
`systemctl status tagent` — the uvicorn process crashed. Check `journalctl -u tagent -n 100`.

**SSE streams disconnecting after 30s**
Nginx buffering. Confirm `proxy_buffering off;` is in the `/api/` location block of `/etc/nginx/sites-available/tagent`.

**Founders can still switch via the UI**
Make sure `TAGENT_AUTH_ENABLED=1` is set in the systemd unit — `POST /api/founders/active` returns 403 only when that env var is set.

---

## Files on the VPS

```
/opt/tagent/                     # Repo clone (owned by tagent user)
├── venv/                        # Python venv
├── webapp-react/dist/           # Built SPA
├── config/
│   ├── llm-config.yaml          # LLM config (already gitignored)
│   └── founder-auth.yaml        # Bcrypt password hashes (gitignored)
└── data/founders/               # Per-founder graphs + raw data

/etc/tagent/jwt-secret            # 48-byte random JWT signing key
/etc/systemd/system/tagent.service
/etc/nginx/sites-available/tagent
/etc/letsencrypt/live/tagent.club/
```
