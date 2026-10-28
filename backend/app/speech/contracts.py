"""Shared speech contracts for Spark. Audio is processed in memory."""
from dataclasses import dataclass
from typing import Protocol
from pydantic import BaseModel, ConfigDict, Field

RETAIN_AUDIO = False

class ProviderDisabled(RuntimeError):
    pass

class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    language: str = Field(default="en", max_length=12)

@dataclass(frozen=True)
class ProviderStatus:
    capability: str
    enabled: bool
    provider: str | None
    reason: str
    credential_present: bool

class SpeechProvider(Protocol):
    def status(self) -> ProviderStatus: ...
    def transcribe(self, scope: object | None, audio: bytes, mime: str) -> Transcript: ...
    def synthesize(self, scope: object | None, text: str) -> bytes: ...
    def cancel(self, scope: object | None) -> None: ...
