"""Read-only status of the assistant and voice providers, so the Studio can show an honest unavailable state."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import CurrentUser
from app.api.routes.design_studio import require_studio_identity
from app.assistant.contracts import SpeechProvider
from app.assistant.providers import get_speech, studio_assistant_status

router = APIRouter(
    prefix="/assistant", tags=["assistant"], dependencies=[Depends(require_studio_identity)]
)


@router.get("/status")
def status(_: CurrentUser, speech: Annotated[SpeechProvider, Depends(get_speech)]):
    def describe(item) -> dict:
        found = item.status() if hasattr(item, "status") else item
        return {
            "capability": found.capability,
            "enabled": found.enabled,
            "provider": found.provider,
            "reason": found.reason,
            "credential_present": found.credential_present,
        }

    return {
        "assistant": describe(studio_assistant_status()),
        "speech": describe(speech),
        "note": "Credentials are never returned; status only says whether one exists.",
    }
