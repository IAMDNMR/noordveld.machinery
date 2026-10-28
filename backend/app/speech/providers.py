"""Configured speech for Spark; credentials are never returned."""
from app.speech.contracts import ProviderDisabled, ProviderStatus
from app.speech.deepgram import deepgram_from_environment
from app.core.config import get_settings

class DisabledSpeech:
    def status(self):
        return ProviderStatus("speech", False, None, "Voice is unavailable. You can keep typing.", False)
    def transcribe(self, scope, audio, mime):
        raise ProviderDisabled(self.status().reason)
    def synthesize(self, scope, text):
        raise ProviderDisabled(self.status().reason)
    def cancel(self, scope):
        return None

def get_speech():
    get_settings()
    return deepgram_from_environment() or DisabledSpeech()
