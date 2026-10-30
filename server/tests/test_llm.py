from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import llm


@pytest.fixture
def models(monkeypatch):
    monkeypatch.setattr(llm, "_cooldown", {})
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(
        gemini_model="primary", fallback_models=["fallback"],
    ))
    models = SimpleNamespace(generate_content_stream=AsyncMock(), generate_content=AsyncMock())
    monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))
    return models


async def chunks(*values):
    for value in values:
        if isinstance(value, Exception):
            raise value
        yield value


@pytest.mark.asyncio
async def test_stream_falls_back_and_shares_cooldown(models):
    models.generate_content_stream.side_effect = [
        chunks(RuntimeError("503 UNAVAILABLE")), chunks("answer"),
    ]
    assert [value async for value in llm.stream_content([], None)] == ["answer"]
    assert [call.kwargs["model"] for call in models.generate_content_stream.await_args_list] == [
        "primary", "fallback",
    ]
    assert llm._cooldown["primary"] > 0
    models.generate_content.return_value = "next response"
    assert await llm.generate_content([], None) == "next response"
    assert models.generate_content.await_args.kwargs["model"] == "fallback"


@pytest.mark.asyncio
async def test_stream_does_not_replay_after_output(models):
    models.generate_content_stream.return_value = chunks("first", RuntimeError("503 UNAVAILABLE"))
    received = []
    with pytest.raises(RuntimeError, match="503"):
        async for value in llm.stream_content([], None):
            received.append(value)
    assert received == ["first"]
    assert models.generate_content_stream.await_count == 1


@pytest.mark.asyncio
async def test_stream_rejects_permanent_error_without_fallback(models):
    models.generate_content_stream.side_effect = RuntimeError("400 invalid request")
    with pytest.raises(RuntimeError, match="400"):
        _ = [value async for value in llm.stream_content([], None)]
    assert models.generate_content_stream.await_count == 1
