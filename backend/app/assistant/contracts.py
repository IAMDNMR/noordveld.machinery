"""Typed contracts for the Design Studio assistant (language model) and for speech (speech-to-text and text-to-speech).

Both are PROVIDERS behind interfaces. In this milestone only disabled implementations ship; nothing here reads a credential
value or makes a network call. The rules the contracts enforce hold whatever provider is plugged in later:

* Model output is untrusted. A `ChangeProposal` is data to be validated against the application schemas, permissions and the
  approval policy OUTSIDE the model; it never mutates anything by itself.
* Speech recognition and synthesis are separate from language-model reasoning. A transcript is shown to the user and enters
  the same proposal workflow as typed text; a spoken command cannot execute anything privileged, and a high-impact change
  needs an explicit confirmation of the displayed transcript.
* Audio is not retained, and a session belongs to one organization and one project.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Paths whose change is high-impact: it needs explicit review and the configured approval process, never a chat "yes".
HIGH_IMPACT_PREFIXES = (
    "business.roles",
    "business.roles.permissions",
    "approvals",
    "business.integrations",
    "business.rules",
)
RETAIN_AUDIO = False  # policy: audio is processed in memory and discarded


class ProviderDisabled(RuntimeError):
    """The provider is not enabled in this environment. The message never contains a credential."""


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionScope(Strict):
    """What a conversation may see and change. Context is limited to exactly this organization, project and revision."""

    organization_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,79}$")
    project_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,79}$")
    revision: int = Field(ge=1)
    artifact: str = Field(default="", max_length=200)


class Evidence(Strict):
    kind: Literal[
        "domain_definition",
        "requirement",
        "process_step",
        "business_rule",
        "source_code",
        "assumption",
    ]
    reference: str = Field(min_length=1, max_length=300)


class Operation(Strict):
    op: Literal["add", "replace", "remove"]
    path: str = Field(min_length=1, max_length=300, pattern=r"^[a-z_]+(\.[A-Za-z0-9_-]+)*$")
    value: object | None = None


class ChangeProposal(Strict):
    """A structured, reviewable change. Applying it is a separate, permission-checked step."""

    scope: SessionScope
    summary: str = Field(min_length=1, max_length=500)
    operations: list[Operation] = Field(min_length=1, max_length=50)
    rationale: str = Field(default="", max_length=2000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=30)
    assumptions: list[str] = Field(default_factory=list, max_length=20)

    @property
    def high_impact(self) -> bool:
        return any(operation.path.startswith(HIGH_IMPACT_PREFIXES) for operation in self.operations)

    @model_validator(mode="after")
    def evidence_or_assumption(self):
        if not self.evidence and not self.assumptions:
            raise ValueError(
                "A proposal cites its evidence or states its assumptions; nothing is proposed from thin air"
            )
        return self


class Transcript(Strict):
    text: str = Field(min_length=1, max_length=4000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    language: str = Field(default="en", max_length=12)


class TranscriptSubmission(Strict):
    """What the Studio sends to the assistant after speech-to-text. The user has seen `text` before it is submitted."""

    scope: SessionScope
    text: str = Field(min_length=1, max_length=4000)
    displayed_to_user: bool
    confirmed: bool = False
    submission_id: str = Field(
        min_length=8, max_length=80
    )  # idempotency: a repeated event is not a second command

    @model_validator(mode="after")
    def shown_first(self):
        if not self.displayed_to_user:
            raise ValueError("A transcript must be shown to the user before it is submitted")
        return self


@dataclass(frozen=True)
class ProviderStatus:
    capability: str
    enabled: bool
    provider: str | None
    reason: str
    credential_present: bool  # whether a credential EXISTS in the environment, never its value


class AssistantProvider(Protocol):
    def status(self) -> ProviderStatus: ...
    def propose(self, scope: SessionScope, message: str, context: dict) -> ChangeProposal | str: ...


class SpeechProvider(Protocol):
    def status(self) -> ProviderStatus: ...
    # A new project has no scope yet (the first thing a user does is speak), so `scope` may be None for speech.
    def transcribe(self, scope: SessionScope | None, audio: bytes, mime: str) -> Transcript: ...
    def synthesize(self, scope: SessionScope | None, text: str) -> bytes: ...
    def cancel(self, scope: SessionScope | None) -> None: ...
