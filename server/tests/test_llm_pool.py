import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.llm_pool import ModelPool, QueueTimeout, cooldown_seconds, retry_delay


def ready_pool(names=None, rpm=1, window=0.04):
    pool = ModelPool(names or ["strong-a", "strong-b"], "embedding", rpm, window)
    for state in pool.states.values():
        state.enabled = True
    pool.initialized = True
    return pool


async def test_selection_balances_least_used_model_and_respects_classes():
    pool = ready_pool(["strong-a", "strong-b", "lite-a", "lite-b"], rpm=12)
    assert [await pool.acquire("strong") for _ in range(2)] == [("strong-a", 0), ("strong-b", 0)]
    assert [await pool.acquire("lite") for _ in range(2)] == [("lite-a", 0), ("lite-b", 0)]
    assert (await pool.acquire())[0] == "strong-a"


async def test_sliding_window_limits_concurrent_bursts_without_failing():
    pool = ready_pool()

    async def reserve():
        name, waited = await pool.acquire(timeout=0.5)
        return name, time.monotonic(), waited

    results = await asyncio.gather(*(reserve() for _ in range(8)))
    for name in pool.names():
        times = [when for model, when, _ in results if model == name]
        assert len(times) == 4
        assert all(right - left >= pool.window - 0.003 for left, right in zip(times, times[1:]))
    assert any(waited > 0 for _, _, waited in results)
    assert not pool.waiters


async def test_queue_timeout_does_not_consume_another_slot():
    pool = ready_pool(["one"], window=1)
    await pool.acquire()
    with pytest.raises(QueueTimeout):
        await pool.acquire(timeout=0.01)
    assert pool.states["one"].total == 1
    assert not pool.waiters


async def test_cancelled_waiter_does_not_block_other_callers():
    pool = ready_pool(["one"])
    await pool.acquire()
    cancelled = asyncio.create_task(pool.acquire(timeout=1))
    await asyncio.sleep(0)
    next_call = asyncio.create_task(pool.acquire(timeout=1))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert (await next_call)[0] == "one"
    assert not pool.waiters


async def test_embedding_capacity_does_not_block_generation_queue():
    pool = ready_pool(window=1)
    await pool.acquire(names=["embedding"])
    embedding = asyncio.create_task(pool.acquire(names=["embedding"], timeout=1))
    await asyncio.sleep(0)
    assert (await pool.acquire(timeout=0.01))[0] == "strong-a"
    embedding.cancel()
    with pytest.raises(asyncio.CancelledError):
        await embedding


async def test_probe_keeps_only_answering_models_and_runs_once():
    pool = ModelPool(["working", "missing", "slow", "empty"], "embedding")

    async def generate(**kwargs):
        name = kwargs["model"]
        if name == "missing":
            raise RuntimeError("404 missing")
        if name == "slow":
            await asyncio.sleep(1)
        return SimpleNamespace(text="OK" if name == "working" else "")

    generate = AsyncMock(side_effect=generate)
    client = lambda: SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    await asyncio.gather(pool.probe(client, 0.01), pool.probe(client, 0.01))
    assert pool.names() == ["working", "slow"]  # slow stays, just cooling down
    assert generate.await_count == 4
    assert all(state.total == 1 for state in pool.states.values() if state.kind == "generation")
    health = await pool.snapshot()
    assert health["ready"] and health["initialized"]
    assert next(model for model in health["models"] if model["model"] == "slow")["status"] == "probe_timeout"


@pytest.mark.parametrize("delay,expected", [("3.5s", 3.5), ({"seconds": "2", "nanos": 500000000}, 2.5)])
def test_structured_retry_delay(delay, expected):
    error = RuntimeError("429 quota")
    error.response_json = {"error": {"details": [{"retryDelay": delay}]}}
    assert retry_delay(error) == expected
    assert cooldown_seconds(error) == expected


def test_daily_cap_is_not_retried_each_minute():
    error = RuntimeError("429 GenerateRequestsPerDay exhausted")
    assert cooldown_seconds(error) >= 86400
    error.details = {"error": {"details": [{"retryDelay": "30s"}]}}
    assert cooldown_seconds(error) == 30


async def test_legacy_model_argument_still_balances_load_within_class():
    pool = ready_pool(["strong-a", "strong-b", "lite-a"], rpm=12)
    assert (await pool.acquire("strong-a"))[0] == "strong-a"
    assert (await pool.acquire("strong-a"))[0] == "strong-b"


async def test_per_model_rpm_overrides_have_independent_limits():
    pool = ModelPool(["small", "large"], "embedding", limits={"small": 1, "large": 2})
    for state in pool.states.values():
        state.enabled = True
    assert (await pool.acquire("small"))[0] == "small"
    assert (await pool.acquire())[0] == "large"
    assert (await pool.acquire())[0] == "large"
    with pytest.raises(QueueTimeout):
        await pool.acquire(timeout=0.01)
    health = await pool.snapshot()
    assert {row["model"]: row["rpm_limit"] for row in health["models"]} == {
        "small": 1, "large": 2, "embedding": 12,
    }


async def test_best_first_uses_pool_order_and_named_model():
    pool = ModelPool(["best", "ok", "small-lite"], "embedding", best_first=True)
    for state in pool.states.values():
        state.enabled = True
    assert [(await pool.acquire())[0] for _ in range(3)] == ["best"] * 3
    assert (await pool.acquire("ok"))[0] == "ok"
    assert (await pool.acquire("lite"))[0] == "small-lite"
