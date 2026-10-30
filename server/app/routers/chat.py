"""POST chat with JSON SSE events and keepalives during tools and model calls."""
import asyncio
import json
import logging
from contextlib import aclosing, suppress

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..agents.chat import ChatTools, respond
from ..db import SessionLocal
from ..models import ChatMessage, Profile
from ..schemas import ChatIn, ProfileData

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])
KEEPALIVE_SECONDS = 10


def sse(event: dict) -> str:
    return "data: " + json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n\n"


async def conversation(body: ChatIn, db):
    if not body.message.strip():
        yield {"type": "error", "message": "Please enter a question before sending."}
        return
    profile = None
    if body.profile_id:
        row = await db.get(Profile, body.profile_id)
        if row is None:
            yield {"type": "error", "message": "That profile could not be found. Please select a saved profile."}
            return
        # Whitelist ProfileData fields; never decrypt or pass Profile.sensitive to Gemini.
        profile = ProfileData.model_validate(row.data)
    rows = (await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == body.session_id)
        .order_by(ChatMessage.id.desc()).limit(10)
    )).scalars().all()
    history = [{"role": row.role, "content": row.content} for row in reversed(rows)]
    db.add(ChatMessage(session_id=body.session_id, role="user", content=body.message))
    await db.commit()

    text, citations = [], []
    async with aclosing(respond(body.message, body.language, history, ChatTools(profile, body.document_ids))) as events:
        async for event in events:
            if event["type"] == "token":
                text.append(event["text"])
            elif event["type"] == "citation":
                citations.append(event["citation"])
            yield event
    answer = ChatMessage(
        session_id=body.session_id, role="assistant", content="".join(text), citations=citations,
    )
    db.add(answer)
    await db.commit()
    await db.refresh(answer)
    yield {"type": "done", "message_id": answer.id}


async def event_stream(body: ChatIn):
    queue: asyncio.Queue = asyncio.Queue(maxsize=16)

    async def produce():
        try:
            # Own the DB session inside the stream, independent of FastAPI dependency teardown.
            async with SessionLocal() as db:
                async with aclosing(conversation(body, db)) as events:
                    async for event in events:
                        await queue.put(event)
        except Exception:
            log.exception("chat stream failed")
            await queue.put({
                "type": "error",
                "message": "I couldn't complete that answer right now. Please try again in a moment.",
            })
        await queue.put(None)

    task = asyncio.create_task(produce())
    try:
        # Start the HTTP body promptly even before the first DB/model operation completes.
        yield ": keepalive\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if event is None:
                break
            yield sse(event)
    finally:
        # Client disconnects must stop outstanding tools, model calls, and DB work.
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@router.post("/chat")
async def chat(body: ChatIn):
    return StreamingResponse(
        event_stream(body), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
