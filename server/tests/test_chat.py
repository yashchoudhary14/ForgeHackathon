"""Contract and grounding checks; external services and Gemini are mocked only here."""
import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from google.genai import types
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents import chat
from app.models import ChatMessage, Profile
from app.routers import chat as route
from app.schemas import ChatIn, FeedItem, ProfileData, SchemeDetail, SchemeSummary, SearchOut


def response(*calls):
    parts = [types.Part.from_function_call(name=name, args=args) for name, args in calls]
    if not parts:
        parts = [types.Part.from_text(text="ready")]
    parts[0].thought_signature = b"original-signature"
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role="model", parts=parts),
    )])


def mock_final(monkeypatch, sentences, step=7):
    text = json.dumps({"sentences": sentences}, ensure_ascii=False)

    async def stream(contents, cfg):
        assert cfg.response_schema is chat.Answer
        for offset in range(0, len(text), step):
            yield types.GenerateContentResponse(candidates=[types.Candidate(
                content=types.Content(role="model", parts=[types.Part.from_text(text=text[offset:offset + step])]),
            )])

    monkeypatch.setattr(chat.llm, "stream_content", stream)


def test_sse_format_preserves_unicode_and_escapes_newlines():
    event = {"type": "token", "text": 'नमस्ते\n"hello"'}
    encoded = route.sse(event)
    assert encoded.startswith("data: ") and encoded.endswith("\n\n")
    assert "नमस्ते" in encoded
    assert encoded.count("\n") == 2
    assert json.loads(encoded[6:]) == event


def test_citations_drop_fake_quotes_and_unknown_sources():
    sources = {"s1": chat.Source("s1", "https://example.gov.in/a", "Title", "Only resident students may apply.")}
    real = chat.Sentence(text="A supported sentence.", evidence=[chat.Evidence(
        source_id="s1", quote="Only resident students may apply.",
    )])
    assert chat.verified_citations(real, sources)[0].quote == "Only resident students may apply."
    # The shared matcher deliberately accepts fuzzy word overlap; chat must enforce verbatim too.
    fake = "Only students resident may apply."
    assert chat.matcher.quote_found(fake, sources["s1"].text)
    assert chat.verified_citations(chat.Sentence(text="Fake.", evidence=[
        chat.Evidence(source_id="s1", quote=fake),
    ]), sources) == []
    assert chat.verified_citations(chat.Sentence(text="Fake.", evidence=[
        chat.Evidence(source_id="invented", quote="Only resident students may apply."),
    ]), sources) == []
    assert chat.verified_citations(chat.Sentence(text="Uncited.", evidence=[]), sources) == []


@pytest.mark.parametrize("step", [1, 2, 7, 1000])
def test_sentence_parser_handles_arbitrary_json_boundaries(step):
    value = {"text": 'हिंदी [text] with a "quote" and\na newline.', "evidence": [{"source_id": "s1", "quote": "text"}]}
    encoded = json.dumps({"sentences": [value, value]}, ensure_ascii=True)
    parser = chat.SentenceStream()
    decoded = []
    for offset in range(0, len(encoded), step):
        decoded.extend(parser.feed(encoded[offset:offset + step]))
    assert parser.finished
    assert [item.model_dump() for item in decoded] == [value, value]


