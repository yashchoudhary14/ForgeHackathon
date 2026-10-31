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


async def test_probe_cache_separates_vertex_projects_locations_and_backends(cache_db, monkeypatch):
    generate = AsyncMock(return_value=SimpleNamespace(text="OK"))
    monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))))
    configurations = [
        dict(gemini_backend="vertex", gcp_project="project-a", gcp_location="global"),
        dict(gemini_backend="vertex", gcp_project="project-b", gcp_location="global"),
        dict(gemini_backend="vertex", gcp_project="project-a", gcp_location="asia-south1"),
        dict(gemini_backend="aistudio", gemini_api_key="test-key"),
        dict(gemini_backend="vertex", gcp_project="project-a", vertex_api_key="vertex-key"),
    ]
    for expected, configuration in enumerate(configurations, 1):
        settings = Settings(_env_file=None, gemini_model_pool="working", **configuration)
        monkeypatch.setattr(llm, "get_settings", lambda: settings)
        llm._pool = None
        await llm.initialize_pool()
        llm._pool = None
        restored = await llm.initialize_pool()
        assert generate.await_count == expected
        assert restored.initialized
        assert restored.best_first == (settings.gemini_backend == "vertex")
