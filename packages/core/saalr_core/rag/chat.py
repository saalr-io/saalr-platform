from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ChatError(Exception):
    """Wraps an LLM chat provider/transport failure (never carries the API key)."""


@dataclass(frozen=True)
class ChatResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    provider: str | None = None
    model: str | None = None


@runtime_checkable
class ChatProvider(Protocol):
    model_name: str
    name: str

    async def complete(self, system: str, user: str) -> ChatResult:
        """Single-shot completion from a system + user message."""
        ...


class StubChatProvider:
    """Deterministic, network-free chat provider for tests. Returns a fixed grounded sentence
    and word-count-based token figures so the pipeline (retrieve -> prompt -> answer -> citations)
    can be tested with no API key."""

    name = "stub"
    model_name = "stub-chat"

    async def complete(self, system: str, user: str) -> ChatResult:
        return ChatResult(
            "Based on the OptionsAcademy materials, here is the answer.",
            prompt_tokens=len((system + " " + user).split()),
            completion_tokens=8,
        )


class OpenAIChatProvider:
    """OpenAI chat completion. `openai` is imported lazily, so importing this module needs no SDK."""

    name = "openai"

    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini") -> None:
        self._api_key = api_key
        self.model_name = model_name
        self._client = None  # lazily built once (reuses the SDK's connection pool)

    async def complete(self, system: str, user: str) -> ChatResult:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ChatError("openai not installed (pip install openai)") from exc
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self._api_key)
        try:
            resp = await self._client.chat.completions.create(
                model=self.model_name, temperature=0,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
        except Exception as exc:
            # Keep the message generic so a provider response body never leaks (incl. the key).
            raise ChatError(f"openai chat failed ({type(exc).__name__})") from exc
        usage = resp.usage
        return ChatResult(
            resp.choices[0].message.content or "",
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )


def make_chat_provider(settings) -> ChatProvider | None:
    """OpenAI chat provider if a key is configured, else None (the assistant returns 503)."""
    if settings.openai_api_key:
        return OpenAIChatProvider(settings.openai_api_key, settings.chat_model)
    return None