async def test_tool_error_is_returned_to_model_and_recovers(monkeypatch):
    search = AsyncMock(side_effect=[
        RuntimeError("backend credentials must not escape"),
        SearchOut(total=1, items=[SchemeSummary(slug="test-scheme", name="Test Scheme", brief="Resident students may apply.")]),
    ])
    monkeypatch.setattr(chat, "_service", lambda name: SimpleNamespace(search=search))
    planned = [
        response(("search_schemes", {"keyword": "first"})),
        response(("search_schemes", {"keyword": "retry"})), response(),
    ]
    seen_error = []

    async def generate(contents, cfg):
        if len(planned) == 2:
            result = contents[-1].parts[0].function_response.response
            assert "error" in result and "credentials" not in result["error"]
            seen_error.append(True)
            assert contents[-2].parts[0].thought_signature == b"original-signature"
        return planned.pop(0)

    monkeypatch.setattr(chat.llm, "generate_content", generate)
    mock_final(monkeypatch, [
        {"text": "छात्र आवेदन कर सकते हैं।", "evidence": [{"source_id": "s1", "quote": "Resident students may apply."}]},
        {"text": "Invented benefit.", "evidence": [{"source_id": "s1", "quote": "Every student gets money."}]},
    ])
    tools = chat.ChatTools(ProfileData(state="Bihar", caste="sc", is_student=True), [])
    events = [event async for event in chat.respond("छात्रवृत्ति?", "hi", [], tools)]
    assert seen_error == [True]
    assert [e["type"] for e in events] == [
        "tool_call", "tool_result", "tool_call", "tool_result", "token", "citation",
    ]
    assert events[-2]["text"] == "छात्र आवेदन कर सकते हैं।"
    assert events[-1]["citation"]["source_url"] == "https://www.myscheme.gov.in/schemes/test-scheme"
    assert search.await_args.kwargs["filters"] == {"state": "Bihar", "caste": "sc", "is_student": True}


async def test_document_scope_and_page_citations(monkeypatch):
    retrieve = AsyncMock(return_value=[
        {"text": "Allowed document text", "page": 3, "document_id": "allowed", "title": "Notice", "source_url": None},
        {"text": "Private other document", "page": 1, "document_id": "other", "title": "Other", "source_url": None},
    ])
    monkeypatch.setattr(chat, "_service", lambda name: SimpleNamespace(retrieve=retrieve))
    tools = chat.ChatTools(None, ["allowed"])
    result = await tools.call("search_documents", {"query": "notice"})
    retrieve.assert_awaited_once_with("notice", document_ids=["allowed"], k=6)
    assert len(result["sources"]) == 1
    assert result["sources"][0]["section"] == "page 3"
    assert result["sources"][0]["source_url"] == "document:allowed"
    await chat.ChatTools(None, []).call("search_documents", {"query": "notice"})
    assert retrieve.await_args.kwargs["document_ids"] is None


async def test_scheme_details_and_eligibility_reuse_matcher(monkeypatch):
    scheme = SchemeDetail(
        id="test", slug="test", name="Test", source_url="https://example.gov.in/ignored",
        benefits_md="Benefit text", eligibility_md="Eligibility text", documents_md="D" * 4000,
        application=[{"mode": "Online", "steps_md": "Apply here"}],
    )
    get_scheme = AsyncMock(return_value=scheme)
    judge = AsyncMock(return_value=SimpleNamespace(model_dump=lambda: {"verdict": "unknown"}))
    monkeypatch.setattr(chat, "_service", lambda name: SimpleNamespace(get_scheme=get_scheme))
    monkeypatch.setattr(chat.matcher, "judge", judge)
    profile = ProfileData(state="Bihar")
    tools = chat.ChatTools(profile, [])
    result = await tools.call("get_scheme", {"slug": "test"})
    assert {s["section"] for s in result["sources"]} == {"benefits", "eligibility", "documents", "how to apply (Online)"}
    assert all(len(s["text"]) <= 3000 for s in result["sources"])
    result = await tools.call("check_eligibility", {"slug": "test"})
    assert result["assessment"]["verdict"] == "unknown"
    judge.assert_awaited_once_with(profile, scheme)
    assert "error" in await chat.ChatTools(None, []).call("check_eligibility", {"slug": "test"})


async def test_latest_updates_use_feed_urls(monkeypatch):
    latest = AsyncMock(return_value=[FeedItem(title="Official update", url="https://pib.gov.in/test", source="PIB")])
    monkeypatch.setattr(chat, "_service", lambda name: SimpleNamespace(get_feed=latest))
    result = await chat.ChatTools(None, []).call("latest_updates", {})
    latest.assert_awaited_once_with(limit=10)
    assert result["sources"][0]["source_url"] == "https://pib.gov.in/test"


