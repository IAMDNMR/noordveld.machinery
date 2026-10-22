"""Short-lived server cache for the already-resolved loopback Studio demo identity."""

from threading import Lock
from time import monotonic

from app.services.orders import User

_lock = Lock()
_identities: dict[str, tuple[float, User]] = {}
_ttl = 300


def remember(user: User) -> User:
    with _lock:
        now = monotonic()
        expired = [key for key, (until, _) in _identities.items() if until <= now]
        for key in expired:
            _identities.pop(key, None)
        if len(_identities) >= 32:
            _identities.pop(next(iter(_identities)))
        _identities[user.id] = (now + _ttl, user)
    return user


def cached(user_id: str | None = None) -> User | None:
    with _lock:
        candidates = [_identities[user_id]] if user_id in _identities else []
        if user_id is None:
            candidates = [
                value for value in _identities.values() if value[1].role.value == "END_USER"
            ]
        return next((user for until, user in candidates if until > monotonic()), None)
