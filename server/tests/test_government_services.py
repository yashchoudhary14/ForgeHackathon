"""Offline service routing, search evidence and consent-bound browser handoffs."""
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app.agents import executor, talk
from app.models import AgentRun, Profile
from app.routers import talk as route
from app.schemas import TalkContext, TalkIn, TalkReply
from app.services import government
from app.services.services_registry import REGISTRY, https_url, match_service, official_url
from test_talk import db, model_response


def service(key="driving_licence", steps=True):
    entry = next(s for s in REGISTRY if s.key == key)
    return {"service_id": key, "service": entry.name, "official_portal_url": entry.portal,
            "steps": ["Select your state and the requested licence service."] if steps else [],
            "documents": [], "fees": None, "time": None, "notes": [],
            "sources": [{"url": entry.verification_url, "title": entry.name}]}


def final_stream(reply):
    async def stream(*args, **kwargs):
        yield NS(text=reply.model_dump_json())
    return stream


def test_registry_contains_verified_https_portals_and_only_explicit_provider_exceptions():
    assert len({s.key for s in REGISTRY}) == len(REGISTRY)
    external = set()
    for entry in REGISTRY:
        assert https_url(entry.portal)
        assert official_url(entry.verification_url)
        if not official_url(entry.portal):
            external.add(entry.portal)
    assert external == {"https://www.onlineservices.nsdl.com", "https://www.pan.utiitsl.com"}


@pytest.mark.parametrize("url", ["http://sarathi.parivahan.gov.in", "javascript:alert(1)",
    "https://gov.in.evil.com", "https://gov.in@evil.com", "https://user:password@portal.gov.in",
    "https://portal.gov.in:8080", "https://portal.gov.in:bad", "https://evil.com/gov.in"])
def test_portal_validation_rejects_spoofed_or_unsafe_urls(url):
    assert not official_url(url)


@pytest.mark.parametrize("query,key", [("apply for a driving licence", "driving_licence"),
    ("driving license", "driving_licence"), ("learner's licence", "learner_licence"),
    ("instant e-PAN", "epan"), ("PAN through UTIITSL", "pan_uti"),
    ("ड्राइविंग लाइसेंस बनवाना है", "driving_licence"), ("passport", "passport")])
def test_service_names_resolve_without_myscheme(query, key):
    assert match_service(query).key == key
    assert talk.service_request(query)


def test_programme_eligibility_and_service_requests_have_distinct_routes():
    assert not talk.service_request("Am I eligible for PM-KISAN benefits?")
    assert not talk.service_request("Find scholarship schemes for me")
    assert talk.service_request("How do I register for PM-KISAN?")
    assert talk.service_request("Am I eligible for a driving licence?")
    assert talk.service_request("Apply for a ration card in Kerala")
    assert not talk.service_request("Why is the sky blue?")


async def test_driving_request_routes_to_service_and_builds_guarded_run(db, monkeypatch):
    finder = AsyncMock(return_value=service())
    schemes = AsyncMock()
    monkeypatch.setattr(government, "find_service", finder)
    monkeypatch.setattr(talk.matcher, "first_matches", schemes)
    planner = AsyncMock()
    monkeypatch.setattr(talk.llm, "generate_content", planner)
    monkeypatch.setattr(talk.llm, "stream_content", final_stream(TalkReply(text="I am opening guided help.")))
    start = Mock()
    monkeypatch.setattr(executor.manager, "start", start)
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "apply for a driving licence")
    events = [event async for event in talk.respond(tools.message, "en", [], tools)]
    finder.assert_awaited_once_with(tools.message, "en", None)
    schemes.assert_not_awaited()
    planner.assert_not_awaited()
    run = db.session.execute(select(AgentRun)).scalars().one()
    assert run.scheme_slug is None and run.meta["service_id"] == "driving_licence"
    assert run.portal_url == "https://sarathi.parivahan.gov.in"
    for expected in ["Select your state", "value_from", "locker", "Buddy", "OTP", "CAPTCHA", "login", "payment", "approval", "final submit"]:
        assert expected in run.goal
    assert "9876543210" not in run.goal and "Private Citizen" not in run.goal
    session = start.call_args.args[0]
    assert session.sensitive["phone"] == "9876543210"  # passed locally, never to Gemini
    assert any(e["type"] == "action" and e["action"].get("service") == "driving_licence" for e in events)
    assert any(e["type"] == "card" and e["card"]["kind"] == "sources" for e in events)


