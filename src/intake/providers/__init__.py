"""Provider selection via the LLM_PROVIDER environment variable (offline | groq | recorded)."""

from __future__ import annotations

import os

from .base import LLMProvider


def get_provider(name: str | None = None) -> LLMProvider:
    name = (name or os.getenv("LLM_PROVIDER") or "offline").strip().lower()
    if name == "offline":
        from .offline import OfflineProvider

        return OfflineProvider()
    if name == "groq":
        from .groq import GroqProvider

        return GroqProvider.from_env()
    if name == "recorded":
        from .recorded import RecordedProvider

        return RecordedProvider()
    raise ValueError(f"Unbekannter LLM_PROVIDER '{name}' (erlaubt: offline, groq, recorded)")


__all__ = ["LLMProvider", "get_provider"]
