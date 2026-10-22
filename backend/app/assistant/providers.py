"""The speech and language providers behind Design Studio, and the safe boundary around them.

Speech (Deepgram) is on when `DEEPGRAM_API_KEY` is present, unless `STUDIO_VOICE=off`. The conversation model is the project's
configured language-model provider (`LLM_PROVIDER`, see `app.llm`), unless `STUDIO_ASSISTANT=off`. Without a key a provider is
reported as unavailable with the reason; nothing pretends to work. This module never returns or logs a credential value: status
only says whether one EXISTS.
"""

from __future__ import annotations

import os

from app.assistant.contracts import (
    AssistantProvider,
    ChangeProposal,
    ProviderDisabled,
    ProviderStatus,
    SessionScope,
    SpeechProvider,
    Transcript,
    TranscriptSubmission,
)
from app.assistant.speech_deepgram import deepgram_from_environment
from app.core.config import get_settings


def _present(name: str) -> bool:
    return bool(os.environ.get(name))


class DisabledAssistant:
    def status(self) -> ProviderStatus:
        return ProviderStatus(
            "assistant",
            False,
            None,
            "The language-model assistant is not enabled in this environment. Design Studio works without it.",
            _present("ANTHROPIC_API_KEY"),
        )

    def propose(self, scope: SessionScope, message: str, context: dict) -> ChangeProposal | str:
        raise ProviderDisabled(self.status().reason)


class DisabledSpeech:
    def status(self) -> ProviderStatus:
        if os.environ.get("STUDIO_VOICE", "").strip().lower() == "off":
            return ProviderStatus(
                "speech",
                False,
                None,
                "Voice is switched off in this environment (STUDIO_VOICE=off). Use the text box.",
                _present("DEEPGRAM_API_KEY"),
            )
        return ProviderStatus(
            "speech",
            False,
            None,
            "Voice is unavailable: no speech provider is configured (DEEPGRAM_API_KEY). Use the text box.",
            False,
        )

    def transcribe(self, scope: SessionScope | None, audio: bytes, mime: str) -> Transcript:
        raise ProviderDisabled(self.status().reason)

    def synthesize(self, scope: SessionScope | None, text: str) -> bytes:
        raise ProviderDisabled(self.status().reason)

    def cancel(self, scope: SessionScope | None) -> None:
        return None  # nothing is running


def get_assistant() -> AssistantProvider:
    """The older change-proposal contract (JSON-path operations). It stays disabled: the Studio conversation uses typed actions (studio_agent)."""
    return DisabledAssistant()


def get_speech() -> SpeechProvider:
    get_settings()  # loads backend/.env into the environment once
    return deepgram_from_environment() or DisabledSpeech()


def get_studio_llm():
    """The configured language model for the Studio conversation, or None when it is off or has no key."""
    if os.environ.get("STUDIO_ASSISTANT", "").strip().lower() == "off":
        return None
    try:
        from app.llm import create_studio_llm

        return create_studio_llm(get_settings())
    except ValueError:
        return None


def studio_assistant_status() -> ProviderStatus:
    get_settings()
    if os.environ.get("STUDIO_ASSISTANT", "").strip().lower() == "off":
        return ProviderStatus(
            "assistant",
            False,
            None,
            "The language model is switched off (STUDIO_ASSISTANT=off). Design Studio uses its built-in rules.",
            False,
        )
    llm = get_studio_llm()
    if llm is None:
        return ProviderStatus(
            "assistant",
            False,
            None,
            "No language model is configured. Design Studio uses its built-in rules, which understand fewer requests.",
            False,
        )
    return ProviderStatus(
        "assistant",
        True,
        f"{llm.name}",
        f"Conversation uses the {llm.name} language model ({getattr(llm, '_model', '')}). It proposes typed changes that are checked before anything is saved.",
        True,
    )


class SubmissionGuard:
    """Turns a transcript into an assistant request without ever executing it: refuses duplicates and unconfirmed high-impact text."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def accept(self, submission: TranscriptSubmission, high_impact: bool) -> bool:
        """True when the text may be sent to the assistant. A repeated submission id returns False (no second command)."""
        if submission.submission_id in self._seen:
            return False
        if high_impact and not submission.confirmed:
            raise PermissionError(
                "A high-impact change needs the user to confirm the displayed transcript"
            )
        self._seen.add(submission.submission_id)
        return True
