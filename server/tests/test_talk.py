"""Offline Talk contracts: real persistence, mocked Gemini/Sarvam/official services."""
import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from google.genai import types
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents import intake, talk
from app.models import AgentRun, ChatMessage, Profile
from app.routers import profile as profile_route, talk as route
from app.schemas import MatchResult, ProfileData, SchemeDetail, SchemeSummary, SensitiveData, SttOut, TalkIn, TalkReply
from app.services import crypto


class AsyncDB:
    def __init__(self, session):
        self.session = session

    def add(self, row):
        self.session.add(row)

    async def get(self, model, key):
        return self.session.get(model, key)

    async def execute(self, query):
        return self.session.execute(query)

    async def commit(self):
        self.session.commit()


@pytest.fixture
def db(monkeypatch, tmp_path):
    engine = create_engine("sqlite://")
    for model in (Profile, ChatMessage, AgentRun):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        database = AsyncDB(session)

        @asynccontextmanager
        async def factory():
            yield database

        monkeypatch.setattr(route, "SessionLocal", factory)
        monkeypatch.setattr(profile_route.db, "SessionLocal", factory)
        monkeypatch.setattr(crypto.get_settings(), "profile_secret", "offline-test-secret")
        monkeypatch.setattr(route.sarvam.get_settings(), "storage_dir", str(tmp_path))
        database.add(Profile(id="farmer", data={"age": 46}, language="en", mode="manual",
                             sensitive=crypto.encrypt_json({"full_name": "Private Citizen", "phone": "9876543210"})))
        session.commit()
        yield database
    engine.dispose()


def model_response(*calls, reply=None):
    parts = [types.Part.from_function_call(name=name, args=args) for name, args in calls]
    if not parts:
        parts = [types.Part.from_text(text=reply.model_dump_json() if reply else "ready")]
    parts[0].thought_signature = b"keep-original-signature"
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=parts))])


def mock_brain(monkeypatch):
    async def respond(message, language, history, tools):
        assert "Private Citizen" not in message
        yield {"type": "delta", "text": "आप किस योजना के बारे में जानना चाहते हैं?"}
        yield {"type": "reply", "text": "आप किस योजना के बारे में जानना चाहते हैं?", "quick_replies": ["योजनाएँ खोजें"]}

    monkeypatch.setattr(route, "respond", respond)
    monkeypatch.setattr(route.sarvam, "tts_to_file", AsyncMock(return_value="/files/audio/test.wav"))


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


async def test_first_audio_detects_then_persists_across_text_audio_and_explicit_switch(db, monkeypatch):
    mock_brain(monkeypatch)
    stt = AsyncMock(side_effect=[SttOut(text="मैं किसान हूँ", language="hi"),
                                SttOut(text="मेरी जमीन है", language="bn")])
    monkeypatch.setattr(route.sarvam, "stt", stt)
    first = [e async for e in route.conversation(TalkIn(profile_id="farmer", lang="en"), b"wav", "audio/wav", db)]
    assert stt.await_args.args == (b"wav", "audio/wav", None)
    assert first[0] == {"type": "transcript", "text": "मैं किसान हूँ", "lang": "hi"}
    assert (await db.get(Profile, "farmer")).language == "hi"
    assert (await db.get(Profile, "farmer")).mode == "talk"
    follow = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="Tell me more"), None, "", db)]
    assert follow[-1]["lang"] == "hi"
    later_audio = [e async for e in route.conversation(TalkIn(profile_id="farmer"), b"later", "audio/wav", db)]
    assert stt.await_args.args[-1] == "hi"
    assert later_audio[-1]["lang"] == "hi"  # STT cannot silently switch the session
    for text, expected in [("English mein bolo", "en"), ("speak Bengali", "bn")]:
        result = [e async for e in route.conversation(TalkIn(profile_id="farmer", text=text), None, "", db)]
        assert result[-1]["lang"] == expected
        assert route.sarvam.tts_to_file.await_args.args[-1] == expected


async def test_first_audio_autodetects_even_after_text_turn(db, monkeypatch):
    mock_brain(monkeypatch)
    _ = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="hello"), None, "", db)]
    stt = AsyncMock(return_value=SttOut(text="नमस्ते", language="hi"))
    monkeypatch.setattr(route.sarvam, "stt", stt)
    _ = [e async for e in route.conversation(TalkIn(profile_id="farmer"), b"wav", "audio/wav", db)]
    assert stt.await_args.args[-1] is None


