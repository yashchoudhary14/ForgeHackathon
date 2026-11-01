"""Pending-step explanations and name onboarding retain the Talk privacy boundary."""
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app.agents import executor, intake, talk
from app.models import AgentRun, ChatMessage, Profile
from app.routers import talk as route
from app.schemas import ProfileData, SensitiveData, SttOut, TalkContext, TalkIn, TalkReply
from app.services import crypto, government
from app.services.service_copy import NAME_QUESTION
from test_talk import db, model_response


@pytest.mark.parametrize("language", list(NAME_QUESTION))
async def test_onboarding_asks_name_first_locally(db, monkeypatch, language):
    row = await db.get(Profile, "farmer")
    row.sensitive = crypto.encrypt_json({"phone": "9876543210"})
    await db.commit()
    model = Mock(side_effect=AssertionError("Name question must stay local"))
    monkeypatch.setattr(talk.llm, "generate_content", model)
    monkeypatch.setattr(talk.llm, "stream_content", model)
    extract = AsyncMock(side_effect=AssertionError("No intake before name"))
    monkeypatch.setattr(intake, "extract", extract)
    monkeypatch.setattr(route.sarvam, "tts_to_file", AsyncMock(return_value=None))
    events = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="hello",
        lang=language, context=TalkContext(onboarding=True)), None, "", db)]
    assert events[-1]["text"] == NAME_QUESTION[language]
    extract.assert_not_awaited()
    saved = db.session.execute(select(ChatMessage).where(ChatMessage.role == "assistant")).scalars().one()
    assert {"talk_profile_question": "full_name"} in saved.citations


@pytest.mark.parametrize("voice", [False, True])
@pytest.mark.parametrize("name", ["अनन्या शर्मा", "Ananya Sharma?"])
async def test_pending_name_is_encrypted_before_respond_language_detection_or_intake(db, monkeypatch, voice, name):
    row = await db.get(Profile, "farmer")
    row.sensitive = crypto.encrypt_json({"phone": "9876543210"})
    db.add(ChatMessage(session_id="talk:farmer", role="assistant", content=NAME_QUESTION["hi"],
                       citations=[{"talk_profile_question": "full_name"}]))
    await db.commit()
    monkeypatch.setattr(route.sarvam, "stt", AsyncMock(return_value=SttOut(text="  " + name + "  ", language="hi")))
    monkeypatch.setattr(route.sarvam, "tts_to_file", AsyncMock(return_value=None))
    extract = AsyncMock(side_effect=AssertionError("Name must never enter intake"))
    monkeypatch.setattr(intake, "extract", extract)
    detect = AsyncMock(return_value="hi")
    monkeypatch.setattr(route, "detect_text_language", detect)
    seen = []

    async def respond(message, language, history, tools):
        seen.append(message)
        assert name not in message + str(history) + str(tools.context)
        assert tools.context["needs_name"] is False
        assert tools.profile_question == "state"
        assert "full_name" not in tools.profile.model_dump()
        assert crypto.decrypt_json(tools.row.sensitive)["full_name"] == name
        yield {"type": "reply", **TalkReply(text="आप किस राज्य में रहते हैं?").model_dump()}

    monkeypatch.setattr(route, "respond", respond)
    body = TalkIn(profile_id="farmer", text=None if voice else "  " + name + "  ",
                  context=TalkContext(onboarding=True))
    _ = [e async for e in route.conversation(body, b"voice" if voice else None, "audio/wav", db)]
    assert seen == ["  [private]  "]
    extract.assert_not_awaited()
    assert name not in str(detect.await_args_list)
    assert crypto.decrypt_json(row.sensitive) == {"phone": "9876543210", "full_name": name}
    assert name not in str(row.data) + str(row.sensitive)
    assert all(name not in r.content for r in db.session.execute(select(ChatMessage)).scalars())


