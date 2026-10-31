"""Offline persistence and API contracts. Only HTTP/Gemini are replaced."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import db, models
from app.db import get_db
from app.routers import activity, notifications
from app.schemas import FeedItem, SchemeDetail
from app.services import monitor
from app.services import notify as notify_service


@pytest.fixture
def alerts_db(monkeypatch):
    engine = create_engine("sqlite://")
    for table in (models.Profile, models.Scheme, models.AgentRun, models.Report, models.ReportVote,
                  models.Notification, models.MonitorItem, models.MonitorCheck):
        table.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        class Adapter:
            async def get(self, *args):
                return session.get(*args)

            async def scalar(self, query):
                return session.scalar(query)

            async def scalars(self, query):
                return session.scalars(query)

            async def execute(self, query):
                return session.execute(query)

            async def commit(self):
                session.commit()

        adapter = Adapter()

        @asynccontextmanager
        async def factory():
            yield adapter

        monkeypatch.setattr(db, "SessionLocal", factory)
        monkeypatch.setattr(notify_service, "SessionLocal", factory)
        monkeypatch.setattr(monitor, "_lock", asyncio.Lock())
        session.add_all([models.Profile(id="one", data={"state": "Bihar", "is_student": True},
                                        sensitive="must never be decrypted or sent"),
                         models.Profile(id="two", data={"occupation": "farmer"}),
                         models.Profile(id="empty", data={})])
        session.commit()
        app = FastAPI()
        app.include_router(notifications.router, prefix="/api")
        app.include_router(activity.router, prefix="/api")

        async def dependency():
            yield adapter

        app.dependency_overrides[get_db] = dependency
        yield session, app
    engine.dispose()


async def test_notifications_scope_order_unread_and_mark_all(alerts_db):
    session, app = alerts_db
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.add_all([
        models.Notification(id=1, profile_id="one", kind="pib", title="Old", created_at=older),
        models.Notification(id=2, profile_id="one", kind="new_scheme", title="New", created_at=older + timedelta(days=1)),
        models.Notification(id=3, profile_id="two", kind="pib", title="Other", created_at=older),
    ])
    session.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/notifications", params={"profile_id": "one", "limit": 1})
        assert response.status_code == 200
        assert response.json()["unread_count"] == 2  # whole inbox, not just this page
        assert [item["id"] for item in response.json()["items"]] == [2]
        assert (await client.post("/api/notifications/read", json={"profile_id": "one", "ids": []})).json()["updated"] == 0
        result = await client.post("/api/notifications/read", json={"profile_id": "one", "ids": [2, 3]})
        assert result.json() == {"updated": 1, "unread_count": 1}
        assert (await client.post("/api/notifications/read", json={"profile_id": "one"})).json() == {
            "updated": 1, "unread_count": 0}
        assert (await client.get("/api/notifications", params={"profile_id": "two"})).json()["unread_count"] == 1
        assert (await client.get("/api/notifications", params={"profile_id": "missing"})).status_code == 404


async def test_notify_dedup_scoped_to_profile_and_kind(alerts_db):
    session, _ = alerts_db
    args = ("one", "new_scheme", "Scheme", "Body", "/schemes/test", {"dedup_key": "same-source"})
    assert await notify_service.notify(*args) is True
    assert await notify_service.notify(*args) is False
    assert await notify_service.notify("two", *args[1:]) is True
    assert await notify_service.notify("one", "pib", *args[2:]) is True
    # Status events without a dedup key retain the existing repeated-event behavior.
    assert await notify_service.notify("one", "run_status", "Changed") is True
    assert await notify_service.notify("one", "run_status", "Changed") is True
    assert len(session.scalars(select(models.Notification)).all()) == 5


async def test_activity_merge_follow_scope_and_stable_order(alerts_db):
    session, app = alerts_db
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.add_all([
        models.AgentRun(id="run", profile_id="one", portal_url="https://gov.in", goal="Apply", kind="application",
                        status="done", receipt={"reference": "official"}, updated_at=start),
        models.Report(id="mine", profile_id="one", title="My report", description="Water", category="water",
                      severity="high", department="Water", lat=1, lng=1, updated_at=start + timedelta(days=1)),
        models.Report(id="followed", profile_id="two", title="Followed", description="Water", category="water",
                      severity="high", department="Water", lat=1, lng=1, official_ref="ref", updated_at=start + timedelta(days=3)),
        models.Report(id="support", profile_id="two", title="Only supported", description="Water", category="water",
                      severity="high", department="Water", lat=1, lng=1, updated_at=start + timedelta(days=4)),
        models.ReportVote(report_id="mine", profile_id="one", kind="follow"),
        models.ReportVote(report_id="followed", profile_id="one", kind="follow"),
        models.ReportVote(report_id="support", profile_id="one", kind="support"),
        models.Notification(id=1, profile_id="one", kind="pib", title="Alert", created_at=start + timedelta(days=2)),
        models.Notification(id=2, profile_id="two", kind="pib", title="Other alert", created_at=start + timedelta(days=5)),
    ])
    session.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = (await client.get("/api/activity", params={"profile_id": "one"})).json()
        assert [(item["type"], item["id"]) for item in first] == [
            ("report", "followed"), ("notification", "1"), ("report", "mine"), ("run", "run")]
        assert first[0]["official"] is True and first[2]["official"] is False
        assert first[-1]["link"] == "/runs/run"
        assert set(first[0]) == {"type", "id", "title", "status", "official", "updated_at", "link"}
        assert (await client.get("/api/activity", params={"profile_id": "one"})).json() == first


async def test_monitor_restarts_do_not_rejudge_or_repeat_alerts(alerts_db, monkeypatch):
    session, app = alerts_db
    # A cached scheme is NOT new, even when the monitor has never run.
    session.add(models.Scheme(slug="existing", lang="en", name="Existing", data={}))
    session.commit()
    detail = SchemeDetail(id="new", slug="new", name="New official scheme", source_url="https://myscheme.gov.in/schemes/new",
                          eligibility_md="Students may apply.")
    listing = AsyncMock(return_value=["existing", "new"])

    async def fetch(slug, *args, **kwargs):
        if session.get(models.Scheme, (slug, "en")) is None:
            session.add(models.Scheme(slug=slug, lang="en", name=detail.name, data={"detail": detail.model_dump()}))
            session.commit()
        return detail

    judge = AsyncMock(return_value=SimpleNamespace(verdict="eligible", reasons=[]))
    triage = AsyncMock(return_value=True)
    monkeypatch.setattr(monitor.myscheme, "all_slugs", listing)
    monkeypatch.setattr(monitor.myscheme, "get_scheme", fetch)
    monkeypatch.setattr(monitor.matcher, "triage", triage)
    monkeypatch.setattr(monitor.matcher, "judge", judge)
    feed = FeedItem(title="Scholarship update for students", url="https://www.pib.gov.in/PressReleasePage.aspx?PRID=123", source="PIB")
    monkeypatch.setattr(monitor.feeds, "get_feed", AsyncMock(return_value=[feed]))

    async def classify(prompt, schema, **kwargs):
        assert kwargs["model"] == "lite"
        assert "must never be decrypted" not in prompt
        return schema(items=[{"id": monitor.item_key("pib", feed.url), "relevant": True,
                              "reason": "Student update", "quote": "Scholarship update for students"}])

    generate = AsyncMock(side_effect=classify)
    monkeypatch.setattr(monitor.llm, "generate_json", generate)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/api/monitor/run")
        assert first.status_code == 200
        assert first.json()["notifications"] == 4 and first.json()["schemes_checked"] == 2
        assert first.json()["stored"] == 1 and first.json()["profiles"] == 2
        assert len(session.scalars(select(models.Notification)).all()) == 4
        # Simulate process restart: all de-dup state must come from the database.
        monkeypatch.setattr(monitor, "_lock", asyncio.Lock())
        second = await client.post("/api/monitor/run")
        assert second.json()["notifications"] == 0
        assert second.json()["schemes_checked"] == second.json()["pib_checked"] == 0
        assert judge.await_count == triage.await_count == generate.await_count == 2
        assert len(session.scalars(select(models.Notification)).all()) == 4


async def test_delivery_before_checkpoint_crash_is_idempotent(alerts_db, monkeypatch):
    session, _ = alerts_db
    profile = session.get(models.Profile, "one")
    item = models.MonitorItem(id="source", kind="new_scheme", source="new", data={})
    session.add(item)
    session.commit()
    detail = SchemeDetail(id="new", slug="new", name="New", source_url="https://myscheme.gov.in/schemes/new",
                          eligibility_md="Students may apply.")
    monkeypatch.setattr(monitor.myscheme, "get_scheme", AsyncMock(return_value=detail))
    monkeypatch.setattr(monitor.matcher, "triage", AsyncMock(return_value=True))
    monkeypatch.setattr(monitor.matcher, "judge", AsyncMock(return_value=SimpleNamespace(verdict="likely", reasons=[])))
    complete = monitor._complete
    monkeypatch.setattr(monitor, "_complete", AsyncMock(side_effect=RuntimeError("crash after delivery")))
    first = monitor.MonitorOut()
    await monitor._scheme_check(profile, item, first, asyncio.Semaphore(1))
    assert first.notifications == 1 and first.errors == 1
    monkeypatch.setattr(monitor, "_complete", complete)
    second = monitor.MonitorOut()
    await monitor._scheme_check(profile, item, second, asyncio.Semaphore(1))
    assert second.notifications == 0 and second.schemes_checked == 1
    assert len(session.scalars(select(models.Notification)).all()) == 1


def test_pib_identity_ignores_print_and_www_variants():
    assert monitor.item_key("pib", "https://pib.gov.in/PressReleasePage.aspx?PRID=123") == monitor.item_key(
        "pib", "https://www.pib.gov.in/PressReleaseIframePage.aspx?prid=123&lang=1")


async def test_monitor_timeout_and_overlapping_manual_request(alerts_db, monkeypatch):
    _, app = alerts_db

    async def slow(*args):
        await asyncio.sleep(1)

    monkeypatch.setattr(monitor, "RUN_SECONDS", 0.01)
    monkeypatch.setattr(monitor, "_discover_schemes", slow)
    monkeypatch.setattr(monitor, "_discover_pib", slow)
    result = await monitor.run_monitor()
    assert result.timed_out and not monitor._lock.locked()
    async with monitor._lock:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/api/monitor/run")).status_code == 409


async def test_retry_backoff_keeps_failed_items_from_blocking_new_work(alerts_db, monkeypatch):
    session, _ = alerts_db
    old = models.MonitorItem(id="old", kind="pib", source="https://pib.gov.in/old", data={},
                            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    fresh = models.MonitorItem(id="fresh", kind="pib", source="https://pib.gov.in/fresh", data={})
    session.add_all([old, fresh])
    session.commit()
    await monitor._defer("one", old.id)
    await monitor._complete("two", old.id)
    pending = await monitor._pending("pib")
    assert ("one", "old") not in [(row.id, item.id) for row, item in pending]
    # An expired retry stays behind work that has never been attempted.
    session.execute(models.MonitorCheck.__table__.update().values(
        retry_after=datetime.now(timezone.utc) - timedelta(minutes=1)))
    session.commit()
    monkeypatch.setattr(monitor, "MAX_PAIRS_PER_KIND", 1)
    pending = await monitor._pending("pib")
    assert pending[0][1].id == "fresh"
    await monitor._complete("one", old.id)
    assert ("one", "old") not in [(row.id, item.id) for row, item in await monitor._pending("pib")]


async def test_irrelevant_pib_is_remembered_without_delivery(alerts_db, monkeypatch):
    session, _ = alerts_db
    profile = session.get(models.Profile, "one")
    item = models.MonitorItem(id="unrelated", kind="pib", source="https://pib.gov.in/other", data={
        "title": "Unrelated official news", "url": "https://pib.gov.in/other", "source": "PIB"})
    session.add(item)
    session.commit()
    monkeypatch.setattr(monitor.llm, "generate_json", AsyncMock(return_value=monitor._PibBatch(items=[
        monitor._Relevance(id=item.id, relevant=False, reason="Unrelated", quote="")])))
    counts = monitor.MonitorOut()
    await monitor._pib_check(profile, [item], counts, asyncio.Semaphore(1))
    assert counts.pib_checked == 1 and counts.notifications == 0
    assert session.get(models.MonitorCheck, (profile.id, item.id)).completed
