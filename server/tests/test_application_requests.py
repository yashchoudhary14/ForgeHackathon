"""Application requests work without a second consent or a live grounding provider."""
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.agents import executor, talk
from app.models import AgentRun, Profile
from app.routers import schemes, talk as route
from app.schemas import SchemeDetail, TalkContext, TalkIn
from app.services import government
from test_talk import db, model_response


@pytest.mark.parametrize("message,key", [
    ("fill my drivers licence for me", "driving_licence"),
    ("Can you fill my driver's licence for me?", "driving_licence"),
    ("Please start my driver’s license", "driving_licence"),
    ("मुझे ड्राइविंग लाइसेंस के लिए आवेदन करना है", "driving_licence"),
    ("ড্রাইভিং লাইসেন্সের জন্য আবেদন করতে চাই", "driving_licence"),
    ("মই ড্ৰাইভিং লাইচেন্সৰ বাবে আবেদন কৰিব বিচাৰোঁ", "driving_licence"),
    ("mera driving licence bana do", "driving_licence"),
    ("apply for passport for me", "passport"),
    ("fill my PM-KISAN form", "pmkisan"),
    ("fill my scholarship scheme form for me", "scholarships"),
    ("start my Vahan application", "vehicle_rc"),
    ("apply for UIDAI for me", "aadhaar"),
    ("start my ECI application", "voter"),
    ("fill my CRS form", "birth_death"),
    ("start my NHA application", "ayushman"),
    ("fill my EPFO form", "epfo"),
    ("start my NSP application", "scholarships"),
    ("fill my CPGRAMS form", "grievance"),
])
async def test_explicit_request_starts_registry_run_in_same_turn(db, monkeypatch, message, key):
    row = await db.get(Profile, "farmer")
    row.data = {**row.data, "state": "Assam"}
    await db.commit()
    monkeypatch.setattr(government, "grounded_answer", AsyncMock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(talk.llm, "generate_content", Mock(side_effect=AssertionError("No planner needed")))
    monkeypatch.setattr(route, "detect_text_language", AsyncMock(return_value="bn"))
    monkeypatch.setattr(route.sarvam, "tts_to_file", AsyncMock(return_value=None))
    start = Mock()
    monkeypatch.setattr(executor.manager, "start", start)
    events = [e async for e in route.conversation(TalkIn(profile_id="farmer", text=message,
        lang="en", context=TalkContext(onboarding=True)), None, "", db)]
    card = next(e["card"] for e in events if e.get("card", {}).get("kind") == "service")
    assert card["service_id"] == key
    assert card["service"] and card["service"] != message
    assert card["official_portal_url"] and card["sources"]
    run = db.session.execute(select(AgentRun)).scalars().one()
    assert run.portal_url == card["official_portal_url"]
    assert run.meta["service_id"] == key
    assert any(e.get("action", {}).get("run_id") == run.id for e in events)
    assert not events[-1]["quick_replies"]
    assert start.call_args.args[0].profile["state"] == "Assam"
    start.assert_called_once()


@pytest.mark.parametrize("message", [
    "How do I fill my drivers licence form?",
    "Can I apply for a passport?",
    "Do not fill my drivers licence for me",
    "Don’t fill my drivers licence for me",
    "Which field should I fill for a driving licence",
    "mera driving licence mat bana do",
    "What is the status of my passport application?",
])
def test_informational_or_refused_application_is_not_consent(message):
    assert not talk.application_consent(message, True, True)


async def test_unrecognized_service_outage_does_not_emit_an_empty_or_raw_text_card(db, monkeypatch):
    monkeypatch.setattr(government, "grounded_answer", AsyncMock(side_effect=RuntimeError("offline")))
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "fill my unrecognized service for me")
    result = await tools.find_service(tools.message)
    assert result["service"] != tools.message
    assert tools.cards == []


@pytest.mark.parametrize("message,query,service,key", [
    ("எனக்காக ஓட்டுநர் உரிமத்திற்கு விண்ணப்பிக்கவும்", "citizen request", "driving_licence", "driving_licence"),
    ("mera gaadi ka registration bhar do", "vehicle registration", None, "vehicle_rc"),
])
async def test_model_can_resolve_other_language_to_registry_without_supplying_a_portal(
        db, monkeypatch, message, query, service, key):
    row = await db.get(Profile, "farmer")
    row.data = {**row.data, "state": "Assam"}
    monkeypatch.setattr(government, "grounded_answer", AsyncMock(side_effect=RuntimeError("offline")))
    args = {"query": query, **({"service": service} if service else {})}
    planner = AsyncMock(return_value=model_response(("find_service", args)))
    monkeypatch.setattr(talk.llm, "generate_content", planner)
    start = Mock()
    monkeypatch.setattr(executor.manager, "start", start)
    tools = talk.TalkTools(db, row, message)
    events = [e async for e in talk.respond(message, "en", [], tools)]
    assert tools.resolved_service == key
    assert any(e.get("action", {}).get("service") == key for e in events)
    run = db.session.execute(select(AgentRun)).scalars().one()
    assert run.portal_url == tools.services[key]["official_portal_url"]
    start.assert_called_once()
    planner.assert_awaited_once()


@pytest.mark.parametrize("fields,url", [
    ({"application": [{"mode": "Online", "url": "https://apply.gov.in/start", "steps_md": ""}]}, "https://apply.gov.in/start"),
    ({"application": [{"mode": "Online", "steps_md": "Visit [apply](https://apply.nic.in/form)."}]}, "https://apply.nic.in/form"),
    ({"references": [{"url": "https://apply.gov.in/form"}]}, "https://apply.gov.in/form"),
    ({"references": [{"link": "https://apply.nic.in/form"}]}, "https://apply.nic.in/form"),
    ({"source_url": "https://ministry.gov.in/scheme"}, "https://ministry.gov.in/scheme"),
    ({}, "https://www.myscheme.gov.in/schemes/test-scheme"),
    ({"application": [{"mode": "Online", "url": "https://gov.in.evil.com", "steps_md": ""}],
      "references": [{"url": "https://gov.in@evil.com"}]}, "https://www.myscheme.gov.in/schemes/test-scheme"),
    ({"application": [{"mode": "Online", "url": "https://apply.gov.in:bad", "steps_md": ""}]}, "https://www.myscheme.gov.in/schemes/test-scheme"),
])
async def test_scheme_application_url_resolution_endpoint(monkeypatch, fields, url):
    detail = SchemeDetail(id="s", slug="test-scheme", name="Official scheme",
                          **{"source_url": "https://example.org", **fields})
    lookup = AsyncMock(return_value=detail)
    monkeypatch.setattr(schemes.myscheme, "get_scheme", lookup)
    app = FastAPI()
    app.include_router(schemes.router, prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/schemes/test-scheme/application-url")
    assert response.status_code == 200
    assert response.json() == {"portal_url": url}
    assert government.scheme_application_url(detail) == url
    lookup.assert_awaited_once_with("test-scheme", lang="en", index=False)
