"""Application access stays scoped to the signed-in organization and grant."""
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from app.api.app_access import require_app
from app.api.dependencies import get_orders
from app.core.config import get_settings
from app.core.roles import Role
from app.core.session import COOKIE, sign
from app.orgs.directory import SqliteOrgDirectory, get_org_directory
from app.services.orders import User


def test_application_grants_and_read_only_access_remain_enforced(tmp_path):
    directory = SqliteOrgDirectory(tmp_path / 'organizations.sqlite')
    directory.seed_organization('org_a', 'Demo organization')
    directory.seed_app_grant('dealer', 'org_a', 'parts_intelligence', 'dealer')
    person = User('dealer', 'Dealer', 'dealer@example.invalid', Role.END_USER)
    class Orders:
        def user(self, user_id):
            return person if user_id == person.id else None
    app = FastAPI()
    app.dependency_overrides[get_orders] = lambda: Orders()
    app.dependency_overrides[get_org_directory] = lambda: directory
    @app.get('/shop', dependencies=[Depends(require_app('agentic_shopping'))])
    def read(): return {'ok': True}
    @app.post('/shop', dependencies=[Depends(require_app('agentic_shopping'))])
    def write(): return {'ok': True}
    client = TestClient(app)
    assert client.get('/shop').status_code == 401
    client.cookies.set(COOKIE, sign(person.id, get_settings().session_secret))
    assert client.get('/shop').status_code == 403
    directory.seed_app_grant('dealer', 'org_a', 'agentic_shopping', 'app_viewer')
    assert client.get('/shop').status_code == 200
    assert client.post('/shop').status_code == 403
    assert client.get('/shop', headers={'X-Org-Id': 'other_org'}).status_code == 404
