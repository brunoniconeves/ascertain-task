from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


class OpenAIError(Exception):
    """Base error for OpenAI client failures (safe to map to 502)."""


class OpenAIUnavailableError(OpenAIError):
    """Raised when OpenAI is not configured (e.g., missing API key)."""


class OpenAIUpstreamError(OpenAIError):
    """Raised when OpenAI API fails or returns an unexpected response."""


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float


class OpenAIClient:
    """
    Minimal OpenAI API client focused on deterministic JSON output.

    Design notes:
    - No logging in this module (prompts/outputs may contain PHI).
    - Deterministic generation (temperature=0) and stateless requests.
    - Returns parsed JSON, validated by caller Pydantic schemas.
    """

    def __init__(self, *, config: OpenAIConfig):
        self._config = config

    async def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        url = f"{self._config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._config.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            # Ask the API to enforce JSON output (still validate defensively).
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise OpenAIUpstreamError("LLM request timed out") from exc
        except httpx.HTTPError as exc:
            raise OpenAIUpstreamError("LLM request failed") from exc

        if resp.status_code != 200:
            # Avoid leaking upstream details to callers; map to generic 502 at the edge.
            raise OpenAIUpstreamError("LLM service returned an error")

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except Exception as exc:  # noqa: BLE001
            raise OpenAIUpstreamError("LLM response was not valid JSON") from exc

        if not isinstance(parsed, dict):
            raise OpenAIUpstreamError("LLM response JSON must be an object")

        return parsed


