"""Deepgram speech provider: speech-to-text (Nova) and text-to-speech (Aura) over HTTPS.

The API key is read from the environment, sent only in the Authorization header to api.deepgram.com, and never logged, returned
or included in an error. Audio is processed in memory and discarded (`RETAIN_AUDIO` is False): nothing is written to disk and
nothing is stored. Every upstream failure becomes `SpeechUnavailable` with a message that is safe to show.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

from app.assistant.contracts import ProviderDisabled, ProviderStatus, SessionScope, Transcript

log = logging.getLogger("app.assistant.speech")
LISTEN = "https://api.deepgram.com/v1/listen"
SPEAK = "https://api.deepgram.com/v1/speak"
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_SPEECH_CHARS = 1500
AUDIO_TYPES = frozenset(
    {
        "audio/webm",
        "audio/ogg",
        "audio/wav",
        "audio/x-wav",
        "audio/mp4",
        "audio/mpeg",
        "audio/flac",
        "audio/aac",
    }
)


class SpeechUnavailable(RuntimeError):
    """The provider is enabled but this request failed (network, quota, unusable audio). The message never contains the key."""


class DeepgramSpeech:
    def __init__(
        self,
        api_key: str,
        http: httpx.Client | None = None,
        *,
        stt_model: str = "nova-3",
        tts_model: str = "aura-2-thalia-en",
        language: str = "en",
    ) -> None:
        self._key = api_key
        self._http = http or httpx.Client(timeout=30.0)
        self._stt, self._tts, self._language = stt_model, tts_model, language

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            "speech",
            True,
            "deepgram",
            f"Voice uses Deepgram ({self._stt} speech-to-text, {self._tts} voice). Audio is not stored.",
            True,
        )

    def _call(self, kind: str, url: str, **kwargs) -> httpx.Response:
        started = time.perf_counter()
        try:
            response = self._http.post(
                url,
                headers={**kwargs.pop("headers", {}), "Authorization": f"Token {self._key}"},
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            log.warning("speech call kind=%s outcome=timeout", kind)
            raise SpeechUnavailable(
                "The speech service timed out. Try again, or type instead."
            ) from exc
        except httpx.HTTPError as exc:
            log.warning("speech call kind=%s outcome=connection:%s", kind, type(exc).__name__)
            raise SpeechUnavailable(
                "The speech service could not be reached. Type instead."
            ) from exc
        outcome = "ok" if response.status_code == 200 else f"http_{response.status_code}"
        log.info(
            "speech call kind=%s latency_ms=%d outcome=%s",
            kind,
            (time.perf_counter() - started) * 1000,
            outcome,
        )
        if response.status_code in (401, 403):
            raise SpeechUnavailable(
                "The speech service rejected its credentials. Voice is unavailable; type instead."
            )
        if response.status_code == 402 or response.status_code == 429:
            raise SpeechUnavailable(
                "The speech service quota is used up. Voice is unavailable for now; type instead."
            )
        if response.status_code != 200:
            raise SpeechUnavailable(
                "The speech service could not process that. Try again, or type instead."
            )
        return response

    def transcribe(self, scope: SessionScope | None, audio: bytes, mime: str) -> Transcript:
        mime = mime.split(";")[0].strip().lower()
        if mime not in AUDIO_TYPES:
            raise SpeechUnavailable("That audio format is not supported.")
        if not audio:
            raise SpeechUnavailable("No audio was received.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise SpeechUnavailable("That recording is too long. Keep it under about a minute.")
        response = self._call(
            "transcribe",
            LISTEN,
            params={
                "model": self._stt,
                "smart_format": "true",
                "punctuate": "true",
                "language": self._language,
            },
            headers={"Content-Type": mime},
            content=audio,
        )
        try:
            alternative = response.json()["results"]["channels"][0]["alternatives"][0]
            text = str(alternative.get("transcript", "")).strip()
            confidence = alternative.get("confidence")
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise SpeechUnavailable("The speech service returned something unreadable.") from exc
        if not text:
            raise SpeechUnavailable("I could not hear any speech in that recording.")
        return Transcript(
            text=text[:4000],
            confidence=float(confidence)
            if isinstance(confidence, (int, float)) and 0 <= confidence <= 1
            else None,
            language=self._language,
        )

    def synthesize(self, scope: SessionScope | None, text: str) -> bytes:
        text = " ".join(text.split())[:MAX_SPEECH_CHARS]
        if not text:
            raise SpeechUnavailable("There is nothing to speak.")
        response = self._call(
            "synthesize", SPEAK, params={"model": self._tts, "encoding": "mp3"}, json={"text": text}
        )
        if not response.content:
            raise SpeechUnavailable("The speech service returned no audio.")
        return response.content

    def cancel(self, scope: SessionScope | None) -> None:
        return None  # each request is a single stateless call; playback is stopped by the browser


def deepgram_from_environment() -> DeepgramSpeech | None:
    """The provider when a key is present and `STUDIO_VOICE` is not `off`; otherwise None (the caller reports an honest disabled state)."""
    key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not key or os.environ.get("STUDIO_VOICE", "").strip().lower() == "off":
        return None
    return DeepgramSpeech(
        key,
        stt_model=os.environ.get("STUDIO_STT_MODEL", "nova-3"),
        tts_model=os.environ.get("STUDIO_TTS_MODEL", "aura-2-thalia-en"),
        language=os.environ.get("STUDIO_VOICE_LANGUAGE", "en"),
    )


__all__ = ["DeepgramSpeech", "SpeechUnavailable", "deepgram_from_environment", "ProviderDisabled"]
