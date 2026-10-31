import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.agents import matcher
from app.routers import assist
from app.schemas import MatchResult, ProfileData, SchemeDetail
from app.services import myscheme

pytestmark = pytest.mark.asyncio


def scheme(slug):
    return SchemeDetail(slug=slug, id=slug, name=slug, eligibility_md="Students may apply.",
                        source_url="https://example.gov.in")


def result(slug, verdict="likely", confidence=0.9):
    return MatchResult(scheme=scheme(slug), verdict=verdict, confidence=confidence, reasons=[])


async def test_stream_emits_before_slow_judge_and_matches_legacy_sort_and_limit(monkeypatch):
    cands = [scheme(s) for s in ["slow", "fast", "tie", "skip", "empty", "broken"]]
    cands[4].eligibility_md = ""
    release = asyncio.Event()
    monkeypatch.setattr(matcher, "candidates", AsyncMock(return_value=cands))
    monkeypatch.setattr(myscheme, "get_scheme", AsyncMock(side_effect=lambda slug, **kw: next(s for s in cands if s.slug == slug)))
    monkeypatch.setattr(matcher, "triage", AsyncMock(side_effect=lambda p, s: s.slug != "skip"))

    async def judge(p, s):
        if s.slug == "slow":
            await release.wait()
        if s.slug == "broken":
            raise RuntimeError("unavailable")
        return result(s.slug, "eligible" if s.slug == "fast" else "likely")

    monkeypatch.setattr(matcher, "judge", judge)
    events = matcher.match_stream(ProfileData(), limit=2)
    assert (await anext(events))["message"] == "found 6 schemes"
    first = await asyncio.wait_for(anext(events), 1)
    assert first["type"] == "result" and first["result"]["scheme"]["slug"] == "fast"
    assert not release.is_set()
    release.set()
    rest = [event async for event in events]
    assert [e["checked"] for e in rest if e["type"] == "progress"] == list(range(1, 7))
    final = rest[-1]
    legacy = await matcher.match(ProfileData(), limit=2)
    assert final == {"type": "done", "results": [r.model_dump(mode="json") for r in legacy]}
    assert [r["scheme"]["slug"] for r in final["results"]] == ["fast", "slow"]


async def test_closing_stream_cancels_remaining_checks(monkeypatch):
    started, cancelled = asyncio.Event(), asyncio.Event()
    cands = [scheme("fast"), scheme("slow")]
    monkeypatch.setattr(matcher, "candidates", AsyncMock(return_value=cands))
    monkeypatch.setattr(myscheme, "get_scheme", AsyncMock(side_effect=lambda slug, **kw: next(s for s in cands if s.slug == slug)))
    monkeypatch.setattr(myscheme, "index_schemes", AsyncMock())

    async def check(p, s, sem):
        if s.slug == "fast":
            await started.wait()
            return result("fast")
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(matcher, "_judge_one", check)
    events = matcher.match_stream(ProfileData())
    await anext(events)
    assert (await anext(events))["type"] == "result"
    await events.aclose()
    assert cancelled.is_set()


async def test_empty_stream(monkeypatch):
    monkeypatch.setattr(matcher, "candidates", AsyncMock(return_value=[]))
    assert [e async for e in matcher.match_stream(ProfileData())] == [
        {"type": "progress", "message": "found 0 schemes", "checked": 0, "total": 0},
        {"type": "done", "results": []},
    ]


async def test_routes_keep_json_contract_and_stream_events_and_validate_profile(monkeypatch):
    db = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(data={"age": 21})))
    app = FastAPI()
    app.include_router(assist.router, prefix="/api")
    app.dependency_overrides[assist.get_db] = lambda: db
    found = result("scholarship").model_dump(mode="json")
    legacy = AsyncMock(return_value=[result("scholarship")])
    monkeypatch.setattr(matcher, "match", legacy)

    async def stream(p, keyword, limit):
        assert p.age == 21 and keyword == "student" and limit == 2
        yield {"type": "progress", "message": "found 1 schemes", "checked": 0, "total": 1}
        yield {"type": "result", "result": found}
        yield {"type": "progress", "message": "checked 1/1", "checked": 1, "total": 1}
        yield {"type": "done", "results": [found]}

    monkeypatch.setattr(matcher, "match_stream", stream)
    body = {"profile_id": "citizen", "keyword": "student", "limit": 2}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        old = await client.post("/api/schemes/match", json=body)
        assert old.status_code == 200 and old.json() == [found]
        legacy.assert_awaited_once_with(ProfileData(age=21), "student", 2)
        response = await client.post("/api/schemes/match/stream", json=body)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no"
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert [e["type"] for e in events] == ["progress", "result", "progress", "done"]
        assert events[-1]["results"] == [found]
        db.get.return_value = None
        for path in ["/api/schemes/match", "/api/schemes/match/stream"]:
            assert (await client.post(path, json=body)).status_code == 404
            assert (await client.post(path, json={})).status_code == 422


async def test_stream_reports_safe_failure_and_closes_generator(monkeypatch):
    closed = asyncio.Event()

    async def broken(*args):
        try:
            yield {"type": "progress", "message": "found 1 schemes"}
            raise RuntimeError("private provider credential")
        finally:
            closed.set()

    monkeypatch.setattr(matcher, "match_stream", broken)
    frames = [frame async for frame in assist.match_events(ProfileData(), None, 8)]
    assert frames[0].startswith(": keepalive")
    error = json.loads(frames[-1][6:])
    assert error["type"] == "error" and "private" not in error["message"]
    assert closed.is_set()


async def test_disconnecting_route_closes_pending_generator(monkeypatch):
    started, closed = asyncio.Event(), asyncio.Event()

    async def waiting(*args):
        try:
            started.set()
            await asyncio.Event().wait()
            yield {}
        finally:
            closed.set()

    monkeypatch.setattr(matcher, "match_stream", waiting)
    frames = assist.match_events(ProfileData(), None, 8)
    await anext(frames)
    pending = asyncio.create_task(anext(frames))
    await started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert closed.is_set()


async def test_keepalives_continue_while_candidate_discovery_is_pending(monkeypatch):
    closed = asyncio.Event()

    async def waiting(*args):
        try:
            await asyncio.Event().wait()
            yield {}
        finally:
            closed.set()

    monkeypatch.setattr(matcher, "match_stream", waiting)
    monkeypatch.setattr(assist, "MATCH_KEEPALIVE_SECONDS", 0.01)
    frames = assist.match_events(ProfileData(), None, 8)
    assert await anext(frames) == ": keepalive\n\n"
    assert await asyncio.wait_for(anext(frames), 1) == ": keepalive\n\n"
    await frames.aclose()
    assert closed.is_set()
