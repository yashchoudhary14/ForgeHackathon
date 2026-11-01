"""Offline Buddy UI handoffs, speech latency and private portal answers."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI

from app.agents import executor, talk
from app.models import AgentRun, Profile
from app.routers import talk as route
from app.schemas import ProfileData, SchemeDetail, SensitiveData, TalkContext, TalkIn, TalkReply
from app.services import sarvam
from test_talk import db, model_response, mock_brain


@pytest.mark.parametrize("name,args,action", [
    ("navigate", {"route": "/locker"}, {"type": "navigate", "route": "/locker"}),
    ("show_profile", {}, {"type": "show_profile"}),
    ("open_report", {}, {"type": "open_report"}),
    ("open_camera", {"doc_type": "income_certificate", "reason": "Income proof"},
     {"type": "open_camera", "doc_type": "income_certificate", "reason": "Income proof"}),
])
async def test_ui_tools_are_explicit_events(db, name, args, action):
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "help")
    assert "error" not in await tools.call(name, args)
    assert tools.actions == [action]


async def test_ui_tools_reject_external_routes_private_fields_and_unsolicited_language(db):
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "hello")
    for name, args in [("navigate", {"route": "//evil.example"}), ("open_camera", {"doc_type": "password", "reason": ""}),
                       ("fill_profile_field", {"field": "phone", "value": "9876543210"}), ("set_language", {"lang": "hi"})]:
        assert "error" in await tools.call(name, args)
    assert not tools.actions


async def test_open_scheme_resolves_the_official_slug_and_language_switch_is_explicit(db, monkeypatch):
    monkeypatch.setattr(talk.myscheme, "get_scheme", AsyncMock(return_value=SchemeDetail(id="s", slug="official", name="Official", source_url="https://www.myscheme.gov.in/schemes/official")))
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "Please speak Hindi")
    await tools.call("open_scheme", {"slug": "official"})
    await tools.call("set_language", {"lang": "hi"})
    assert tools.actions == [{"type": "open_scheme", "slug": "official"}, {"type": "set_language", "lang": "hi"}]
    assert (await db.get(Profile, "farmer")).language == "hi"


async def test_field_action_uses_extracted_citizen_fact_not_invented_tool_value(db, monkeypatch):
    monkeypatch.setattr(talk.intake, "extract", AsyncMock(return_value=(ProfileData(age=23), SensitiveData())))
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "I am 23")
    await tools.call("fill_profile_field", {"field": "age", "value": "90"})
    assert tools.actions == [{"type": "fill_profile_field", "field": "age", "value": 23}]
    assert (await db.get(Profile, "farmer")).data["age"] == 23


async def test_action_sse_is_emitted_before_final_reply(db, monkeypatch):
    monkeypatch.setattr(talk.llm, "generate_content", AsyncMock(return_value=model_response(("show_profile", {}))))
    async def stream(*args, **kwargs):
        yield SimpleNamespace(text=TalkReply(text="Your profile is open.").model_dump_json())
    monkeypatch.setattr(talk.llm, "stream_content", stream)
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "open profile")
    events = [e async for e in talk.respond(tools.message, "en", [], tools)]
    assert next(e for e in events if e["type"] == "action")["action"] == {"type": "show_profile"}
    assert [e["type"] for e in events].index("action") < [e["type"] for e in events].index("delta")


async def test_context_checks_owner_and_never_sends_id_or_query_to_model(db, monkeypatch):
    mock_brain(monkeypatch)
    db.add(Profile(id="other", data={}))
    db.add(AgentRun(id="private-run", profile_id="other", portal_url="https://portal.gov.in", goal="private"))
    await db.commit()
    contexts = []
    async def respond(message, language, history, tools):
        contexts.append(tools.context)
        yield {"type": "reply", "text": "Hello.", "quick_replies": []}
    monkeypatch.setattr(route, "respond", respond)
    _ = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="hi", lang="en", context=TalkContext(
        page="/locker?phone=9876543210", run_id="private-run", pending_step="otp")), None, "", db)]
    assert contexts == [{"page": "/", "onboarding": False}]
    assert "9876543210" not in str(contexts) and "private-run" not in str(contexts)


async def test_current_scheme_is_resolved_from_official_data_before_model_context(db, monkeypatch):
    mock_brain(monkeypatch)
    get_scheme = AsyncMock(return_value=SimpleNamespace(slug="official-support"))
    monkeypatch.setattr(route.myscheme, "get_scheme", get_scheme)
    async def respond(message, language, history, tools):
        assert tools.context == {"page": "/schemes/:slug", "onboarding": False, "scheme_slug": "official-support"}
        assert "official-support" in tools.known_slugs
        yield {"type": "reply", "text": "Ready to help.", "quick_replies": []}
    monkeypatch.setattr(route, "respond", respond)
    _ = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="help with this", lang="en", context=TalkContext(page="/schemes/official-support")), None, "", db)]
    get_scheme.assert_awaited_once_with("official-support", lang="en", index=False)


async def test_multipart_accepts_context_and_speech_option(db, monkeypatch):
    mock_brain(monkeypatch)
    monkeypatch.setattr(route.sarvam, "stt", AsyncMock(return_value=SimpleNamespace(text="hello", language="en")))
    app = FastAPI(); app.include_router(route.router, prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post("/api/talk", data={"profile_id": "farmer", "lang": "en", "context": '{"page":"/locker","pending_step":null,"run_id":null}', "stream_audio": "true"}, files={"audio": ("clip.webm", b"audio", "audio/webm")})
    assert result.status_code == 200 and '"type":"done"' in result.text


async def test_first_sentence_audio_arrives_while_scheme_tool_is_still_blocked(monkeypatch):
    release, cancelled = asyncio.Event(), asyncio.Event()
    async def events():
        try:
            yield {"type": "delta", "text": "I am checking official schemes. "}
            await release.wait()
            yield {"type": "card", "card": {"kind": "scheme", "slug": "s"}}
        finally:
            cancelled.set()
    monkeypatch.setattr(route.sarvam, "tts_to_file", AsyncMock(return_value="/files/first.wav"))
    output = route.spoken_events(events(), "en", True)
    assert (await anext(output))["type"] == "delta"
    audio = await asyncio.wait_for(anext(output), 1)
    assert audio["type"] == "audio" and not release.is_set()
    await output.aclose()
    assert cancelled.is_set()


async def test_sentence_audio_is_not_repeated_in_final_audio(db, monkeypatch):
    mock_brain(monkeypatch)
    async def respond(*args):
        yield {"type": "delta", "text": "Here is the first sentence. "}
        yield {"type": "delta", "text": "Here is the next one."}
        yield {"type": "reply", "text": "Here is the first sentence. Here is the next one.", "quick_replies": []}
    monkeypatch.setattr(route, "respond", respond)
    speech = AsyncMock(side_effect=["/files/first.wav", "/files/rest.wav"])
    monkeypatch.setattr(route.sarvam, "tts_to_file", speech)
    events = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="hello", lang="en", stream_audio=True), None, "", db)]
    assert [call.args[0] for call in speech.await_args_list] == ["Here is the first sentence.", "Here is the next one."]
    assert [e for e in events if e["type"] == "audio"] == [{"type": "audio", "audio_url": "/files/first.wav"}]
    assert events[-1]["audio_url"] == "/files/rest.wav"


async def test_onboarding_saves_one_answer_without_scheme_matching_or_tool_planner(db, monkeypatch):
    mock_brain(monkeypatch)
    extract = AsyncMock(return_value=(ProfileData(state="Bihar"), SensitiveData()))
    monkeypatch.setattr(talk.intake, "extract", extract)
    match = AsyncMock(); monkeypatch.setattr(talk.matcher, "first_matches", match)
    _ = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="Bihar", lang="en", context=TalkContext(onboarding=True)), None, "", db)]
    assert (await db.get(Profile, "farmer")).data["state"] == "Bihar"
    extract.assert_awaited_once(); match.assert_not_awaited()


async def test_short_onboarding_no_is_tied_to_the_question_being_asked(db, monkeypatch):
    mock_brain(monkeypatch)
    row = await db.get(Profile, "farmer")
    row.data = {"state": "Bihar", "age": 23, "gender": "female", "occupation": "farmer"}
    await db.commit()
    extract = AsyncMock(return_value=(ProfileData(is_student=False), SensitiveData()))
    monkeypatch.setattr(talk.intake, "extract", extract)
    _ = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="no", lang="en", context=TalkContext(onboarding=True)), None, "", db)]
    assert extract.await_args.args[0] == "Answer to profile question is_student: no"
    assert row.data["is_student"] is False


async def test_capture_waits_for_resume_then_selects_bounded_variant(monkeypatch):
    item = SimpleNamespace(id="doc", profile_id="farmer", doc_type="income_certificate", meta={"readable": True, "detected_doc_type": "income_certificate"}, variants=[{"format": "jpg", "bytes": 150000, "path": "encrypted"}])
    wrong = SimpleNamespace(**{**item.__dict__, "meta": {"readable": True, "detected_doc_type": "aadhaar"}})
    rounds = iter([[wrong], [item]])
    def query_result(query):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: next(rounds)))
    database = SimpleNamespace(execute=AsyncMock(side_effect=query_result))
    @asynccontextmanager
    async def session(): yield database
    monkeypatch.setattr(executor, "SessionLocal", session)
    rs = executor.RunSession("run", "", "https://portal.gov.in", {}, {}, profile_id="farmer")
    rs.set_status = AsyncMock(); rs.human_event = AsyncMock(return_value={"kind": "confirm_upload"})
    rs.wait_human = AsyncMock(return_value={"type": "resume"})
    result, variant = await rs.document_for_upload("income_certificate", 3, ".jpg", "200 KB")
    assert result is item and variant["bytes"] <= 200000
    assert rs.human_event.await_args.kwargs["capture_required"] is True
    assert rs.human_event.await_args.kwargs["doc_type"] == "income_certificate"
    rs.wait_human.assert_awaited_once_with({"kind": "confirm_upload"}, {"resume"})


async def test_missing_or_stale_confirmation_cannot_fill_a_new_request():
    rs = executor.RunSession("run", "", "https://portal.gov.in", {}, {})
    rs.emit = AsyncMock()
    for message in [{"type": "human_input", "value": "old"}, {"type": "human_input", "value": "old", "request_id": "previous"}, {"type": "human_input", "value": "new", "request_id": "current"}]:
        await rs.inbox.put(message)
    response = await rs.wait_human({"type": "needs_human", "request_id": "current"}, {"human_input"})
    assert response["value"] == "new" and rs.pending is None


async def test_private_audio_never_falls_back_to_gemini(monkeypatch):
    monkeypatch.setattr(sarvam, "get_settings", lambda: SimpleNamespace(sarvam_api_key=""))
    generate = AsyncMock(); monkeypatch.setattr(sarvam.llm, "generate_json", generate)
    with pytest.raises(RuntimeError, match="SARVAM_API_KEY"):
        await sarvam.stt(b"private OTP recording", "audio/webm", "hi")
    generate.assert_not_awaited()


async def test_portal_question_translation_cannot_fall_back_to_gemini(monkeypatch):
    monkeypatch.setattr(sarvam, "get_settings", lambda: SimpleNamespace(sarvam_api_key=""))
    with pytest.raises(RuntimeError, match="Private translation"):
        await sarvam.translate("private portal question", "en", "hi", allow_llm=False)


def test_language_changes_only_affect_this_profiles_live_runs():
    manager = executor.RunManager()
    mine = executor.RunSession("mine", "", "https://portal.gov.in", {}, {}, profile_id="owner")
    other = executor.RunSession("other", "", "https://portal.gov.in", {}, {}, profile_id="other")
    manager.sessions = {"mine": mine, "other": other}
    manager.set_language("owner", "hi")
    assert mine.language == "hi" and other.language == "en"
