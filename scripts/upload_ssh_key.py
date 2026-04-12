"""Upload SSH public key to Hostinger and attach it to the VPS."""
import json
import os
import sys
import urllib.request
from pathlib import Path

TOKEN = os.environ.get("HOSTINGER_API_TOKEN", "")
if not TOKEN:
    print("Set HOSTINGER_API_TOKEN env var first.")
    sys.exit(1)
VM_ID = int(os.environ.get("HOSTINGER_VM_ID", "1580697"))
KEY_NAME = os.environ.get("SSH_KEY_NAME", "tagent-deploy")
KEY_PATH = Path(__file__).parent.parent / "hostinger_mcp.pub"


def req(method, path, body=None):
    url = f"https://developers.hostinger.com{path}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "curl/8.4.0",
    }
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read())
        except Exception:
            err_body = str(e)
        return {"_error": True, "status": e.code, "body": err_body}


pubkey = KEY_PATH.read_text().strip()
print(f"Uploading key: {pubkey[:50]}...")

# 1. Upload key
result = req("POST", "/api/vps/v1/public-keys", {"name": KEY_NAME, "key": pubkey})
print(f"Upload result: {json.dumps(result)[:400]}")

if result.get("_error"):
    # Maybe it already exists — list and find
    keys = req("GET", "/api/vps/v1/public-keys")
    if isinstance(keys, list):
        for k in keys:
            if k.get("name") == KEY_NAME or k.get("key", "").strip() == pubkey:
                result = k
                print(f"Using existing key: {k}")
                break

key_id = result.get("id")
if not key_id:
    print("Could not get key ID. Aborting.")
    sys.exit(1)

print(f"Key ID: {key_id}")

# 2. Attach to VPS
attach = req("POST", f"/api/vps/v1/public-keys/attach/{VM_ID}", {"ids": [key_id]})
print(f"Attach result: {json.dumps(attach)[:400]}")
