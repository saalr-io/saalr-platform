import pytest

from saalr_core.llm.gateway import ChatGateway
from saalr_core.rag.chat import ChatError, StubChatProvider


class _Fail:
    name = "fail"
    model_name = "fail-model"

    async def complete(self, system, user):
        raise ChatError("down")


async def test_single_provider_stamps_provider_and_model():
    g = ChatGateway([StubChatProvider()])
    r = await g.complete("sys", "user")
    assert r.provider == "stub" and r.model == "stub-chat"
    assert r.text


async def test_falls_through_to_next_on_chat_error():
    g = ChatGateway([_Fail(), StubChatProvider()])
    r = await g.complete("sys", "user")
    assert r.provider == "stub"  # the stub won after the first failed


async def test_all_providers_exhausted_raises():
    g = ChatGateway([_Fail(), _Fail()])
    with pytest.raises(ChatError):
        await g.complete("sys", "user")


def test_empty_gateway_rejected():
    with pytest.raises(ValueError):
        ChatGateway([])
