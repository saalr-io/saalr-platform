from saalr_core.rag.chat import (
    ChatProvider,
    ChatResult,
    OpenAIChatProvider,
    StubChatProvider,
    make_chat_provider,
)


async def test_stub_provider_returns_answer_and_token_counts():
    p = StubChatProvider()
    result = await p.complete("system instruction", "a user question here")
    assert isinstance(result, ChatResult)
    assert result.text and isinstance(result.prompt_tokens, int)
    assert result.completion_tokens > 0
    assert p.model_name == "stub-chat"


def test_make_chat_provider_none_without_key():
    class _S:
        openai_api_key = None
        chat_model = "gpt-4o-mini"
    assert make_chat_provider(_S()) is None


def test_make_chat_provider_openai_with_key():
    class _S:
        openai_api_key = "sk-test"
        chat_model = "gpt-4o-mini"
    p = make_chat_provider(_S())
    assert p is not None and isinstance(p, ChatProvider)
    assert isinstance(p, OpenAIChatProvider) and p.model_name == "gpt-4o-mini"