async def test_save_facts_merges_and_never_decrypts_into_intake(db, monkeypatch):
    row = await db.get(Profile, "farmer")
    encrypted = row.sensitive
    extract = AsyncMock(return_value=(ProfileData(age=46, state="Uttar Pradesh", occupation="farmer", land_acres=2), SensitiveData()))
    monkeypatch.setattr(intake, "extract", extract)
    tools = talk.TalkTools(db, row, "I farm two acres in Uttar Pradesh")
    result = await tools.call("save_profile_facts", {})
    assert result["profile"]["land_acres"] == 2
    assert row.data["age"] == 46 and row.sensitive == encrypted
    assert extract.await_args.args[2] == SensitiveData()
    await tools.call("save_profile_facts", {})
    assert extract.await_count == 1


async def test_gemini_dispatches_tools_preserves_signature_and_emits_real_cards(db, monkeypatch):
    row = await db.get(Profile, "farmer")
    monkeypatch.setattr(intake, "extract", AsyncMock(return_value=(ProfileData(state="Uttar Pradesh", occupation="farmer", land_acres=2), SensitiveData())))
    matches = [MatchResult(scheme=SchemeSummary(slug=f"scheme-{i}", name=f"Official {i}", brief="Official description"),
                           verdict="likely", confidence=.8, reasons=[]) for i in range(5)]
    match = AsyncMock(return_value=matches)
    monkeypatch.setattr(talk.matcher, "match", match)
    reply = TalkReply(text="आपके लिए योजनाएँ मिली हैं। क्या इनके बारे में समझाऊँ?", quick_replies=["समझाएँ"])
    planned = [model_response(("save_profile_facts", {}), ("find_schemes", {})), model_response(), model_response(reply=reply)]

    async def generate(contents, cfg, model):
        assert model == "strong"
        assert "Private Citizen" not in str(contents) + str(cfg)
        if len(planned) == 2:
            assert contents[-2].parts[0].thought_signature == b"keep-original-signature"
            assert len(contents[-1].parts) == 2
        return planned.pop(0)

    monkeypatch.setattr(talk.llm, "generate_content", generate)
    tools = talk.TalkTools(db, row, "farmer in UP with two acres")
    result = [e async for e in talk.respond(tools.message, "hi", [], tools)]
    assert [e["type"] for e in result] == ["card"] * 5 + ["delta", "reply"]
    assert {"kind", "slug", "name", "verdict", "summary"} <= result[0]["card"].keys()
    assert match.await_args.args[0].land_acres == 2
    assert match.await_args.kwargs["limit"] == 5


async def test_tool_allowlist_and_sanitized_failure(db, monkeypatch):
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "hello")
    assert "error" in await tools.call("__dict__", {})
    monkeypatch.setattr(talk.matcher, "match", AsyncMock(side_effect=RuntimeError("secret credential")))
    monkeypatch.setattr(intake, "extract", AsyncMock(return_value=(ProfileData(), SensitiveData())))
    assert "secret" not in str(await tools.call("find_schemes", {}))
    report = await tools.call("report_issue", {"title": "पानी नहीं आ रहा"})
    assert report["card"] == {"kind": "report", "report_id": None, "title": "पानी नहीं आ रहा"}
    assert report["action"] == "open_report_flow" and report["filed"] is False


@pytest.mark.parametrize("url", ["https://gov.in.evil.com/apply", "https://evil.com/gov.in", "javascript:alert(1)", "https://example.org", "https://gov.in@evil.com/"])
async def test_application_rejects_unofficial_or_nonapplication_urls(db, monkeypatch, url):
    scheme = SchemeDetail(id="s", slug="s", name="Official", source_url="https://real.gov.in",
                          references=[{"url": "https://real.gov.in/apply"}], application=[{"mode": "Online", "url": url, "steps_md": "Apply"}])
    monkeypatch.setattr(talk.myscheme, "get_scheme", AsyncMock(return_value=scheme))
    assert "error" in await talk.TalkTools(db, await db.get(Profile, "farmer"), "apply").call("start_application", {"slug": "s"})
    assert not db.session.execute(select(AgentRun)).scalars().all()


