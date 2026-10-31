import asyncio
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
