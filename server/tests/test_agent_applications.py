from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI

from app.agents import executor
from app.db import get_db
from app.models import AgentRun, Profile
from app.routers import agent
from app.services import crypto


class Context:
    def __init__(self, db): self.db = db
    async def __aenter__(self): return self.db
    async def __aexit__(self, *args): pass


def harness(monkeypatch, tmp_path, decision, *, item=None):
    rs = executor.RunSession("run", "Check eligibility", "https://portal.gov.in", {}, {}, profile_id="owner", language="hi")
    snap = {"url": rs.portal_url, "title": "Form", "headings": [], "errors": [], "captcha": False, "text": "",
        "elements": [{"id": 1, "tag": "input", "type": "file", "accept": "application/pdf", "size_hint": "maximum 300 KB"}]}
    rs.browser = SimpleNamespace(page=SimpleNamespace(url=rs.portal_url),
        snapshot=AsyncMock(return_value=snap), screenshot=AsyncMock(return_value=b""), decision_screenshot=AsyncMock(return_value=b""),
        upload=AsyncMock(), click=AsyncMock(), fill=AsyncMock(), settle=AsyncMock())
    rs.set_status = AsyncMock()
    rs.human_event = AsyncMock(side_effect=lambda kind, *args, **kwargs: {"type": "needs_human", "kind": kind, **kwargs})
    rs.emit = AsyncMock()
    rs.duplicate_runs = AsyncMock(return_value=[])
    def query_result(query):
        # Planner reads document types; upload selection now checks all candidates.
        values = SimpleNamespace(all=lambda: [item] if item else []) if query.column_descriptions[0]["expr"] is executor.LockerItem else ["income_certificate"]
        return SimpleNamespace(scalars=lambda: values, scalar_one_or_none=lambda: item)
    db = SimpleNamespace(add=Mock(), commit=AsyncMock(), get=AsyncMock(return_value=item), execute=AsyncMock(side_effect=query_result))
    monkeypatch.setattr(executor, "SessionLocal", lambda: Context(db))
    monkeypatch.setattr(executor, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path, agent_model="lite"))
    monkeypatch.setattr(executor.llm, "generate_json", AsyncMock(side_effect=[
        executor.ActionPlan(actions=[decision]), executor.ActionPlan(actions=[executor.Decision(thought="Finished", action="done", reference_no="ACK123")])]))
    return rs, snap, db


@pytest.mark.parametrize("approved", [True, False])
async def test_locker_attachment_waits_for_explicit_approval(monkeypatch, tmp_path, approved):
    item = SimpleNamespace(id="doc", profile_id="owner", title="Income certificate", doc_type="income_certificate",
        meta={"readable": True, "issues": []}, variants=[{"format": "jpg", "bytes": 100_000, "path": "jpg.enc"},
                                                       {"format": "pdf", "bytes": 240_000, "path": "pdf.enc"}])
    decision = executor.Decision(thought="Attach the document", action="upload", element_id=1, doc_type="income_certificate")
    rs, _, _ = harness(monkeypatch, tmp_path, decision, item=item)
    monkeypatch.setattr(executor.locker, "decrypt_file", lambda path: b"PDF CONTENT" if path == "pdf.enc" else b"WRONG")
    await rs.inbox.put({"type": "approve" if approved else "abort"})
    graph = executor.build_graph(rs)
    if not approved:
        with pytest.raises(executor.RunAborted):
            await graph.ainvoke({"step": 0, "history": []})
        rs.browser.upload.assert_not_awaited()
        return
    result = await graph.ainvoke({"step": 0, "history": []})
    rs.browser.upload.assert_awaited_once_with(1, {"name": "income_certificate.pdf", "mimeType": "application/pdf", "buffer": b"PDF CONTENT"})
    event_args = rs.human_event.call_args
    assert event_args.args[0] == "confirm_upload"
    assert event_args.kwargs["document"]["id"] == "doc"
    assert "path" not in event_args.kwargs["document"]
    assert result["receipt"]["reference_no"] == "ACK123"
    assert result["receipt"]["attachments"][0]["id"] == "doc"


