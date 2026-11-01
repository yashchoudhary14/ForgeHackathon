"""Offline lifecycle checks: no browser launch, database, or model calls."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI, WebSocketDisconnect

from app.agents import executor
from app.db import get_db
from app.models import AgentRun
from app.routers import agent


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(now=0)
    monkeypatch.setattr(executor, "time", SimpleNamespace(monotonic=lambda: clock.now))
    return clock


class TickingInbox:
    """Advance a fake second for each inbox poll, without sleeping."""
    def __init__(self, clock, on_tick=lambda: None):
        self.clock, self.on_tick = clock, on_tick

    async def get(self):
        self.clock.now += 1
        self.on_tick()
        raise TimeoutError


@pytest.fixture
def session_factory(monkeypatch):
    saved = {}
    db = MagicMock()
    db.get = AsyncMock(side_effect=lambda model, key: saved.get(key))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(executor, "SessionLocal", lambda: db)
    monkeypatch.setattr(executor, "notify", AsyncMock())

    def make(run_id="run-1", status="queued"):
        row = AgentRun(id=run_id, profile_id="owner", goal="Check eligibility",
                       portal_url="https://portal.gov.in", kind="application",
                       status=status, meta={})
        saved[run_id] = row
        rs = executor.RunSession(run_id, row.goal, row.portal_url, {}, {}, profile_id="owner")
        rs.status = status
        rs.browser = SimpleNamespace(start=AsyncMock(), goto=AsyncMock(), close=AsyncMock(), last_frame=None)
        rs.emit = AsyncMock()
        return rs, row

    return make, db


@pytest.mark.parametrize("kind", ["confirm_submit", "captcha", "otp"])
async def test_unwatched_human_wait_aborts_and_releases_slot(monkeypatch, clock, session_factory, kind):
    make, _ = session_factory
    rs, row = make()
    next_rs, _ = make("next")
    rs.inbox = TickingInbox(clock)

    async def graph_invoke(*args):
        await rs.wait_human({"type": "needs_human", "kind": kind}, {"approve", "resume"})

    monkeypatch.setattr(executor, "build_graph", lambda session: SimpleNamespace(ainvoke=graph_invoke))
    real_run = executor.run
    next_started = asyncio.Event()

    async def run(session):
        if session is rs:
            await real_run(session)
        else:
            next_started.set()

    monkeypatch.setattr(executor, "run", run)
    manager = executor.RunManager(max_parallel=1)
    manager.start(rs)
    manager.start(next_rs)
    await asyncio.wait_for(asyncio.gather(rs.task, next_rs.task), 5)

    assert clock.now == executor.UNWATCHED_TIMEOUT == 120
    assert row.status == rs.status == "aborted"
    assert row.error == "Stopped: nobody was watching"
    rs.emit.assert_any_await({"type": "error", "message": row.error})
    assert rs.pending is None and rs.human_wait_seconds == 120
    rs.browser.close.assert_awaited_once()
    assert next_started.is_set()


async def test_watched_human_wait_keeps_fifteen_minute_limit(clock, session_factory):
    make, _ = session_factory
    rs, _ = make()
    rs.subscribe(object())
    rs.inbox = TickingInbox(clock)
    with pytest.raises(TimeoutError, match="15 minutes"):
        await rs.wait_human({"kind": "otp"}, {"resume"})
    assert clock.now == executor.HUMAN_TIMEOUT == 900
    assert rs.pending is None


async def test_reload_resets_unwatched_grace_after_long_watched_wait(clock, session_factory):
    make, _ = session_factory
    rs, _ = make()
    ws, reloaded_ws = object(), object()
    rs.subscribe(ws)

    def tick():
        if clock.now == 200:
            rs.unsubscribe(ws)
        elif clock.now == 300:
            rs.subscribe(reloaded_ws)
        elif clock.now == 500:
            rs.unsubscribe(reloaded_ws)
            rs.unsubscribe(ws)  # A stale disconnect must not restart the clock.

    rs.inbox = TickingInbox(clock, tick)
    with pytest.raises(executor.RunAborted, match="nobody was watching"):
        await rs.wait_human({"kind": "confirm_submit"}, {"approve"})
    assert clock.now == 620


async def test_other_viewer_prevents_unwatched_abort(clock, session_factory):
    make, _ = session_factory
    rs, _ = make()
    ws = object()
    rs.subscribe(ws)
    rs.subscribe(object())
    rs.inbox = TickingInbox(clock, lambda: rs.unsubscribe(ws))
    with pytest.raises(TimeoutError, match="15 minutes"):
        await rs.wait_human({"kind": "captcha"}, {"resume"})
    assert clock.now == 900


async def test_already_unwatched_run_aborts_without_another_grace_period(clock, session_factory):
    make, _ = session_factory
    rs, _ = make()
    clock.now = 500
    rs.inbox = TickingInbox(clock)
    with pytest.raises(executor.RunAborted):
        await rs.wait_human({"kind": "otp"}, {"resume"})
    assert clock.now == 500


@pytest.fixture
async def api(session_factory, monkeypatch):
    make, db = session_factory
    manager = executor.RunManager()
    monkeypatch.setattr(agent, "manager", manager)
    app = FastAPI()
    app.include_router(agent.router, prefix="/api")

    async def dependency():
        yield db

    app.dependency_overrides[get_db] = dependency
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, manager, make, db


@pytest.mark.parametrize("owner,status", [(None, 401), ("other", 404)])
async def test_abort_endpoint_requires_owner(api, owner, status):
    client, manager, make, db = api
    rs, row = make()
    manager.sessions[rs.id] = rs
    response = await client.post("/api/agent/runs/run-1/abort", params={} if owner is None else {"profile_id": owner})
    assert response.status_code == status
    assert row.status == "queued"
    db.commit.assert_not_awaited()


async def test_abort_endpoint_missing_run(api):
    client, _, _, _ = api
    response = await client.post("/api/agent/runs/missing/abort", params={"profile_id": "owner"})
    assert response.status_code == 404


@pytest.mark.parametrize("phase", ["not_started", "queued", "driving", "waiting", "not_live"])
async def test_abort_endpoint_stops_every_live_phase(api, monkeypatch, phase):
    client, manager, make, _ = api
    rs, row = make()
    entered = asyncio.Event()

    async def graph_invoke(*args):
        entered.set()
        if phase == "waiting":
            await rs.wait_human({"kind": "confirm_submit"}, {"approve"})
        else:
            await asyncio.Event().wait()

    monkeypatch.setattr(executor, "build_graph", lambda session: SimpleNamespace(ainvoke=graph_invoke))
    if phase == "queued":
        manager.sem = asyncio.Semaphore(0)
    if phase != "not_live":
        manager.start(rs)
        if phase in ("driving", "waiting"):
            await asyncio.wait_for(entered.wait(), 5)
        elif phase == "queued":
            await asyncio.sleep(0)
    response = await client.post("/api/agent/runs/run-1/abort", headers={"X-Profile-ID": "owner"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == row.status == "aborted"
    assert row.error == "Run aborted by user"
    if rs.task:
        assert rs.task.done()
    assert rs.pending is None
    if phase in ("driving", "waiting"):
        rs.browser.close.assert_awaited_once()
    else:
        rs.browser.start.assert_not_awaited()


@pytest.mark.parametrize("status", ["done", "failed", "aborted"])
async def test_abort_endpoint_preserves_terminal_runs(api, status):
    client, _, make, db = api
    _, row = make(status=status)
    row.error = "original outcome"
    for _ in range(2):
        response = await client.post("/api/agent/runs/run-1/abort", params={"profile_id": "owner"})
        assert response.status_code == 200
        assert response.json()["status"] == status
        assert response.json()["error"] == "original outcome"
    db.commit.assert_not_awaited()


async def test_failed_ws_initial_replay_removes_subscriber(monkeypatch, session_factory, clock):
    make, db = session_factory
    rs, _ = make()
    manager = executor.RunManager()
    manager.sessions[rs.id] = rs
    monkeypatch.setattr(agent, "manager", manager)
    ws = MagicMock(accept=AsyncMock(), send_json=AsyncMock(side_effect=WebSocketDisconnect()))
    await agent.run_ws(ws, rs.id, "owner", db)
    assert not rs.subs


async def test_dead_subscriber_starts_grace_period(clock):
    rs = executor.RunSession("dead-ws", "", "https://portal.gov.in", {}, {})
    ws = MagicMock(send_json=AsyncMock(side_effect=RuntimeError("disconnected")))
    rs.subscribe(ws)
    clock.now = 300
    await rs.emit({"type": "status", "status": "needs_human"})
    assert not rs.subs and rs.last_subscriber_at == 300


async def test_default_manager_starts_three_runs(monkeypatch):
    manager = executor.RunManager()
    started = []
    release = asyncio.Event()

    async def run(rs):
        started.append(rs.id)
        await release.wait()

    monkeypatch.setattr(executor, "run", run)
    sessions = [executor.RunSession(str(i), "", "https://portal.gov.in", {}, {}) for i in range(4)]
    for rs in sessions:
        manager.start(rs)
    await asyncio.sleep(0)
    assert started == ["0", "1", "2"]
    release.set()
    await asyncio.gather(*(rs.task for rs in sessions))
    assert started == ["0", "1", "2", "3"]