async def test_tool_timeout_and_invalid_tool_are_recoverable(monkeypatch):
    async def slow(**kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(chat, "TOOL_TIMEOUT", 0.01)
    monkeypatch.setattr(chat, "_service", lambda name: SimpleNamespace(get_feed=slow))
    tools = chat.ChatTools(None, [])
    assert "timed out" in (await tools.call("latest_updates", {}))["error"]
    assert "Unknown tool" in (await tools.call("__dict__", {}))["error"]


async def test_tool_round_limit_and_empty_source_fallback(monkeypatch):
    generate = AsyncMock(side_effect=lambda *args: response(("search_schemes", {"keyword": "retry"})))
    monkeypatch.setattr(chat.llm, "generate_content", generate)
    monkeypatch.setattr(chat, "_service", lambda name: SimpleNamespace(search=AsyncMock(return_value=SearchOut(total=0, items=[]))))
    mock_final(monkeypatch, [{"text": "Unsupported.", "evidence": []}])
    events = [e async for e in chat.respond("question", "hi", [], chat.ChatTools(None, []))]
    assert generate.await_count == 6
    assert len([e for e in events if e["type"] == "tool_call"]) == 6
    assert events[-1] == {"type": "token", "text": chat.NO_ANSWER["hi"]}


async def test_final_sentences_stream_before_generation_finishes_and_close_upstream(monkeypatch):
    monkeypatch.setattr(chat.llm, "generate_content", AsyncMock(return_value=response()))
    closed = asyncio.Event()
    value = {"text": "A supported answer.", "evidence": [{"source_id": "s1", "quote": "Source text"}]}

    async def stream(*args):
        try:
            yield types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(
                role="model", parts=[types.Part.from_text(text='{"sentences":[' + json.dumps(value))],
            ))])
            await asyncio.Event().wait()  # final generation has not completed
        finally:
            closed.set()

    monkeypatch.setattr(chat.llm, "stream_content", stream)
    tools = chat.ChatTools(None, [])
    tools._source("https://example.gov.in/source", "Source", "Source text")
    agent = chat.respond("question", "en", [], tools)
    assert await anext(agent) == {"type": "token", "text": "A supported answer."}
    await agent.aclose()
    assert closed.is_set()


async def test_incomplete_final_json_is_an_error(monkeypatch):
    monkeypatch.setattr(chat.llm, "generate_content", AsyncMock(return_value=response()))

    async def stream(*args):
        yield types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(
            role="model", parts=[types.Part.from_text(text='{"sentences":[')],
        ))])

    monkeypatch.setattr(chat.llm, "stream_content", stream)
    with pytest.raises(ValueError, match="Incomplete"):
        _ = [e async for e in chat.respond("question", "en", [], chat.ChatTools(None, []))]


class AsyncDB:
    """Async facade over real SQLite persistence, avoiding an extra test dependency."""
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

    async def refresh(self, row):
        self.session.refresh(row)


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Profile.__table__.create(engine)
    ChatMessage.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        database = AsyncDB(session)

        @asynccontextmanager
        async def factory():
            yield database

        monkeypatch.setattr(route, "SessionLocal", factory)
        yield database
    engine.dispose()


