import json
import secrets
from datetime import datetime, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from graphql import GraphQLError

ph = PasswordHasher()

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return ph.verify(stored_hash, password)
    except VerifyMismatchError:
        return False

def new_session_id() -> str:
    return secrets.token_urlsafe(32)

def session_payload(*, authenticated: bool, user_id: int | None = None, email: str | None = None) -> str:
    now = datetime.now(timezone.utc).isoformat()
    return json.dumps({
        "authenticated": authenticated,
        "user_id": user_id,
        "email": email,
        "created_at": now,
        "rotated_at": now if authenticated else None,
    })

async def enforce_rate_limit(redis, key: str, limit: int, window_seconds: int, response=None):
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    ttl = await redis.ttl(key)
    if count > limit:
        if response is not None:
            response.status_code = 429
            response.headers["Retry-After"] = str(max(ttl, 1))
        raise GraphQLError(
            "Rate limit exceeded. Try again later.",
            extensions={"code": "RATE_LIMITED", "limit": limit, "retryAfter": max(ttl, 1)},
        )
    return count
