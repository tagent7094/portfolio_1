"""Quick auth round-trip test."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["TAGENT_JWT_SECRET"] = "test-secret-for-roundtrip"

from src.auth.passwords import hash_password, verify_password
from src.auth.tokens import issue_token, decode_token

# Password round-trip
h = hash_password("hunter2")
assert verify_password("hunter2", h), "password verify failed"
assert not verify_password("wrong", h), "password should not verify wrong"
assert not verify_password("", h), "empty password should fail"
print("[OK] passwords")

# Token round-trip
t = issue_token("sharath")
claims = decode_token(t)
assert claims is not None, "token decode failed"
assert claims["sub"] == "sharath", f"sub mismatch: {claims}"
assert decode_token("garbage") is None, "garbage token should fail"
assert decode_token("") is None, "empty token should fail"
print("[OK] tokens")

# Subdomain resolution
from webapp.auth_middleware import _resolve_subdomain_slug
assert _resolve_subdomain_slug("sharath.tagent.club") == "sharath"
assert _resolve_subdomain_slug("anish_popli.tagent.club") == "anish_popli"
assert _resolve_subdomain_slug("tagent.club") is None
assert _resolve_subdomain_slug("localhost") is None
assert _resolve_subdomain_slug("localhost:8000") is None
assert _resolve_subdomain_slug("127.0.0.1") is None
assert _resolve_subdomain_slug("sharath.tagent.club:8000") == "sharath"
print("[OK] subdomain resolution")

# Store round-trip (uses real config dir)
from src.auth.store import set_password, get_hash
import tempfile, shutil
from pathlib import Path
from src.auth import store as store_mod

# Backup current and use a temp file
tmp = Path(tempfile.mkdtemp())
backup = store_mod._AUTH_FILE.read_text(encoding="utf-8") if store_mod._AUTH_FILE.exists() else None
store_mod._AUTH_FILE = tmp / "founder-auth.yaml"
try:
    set_password("test_slug", "p4ssw0rd")
    h = get_hash("test_slug")
    assert h is not None, "hash not stored"
    assert verify_password("p4ssw0rd", h)
    print("[OK] store")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\nAll auth tests passed.")
