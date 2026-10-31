import asyncio
import weakref
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents import explainer, intake, matcher
from app.models import LLMCache
from app.schemas import ExplainIn, ProfileData, SchemeDetail
from app.services import llm, llm_cache
from test_llm import models


@pytest.fixture
def cache_db(monkeypatch):
    engine = create_engine("sqlite://")
    LLMCache.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        class Adapter:
            async def scalar(self, query):
                return session.scalar(query)

            async def execute(self, query):
                return session.execute(query)

            async def commit(self):
                session.commit()

        @asynccontextmanager
        async def factory():
            yield Adapter()

        monkeypatch.setattr(llm_cache, "SessionLocal", factory)
        monkeypatch.setattr(llm_cache, "_locks", weakref.WeakValueDictionary())
        monkeypatch.setattr(llm_cache, "stats", dict(hits=0, misses=0, writes=0, errors=0))
        monkeypatch.setattr(llm, "_embedding_inflight", {})
        yield session
    engine.dispose()


async def test_cache_is_persistent_single_flight_and_expires(cache_db):
    factory = AsyncMock(return_value={"answer": "source-grounded output"})
    parts = {"profile": {"state": "Bihar"}, "slug": "scheme"}
    values = await asyncio.gather(*(llm.cached("test", parts, factory) for _ in range(8)))
    assert values == [{"answer": "source-grounded output"}] * 8
    assert factory.await_count == 1
    key = llm_cache.cache_key("test", parts)
    row = cache_db.get(LLMCache, key)
    assert len(row.key) == 64 and "Bihar" not in row.key
    assert row.value == values[0]
    row.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    cache_db.commit()
    await llm.cached("test", parts, factory)
    assert factory.await_count == 2
    refreshed = cache_db.scalar(select(LLMCache.created_at)).replace(tzinfo=timezone.utc)
    assert refreshed > datetime.now(timezone.utc) - timedelta(minutes=1)


async def test_empty_answers_hit_cache_but_errors_are_not_cached(cache_db):
    empty = AsyncMock(return_value="")
    assert await llm.cached("empty", [], empty) == ""
    assert await llm.cached("empty", [], empty) == ""
    assert empty.await_count == 1
    broken = AsyncMock(side_effect=RuntimeError("upstream error"))
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await llm.cached("broken", [], broken)
    assert broken.await_count == 2
    assert cache_db.get(LLMCache, llm_cache.cache_key("broken", [])) is None


async def test_judge_cache_separates_profiles_and_updated_sources(cache_db, monkeypatch):
    judgement = matcher._Judgement(
        verdict="eligible", confidence=0.9,
        reasons=[matcher._Reason(claim="Student", met=True, quote="The applicant must be a student.", section="eligibility")],
        missing_info=[], documents_needed=[],
    )
    generate = AsyncMock(return_value=judgement)
    monkeypatch.setattr(llm, "generate_json", generate)
    scheme = SchemeDetail(id="test", slug="test", name="Source", source_url="https://example.gov.in/test",
                          eligibility_md="The applicant must be a student.")
    profile = ProfileData(is_student=True)
    first = await matcher.judge(profile, scheme)
    assert await matcher.judge(profile, scheme) == first
    assert generate.await_count == 1 and first.reasons[0].citation.quote in scheme.eligibility_md
    await matcher.judge(profile.model_copy(update={"state": "Bihar"}), scheme)
    await matcher.judge(profile, scheme.model_copy(update={"eligibility_md": scheme.eligibility_md + " New criterion."}))
    assert generate.await_count == 3


async def test_explainer_cache_uses_source_language_and_profile(cache_db, monkeypatch):
    load = AsyncMock(return_value=("Title", "Exact source words.", "https://example.gov.in/test"))
    monkeypatch.setattr(explainer, "_load_source", load)
    generate = AsyncMock(return_value=explainer._Explained(
        title="Title", summary="Summary", key_points=["Point"], your_rights=[], what_it_means_for_you="",
        deadlines=[], documents_needed=[], evidence=[explainer._Evidence(quote="Exact source words.", supports="Point")],
    ))
    monkeypatch.setattr(llm, "generate_json", generate)
    body = ExplainIn(source={"type": "scheme", "slug": "test"}, language="en", with_audio=False)
    first = await explainer.explain(body, None)
    assert await explainer.explain(body, None) == first
    assert generate.await_count == 1
    await explainer.explain(body.model_copy(update={"language": "hi"}), None)
    await explainer.explain(body, ProfileData(state="Bihar"))
    load.return_value = ("Title", "Updated source words.", "https://example.gov.in/test")
    updated = await explainer.explain(body, None)
    assert not updated.citations  # cached old evidence cannot leak into a changed source
    assert generate.await_count == 4


async def test_intake_question_cache_is_per_profile_and_language(cache_db, monkeypatch):
    generate = AsyncMock(return_value="Which state do you live in?")
    monkeypatch.setattr(llm, "generate", generate)
    assert await intake.follow_up(ProfileData(), "en") == "Which state do you live in?"
    await intake.follow_up(ProfileData(), "en")
    assert generate.await_count == 1
    await intake.follow_up(ProfileData(state="Bihar"), "en")
    await intake.follow_up(ProfileData(), "hi")
    assert generate.await_count == 3


async def test_embedding_cache_deduplicates_and_separates_tasks(cache_db, models):
    async def embed(**kwargs):
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0, 2.0, 3.0]) for text in kwargs["contents"]])

    models.embed_content.side_effect = embed
    first = await llm.embed(["same", "same", "other"])
    assert len(first) == 3 and first[0] == first[1]
    assert models.embed_content.await_count == 1
    assert models.embed_content.await_args.kwargs["contents"] == ["same", "other"]
    assert await llm.embed(["other", "same"]) == [first[2], first[0]]
    assert models.embed_content.await_count == 1
    await llm.embed_query("same")
    assert models.embed_content.await_count == 2


async def test_concurrent_embeddings_run_in_parallel_and_share_duplicates(cache_db, models, monkeypatch):
    monkeypatch.setattr(llm.get_settings(), "gemini_call_timeout", 1)
    active = peak = 0

    async def embed(**kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0, 2.0, 3.0]) for text in kwargs["contents"]])

    models.embed_content.side_effect = embed
    results = await asyncio.gather(*(llm.embed([text]) for text in ["a", "b", "c", "a"]))
    assert peak == 3
    assert models.embed_content.await_count == 3
    assert results[0] == results[3]
    assert not llm._embedding_inflight


async def test_health_reports_usage_and_cache_without_credentials(cache_db, models):
    import httpx
    from app.main import app

    await llm.generate_content([], None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health/llm")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] and "cache" in data
    assert next(model for model in data["models"] if model["model"] == "primary")["used_last_minute"] == 1
    assert "api_key" not in response.text and "profile" not in response.text
