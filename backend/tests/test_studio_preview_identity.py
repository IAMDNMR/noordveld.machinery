from fastapi import Request

from app.api.dependencies import current_user
from app.core.config import get_settings
from app.core.roles import Role
from app.core.session import sign
from app.design_studio import preview_identity
from app.services.orders import User


def test_cached_identity_is_used_only_for_signed_loopback_studio_sessions(monkeypatch):
    monkeypatch.setattr(preview_identity, "_identities", {})
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    user = User("preview-user", "Preview", "preview@example.invalid", Role.END_USER)
    preview_identity.remember(user)
    calls = []

    class Orders:
        def user(self, user_id):
            calls.append(user_id)
            return user if user_id == user.id else None

    def request(path):
        return Request(
            {
                "type": "http",
                "path": path,
                "scheme": "http",
                "server": ("localhost", 8000),
                "client": ("127.0.0.1", 1234),
                "headers": [],
                "query_string": b"",
            }
        )

    secret = get_settings().session_secret
    token = sign(user.id, "studio:" + secret)
    assert current_user(Orders(), request("/api/v1/design-studio/projects"), None, token) == user
    assert calls == []
    assert current_user(Orders(), request("/api/v1/orders"), sign(user.id, secret), token) == user
    assert calls == [user.id]
    monkeypatch.setenv("VERCEL_ENV", "production")
    assert current_user(Orders(), request("/api/v1/design-studio/projects"), None, token) == user
    assert calls == [user.id, user.id]


def test_expired_preview_identity_is_not_reused(monkeypatch):
    monkeypatch.setattr(preview_identity, "_identities", {})
    monkeypatch.setattr(preview_identity, "monotonic", lambda: 0)
    user = User("preview-user", "Preview", "preview@example.invalid", Role.END_USER)
    preview_identity.remember(user)
    assert preview_identity.cached(user.id) == user
    monkeypatch.setattr(preview_identity, "monotonic", lambda: 301)
    assert preview_identity.cached(user.id) is None
