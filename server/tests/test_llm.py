from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import llm
from app.config import Settings
from app.services.llm_pool import ModelPool


@pytest.fixture
def models(monkeypatch):
    monkeypatch.setattr(llm, "_cooldown", {})
    settings = Settings(_env_file=None, gemini_model_pool="primary,fallback", gemini_call_timeout=0.03,
                        gemini_queue_timeout=0.1, embed_dim=3)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    pool = ModelPool(settings.model_pool, settings.gemini_embed_model)
    pool.initialized = True
    for state in pool.states.values():
        state.enabled = True
    monkeypatch.setattr(llm, "_pool", pool)
    models = SimpleNamespace(generate_content_stream=AsyncMock(), generate_content=AsyncMock(), embed_content=AsyncMock())
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
async def test_generation_timeout_falls_back_and_cancels_first_call(models):
    import asyncio
    cancelled = []

    async def generate(**kwargs):
        if kwargs["model"] == "primary":
            try:
                await asyncio.sleep(1)
            finally:
                cancelled.append(True)
        return "fallback answer"

    models.generate_content.side_effect = generate
    assert await llm.generate_content([], None) == "fallback answer"
    assert cancelled == [True]
    assert [call.kwargs["model"] for call in models.generate_content.await_args_list] == ["primary", "fallback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["open", "first_chunk"])
async def test_stream_timeout_before_first_chunk_falls_back(models, stage):
    import asyncio
    closed = []

    async def slow_chunks():
        try:
            await asyncio.sleep(1)
            yield "too late"
        finally:
            closed.append(True)

    async def open_stream(**kwargs):
        if kwargs["model"] == "primary":
            if stage == "open":
                await asyncio.sleep(1)
            return slow_chunks()
        return chunks("fallback")

    models.generate_content_stream.side_effect = open_stream
    assert [part async for part in llm.stream_content([], None)] == ["fallback"]
    if stage == "first_chunk":
        assert closed == [True]


@pytest.mark.asyncio
async def test_429_uses_provider_retry_delay(models):
    import time
    error = RuntimeError("429 RESOURCE_EXHAUSTED")
    error.response_json = {"error": {"details": [{"retryDelay": "2.5s"}]}}
    models.generate_content.side_effect = [error, "recovered"]
    assert await llm.generate_content([], None) == "recovered"
    remaining = llm.pool().states["primary"].cooldown_until - time.monotonic()
    assert 2 <= remaining <= 2.5


@pytest.mark.asyncio
async def test_stream_rejects_permanent_error_without_fallback(models):
    models.generate_content_stream.side_effect = RuntimeError("400 invalid request")
    with pytest.raises(RuntimeError, match="400"):
        _ = [value async for value in llm.stream_content([], None)]
    assert models.generate_content_stream.await_count == 1