async def test_application_uses_official_steps_creates_application_run_and_local_secrets(db, monkeypatch):
    from app.agents import executor

    scheme = SchemeDetail(id="s", slug="s", name="Official", source_url="https://www.myscheme.gov.in/schemes/s",
                          application=[{"mode": "Online", "steps_md": "Apply at [portal](https://farmer.gov.in/apply)."}])
    monkeypatch.setattr(talk.myscheme, "get_scheme", AsyncMock(return_value=scheme))
    start, run_session = Mock(), Mock()
    monkeypatch.setattr(executor.manager, "start", start)
    monkeypatch.setattr(executor, "RunSession", run_session)
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "apply Official")
    result = await tools.call("start_application", {"slug": "s"})
    assert result["card"]["kind"] == "run"
    run = db.session.execute(select(AgentRun)).scalars().one()
    assert run.kind == "application" and run.portal_url == "https://farmer.gov.in/apply"
    assert run.profile_id == "farmer" and run.status == "queued"
    assert run_session.call_args.args[4]["phone"] == "9876543210"
    await tools.call("start_application", {"slug": "s"})
    start.assert_called_once()


@pytest.mark.parametrize("message,offer,allowed", [("hello", None, False), ("yes", None, False),
    ("yes", "other", False), ("Do not apply Official", "s", False), ("yes, explain first", "s", False),
    ("हाँ, भर दो", "s", True), ("yes", "s", True)])
async def test_application_requires_explicit_scheme_request_or_bound_consent(db, monkeypatch, message, offer, allowed):
    from app.agents import executor
    scheme = SchemeDetail(id="s", slug="s", name="Official", source_url="https://www.myscheme.gov.in/schemes/s",
                          application=[{"mode": "Online", "steps_md": "https://portal.gov.in"}])
    monkeypatch.setattr(talk.myscheme, "get_scheme", AsyncMock(return_value=scheme))
    start = Mock()
    monkeypatch.setattr(executor.manager, "start", start)
    monkeypatch.setattr(executor, "RunSession", Mock())
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), message,
                           [{"role": "assistant", "content": "Apply?", "offer_slug": offer}])
    result = await tools.call("start_application", {"slug": "s"})
    assert ("card" in result) == allowed
    assert start.called == allowed


async def test_explain_uses_explainer_in_session_language_and_requires_quotes(db, monkeypatch):
    from app.schemas import Citation, ExplainOut
    row = await db.get(Profile, "farmer")
    row.language = "hi"
    result = ExplainOut(title="Official", summary="छोटी व्याख्या", key_points=[], your_rights=[],
                        citations=[Citation(source_url="https://portal.gov.in", quote="Official quote")], language="hi")
    explain = AsyncMock(return_value=result)
    monkeypatch.setattr(talk.explainer, "explain", explain)
    tools = talk.TalkTools(db, row, "explain")
    assert (await tools.call("explain_scheme", {"slug": "s"}))["summary"] == "छोटी व्याख्या"
    assert explain.await_args.args[0].language == "hi" and not explain.await_args.args[0].with_audio
    result.citations = []
    assert "error" in await tools.call("explain_scheme", {"slug": "s"})


async def test_empty_audio_does_not_prevent_later_language_detection(db, monkeypatch):
    mock_brain(monkeypatch)
    stt = AsyncMock(side_effect=[SttOut(text="", language="en"), SttOut(text="नमस्ते", language="hi")])
    monkeypatch.setattr(route.sarvam, "stt", stt)
    first = [e async for e in route.conversation(TalkIn(profile_id="farmer"), b"a", "audio/wav", db)]
    assert first[-1]["type"] == "error"
    _ = [e async for e in route.conversation(TalkIn(profile_id="farmer"), b"b", "audio/wav", db)]
    assert stt.await_args.args[-1] is None


async def test_my_activity_is_profile_scoped_and_latest_first(db):
    db.add(Profile(id="other", data={}))
    for index in range(3):
        db.add(AgentRun(id=str(index), profile_id="farmer" if index < 2 else "other", goal="Apply", portal_url="https://example.gov.in", kind="application"))
    await db.commit()
    result = await talk.TalkTools(db, await db.get(Profile, "farmer"), "activity").call("my_activity", {})
    assert [r["run_id"] for r in result["runs"]] == ["1", "0"]