async def test_payment_control_is_human_only(monkeypatch, tmp_path):
    decision = executor.Decision(thought="Pay", action="request_approval", element_id=1)
    rs, snap, _ = harness(monkeypatch, tmp_path, decision)
    snap["elements"] = [{"id": 1, "tag": "button", "text": "Pay now"}]
    rs.wait_human = AsyncMock(return_value={"type": "resume"})
    await executor.build_graph(rs).ainvoke({"step": 0, "history": []})
    assert rs.human_event.call_args.args[0] == "payment"
    rs.browser.click.assert_not_awaited()
    rs.browser.fill.assert_not_awaited()


async def test_duplicate_cannot_be_submitted_with_ordinary_approval(monkeypatch, tmp_path):
    decision = executor.Decision(thought="Submit", action="request_approval", element_id=1)
    rs, snap, _ = harness(monkeypatch, tmp_path, decision)
    snap["elements"] = [{"id": 1, "tag": "button", "text": "Submit"}]
    rs.duplicate_runs = AsyncMock(return_value=["previous-run"])
    await rs.inbox.put({"type": "approve"})
    await rs.inbox.put({"type": "abort"})
    with pytest.raises(executor.RunAborted):
        await executor.build_graph(rs).ainvoke({"step": 0, "history": []})
    rs.browser.click.assert_not_awaited()
    assert rs.human_event.call_args.kwargs["duplicate_run_ids"] == ["previous-run"]


@pytest.mark.parametrize("status", ["done", "failed", "needs_human", "awaiting_approval"])
async def test_status_changes_notify_once_with_run_link(monkeypatch, status):
    saved = SimpleNamespace(status="running")
    db = SimpleNamespace(get=AsyncMock(return_value=saved), commit=AsyncMock())
    monkeypatch.setattr(executor, "SessionLocal", lambda: Context(db))
    notify = AsyncMock()
    monkeypatch.setattr(executor, "notify", notify)
    rs = executor.RunSession("run", "", "https://portal.gov.in", {}, {}, profile_id="owner")
    await rs.set_status(status)
    await rs.set_status(status)
    assert saved.status == status
    notify.assert_awaited_once()
    assert notify.call_args.args[:2] == ("owner", "run_status")
    assert notify.call_args.kwargs["link"] == "/runs/run"


async def test_resume_reuses_encrypted_answers_kind_and_metadata(monkeypatch):
    old = AgentRun(id="old", profile_id="owner", scheme_slug="scheme", portal_url="https://portal.gov.in", goal="Apply",
        kind="complaint", status="failed", meta={"report_id": "report", "answers_encrypted": crypto.encrypt_json({"dob": "01/02/2000"})})
    prof = Profile(id="owner", data={"state": "Bihar"}, sensitive=crypto.encrypt_json({"full_name": "Private Name"}), language="hi")
    rows = []
    async def get(model, key): return old if model is AgentRun else prof
    async def commit():
        if rows:
            rows[-1].id = "new"
            rows[-1].status = "queued"
    db = SimpleNamespace(get=get, add=rows.append, commit=commit)
    async def dependency(): yield db
    start = Mock()
    monkeypatch.setattr(agent.manager, "get", lambda key: None)
    monkeypatch.setattr(agent.manager, "start", start)
    app = FastAPI()
    app.include_router(agent.router, prefix="/api")
    app.dependency_overrides[get_db] = dependency
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/agent/runs/old/resume?profile_id=owner")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "new" and body["kind"] == "complaint" and body["meta"]["report_id"] == "report"
    assert "answers_encrypted" not in body["meta"]
    session = start.call_args.args[0]
    assert session.language == "hi" and session.answers == {"dob": "01/02/2000"}
    assert session.sensitive["full_name"] == "Private Name"
    assert old.status == "failed"
