from __future__ import annotations

from dataclasses import replace

from saalr_core.rag.chat import ChatError, ChatProvider, ChatResult, OpenAIChatProvider


class AnthropicChatProvider:
    """Anthropic chat. `anthropic` is imported lazily, so importing this module needs no SDK."""

    name = "anthropic"

    def __init__(self, api_key: str, model_name: str = "claude-3-5-haiku-latest",
                 max_tokens: int = 1024) -> None:
        self._api_key = api_key
        self.model_name = model_name
        self._max_tokens = max_tokens
        self._client = None  # lazily built once

    async def complete(self, system: str, user: str) -> ChatResult:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ChatError("anthropic not installed (pip install anthropic)") from exc
        if self._client is None:
            self._client = AsyncAnthropic(api_key=self._api_key)
        try:
            resp = await self._client.messages.create(
                model=self.model_name, max_tokens=self._max_tokens,
                system=system, messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            # Keep the message generic so a provider response body never leaks (incl. the key).
            raise ChatError(f"anthropic chat failed ({type(exc).__name__})") from exc
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
        )
        usage = resp.usage
        return ChatResult(
            text,
            usage.input_tokens if usage else 0,
            usage.output_tokens if usage else 0,
        )


class ChatGateway:
    """Ordered fallback over chat providers. Implements the ChatProvider Protocol so it is a
    drop-in wherever a single provider is expected. Tries each provider in turn; on ChatError it
    falls to the next; the first success is returned stamped with the winning provider + model."""

    name = "gateway"

    def __init__(self, providers: list[ChatProvider]) -> None:
        if not providers:
            raise ValueError("ChatGateway requires at least one provider")
        self.providers = providers

    @property
    def model_name(self) -> str:
        return self.providers[0].model_name  # nominal/primary

    async def complete(self, system: str, user: str) -> ChatResult:
        errors: list[str] = []
        for p in self.providers:
            try:
                result = await p.complete(system, user)
            except ChatError as exc:
                errors.append(f"{getattr(p, 'name', '?')}: {exc}")
                continue
            return replace(result, provider=getattr(p, "name", None), model=p.model_name)
        raise ChatError("all providers exhausted: " + "; ".join(errors))


def make_chat_gateway(settings) -> ChatGateway | None:
    """Assemble [OpenAI, Anthropic] in order from whatever keys are configured, else None."""
    providers: list[ChatProvider] = []
    if settings.openai_api_key:
        providers.append(OpenAIChatProvider(settings.openai_api_key, settings.chat_model))
    if settings.anthropic_api_key:
        providers.append(AnthropicChatProvider(settings.anthropic_api_key, settings.anthropic_model))
    if not providers:
        return None
    return ChatGateway(providers)
