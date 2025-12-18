from __future__ import annotations

from app.core.llm.openai_client import OpenAIClient, OpenAIConfig
from app.core.settings import get_settings


def get_openai_client() -> OpenAIClient | None:
    """
    Dependency provider for OpenAIClient.

    Returns None when not configured so routes can return a safe 502 without
    raising during dependency resolution.
    """

    settings = get_settings()
    if not settings.openai_api_key:
        return None

    config = OpenAIConfig(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        timeout_seconds=float(settings.openai_timeout_seconds),
    )
    return OpenAIClient(config=config)


