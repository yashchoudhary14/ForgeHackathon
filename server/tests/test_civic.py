"""Offline civic contracts: model/HTTP calls are mocked, no database needed."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app.agents import civic
from app.db import get_db
from app.models import AgentRun, Profile, Report, ReportEvent
from app.routers import reports
from app.schemas import CivicTriage, ComplaintDraft, ReportActorIn, ReportVoteIn, SttOut
from app.services import geo


TRIAGE = dict(category="roads", title="Broken road", title_local="टूटी सड़क",
              description="A deep pothole in the road", severity="urgent",
              severity_reason="The deep hole poses an immediate road safety hazard",
              department="Public Works Department, Delhi")
NOW = datetime.now(timezone.utc)


def report(**overrides):
    values = dict(id="report", profile_id="reporter", category="roads", title="Broken road",
                  description="Deep pothole", severity="urgent", department="Public Works Department, Delhi",
                  lat=28.606356, lng=77.046806, language="hi", status="open", supporters=1,
                  media=[], ai=TRIAGE.copy(), embedding=[1., 0.], address="Dwarka, Delhi",
                  official_ref=None, official_status=None, created_at=NOW, updated_at=NOW)
    return Report(**(values | overrides))


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeDB:
    def __init__(self, scalar_values=(), rows=()):
        self.scalar_values = iter(scalar_values)
        self.rows = rows
        self.added = []
        self.queries = []
        self.commits = 0

    async def scalar(self, query):
        self.queries.append(query)
        return next(self.scalar_values)

    async def scalars(self, query):
        self.queries.append(query)
        return Rows(self.rows)

    def add(self, obj):
        if isinstance(obj, AgentRun) and obj.id is None:
            obj.id = "created-run"
        self.added.append(obj)

    async def get(self, cls, key):
        if cls is Profile:
            return Profile(id=key, language="hi", sensitive=None, data={})

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass


class AttachmentDB(FakeDB):
    async def get(self, cls, key):
        if cls is AgentRun:
            return AgentRun(id=key, profile_id="reporter", kind="complaint", meta={"report_id": "report"})
        return await super().get(cls, key)


def test_triage_parse_preserves_local_title_reason_and_rejects_invented_department():
    result = civic.parse_triage(TRIAGE)
    assert result.title_local == "टूटी सड़क" and result.severity_reason
    with pytest.raises(ValueError, match="curated list"):
        civic.parse_triage(TRIAGE | {"department": "Imaginary Ministry"})
    with pytest.raises(ValidationError):
        civic.parse_triage(TRIAGE | {"severity": "critical"})
    with pytest.raises(ValidationError):
        civic.parse_triage(TRIAGE | {"title": ""})


@pytest.mark.asyncio
async def test_triage_uses_vision_wrapper_and_language(monkeypatch):
    generate = AsyncMock(return_value=CivicTriage(**TRIAGE))
    monkeypatch.setattr(civic.llm, "generate_json", generate)
    result = await civic.triage("पानी भरा है", "hi", "Dwarka, Delhi", b"image bytes", "image/jpeg")
    args, kwargs = generate.call_args
    assert kwargs["model"] == "lite"
    assert args[0][1].inline_data.data == b"image bytes"
    assert "hi" in args[0][0] and result.title == TRIAGE["title"]
    assert "drinking-water" in kwargs["system"]


def test_duplicates_exclude_wrong_category_closed_and_over_300m():
    origin = report()
    values = [origin, report(id="closed", status="closed"), report(id="water", category="water"),
              report(id="far", lat=origin.lat + .003), report(id="resolved", status="resolved")]
    found = civic.rank_duplicates(values, "roads", origin.lat, origin.lng, [1., 0.])
    assert {item[0].id for item in found} == {"report", "resolved"}
    assert found[0][1] == 0 and found[0][2] == 1


def test_duplicate_ranking_uses_distance_and_semantic_similarity():
    a = report(id="same", lat=28.607, embedding=[1., 0.])
    b = report(id="different", lat=28.607, embedding=[0., 1.])
    assert civic.rank_duplicates([b, a], "roads", 28.606356, 77.046806, [1., 0.])[0][0].id == "same"
    assert civic.cosine(None, [1., 0.]) == 0
    assert civic.cosine([0., 0.], [1., 0.]) == 0
    assert geo.distance_m(0, 179.999, 0, -179.999) < 300


@pytest.mark.parametrize("message,expected", [("Status: Case closed", "closed"), ("Disposed", "closed"),
    ("Current Status: Under process\nForwarded to the department", "in_progress"),
    ("Resolved", "resolved"), ("The citizen requested the case be closed", None)])
def test_official_state_uses_explicit_labels_only(message, expected):
    assert civic.official_report_status(message) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,event_kind", [("support", "support"), ("still_broken", "still_broken"),
                                               ("fixed", "fixed_claim"), ("follow", "follow")])
async def test_vote_is_idempotent_and_citizen_claims_do_not_change_official_status(kind, event_kind):
    item = report()
    db = FakeDB([item, 1, item, None])
    body = ReportVoteIn(profile_id="neighbour", kind=kind)
    await reports.vote(item.id, body, db)
    await reports.vote(item.id, body, db)
    assert item.supporters == (2 if kind == "support" else 1)
    assert len(db.added) == 1
    assert db.added[0].source == "citizen" and db.added[0].kind == event_kind
    assert item.status == "open" and item.official_status is None
    # Assert that production uses the database uniqueness boundary, including kind.
    from sqlalchemy.dialects import postgresql
    sql = str(db.queries[1].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (report_id, profile_id, kind) DO NOTHING" in sql


@pytest.mark.asyncio
async def test_successful_complaint_receipt_is_saved_once_and_notifies_reporter_and_followers():
    item = report()
    run = AgentRun(id="run", kind="complaint", status="done", meta={"report_id": item.id},
                   receipt={"reference_no": "DOURD/E/2026/000123", "summary": "Registered"})
    db = FakeDB([item], ["reporter", "follower"])
    update = await civic.apply_completion(db, run)
    assert update == (item.id, "CPGRAMS grievance registered: DOURD/E/2026/000123", {"reporter", "follower"})
    assert item.status == "filed" and item.official_ref == "DOURD/E/2026/000123"
    assert db.added[0].source == "official" and db.added[0].kind == "filed"
    assert await civic.apply_completion(db, run) is None
    assert len(db.added) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status,reference", [("failed", "REG123"), ("aborted", "REG123"),
                                               ("done", ""), ("done", "not a registration number")])
async def test_failed_or_missing_receipt_never_marks_filed(status, reference):
    item = report()
    run = AgentRun(id="run", kind="complaint", status=status, meta={"report_id": item.id},
                   receipt={"reference_no": reference})
    db = FakeDB([item])
    assert await civic.apply_completion(db, run) is None
    assert item.official_ref is None and item.status == "open" and not db.added


@pytest.mark.asyncio
async def test_status_changed_only_and_mismatched_registration_is_rejected():
    item = report(status="filed", official_ref="REG123", official_status="Under examination")
    db = FakeDB([item, item, item], ["follower"])
    def run(message, reference="REG123"):
        return AgentRun(id="check", kind="status_check", status="done",
                        meta={"report_id": item.id, "official_ref": "REG123"},
                        receipt={"reference_no": reference, "summary": message})
    assert await civic.apply_completion(db, run(" Under  examination ")) is None
    update = await civic.apply_completion(db, run("Action report received"))
    assert update[2] == {"reporter", "follower"}
    assert item.official_status == "Action report received" and len(db.added) == 1
    assert await civic.apply_completion(db, run("Closed", "WRONG123")) is None
    assert item.official_status == "Action report received"


@pytest.mark.asyncio
async def test_finish_hook_commits_before_notifications_without_browser(monkeypatch):
    item = report()
    run = AgentRun(id="run", kind="complaint", status="done", meta={"report_id": item.id},
                   receipt={"reference_no": "REG123"})
    db = FakeDB([run, item], ["follower", "reporter"])
    class Session:
        async def __aenter__(self):
            return db
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(civic, "SessionLocal", Session)
    calls = []
    async def notification(*args):
        assert db.commits == 1
        calls.append(args)
    monkeypatch.setattr(civic, "notify", notification)
    await civic.finish_run(run.id)
    assert {args[0] for args in calls} == {"reporter", "follower"}


@pytest.mark.asyncio
async def test_task_callback_runs_after_browser_client_has_gone(monkeypatch):
    finish = AsyncMock()
    monkeypatch.setattr(civic, "finish_run", finish)
    task = asyncio.create_task(asyncio.sleep(0))
    civic.watch_run(SimpleNamespace(id="background", task=task))
    await task
    await asyncio.sleep(0)
    await asyncio.gather(*list(civic._completion_tasks))
    finish.assert_awaited_once_with("background")


@pytest.mark.asyncio
async def test_recovery_scans_and_finishes_persisted_runs(monkeypatch):
    db = FakeDB(rows=["completed-while-disconnected"])
    class Session:
        async def __aenter__(self):
            return db
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(civic, "SessionLocal", Session)
    finish = AsyncMock()
    monkeypatch.setattr(civic, "_safe_finish", finish)
    await civic.recover_completions()
    finish.assert_awaited_once_with("completed-while-disconnected")


def test_goals_and_redaction_keep_personal_details_local():
    text = civic.redact("Ravi, 9876543210, me@example.com, 1234 5678 9012, 10 Private Lane", {
        "full_name": "Ravi", "address": "10 Private Lane"})
    assert all(value not in text for value in ["Ravi", "9876543210", "me@example.com", "1234 5678 9012", "10 Private Lane"])
    draft = ComplaintDraft(subject="Repair road", english="Please repair", local="कृपया मरम्मत करें", language="hi")
    goal = civic.complaint_goal(report(), draft)
    assert "value_from=phone" in goal and "approval" in goal and "reference_no" in goal
    assert "value_from=registration_number" in civic.status_goal()


def test_redaction_does_not_corrupt_department_or_substrings():
    result = civic.redact_triage(CivicTriage(**(TRIAGE | {"department": "Gram Panchayat", "description": "Ram reported a broken road"})),
                                 {"full_name": "Ram"})
    assert result.department == "Gram Panchayat"
    assert "Ram" not in result.description
    assert civic.redact("BSES Rajdhani Power Limited", {"full_name": "Raj"}) == "BSES Rajdhani Power Limited"


@pytest.mark.asyncio
async def test_file_uses_existing_manager_kind_meta_and_local_phone(monkeypatch):
    item = report()
    db = FakeDB([item, None])
    draft = ComplaintDraft(subject="Repair road", english="Please repair", local="मरम्मत करें", language="hi")
    monkeypatch.setattr(civic, "draft_complaint", AsyncMock(return_value=draft))
    monkeypatch.setattr(reports.crypto, "decrypt_json", lambda _: {"phone": "9876543210"})
    sessions = []
    monkeypatch.setattr(reports.manager, "start", sessions.append)
    monkeypatch.setattr(civic, "watch_run", lambda _: None)
    await reports.start_civic_run(item.id, ReportActorIn(profile_id="reporter"), db, "complaint")
    run = next(obj for obj in db.added if isinstance(obj, AgentRun))
    assert run.kind == "complaint" and run.meta["report_id"] == item.id
    assert run.portal_url == "https://pgportal.gov.in/"
    assert sessions[0].sensitive["phone"] == "9876543210"
    assert "9876543210" not in sessions[0].goal and sessions[0].citizen_view()["phone"] == "<set>"


@pytest.mark.asyncio
async def test_nominatim_has_identification_and_persistent_cache(monkeypatch):
    read = AsyncMock(side_effect=[None, {"address": "Dwarka, Delhi"}])
    write = AsyncMock()
    monkeypatch.setattr(geo.llm_cache, "read", read)
    monkeypatch.setattr(geo.llm_cache, "write", write)
    monkeypatch.setattr(geo, "_last_request", 0)
    monkeypatch.setattr(geo, "_lock", asyncio.Lock())
    calls = []
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(200, json={"display_name": "Dwarka, Delhi"}, request=httpx.Request("GET", url))
    monkeypatch.setattr(geo.httpx, "AsyncClient", Client)
    assert await geo.reverse_geocode(28.6, 77.04) == "Dwarka, Delhi"
    assert await geo.reverse_geocode(28.6, 77.04) == "Dwarka, Delhi"
    assert len(calls) == 1 and "Adhikaar" in calls[0][1]["headers"]["User-Agent"]
    write.assert_awaited_once()


@pytest.mark.asyncio
async def test_http_triage_transcribes_audio_and_returns_duplicates(monkeypatch):
    item = report()
    monkeypatch.setattr(reports.sarvam, "stt", AsyncMock(return_value=SttOut(text="सड़क टूटी है", language="hi")))
    monkeypatch.setattr(reports.crypto, "decrypt_json", lambda _: {})
    monkeypatch.setattr(reports, "get_settings", lambda: SimpleNamespace(sarvam_api_key="test-key"))
    monkeypatch.setattr(reports.geo, "reverse_geocode", AsyncMock(return_value="Dwarka, Delhi"))
    classify = AsyncMock(return_value=CivicTriage(**TRIAGE))
    monkeypatch.setattr(civic, "triage", classify)
    monkeypatch.setattr(reports.llm, "embed", AsyncMock(return_value=[[1., 0.]]))
    monkeypatch.setattr(civic, "duplicates", AsyncMock(return_value=[(item, 20, 1, .96)]))
    app = FastAPI()
    app.include_router(reports.router, prefix="/api")
    async def database():
        yield FakeDB()
    app.dependency_overrides[get_db] = database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/reports/triage", data={"profile_id": "reporter", "lat": "28.6", "lng": "77.04"},
                                     files={"audio": ("voice.wav", b"voice", "audio/wav")})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["title_local"] == TRIAGE["title_local"] and result["duplicates"][0]["id"] == item.id
        assert result["language"] == "hi"
        assert "सड़क टूटी है" in classify.call_args.args[0]
        bad = await client.post("/api/reports/triage", json={"profile_id": "reporter", "lat": 91, "lng": 0, "text": "road"})
        assert bad.status_code == 422


@pytest.mark.asyncio
async def test_media_is_saved_under_storage_with_public_url(monkeypatch, tmp_path):
    monkeypatch.setattr(reports, "get_settings", lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    media = await reports.save_media([{"type": "photo", "suffix": "jpg", "mime": "image/jpeg", "data": b"photo"}])
    assert (tmp_path / media[0]["path"]).read_bytes() == b"photo"
    assert media[0]["url"] == "/files/" + media[0]["path"]


@pytest.mark.asyncio
async def test_attachment_requires_explicit_approval_and_correct_paused_field(monkeypatch):
    item = report()
    body = reports.AttachmentIn(profile_id="reporter", run_id="run")
    with pytest.raises(HTTPException) as error:
        await reports.attach_photo(item.id, body, AttachmentDB([item]))
    assert error.value.status_code == 409
    monkeypatch.setattr(reports.manager, "get", lambda _: SimpleNamespace(
        pending={"field": "phone"}, status="needs_human"))
    with pytest.raises(HTTPException) as error:
        await reports.attach_photo(item.id, body.model_copy(update={"approved": True}), AttachmentDB([item]))
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_approved_attachment_uses_only_stored_photo_and_resumes(monkeypatch, tmp_path):
    photo = tmp_path / "reports" / "photo.jpg"
    photo.parent.mkdir()
    photo.write_bytes(b"photo")
    item = report(media=[{"type": "photo", "path": "reports/photo.jpg", "url": "/files/reports/photo.jpg", "mime": "image/jpeg"}])
    field = SimpleNamespace(get_attribute=AsyncMock(return_value=".jpeg"), set_input_files=AsyncMock())
    inputs = SimpleNamespace(count=AsyncMock(return_value=1), first=field)
    page = SimpleNamespace(url="https://pgportal.gov.in/", locator=lambda _: inputs)
    session = SimpleNamespace(pending={"field": "issue_photo"}, status="needs_human",
                              browser=SimpleNamespace(page=page), inbox=asyncio.Queue())
    monkeypatch.setattr(reports.manager, "get", lambda _: session)
    monkeypatch.setattr(reports, "get_settings", lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    db = AttachmentDB([item])
    result = await reports.attach_photo(item.id, reports.AttachmentIn(profile_id="reporter", run_id="run", approved=True), db)
    assert result["uploaded"] is True
    field.set_input_files.assert_awaited_once_with(str(photo.resolve()))
    assert await session.inbox.get() == {"type": "resume"}
    assert db.commits == 1 and db.added[0].kind == "attachment"


@pytest.mark.asyncio
async def test_file_reuses_active_run_and_rejects_refiling():
    item = report()
    active = AgentRun(id="existing-run", status="needs_human")
    response = await reports.start_civic_run(item.id, ReportActorIn(profile_id="reporter"), FakeDB([item, active]), "complaint")
    assert response.run_id == "existing-run"
    with pytest.raises(HTTPException) as error:
        await reports.start_civic_run(item.id, ReportActorIn(profile_id="reporter"),
                                      FakeDB([report(official_ref="REG123")]), "complaint")
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_status_check_needs_registration_and_uses_status_portal(monkeypatch):
    with pytest.raises(HTTPException) as error:
        await reports.start_civic_run("report", ReportActorIn(profile_id="reporter"), FakeDB([report()]), "status_check")
    assert error.value.status_code == 409
    item = report(official_ref="REG123", status="filed")
    db = FakeDB([item, None])
    sessions = []
    monkeypatch.setattr(reports.manager, "start", sessions.append)
    monkeypatch.setattr(civic, "watch_run", lambda _: None)
    await reports.start_civic_run(item.id, ReportActorIn(profile_id="reporter"), db, "status_check")
    run = db.added[0]
    assert run.kind == "status_check" and run.portal_url == "https://pgportal.gov.in/Status"
    assert run.meta["official_ref"] == "REG123"
    assert sessions[0].profile["registration_number"] == "REG123"
