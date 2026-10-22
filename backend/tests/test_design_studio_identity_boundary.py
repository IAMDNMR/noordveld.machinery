"""Authentication boundary tests use a fake identity repository, never Neo4j."""
from fastapi.testclient import TestClient

from app.api.dependencies import get_orders_repository
from app.api.routes.design_studio import get_project_store
from app.core.config import get_settings
from app.core.session import COOKIE, sign
from app.main import app
from tests.support.fake_orders import FakeRepo




def test_deployed_environment_refuses_demo_login_and_studio_before_storage(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    app.dependency_overrides[get_orders_repository] = lambda: FakeRepo()
    calls = []
    app.dependency_overrides[get_project_store] = lambda: calls.append("storage")
    try:
        client = TestClient(app)
        assert client.get("/api/v1/auth/demo-users").status_code == 404
        assert client.post("/api/v1/auth/login", json={"user_id": "U-ANNA"}).status_code == 404
        assert client.get("/api/v1/design-studio/projects").status_code == 503
        client.cookies.set(COOKIE, sign("U-ANNA", get_settings().session_secret))
        assert client.get("/api/v1/design-studio/projects").status_code == 503
        assert client.get("/api/v1/design-studio/projects", headers={"X-User-ID": "U-ANNA"}).status_code == 503
        assert calls == []
    finally:
        app.dependency_overrides.pop(get_orders_repository, None)
        app.dependency_overrides.pop(get_project_store, None)




