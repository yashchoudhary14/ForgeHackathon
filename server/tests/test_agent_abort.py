import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents import executor


@pytest.mark.parametrize("kind", ["confirm_submit", "captcha", "otp"])
async def test_abort_while_waiting_is_saved_cleanly(monkeypatch, tmp_path, kind):
    rs = executor.RunSession("abort-test", "Check eligibility", "https://scholarships.gov.in/", {}, {})
    saved_run = SimpleNamespace(status="queued", error=None)
    db = MagicMock()
    db.get = AsyncMock(return_value=saved_run)
    db.commit = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(executor, "SessionLocal", lambda: db)
    monkeypatch.setattr(executor, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path, agent_model="test"))

    snap = {"url": rs.portal_url, "title": "Form", "headings": [], "errors": [],
            "elements": [{"id": 1, "tag": "input", "label": "Verification"}],
            "captcha": False, "text": "Form"}
    browser = SimpleNamespace(page=SimpleNamespace(url=rs.portal_url))
    for name in ("start", "goto", "close", "screenshot", "click", "fill", "settle"):
        setattr(browser, name, AsyncMock())
    browser.snapshot = AsyncMock(return_value=snap)
    browser.decision_screenshot = AsyncMock(return_value=b"image")
    rs.browser = browser
    decision = executor.Decision(thought="Human help required", element_id=1,
        action="request_approval" if kind == "confirm_submit" else "ask_human",
        kind=None if kind == "confirm_submit" else kind)
    plan = AsyncMock(return_value=executor.ActionPlan(actions=[decision]))
    monkeypatch.setattr(executor.llm, "generate_json", plan)

    waiting = asyncio.Event()
    events = []

    async def emit(event):
        events.append(event)
        if event.get("type") == "needs_human":
            assert event["kind"] == kind
            waiting.set()

    rs.emit = emit
    task = asyncio.create_task(executor.run(rs))
    try:
        await asyncio.wait_for(waiting.wait(), timeout=5)
        assert saved_run.status == ("awaiting_approval" if kind == "confirm_submit" else "needs_human")
        await rs.inbox.put({"type": "abort"})
        await asyncio.wait_for(task, timeout=5)
    finally:
        if not task.done():
            task.cancel()
            await task

    assert saved_run.status == rs.status == "aborted"
    assert saved_run.error == "Run aborted by user"
    assert events[-2:] == [{"type": "status", "status": "aborted"},
                           {"type": "error", "message": "Run aborted"}]
    assert rs.pending is None
    browser.close.assert_awaited_once()
    browser.click.assert_not_awaited()
    browser.fill.assert_not_awaited()
    plan.assert_awaited_once()
from unittest.mock import AsyncMock

from app.agents import executor
from app.agents.executor import ActionPlan, Decision, RunSession


class FakeBrowser:
    page = type("Page", (), {"url": "https://portal.gov.in"})()

    async def snapshot(self):
        return {"url": self.page.url, "title": "Form", "headings": [], "errors": [], "captcha": False,
                "elements": [{"id": 1, "tag": "button", "text": "Final Submit"}], "text": ""}

    async def decision_screenshot(self):
        return b""

    async def screenshot(self, **kwargs):
        return b""

    start = goto = close = settle = AsyncMock()


class FakeDB:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def add(self, row):
        pass

    commit = AsyncMock()


async def test_abort_at_approval_is_saved_as_aborted(monkeypatch):
    monkeypatch.setattr(executor, "SessionLocal", FakeDB)
    plan = ActionPlan(actions=[Decision(thought="Ready", action="click", element_id=1)])
    monkeypatch.setattr(executor.llm, "generate_json", AsyncMock(return_value=plan))
    rs = RunSession("run-1", "check eligibility", "https://portal.gov.in", {}, {})
    rs.browser = FakeBrowser()
    statuses = []

    async def set_status(status, **kwargs):
        statuses.append(status)
        if status == "awaiting_approval":
            await rs.inbox.put({"type": "abort"})

    rs.set_status = set_status
    rs.emit = AsyncMock()
    await asyncio.wait_for(executor.run(rs), 5)
    assert statuses[-1] == "aborted"
