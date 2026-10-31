"""JSON/multipart Talk input, persisted conversation and cancellable SSE output."""
import asyncio
import json
import logging
from contextlib import aclosing, suppress
from weakref import WeakValueDictionary

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from starlette.datastructures import UploadFile

from ..agents.talk import TalkTools, requested_language, respond, safe_text
from ..db import SessionLocal
from ..models import ChatMessage, Profile
from ..schemas import ProfileData, TalkIn
from ..services import crypto, sarvam
from .chat import sse

log = logging.getLogger(__name__)
router = APIRouter(tags=["talk"])
KEEPALIVE_SECONDS = 10
# One worker: serialize overlapping turns so they cannot race on profile language,
# facts or consent. Weak entries disappear once no request references the lock.
_profile_locks: WeakValueDictionary = WeakValueDictionary()


async def conversation(body: TalkIn, audio: bytes | None, content_type: str, db):
    profile = await db.get(Profile, body.profile_id)
    if profile is None:
        yield {"type": "error", "message": "Please select a saved profile first."}
        return
    session_id = "talk:" + profile.id
    language = body.lang or profile.language or "en"
    text = body.text or ""
    if audio is not None:
        # A separate marker distinguishes the first *audio* turn from text history,
        # and survives process restarts. Default profiles.language='en' isn't detection.
        prior_audio = (await db.execute(select(ChatMessage.id).where(
            ChatMessage.session_id == session_id, ChatMessage.role == "transcript").limit(1))).first()
        transcript = await sarvam.stt(audio, content_type, language if prior_audio else None)
        text = transcript.text
        if not prior_audio:
            language = transcript.language
    if not text.strip():
        yield {"type": "error", "message": "I could not hear any words. Please try again."}
        return
    language = requested_language(text) or language
    if audio is not None:
        db.add(ChatMessage(session_id=session_id, role="transcript", content=language))
    profile.language, profile.mode = language, "talk"
    await db.commit()
    yield {"type": "transcript", "text": text, "lang": language}

    sensitive = crypto.decrypt_json(profile.sensitive)
    message = safe_text(text, sensitive)
    rows = (await db.execute(select(ChatMessage).where(
        ChatMessage.session_id == session_id, ChatMessage.role.in_(["user", "assistant"]))
        .order_by(ChatMessage.id.desc()).limit(10))).scalars().all()
    history = [{"role": r.role, "content": safe_text(r.content, sensitive),
                "offer_slug": next((c.get("talk_offer_slug") for c in (r.citations or []) if "talk_offer_slug" in c), None)}
               for r in reversed(rows)]
    db.add(ChatMessage(session_id=session_id, role="user", content=message))
    await db.commit()
    tools = TalkTools(db, profile, message, history)
    reply, cards = None, []
    async with aclosing(respond(message, language, history, tools)) as events:
        async for event in events:
            if event["type"] == "reply":
                reply = event
            else:
                if event["type"] == "card":
                    cards.append(event["card"])
                yield event
    if reply is None:
        raise ValueError("Talk returned no final reply")
    # Card context makes a later 'yes, apply' resolve to the scheme actually shown.
    content = reply["text"]
    if cards:
        content += "\nCards shown: " + json.dumps(cards, ensure_ascii=False)
    offer = reply.get("application_offer_slug")
    db.add(ChatMessage(session_id=session_id, role="assistant", content=content,
                       citations=[{"talk_offer_slug": offer}] if offer else []))
    await db.commit()
    audio_url = None
    try:
        audio_url = await sarvam.tts_to_file(reply["text"], language)
    except Exception:
        log.warning("talk speech unavailable for language %s", language)
    yield {"type": "done", "text": reply["text"], "lang": language,
           "audio_url": audio_url, "quick_replies": reply["quick_replies"],
           "profile": ProfileData.model_validate(profile.data or {}).model_dump(exclude_none=True)}


async def event_stream(body: TalkIn, audio: bytes | None = None, content_type: str = "audio/webm"):
    queue: asyncio.Queue = asyncio.Queue(maxsize=16)

    async def produce():
        try:
            lock = _profile_locks.setdefault(body.profile_id, asyncio.Lock())
            async with lock:
                async with SessionLocal() as db:
                    async with aclosing(conversation(body, audio, content_type, db)) as events:
                        async for event in events:
                            await queue.put(event)
        except Exception:
            log.warning("talk stream failed")
            await queue.put({"type": "error", "message": "I couldn't complete that reply. Please try again."})
        await queue.put(None)

    task = asyncio.create_task(produce())
    try:
        yield ": keepalive\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if event is None:
                break
            yield sse(event)
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@router.post("/talk")
async def talk(request: Request):
    audio, content_type = None, "audio/webm"
    try:
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            async with request.form(max_files=1, max_fields=3) as form:
                values = {k: form[k] for k in ("profile_id", "text", "lang") if k in form}
                body = TalkIn.model_validate(values)
                upload = form.get("audio")
                if upload is not None:
                    if not isinstance(upload, UploadFile):
                        raise HTTPException(422, "audio must be a file")
                    audio = await upload.read(sarvam.MAX_AUDIO_BYTES + 1)
                    content_type = upload.content_type or content_type
                    if len(audio) > sarvam.MAX_AUDIO_BYTES:
                        raise HTTPException(413, "Audio exceeds the 20 MB limit")
                    if not audio:
                        raise HTTPException(422, "Audio must not be empty")
        elif request.headers.get("content-type", "").startswith("application/json"):
            body = TalkIn.model_validate(await request.json())
        else:
            raise HTTPException(415, "Send JSON text or multipart audio")
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(422, "Provide profile_id, text or audio, and an optional language code") from exc
    if audio is not None and body.text and body.text.strip():
        raise HTTPException(422, "Send either text or audio, not both")
    if audio is None and not (body.text or "").strip():
        raise HTTPException(422, "Provide text or an audio file")
    return StreamingResponse(event_stream(body, audio, content_type), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