async def test_history_is_last_ten_in_session_and_both_messages_are_saved(db, monkeypatch):
    for index in range(12):
        db.add(ChatMessage(session_id="own", role="user" if index % 2 == 0 else "assistant", content=str(index)))
    db.add(ChatMessage(session_id="other", role="user", content="other session"))
    db.add(Profile(id="profile", data={"state": "Bihar", "full_name": "private extra field"}, sensitive="encrypted private data"))
    await db.commit()
    citation = {"source_url": "https://example.gov.in/notice", "title": "Notice", "quote": "source text", "section": "page 1"}

    async def respond(message, language, history, tools):
        assert [item["content"] for item in history] == [str(i) for i in range(2, 12)]
        assert tools.profile.model_dump(exclude_none=True) == {"state": "Bihar"}
        assert tools.document_ids == ["doc"]
        yield {"type": "token", "text": "Answer "}
        yield {"type": "token", "text": "text"}
        yield {"type": "citation", "citation": citation}

    monkeypatch.setattr(route, "respond", respond)
    events = [e async for e in route.conversation(ChatIn(
        session_id="own", message="New question", profile_id="profile", document_ids=["doc"],
    ), db)]
    saved = db.session.execute(select(ChatMessage).where(ChatMessage.session_id == "own").order_by(ChatMessage.id)).scalars().all()
    assert len(saved) == 14
    assert saved[-2].role == "user" and saved[-2].content == "New question"
    assert saved[-1].role == "assistant" and saved[-1].content == "Answer text"
    assert saved[-1].citations == [citation]
    assert events[-1] == {"type": "done", "message_id": saved[-1].id}


async def test_http_sse_contract(db, monkeypatch):
    async def respond(*args):
        yield {"type": "tool_call", "name": "latest_updates", "args": {}}
        yield {"type": "tool_result", "name": "latest_updates", "summary": "Retrieved 1 source passages."}
        yield {"type": "token", "text": "नमस्ते"}
        yield {"type": "citation", "citation": {"source_url": "https://pib.gov.in/test", "title": "Title", "quote": "Quote", "section": None}}

    monkeypatch.setattr(route, "respond", respond)
    app = FastAPI()
    app.include_router(route.router, prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post("/api/chat", json={"session_id": "http", "message": "hello", "language": "hi"})
    assert result.status_code == 200
    assert result.headers["content-type"].startswith("text/event-stream")
    assert result.headers["x-accel-buffering"] == "no"
    events = [json.loads(line[6:]) for line in result.text.splitlines() if line.startswith("data: ")]
    assert [e["type"] for e in events] == ["tool_call", "tool_result", "token", "citation", "done"]
    assert isinstance(events[-1]["message_id"], int)


async def test_keepalive_and_disconnect_cancel_work(db, monkeypatch):
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def respond(*args):
        started.set()
        try:
            await asyncio.Event().wait()
            yield {"type": "token", "text": "unreachable"}
        finally:
            cancelled.set()

    monkeypatch.setattr(route, "respond", respond)
    monkeypatch.setattr(route, "KEEPALIVE_SECONDS", 0.01)
    stream = route.event_stream(ChatIn(session_id="cancel", message="question"))
    assert await anext(stream) == ": keepalive\n\n"
    await started.wait()
    assert await anext(stream) == ": keepalive\n\n"
    await stream.aclose()
    assert cancelled.is_set()
    saved = db.session.execute(select(ChatMessage).where(ChatMessage.session_id == "cancel")).scalars().all()
    assert [row.role for row in saved] == ["user"]


async def test_model_failure_closes_with_friendly_error_and_no_done(db, monkeypatch):
    async def respond(*args):
        raise RuntimeError("secret upstream failure")
        yield

    monkeypatch.setattr(route, "respond", respond)
    frames = [frame async for frame in route.event_stream(ChatIn(session_id="error", message="question"))]
    events = [json.loads(frame[6:]) for frame in frames if frame.startswith("data: ")]
    assert len(events) == 1 and events[0]["type"] == "error"
    assert "secret" not in events[0]["message"]
    assert db.session.execute(select(ChatMessage).where(ChatMessage.role == "assistant")).scalars().all() == []


async def test_missing_profile_and_empty_question_do_not_write_messages(db):
    for body in [ChatIn(session_id="a", message=" "), ChatIn(session_id="a", message="hello", profile_id="missing")]:
        events = [event async for event in route.conversation(body, db)]
        assert [e["type"] for e in events] == ["error"]
    assert db.session.execute(select(ChatMessage)).scalars().all() == []
