"""Assistant and speech contracts with isolated mocks. No network; a credential's value is never read, returned or logged."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.assistant.contracts import (RETAIN_AUDIO, ChangeProposal, Evidence, Operation, ProviderDisabled, ProviderStatus, SessionScope, Transcript, TranscriptSubmission)
from app.assistant.providers import DisabledAssistant, DisabledSpeech, SubmissionGuard

SCOPE = SessionScope(organization_id="org_a", project_id="app_tms", revision=3)


class FakeAssistant:
    """A well-behaved stand-in provider: returns a structured proposal citing evidence."""
    def status(self) -> ProviderStatus:
        return ProviderStatus("assistant", True, "fake", "test double", False)

    def propose(self, scope, message, context):
        return ChangeProposal(scope=scope, summary="Add a branch for delayed shipments", operations=[Operation(op="add", path="workflow_definitions.wf_transport_lifecycle.states", value={"id": "tl_x"})],
                              evidence=[Evidence(kind="process_step", reference="wf_transport_lifecycle/tl_check_delivery")])


class FakeSpeech:
    def __init__(self):
        self.cancelled = 0

    def status(self) -> ProviderStatus:
        return ProviderStatus("speech", True, "fake", "test double", False)

    def transcribe(self, scope, audio, mime):
        return Transcript(text="add a branch for delayed shipments", confidence=0.93)

    def synthesize(self, scope, text):
        return b"audio"

    def cancel(self, scope):
        self.cancelled += 1






def test_status_endpoint_never_returns_a_credential(monkeypatch):
    from app.api.dependencies import current_user
    from app.core.roles import Role
    from app.main import create_app
    from app.services.orders import User
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "super-secret-value-123")
    monkeypatch.setenv("STUDIO_ASSISTANT", "off")
    app = create_app()
    app.dependency_overrides[current_user] = lambda: User("u", "U", "u@example.invalid", Role.END_USER)
    with TestClient(app) as client:
        response = client.get("/api/v1/assistant/status")
        assert response.status_code == 200 and "super-secret-value-123" not in response.text
        body = response.json()
        assert body["assistant"]["enabled"] is False and body["speech"]["enabled"] is True and body["speech"]["provider"] == "deepgram" and body["speech"]["credential_present"] is True
    monkeypatch.setenv("VERCEL_ENV", "production")
    with TestClient(app) as client:
        assert client.get("/api/v1/assistant/status").status_code == 503