async def test_http_json_and_multipart_sse_shape_audio_is_browser_playable(db, monkeypatch, tmp_path):
    # Exercise the real storage helper and StaticFiles mount, mocking only Sarvam's bytes.
    from app.services.sarvam import tts_to_file
    mock_brain(monkeypatch)
    monkeypatch.setattr(route.sarvam, "tts_to_file", tts_to_file)
    monkeypatch.setattr(route.sarvam, "tts", AsyncMock(return_value=b"RIFF-offline-WAVE"))
    monkeypatch.setattr(route.sarvam, "stt", AsyncMock(return_value=SttOut(text="मैं किसान हूँ", language="hi")))
    app = FastAPI()
    app.include_router(route.router, prefix="/api")
    app.mount("/files", StaticFiles(directory=str(tmp_path)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for kwargs in [{"json": {"profile_id": "farmer", "text": "hello"}},
                       {"data": {"profile_id": "farmer"}, "files": {"audio": ("voice.wav", b"wav", "audio/wav")}}]:
            result = await client.post("/api/talk", **kwargs)
            assert result.status_code == 200 and result.headers["content-type"].startswith("text/event-stream")
            assert result.headers["x-accel-buffering"] == "no"
            decoded = events(result)
            assert [e["type"] for e in decoded] == ["transcript", "delta", "done"]
            assert set(decoded[-1]) == {"type", "text", "lang", "audio_url", "quick_replies", "profile"}
            audio = await client.get(decoded[-1]["audio_url"])
            assert audio.status_code == 200 and audio.headers["content-type"].startswith("audio/")


async def test_speech_failure_still_finishes_with_text(db, monkeypatch):
    mock_brain(monkeypatch)
    monkeypatch.setattr(route.sarvam, "tts_to_file", AsyncMock(side_effect=ValueError("Unsupported language")))
    result = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="hello"), None, "", db)]
    assert result[-1]["type"] == "done" and result[-1]["audio_url"] is None
    assert result[-1]["text"]


async def test_profile_language_and_mode_only_update_preserves_data_and_ciphertext(db):
    app = FastAPI()
    app.include_router(profile_route.router, prefix="/api")
    before = (await db.get(Profile, "farmer")).sensitive
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        result = await client.put("/api/profile/farmer", json={"language": "hi", "mode": "talk"})
        assert result.status_code == 200
        assert result.json()["language"] == "hi" and result.json()["mode"] == "talk"
        assert result.json()["data"]["age"] == 46
        invalid = await client.put("/api/profile/farmer", json={"mode": "invalid"})
        assert invalid.status_code == 422
    assert (await db.get(Profile, "farmer")).sensitive == before


def test_privacy_redacts_before_model_and_language_mentions_do_not_switch():
    text = talk.safe_text("My name is New Person, I am a farmer. 9876543210 user@example.com 1234 5678 9012", {})
    assert "New Person" not in text and "9876543210" not in text and "example.com" not in text and "5678" not in text
    assert "farmer" in text
    assert talk.safe_text("hello Private Citizen", {"full_name": "Private Citizen"}) == "hello [private]"
    assert "1990" not in talk.safe_text("12/11/1990", {})
    assert "123456" not in talk.safe_text("OTP is 123456", {})
    assert talk.requested_language("My daughter studies English") is None
    assert talk.requested_language("मेरे गाँव में Bengali स्कूल है") is None


async def test_keepalive_and_disconnect_cancel_work(db, monkeypatch):
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def slow(*args):
        started.set()
        try:
            await asyncio.Event().wait()
            yield
        finally:
            cancelled.set()

    monkeypatch.setattr(route, "respond", slow)
    monkeypatch.setattr(route, "KEEPALIVE_SECONDS", .01)
    stream = route.event_stream(TalkIn(profile_id="farmer", text="hello"))
    assert await anext(stream) == ": keepalive\n\n"
    await started.wait()
    assert json.loads((await anext(stream))[6:])["type"] == "transcript"
    assert await anext(stream) == ": keepalive\n\n"
    await stream.aclose()
    assert cancelled.is_set()


@pytest.mark.parametrize("body", [{"profile_id": "farmer"}, {"profile_id": "farmer", "text": " "},
                                  {"text": "hello"}, {"profile_id": "farmer", "text": "x", "lang": "invalid"}])
async def test_invalid_json_rejected_before_stream(db, body):
    app = FastAPI()
    app.include_router(route.router, prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/talk", json=body)).status_code == 422