@pytest.mark.parametrize("message,offered,allowed", [
    ("How do I apply for a driving licence?", False, False),
    ("Do not apply for a driving licence", True, False),
    ("yes, explain first", True, False), ("yes", False, False),
    ("yes, but later", True, False),
    ("driving licence application status", False, False),
    ("I already submitted my driving licence application", False, False),
    ("apply for a passport", False, False),
    ("apply for a driving licence", False, True), ("yes", True, True),
    ("हाँ", True, True), ("ড্রাইভিং লাইসেন্সের আবেদন করুন", False, True),
])
async def test_service_start_requires_specific_citizen_consent(db, monkeypatch, message, offered, allowed):
    details = service()
    history = [{"role": "assistant", "content": "May I help apply?", "services": [details],
                "offer_service": "driving_licence" if offered else None}]
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), message, history)
    start = Mock()
    monkeypatch.setattr(executor.manager, "start", start)
    result = await tools.call("start_application", {"service": "driving_licence"})
    assert ("card" in result) == allowed
    assert start.called == allowed
    if allowed:
        assert await tools.call("start_application", {"service": "driving_licence"}) == result
        start.assert_called_once()


async def test_how_to_request_shows_service_without_starting_agent(db, monkeypatch):
    monkeypatch.setattr(government, "find_service", AsyncMock(return_value=service()))
    monkeypatch.setattr(talk.llm, "stream_content", final_stream(TalkReply(text="Which state are you in?")))
    start = Mock()
    monkeypatch.setattr(executor.manager, "start", start)
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "How do I apply for a driving licence?")
    events = [e async for e in talk.respond(tools.message, "en", [], tools)]
    assert any(e.get("card", {}).get("kind") == "service" for e in events)
    start.assert_not_called()


async def test_service_request_cannot_accidentally_fall_back_to_scheme_matcher(db, monkeypatch):
    match = AsyncMock()
    monkeypatch.setattr(talk.matcher, "first_matches", match)
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "apply for a driving licence")
    result = await tools.call("find_schemes", {"keyword": "driving licence"})
    assert "find_service" in result["error"]
    match.assert_not_awaited()


async def test_pan_provider_is_guide_only_and_opens_verified_link(db, monkeypatch):
    details = service("pan")
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "apply for a PAN card")
    tools.services["pan"] = details
    start = Mock()
    monkeypatch.setattr(executor.manager, "start", start)
    result = await tools.call("start_application", {"service": "pan"})
    assert result["status"] == "guide_only"
    assert tools.actions == [{"type": "open_portal", "url": "https://www.onlineservices.nsdl.com"}]
    assert not db.session.execute(select(AgentRun)).scalars().all()
    start.assert_not_called()


async def test_start_rejects_unretrieved_service_and_missing_grounded_steps(db, monkeypatch):
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "apply for a driving licence")
    assert "error" in await tools.call("start_application", {"service": "https://evil.com"})
    assert "error" in await tools.call("start_application", {"slug": "s", "service": "driving_licence"})
    tools.services["driving_licence"] = service(steps=False)
    assert "verified" in (await tools.call("start_application", {"service": "driving_licence"}))["error"]
    assert not db.session.execute(select(AgentRun)).scalars().all()


def grounded_response():
    chunks = [NS(web=NS(uri="https://transport.gov.in/licence", title="Transport")),
              NS(web=NS(uri="https://unofficial.example/advice", title="Unofficial"))]
    supports = [NS(segment=NS(text="Select your state."), grounding_chunk_indices=[0]),
                NS(segment=NS(text="Everyone gets guaranteed approval."), grounding_chunk_indices=[1]),
                NS(segment=NS(text="Unsupported claim."), grounding_chunk_indices=[])]
    return NS(candidates=[NS(grounding_metadata=NS(grounding_chunks=chunks, grounding_supports=supports))])


