import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.config import Settings
from app.services import llm
from app.services.llm_pool import ModelPool
from test_llm_cache import cache_db  # noqa: F401


async def test_database_probe_cache_survives_pool_restart_and_preserves_failures(cache_db, monkeypatch):
    settings = Settings(_env_file=None, gemini_api_key="test-key", gemini_model_pool="working,missing,busy")
    monkeypatch.setattr(llm, "get_settings", lambda: settings)

    async def generate(**kwargs):
        if kwargs["model"] == "missing":
            raise RuntimeError("404 missing")
        if kwargs["model"] == "busy":
            raise RuntimeError("429 requests per day exhausted")
        return SimpleNamespace(text="OK")

    generate = AsyncMock(side_effect=generate)
    monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))))
    first = await llm.initialize_pool()
    assert generate.await_count == 3
    llm._pool = None
    second = await llm.initialize_pool()
    assert first is not second and second.initialized
    assert generate.await_count == 3
    assert not second.states["missing"].enabled
    assert second.states["busy"].cooldown_until - time.monotonic() > 86000
    assert second.states["working"].total == 1
    assert len(second.states["working"].requests) == 1


async def test_failed_probe_is_reused_for_an_hour_and_expired_probe_is_refreshed():
    generate = AsyncMock(side_effect=RuntimeError("404 missing"))
    client = lambda: SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    first = ModelPool(["missing"], "embedding")
    save = AsyncMock()
    await first.probe(client, 1, save=save)
    saved = save.await_args.args[0]
    second = ModelPool(["missing"], "embedding")
    load = AsyncMock(return_value=saved)
    await second.probe(client, 1, load=load)
    await second.probe(client, 1, load=load)
    assert generate.await_count == 1 and not second.names()
    saved["probed_at"] -= 3601
    third = ModelPool(["missing"], "embedding")
    await third.probe(client, 1, load=load)
    assert generate.await_count == 2
