"""Speech recognition and spoken replies for Spark."""

import threading
import time
from collections import OrderedDict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.api.app_access import require_any_app
from app.core.config import get_settings
from app.speech.contracts import ProviderDisabled, SpeechProvider
from app.speech.providers import get_speech
from app.speech.deepgram import MAX_AUDIO_BYTES, SpeechUnavailable

_requests: OrderedDict[str, deque] = OrderedDict()
_lock = threading.Lock()


def limit_spark(request: Request):
    """Bound anonymous demo model/speech use without trusting forwarded IP headers."""
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _lock:
        bucket = _requests.setdefault(key, deque())
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= 20:
            raise HTTPException(429, detail={"code": "spark_rate_limit", "message": "Please wait a moment before asking again."})
        bucket.append(now)
        _requests.move_to_end(key)
        while len(_requests) > 1024:
            _requests.popitem(last=False)


router = APIRouter(prefix="/spark/voice", tags=["spark voice"], dependencies=[
    Depends(require_any_app("parts_intelligence", "agentic_shopping")), Depends(limit_spark),
])
Speech = Annotated[SpeechProvider, Depends(get_speech)]


@router.get("/status")
def status(speech: Speech):
    found = speech.status()
    # hands_free: a spoken message is sent and answered aloud through the same conversation as typing; dictate: speech only fills the box
    return {"enabled": found.enabled, "reason": "" if found.enabled else "Voice is unavailable in this environment. You can keep typing.",
            "mode": get_settings().spark_voice_mode}


@router.post("/transcribe")
async def transcribe(request: Request, speech: Speech):
    audio = bytearray()
    async for chunk in request.stream():
        audio.extend(chunk)
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(413, detail={"code": "audio_too_large", "message": "Keep recordings under a minute."})
    try:
        transcript = await run_in_threadpool(speech.transcribe, None, bytes(audio), request.headers.get("content-type", ""))
    except (ProviderDisabled, SpeechUnavailable):
        raise HTTPException(503, detail={"code": "voice_unavailable", "message": "Speech recognition is unavailable. You can keep typing."}) from None
    return transcript


class SpeakRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=1500)


@router.post("/speak")
async def speak(body: SpeakRequest, speech: Speech):
    try:
        audio = await run_in_threadpool(speech.synthesize, None, body.text)
    except (ProviderDisabled, SpeechUnavailable):
        raise HTTPException(503, detail={"code": "voice_unavailable", "message": "Spoken replies are unavailable. The answer is available as text."}) from None
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