async def test_grounding_uses_google_search_and_discards_unofficial_unsupported_passages(monkeypatch):
    generate = AsyncMock(return_value=grounded_response())
    monkeypatch.setattr(government.llm, "generate_content", generate)
    result = await government.grounded_answer("licence steps", "hi", official_only=True)
    assert result == {"text": "Select your state.", "sources": [{"url": "https://transport.gov.in/licence", "title": "Transport"}]}
    config = generate.await_args.args[1]
    assert config.tools[0].google_search is not None
    assert "site:gov.in" in config.system_instruction and "hi" in config.system_instruction
    assert generate.await_args.kwargs["model"] == "strong"


async def test_missing_grounding_metadata_never_turns_model_draft_into_evidence(monkeypatch):
    monkeypatch.setattr(government.llm, "generate_content", AsyncMock(return_value=NS(text="Invented fees", candidates=[])))
    assert await government.grounded_answer("fees", "en") == {"text": "", "sources": []}


async def test_service_structure_keeps_only_grounded_excerpts_and_registry_portal(monkeypatch):
    evidence = {"text": "Choose your state. Proof of residence. Fees vary by state.",
                "sources": [{"url": "https://transport.gov.in/guide", "title": "Guide"}]}
    monkeypatch.setattr(government, "grounded_answer", AsyncMock(return_value=evidence))
    monkeypatch.setattr(government.llm, "generate_json", AsyncMock(return_value=government.ServiceExtraction(
        service="Invented", official_portal_url="https://evil.com", steps=["Choose your state.", "Skip verification."],
        documents=["Proof of residence."], fees="₹999", time="1 day", notes=["Fees vary by state."])))
    result = await government.find_service("driving licence", "en", "Bihar")
    assert result["official_portal_url"] == "https://sarathi.parivahan.gov.in"
    assert result["steps"] == ["Choose your state."] and result["documents"] == ["Proof of residence."]
    assert result["fees"] is None and result["time"] is None
    assert result["notes"] == ["Fees vary by state."]


async def test_unknown_service_uses_official_search_and_requires_source_backed_portal(monkeypatch):
    search = AsyncMock(return_value={"text": "Apply through the state portal.",
        "sources": [{"url": "https://kerala.gov.in/ration", "title": "Kerala"}]})
    monkeypatch.setattr(government, "grounded_answer", search)
    extract = AsyncMock(return_value=government.ServiceExtraction(service="Ration card",
        official_portal_url="https://madeup.gov.in", steps=["Apply through the state portal."]))
    monkeypatch.setattr(government.llm, "generate_json", extract)
    result = await government.find_service("ration card", "en", "Kerala")
    assert search.await_args.kwargs == {"official_only": True}
    assert json.loads(search.await_args.args[0])["state"] == "Kerala"
    assert result["official_portal_url"] is None
    extract.return_value.official_portal_url = "https://kerala.gov.in/ration"
    assert (await government.find_service("ration card", "en", "Kerala"))["official_portal_url"] == "https://kerala.gov.in/ration"


async def test_registry_still_works_without_live_search_and_does_not_invent_details(monkeypatch):
    monkeypatch.setattr(government, "grounded_answer", AsyncMock(side_effect=RuntimeError("provider secret")))
    result = await government.find_service("driving licence", "hi")
    assert result["official_portal_url"] == "https://sarathi.parivahan.gov.in"
    assert not result["steps"] and not result["documents"] and result["fees"] is None
    assert "provider secret" not in str(result)


async def test_general_question_falls_back_to_grounded_answer_and_links(db, monkeypatch):
    monkeypatch.setattr(talk.llm, "generate_content", AsyncMock(return_value=model_response()))
    search = AsyncMock(return_value={"text": "A supported answer.", "sources": [{"url": "https://science.gov.in", "title": "Science"}]})
    monkeypatch.setattr(government, "grounded_answer", search)
    monkeypatch.setattr(talk.llm, "stream_content", final_stream(TalkReply(text="A supported answer.")))
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "Why is the sky blue?")
    events = [e async for e in talk.respond(tools.message, "hi", [], tools)]
    search.assert_awaited_once_with(tools.message, "en")  # persisted session language on the tools
    assert any(e.get("card", {}).get("kind") == "sources" for e in events)


