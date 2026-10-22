"""Retained packages survive restart and cannot cross owner/project boundaries."""

import hashlib
import sqlite3

import pytest

from app.design_studio.releases import ReleaseStore, retain_package
from tests.support.frontend import with_frontend


def test_immutable_archive_and_history_survive_restart(tmp_path):
    path = tmp_path / "releases.sqlite"
    store = ReleaseStore(path)
    files = {"README.md": b"first approved revision"}
    saved = retain_package(store, "alice", "project", 12, "alice", files)
    original = store.archive("alice", "project", saved["id"])
    run = store.start_test("alice", "project", saved["id"], "reviewer")
    store.finish_test(
        "alice", "project", run, {"passed": True, "ran": 3, "passed_count": 2, "skipped_count": 1}
    )
    restarted = ReleaseStore(path)
    assert restarted.get("alice", "project", saved["id"])["tests"][0]["status"] == "partial"
    # Retrying retention never replaces an existing immutable archive or actor.
    same = store.retain("alice", "project", 12, "another", files, b"changed zip", {})
    assert same["actor"] == "alice"
    assert restarted.archive("alice", "project", saved["id"]) == original
    assert hashlib.sha256(original).hexdigest() == same["archive_sha256"]
    backup = tmp_path / "backup.sqlite"
    assert restarted.backup(backup) == {"archive_count": 1, "verified": True}
    restored = ReleaseStore(backup)
    assert restored.archive("alice", "project", saved["id"]) == original
    assert restored.get("alice", "project", saved["id"])["tests"][0]["status"] == "partial"
    with pytest.raises(FileExistsError):
        restarted.backup(backup)
    newer = retain_package(restarted, "alice", "project", 13, "alice", {"README.md": b"new"})
    assert newer["id"] != saved["id"]
    assert len(restarted.list("alice", "project")) == 2
    with pytest.raises(ValueError, match="already finished"):
        store.finish_test("alice", "project", run, {"passed": True})




def test_release_api_permissions_revision_checks_and_test_history(monkeypatch):
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from fastapi.testclient import TestClient
    from app.design_studio.local_app import create_local_app
    from app.design_studio.runtime_demo import synthetic_transport
    from app.api.routes.design_studio import get_project_store
    from app.orgs.directory import get_org_directory
    from app.design_studio.runtime_launcher import manager

    monkeypatch.setenv("DESIGN_STUDIO_LOCAL_DEV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.setattr(
        manager,
        "test",
        lambda *args: {
            "passed": True,
            "ran": 3,
            "passed_count": 2,
            "skipped_count": 1,
            "failed_count": 0,
            "cases": [],
            "seconds": 0,
            "output_tail": "",
        },
    )
    with TemporaryDirectory(prefix="noordveld-studio-") as directory:
        app = create_local_app(Path(directory) / "studio.sqlite")
        project = app.dependency_overrides[get_project_store]().create(
            "studio-alice", with_frontend(synthetic_transport())
        )
        app.dependency_overrides[get_org_directory]().register_project(
            project.id, "org_noordveld", "studio-alice"
        )
        root = "/api/v1/design-studio/projects/" + project.id
        headers = {"X-Org-Id": "org_noordveld"}
        with TestClient(app) as client:
            client.post("/api/v1/auth/login", json={"user_id": "studio-alice"})
            assert (
                client.post(
                    root + "/releases", json={"expected_revision": 999}, headers=headers
                ).status_code
                == 409
            )
            saved = client.post(
                root + "/releases", json={"expected_revision": project.revision}, headers=headers
            )
            assert saved.status_code == 200, saved.text
            release = saved.json()
            response = client.post(root + "/runtime/test", json={}, headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()["release_id"] == release["id"]
            retained = client.get(root + "/releases", headers=headers).json()
            assert retained[0]["tests"][0]["status"] == "partial"
            assert client.get(
                root + "/releases/" + release["id"] + "/archive", headers=headers
            ).content.startswith(b"PK")
            from app.design_studio.runtime_launcher import LaunchError

            def timeout(*args):
                raise LaunchError("The test worker timed out.")

            monkeypatch.setattr(manager, "test", timeout)
            assert client.post(root + "/runtime/test", json={}, headers=headers).status_code == 502
            dashboard = client.get(
                "/api/v1/design-studio/project-dashboard", headers=headers
            ).json()
            assert dashboard["counts"]["needs_attention"] == 1
            assert dashboard["projects"][0]["release"]["test_status"] == "failed"
            client.post("/api/v1/auth/login", json={"user_id": "studio-bob"})
            assert client.get(root + "/releases", headers=headers).status_code == 200
            assert (
                client.post(
                    root + "/releases", json={"expected_revision": 1}, headers=headers
                ).status_code
                == 403
            )
            assert (
                client.get(
                    root + "/releases/" + release["id"] + "/archive", headers=headers
                ).status_code
                == 403
            )
