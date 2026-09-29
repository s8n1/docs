"""Password authentication with SQLite-backed sessions.

- Passwords are hashed with PBKDF2-HMAC-SHA256 (200k iterations, random salt).
- Sessions are opaque random tokens stored in an HttpOnly cookie.
- Accounts sign in with email **or username**; there is no phone-number step.
- The fixed administrator (`admin` / `13811372` by default) is seeded by
  `db.init_db()` and can log in with just its username and password.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request

from api import db

SESSION_COOKIE = "de_session"
SESSION_DAYS = 30
_PBKDF2_ITERATIONS = 200_000

# In-process login throttle. Failed logins are counted per identifier + client
# host; once LOGIN_MAX_FAILURES failures land inside LOGIN_WINDOW_SECONDS the
# key is refused with 429 until the window slides past. Single-process uvicorn
# keeps this in memory on purpose: no schema, no shared state, no surprises.
LOGIN_MAX_FAILURES = 8
LOGIN_WINDOW_SECONDS = 300
_login_failures: dict[str, list[float]] = {}


def login_key(identifier: str, host: str | None) -> str:
    return f"{(identifier or '').strip().lower()}|{host or 'unknown'}"


def _prune(key: str, now: float) -> list[float]:
    kept = [t for t in _login_failures.get(key, []) if now - t < LOGIN_WINDOW_SECONDS]
    if kept:
        _login_failures[key] = kept
    else:
        _login_failures.pop(key, None)
    return kept


def login_blocked(key: str) -> int:
    """Seconds the caller must wait, or 0 when the key may try again."""
    now = time.monotonic()
    recent = _prune(key, now)
    if len(recent) < LOGIN_MAX_FAILURES:
        return 0
    oldest = min(recent)
    return max(1, int(LOGIN_WINDOW_SECONDS - (now - oldest)))


def note_login_failure(key: str) -> None:
    now = time.monotonic()
    recent = _prune(key, now)
    recent.append(now)
    _login_failures[key] = recent


def clear_login_failures(key: str) -> None:
    _login_failures.pop(key, None)


def reset_login_throttle() -> None:
    """Drop every counter (used by tests)."""
    _login_failures.clear()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        ).hex()
        return hmac.compare_digest(calc, digest)
    except (ValueError, TypeError):
        return False


def create_session(user_id: int | None, initial_tokens: int = 0) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO sessions (token, user_id, tokens, created_at, expires_at, last_seen) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (token, user_id, max(int(initial_tokens), 0),
         now.isoformat(timespec="seconds"),
         (now + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds"),
         now.isoformat(timespec="seconds")),
    )
    return token


def delete_session(token: str) -> None:
    db.execute("DELETE FROM sessions WHERE token = ?", (token,))


def current(request: Request) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve (user, session) from the request cookie. Expired sessions are dropped."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None, None
    row = db.query_one(
        """SELECT s.token, s.user_id, s.expires_at, u.id AS uid, u.username, u.email,
                  u.name, u.role, u.banned
           FROM sessions s LEFT JOIN users u ON u.id = s.user_id
           WHERE s.token = ?""",
        (token,),
    )
    if not row:
        return None, None
    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except ValueError:
        expires = datetime.now(timezone.utc) - timedelta(seconds=1)
    if expires <= datetime.now(timezone.utc):
        delete_session(token)
        return None, None
    session = {"token": row["token"], "user_id": row["user_id"]}
    if row["uid"] is None:
        return None, session
    user = {
        "id": row["uid"], "username": row["username"], "email": row["email"],
        "name": row["name"], "role": row["role"], "banned": bool(row["banned"]),
    }
    return user, session


def require_user(request: Request) -> dict[str, Any]:
    user, _ = current(request)
    if user is None:
        raise HTTPException(401, "Authentication required")
    if user["banned"]:
        raise HTTPException(403, "Account is disabled")
    return user


def require_admin(request: Request) -> dict[str, Any]:
    user = require_user(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def public_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {k: user[k] for k in ("id", "username", "email", "name", "role", "banned")}
