"""OpenRouter API calls and model listing."""
from __future__ import annotations

from typing import Any

import httpx

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
REQUEST_TIMEOUT = 120  # seconds


class AIError(Exception):
    pass


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/roast-tool/roast",
        "X-Title": "roast - AI Code Reviewer",
        "Content-Type": "application/json",
    }


def chat(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    system: str,
) -> str:
    """Send a chat completion request and return the assistant message."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
    }

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers=_headers(api_key),
                json=payload,
            )
    except httpx.TimeoutException:
        raise AIError(
            f"Request timed out after {REQUEST_TIMEOUT}s. "
            "The model may be slow — try again or choose a faster model."
        )
    except httpx.NetworkError as e:
        raise AIError(f"Network error connecting to OpenRouter: {e}")

    if response.status_code == 401:
        raise AIError("Invalid API key. Run `roast config` to update it.")
    if response.status_code == 402:
        raise AIError("OpenRouter account has insufficient credits.")
    if response.status_code == 429:
        raise AIError("Rate limit hit. Wait a moment and try again.")
    if response.status_code >= 500:
        raise AIError(f"OpenRouter server error ({response.status_code}). Try again later.")
    if response.status_code != 200:
        try:
            detail = response.json().get("error", {}).get("message") or response.text[:400]
        except Exception:
            detail = response.text[:400]
        raise AIError(f"OpenRouter returned {response.status_code}: {detail}")

    try:
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        raise AIError(f"Unexpected response format from OpenRouter: {e}")


def list_models(api_key: str) -> list[dict[str, Any]]:
    """Fetch available models from OpenRouter."""
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{OPENROUTER_BASE}/models",
                headers=_headers(api_key),
            )
    except httpx.TimeoutException:
        raise AIError("Timed out fetching model list.")
    except httpx.NetworkError as e:
        raise AIError(f"Network error: {e}")

    if response.status_code == 401:
        raise AIError("Invalid API key. Run `roast config` to update it.")
    if response.status_code != 200:
        raise AIError(f"Failed to fetch models ({response.status_code}).")

    try:
        return response.json().get("data", [])
    except ValueError:
        raise AIError("Invalid JSON in model list response.")
