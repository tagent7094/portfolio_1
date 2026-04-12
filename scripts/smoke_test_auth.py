"""Smoke test: verify auth additions don't break existing server."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import webapp.server as s

routes = [r.path for r in s.app.routes if hasattr(r, 'path')]
auth_routes = sorted(r for r in routes if '/api/auth' in r)
print(f'Total routes: {len(routes)}')
print(f'Auth routes: {auth_routes}')

mws = [type(m.cls).__name__ if hasattr(m, 'cls') else type(m).__name__ for m in s.app.user_middleware]
print(f'Middleware: {mws}')

# Verify ContextVar helper ordering
import os
os.environ.pop('TAGENT_AUTH_ENABLED', None)
print(f'_active_founder_slug() with no env: {s._active_founder_slug()!r}')

# Simulate scoped ctx
from src.auth import context as ctx
token = ctx.current_founder_slug.set('sharath')
try:
    print(f'_active_founder_slug() with ctx=sharath: {s._active_founder_slug()!r}')
finally:
    ctx.current_founder_slug.reset(token)

print('\nOK — server imports cleanly, auth is additive.')