async def test_service_offer_survives_persistence_and_yes_is_bound_to_it(db, monkeypatch):
    monkeypatch.setattr(government, "find_service", AsyncMock(return_value=service()))
    monkeypatch.setattr(route.sarvam, "tts_to_file", AsyncMock(return_value=None))
    monkeypatch.setattr(talk.llm, "stream_content", final_stream(TalkReply(
        text="Shall I help you apply?", application_offer_service="driving_licence")))
    first = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="driving licence", lang="en"), None, "", db)]
    assert first[-1]["type"] == "done"
    start = Mock()
    monkeypatch.setattr(executor.manager, "start", start)
    monkeypatch.setattr(talk.llm, "stream_content", final_stream(TalkReply(text="Opening guided help.")))
    second = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="yes", lang="en"), None, "", db)]
    assert any(e["type"] == "action" and e["action"]["type"] == "start_application" for e in second)
    start.assert_called_once()


async def test_grounded_facts_are_not_rewritten_by_final_model(db, monkeypatch):
    details = {**service(), "guidance": "Select your state. Fees depend on the selected service."}
    monkeypatch.setattr(government, "find_service", AsyncMock(return_value=details))
    rewrite = Mock(side_effect=AssertionError("Supported claims must not be rewritten"))
    monkeypatch.setattr(talk.llm, "stream_content", rewrite)
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "driving licence")
    events = [e async for e in talk.respond(tools.message, "en", [], tools)]
    reply = events[-1]
    assert reply["text"] == details["guidance"] + "\n\nWould you like help applying?"
    assert reply["application_offer_service"] == "driving_licence"
    rewrite.assert_not_called()


async def test_a_question_can_interrupt_onboarding_without_forcing_profile_matching(db, monkeypatch):
    details = {**service(), "guidance": "Select your state."}
    finder = AsyncMock(return_value=details)
    monkeypatch.setattr(government, "find_service", finder)
    intake = AsyncMock()
    monkeypatch.setattr(talk.intake, "extract", intake)
    monkeypatch.setattr(route.sarvam, "tts_to_file", AsyncMock(return_value=None))
    events = [e async for e in route.conversation(TalkIn(profile_id="farmer", text="How do I apply for a driving licence?",
              lang="en", context=TalkContext(onboarding=True)), None, "", db)]
    assert any(e.get("card", {}).get("kind") == "service" for e in events)
    finder.assert_awaited_once()
    intake.assert_not_awaited()


async def test_service_followup_is_grounded_again_with_public_context(db, monkeypatch):
    details = service()
    finder = AsyncMock(return_value={**details, "guidance": "Current grounded documents."})
    monkeypatch.setattr(government, "find_service", finder)
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "What documents do I need?",
                           [{"role": "assistant", "content": "Previous answer", "services": [details]}])
    await tools.call("find_service", {"query": "invented unrelated search"})
    query = finder.await_args.args[0]
    assert "What documents" in query and "Driving licence" in query
    assert "invented" not in query and "9876543210" not in query


async def test_google_citation_redirects_are_resolved_without_fetching_destination(monkeypatch):
    requests = []
    class Response:
        status_code = 302
        headers = {"location": "https://transport.gov.in/licence"}
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    class Client:
        def __init__(self, **kwargs): assert kwargs["follow_redirects"] is False
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def stream(self, method, uri):
            requests.append(uri)
            return Response()
    monkeypatch.setattr(government.httpx, "AsyncClient", Client)
    uri = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/test"
    assert await government.source_url(uri) == "https://transport.gov.in/licence"
    assert requests == [uri]
    assert await government.source_url("https://vertexaisearch.cloud.google.com/other") is None


async def test_creative_request_can_be_answered_without_search_or_service_run(db, monkeypatch):
    monkeypatch.setattr(talk.llm, "generate_content", AsyncMock(return_value=model_response()))
    search = AsyncMock()
    monkeypatch.setattr(government, "grounded_answer", search)
    reply = TalkReply(text="A little poem about the morning.")
    monkeypatch.setattr(talk.llm, "stream_content", final_stream(reply))
    tools = talk.TalkTools(db, await db.get(Profile, "farmer"), "Please write a short poem")
    events = [e async for e in talk.respond(tools.message, "en", [], tools)]
    assert events[-1]["text"] == reply.text
    search.assert_not_awaited()
    assert not talk.direct_task("Write the fees and documents needed for a driving licence")
    assert talk.asks_for_help("कविता लिखो")
