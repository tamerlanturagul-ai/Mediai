"""P0 security bundle (TASK-009): API-key auth + rate limiting.

Auth model
---------
- Production secret comes from the ``API_KEYS`` env var (comma-separated,
  e.g. ``API_KEYS=key-one,key-two``). Comparison is constant-time via
  ``hmac.compare_digest``.
- When ``API_KEYS`` is unset/empty, /api/* stays OPEN. This keeps local dev
  and the pre-existing test-suite (which sends no keys) working; production
  deployments MUST set ``API_KEYS``. See REPORT (new env vars section).
- ``/api/health`` is always open (liveness probe). CORS preflights
  (``OPTIONS``) are exempt so browsers can negotiate headers.

Rate limits (slowapi, per client IP, per endpoint)
--------------------------------------------------
- POST /api/triage/initial : 30/minute
- POST /api/triage/final   : 30/minute
- POST /api/triage/photo   : 10/minute
- POST /api/sport/plan     : 30/minute
- GET  /api/conditions     : 60/minute
- GET  /api/health         : unlimited (stays open)
"""
from __future__ import annotations

import hmac
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

API_KEYS_ENV = "API_KEYS"

# --- rate-limit budgets (requests / minute / client IP) ---
LIMIT_TRIAGE_INITIAL = "30/minute"
LIMIT_TRIAGE_FINAL = "30/minute"
LIMIT_TRIAGE_PHOTO = "10/minute"
LIMIT_SPORT_PLAN = "30/minute"
LIMIT_CONDITIONS = "60/minute"

limiter = Limiter(key_func=get_remote_address, default_limits=[])


def get_api_keys() -> list[str]:
    """Parse API_KEYS env (comma-separated). Empty list == auth disabled."""
    raw = os.getenv(API_KEYS_ENV, "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def is_auth_enforced() -> bool:
    """True iff at least one API key is configured."""
    return bool(get_api_keys())


def key_matches(provided: str | None, keys: list[str]) -> bool:
    """Constant-time membership check of the presented key."""
    if not provided:
        return False
    return any(hmac.compare_digest(provided, k) for k in keys)


def requires_auth(path: str, method: str = "") -> bool:
    """True for protected /api/* routes. /api/health + OPTIONS stay open."""
    if method.upper() == "OPTIONS":
        return False
    if not path.startswith("/api/"):
        return False
    return path != "/api/health"
