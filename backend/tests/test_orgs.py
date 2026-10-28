"""Organization workspaces use account access without application-generation dependencies."""
from fastapi.testclient import TestClient
from app.api.dependencies import current_user
from app.core.roles import Role
from app.main import create_app
from app.orgs.directory import SqliteOrgDirectory, get_org_directory
from app.services.orders import User


def test_organizations_are_isolated_and_workspace_only_lists_available_applications(tmp_path):
    directory = SqliteOrgDirectory(tmp_path / 'organizations.sqlite')
    directory.seed_organization('org_a', 'Organization A')
    directory.seed_organization('org_b', 'Organization B')
    directory.seed_app_grant('alice', 'org_a', 'parts_store', 'customer')
    directory.seed_app_grant('bob', 'org_b', 'orders', 'customer')
    app = create_app()
    app.dependency_overrides[get_org_directory] = lambda: directory
    app.dependency_overrides[current_user] = lambda: User('alice', 'Alice', 'a@example.invalid', Role.END_USER)
    client = TestClient(app)
    result = client.get('/api/v1/workspace')
    assert result.status_code == 200
    data = result.json()
    assert [item['id'] for item in data['organizations']] == ['org_a']
    assert all(item['status'] == 'operational' for item in data['applications'])
    assert next(item for item in data['applications'] if item['id'] == 'parts_store')['launchable']
    assert not next(item for item in data['applications'] if item['id'] == 'orders')['launchable']
    assert client.get('/api/v1/workspace?org=org_b').status_code == 404
