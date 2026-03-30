"""Minimal Anthropic Messages API adapter."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel

from pm_agent.config.models import AnthropicConfig


class AnthropicAdapterError(RuntimeError):
    """Raised when Anthropic requests fail or return invalid content."""


def _extract_json_payload(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    for opener, closer in (("{", "}"), ("[", "]")):
        start = stripped.find(opener)
        end = stripped.rfind(closer)
        if start != -1 and end != -1 and end > start:
            return stripped[start : end + 1]

    raise AnthropicAdapterError("Anthropic response did not contain JSON")


class AnthropicMessagesClient:
    def __init__(
        self,
        *,
        config: AnthropicConfig,
        api_key: str | None = None,
        user_agent: str = "auto-pm/0.1.0",
    ) -> None:
        self._config = config
        self._api_key = api_key or os.getenv(config.api_key_env)
        self._user_agent = user_agent

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def create_message(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        if not self._api_key:
            raise AnthropicAdapterError(
                f"{self._config.api_key_env} is required for Anthropic-backed synthesis"
            )

        payload = {
            "model": self._config.model,
            "max_tokens": max_tokens or self._config.max_tokens,
            "temperature": self._config.temperature if temperature is None else temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        request = Request(
            f"{self._config.api_base_url.rstrip('/')}/v1/messages",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "user-agent": self._user_agent,
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise AnthropicAdapterError(f"Anthropic API error {exc.code}") from exc
        except URLError as exc:
            raise AnthropicAdapterError(f"Anthropic API request failed: {exc.reason}") from exc

        content = body.get("content", [])
        texts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if not texts:
            raise AnthropicAdapterError("Anthropic response did not include text content")
        return "\n".join(texts).strip()

    def create_json_message(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        max_tokens: int | None = None,
    ) -> BaseModel:
        response_text = self.create_message(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
        )
        payload_text = _extract_json_payload(response_text)
        payload: Any = json.loads(payload_text)
        return response_model.model_validate(payload)