async def test_saved_name_is_not_requested_again_and_other_fields_keep_order(db, monkeypatch):
    row = await db.get(Profile, "farmer")  # fixture already has encrypted full_name
    extract = AsyncMock(return_value=(ProfileData(age=46), SensitiveData()))
    monkeypatch.setattr(intake, "extract", extract)
    monkeypatch.setattr(route.sarvam, "tts_to_file", AsyncMock(return_value=None))

    async def stream(contents, cfg, model):
        assert "The next question must ask for state" in cfg.system_instruction
        assert "Private Citizen" not in str(contents) + str(cfg)
        yield model_response(reply=TalkReply(text="Which state do you live in?"))

    monkeypatch.setattr(talk.llm, "stream_content", stream)
    events = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="hello", lang="en",
        context=TalkContext(onboarding=True)), None, "", db)]
    assert events[-1]["text"] == "Which state do you live in?"
    extract.assert_awaited_once()


@pytest.mark.parametrize("kind,capture", [("confirm_upload", False), ("confirm_upload", True),
                                         ("missing_field", False), ("capture_required", True)])
@pytest.mark.parametrize("question,language", [("which document is that?", "en"),
    ("yeh kaunsa document hai?", "hi"), ("এটা কোন নথি?", "bn")])
async def test_pending_step_explanation_has_redacted_details_and_current_language(
        db, monkeypatch, kind, capture, question, language):
    run = AgentRun(profile_id="farmer", portal_url="https://sarathi.parivahan.gov.in", goal="Apply", kind="application")
    db.add(run)
    await db.commit()
    pending = {"kind": kind, "field": "income_certificate", "doc_type": "income_certificate",
               "message": "Provide income certificate for Private Citizen (9876543210), secret answer. Attach Private scan.pdf.",
               "capture_required": capture, "request_id": "private-request",
               "value": "personal field value", "document": {"title": "Private scan.pdf", "meta": {"full_name": "Private Citizen"}}}
    live = NS(pending=pending, sensitive={"full_name": "Private Citizen", "phone": "9876543210"},
              answers={"answer": "secret answer"}, private_values=set())
    monkeypatch.setattr(executor.manager, "get", Mock(return_value=live))
    monkeypatch.setattr(executor.manager, "set_language", Mock())
    monkeypatch.setattr(route, "detect_text_language", AsyncMock(return_value=language))
    monkeypatch.setattr(route.sarvam, "tts_to_file", AsyncMock(return_value=None))
    search = AsyncMock(return_value={"text": "Verified document explanation.", "sources": []})
    monkeypatch.setattr(government, "grounded_answer", search)

    async def generate(contents, cfg, model):
        assert "who issues it and how to obtain it" in cfg.system_instruction
        assert talk.explainer.LANG_NAMES[language] in cfg.system_instruction
        assert "income_certificate" in cfg.system_instruction
        for private in ("Private Citizen", "9876543210", "secret answer", "Private scan.pdf",
                        "personal field value", "private-request"):
            assert private not in str(contents) + str(cfg)
        return model_response(("grounded_answer", {"query": question}))

    monkeypatch.setattr(talk.llm, "generate_content", generate)
    events = [e async for e in route.conversation(TalkIn(profile_id="farmer", text=question, lang=language,
        context=TalkContext(run_id=run.id, pending_step=kind, onboarding=True)), None, "", db)]
    query, lang = search.await_args.args
    assert "income_certificate" in query and "Provide income certificate" in query
    assert lang == language
    assert live.pending is pending  # explaining does not resume or approve anything
    assert not any(e["type"] == "action" for e in events)


async def test_another_profiles_run_never_supplies_pending_context(db, monkeypatch):
    db.add(AgentRun(id="other-run", profile_id="someone-else", portal_url="https://crsorgi.gov.in", goal="Apply"))
    await db.commit()
    get = Mock(side_effect=AssertionError("Cannot read another citizen's session"))
    monkeypatch.setattr(executor.manager, "get", get)
    monkeypatch.setattr(route.sarvam, "tts_to_file", AsyncMock(return_value=None))

    async def respond(message, language, history, tools):
        assert "pending_step" not in tools.context
        yield {"type": "reply", **TalkReply(text="Which document do you mean?").model_dump()}

    monkeypatch.setattr(route, "respond", respond)
    _ = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="which document?", lang="en",
        context=TalkContext(run_id="other-run", pending_step="confirm_upload")), None, "", db)]
    get.assert_not_called()
