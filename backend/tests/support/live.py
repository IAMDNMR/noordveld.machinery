"""Opt-in live language-model tests. They spend real provider quota, so they run only with RUN_LLM_LIVE_TESTS=true and a configured
provider key; the normal suite uses scripted or mocked models."""
from __future__ import annotations

import os

import pytest

from app.core.config import get_settings
from app.llm import LLMUnavailable, create_llm

ENABLED = os.environ.get("RUN_LLM_LIVE_TESTS", "").lower() == "true"
live = pytest.mark.skipif(not (ENABLED and get_settings().llm_configured), reason="live LLM tests are opt-in: set RUN_LLM_LIVE_TESTS=true with a provider key")


class Unworded:
    """The configured provider's real understanding call; its wording call is switched off so a live run stays small."""

    def __init__(self, model) -> None:
        self._model = model
        self.name = model.name

    def __getattr__(self, attr):
        return getattr(self._model, attr)

    def generate_grounded_response(self, *a, **k):
        raise LLMUnavailable("wording disabled in this test")


def live_model(worded: bool = False):
    model = create_llm(get_settings())
    return model if worded else Unworded(model)
