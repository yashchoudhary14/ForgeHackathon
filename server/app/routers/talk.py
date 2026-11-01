"""JSON/multipart Talk input, persisted conversation and cancellable SSE output."""
import asyncio
import json
import logging
import re
from contextlib import aclosing, suppress
from weakref import WeakValueDictionary

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from starlette.datastructures import UploadFile

from ..agents.talk import ONBOARDING_FIELDS, UI_ROUTES, TalkTools, asks_for_help, detect_text_language, requested_language, respond, safe_text, script_language
from ..db import SessionLocal
from ..models import AgentRun, ChatMessage, Profile
from ..schemas import ProfileData, TalkIn
from ..services import crypto, sarvam
from ..services import myscheme
from .chat import sse

log = logging.getLogger(__name__)
router = APIRouter(tags=["talk"])
KEEPALIVE_SECONDS = 10
# One worker: serialize overlapping turns so they cannot race on profile language,
# facts or consent. Weak entries disappear once no request references the lock.
_profile_locks: WeakValueDictionary = WeakValueDictionary()


async def spoken_events(events, language: str, enabled: bool):
    """Race the next model/tool event against first-sentence speech.

    In particular, a slow scheme match must not hold back already available audio.
    The caller removes spoken_text before exposing the event to the client.
    """
    pending, speech = None, None
    accumulated, sentence = "", ""
    iterator = events.__aiter__()
    try:
        pending = asyncio.create_task(anext(iterator))
        while pending is not None:
            done, _ = await asyncio.wait({pending, speech} if speech else {pending}, return_when=asyncio.FIRST_COMPLETED)
            if speech and speech in done:
                try:
                    url = speech.result()
                    if url:
                        yield {"type": "audio", "audio_url": url, "spoken_text": sentence}
                except Exception:
                    log.warning("First-sentence speech unavailable")
                speech = None
            if pending not in done:
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                pending = None
                break
            pending = None
            if enabled and event["type"] == "delta":
                accumulated += event["text"]
                match = re.match(r"^(.{8,}?[.!?।])(?:\s|$)", accumulated, re.S)
                if match:
                    sentence = match[1]
                    speech = asyncio.create_task(sarvam.tts_to_file(sentence, language))
                    enabled = False
            yield event
            pending = asyncio.create_task(anext(iterator))
        if speech:
            try:
                url = await speech
                if url:
                    yield {"type": "audio", "audio_url": url, "spoken_text": sentence}
            except Exception:
                log.warning("First-sentence speech unavailable")
    finally:
        for task in (pending, speech):
            if task and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await iterator.aclose()


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
    sensitive = crypto.decrypt_json(profile.sensitive)
    message = safe_text(text, sensitive)
    if audio is None and not body.lang and language == "en":
        prior_turn = (await db.execute(select(ChatMessage.id).where(
            ChatMessage.session_id == session_id, ChatMessage.role == "user").limit(1))).first()
        if not prior_turn:
            language = await detect_text_language(message)
    # The client always sends its current UI language. Typed Hindi/Bengali script in an
    # English (or other-script) session means the citizen is using that language now.
    scripted = script_language(message)
    if audio is None and scripted and scripted != language and not (scripted == "bn" and language == "as"):
        detected = await detect_text_language(message) if scripted == "bn" else scripted
        language = detected if detected in ("bn", "as") or scripted == "hi" else "bn"
    language = requested_language(text) or language
    if audio is not None:
        db.add(ChatMessage(session_id=session_id, role="transcript", content=language))
    profile.language, profile.mode = language, "talk"
    from ..agents.executor import manager
    manager.set_language(profile.id, language)
    await db.commit()
    yield {"type": "transcript", "text": text, "lang": language}

    rows = (await db.execute(select(ChatMessage).where(
        ChatMessage.session_id == session_id, ChatMessage.role.in_(["user", "assistant"]))
        .order_by(ChatMessage.id.desc()).limit(10))).scalars().all()
    history = [{"role": r.role, "content": safe_text(r.content, sensitive),
                "offer_slug": next((c.get("talk_offer_slug") for c in (r.citations or []) if "talk_offer_slug" in c), None),
                "offer_service": next((c.get("talk_offer_service") for c in (r.citations or []) if "talk_offer_service" in c), None),
                "pending_service": next((c.get("talk_pending_service") for c in (r.citations or []) if "talk_pending_service" in c), None),
                "services": next((c.get("talk_services", []) for c in (r.citations or []) if "talk_services" in c), [])}
               for r in reversed(rows)]
    db.add(ChatMessage(session_id=session_id, role="user", content=message))
    await db.commit()
    tools = TalkTools(db, profile, message, history)
    if body.action:
        tools.requested_service = body.action.service
    if body.context:
        page = body.context.page
        tools.context = {"page": page if page in UI_ROUTES else "/runs/:id" if re.fullmatch(r"/runs/[\w-]+", page) else "/schemes/:slug" if re.fullmatch(r"/schemes/[\w-]+", page) else "/",
                         "onboarding": body.context.onboarding and not asks_for_help(message)
                                       and not body.action and not tools.pending_service and not tools.offered_service}
        current_scheme = re.fullmatch(r"/schemes/([A-Za-z0-9_-]{1,200})", page)
        if current_scheme:
            try:
                async with asyncio.timeout(4):
                    detail = await myscheme.get_scheme(current_scheme[1], lang="en", index=False)
                tools.context["scheme_slug"] = detail.slug  # only a verified official slug reaches Gemini
                tools.known_slugs.add(detail.slug)
            except Exception:
                log.warning("Current scheme context unavailable")
        if body.context.run_id:
            run = await db.get(AgentRun, body.context.run_id)
            if run and run.profile_id == profile.id:
                # IDs and human answers are never model context. Resolve current state locally.
                live = manager.get(run.id)
                tools.context.update({"run_active": run.status not in {"done", "failed", "aborted"},
                                      "pending_step": live.pending.get("kind") if live and live.pending else None})
    if tools.context.get("onboarding"):
        yield {"type": "progress", "stage": "saving_profile"}
        tools.profile_question = next((field for field in ONBOARDING_FIELDS if getattr(tools.profile, field) is None), None)
        await tools.save_profile_facts()
    reply, cards = None, []
    first_sentence = ""
    async with aclosing(spoken_events(respond(message, language, history, tools), language, body.stream_audio)) as events:
        async for event in events:
            if event["type"] == "reply":
                reply = event
            else:
                if event["type"] == "card":
                    cards.append(event["card"])
                if event["type"] == "audio":
                    first_sentence = event.pop("spoken_text")
                yield event
    if reply is None:
        raise ValueError("Talk returned no final reply")
    # Card context makes a later 'yes, apply' resolve to the scheme actually shown.
    content = reply["text"]
    if cards:
        content += "\nCards shown: " + json.dumps(cards, ensure_ascii=False)
    offer = reply.get("application_offer_slug")
    metadata = []
    if offer:
        metadata.append({"talk_offer_slug": offer})
    if reply.get("application_offer_service"):
        metadata.append({"talk_offer_service": reply["application_offer_service"]})
    if tools.services:
        metadata.append({"talk_services": list(tools.services.values())})
    if tools.pending_service:
        metadata.append({"talk_pending_service": tools.pending_service})
    db.add(ChatMessage(session_id=session_id, role="assistant", content=content,
                       citations=metadata))
    await db.commit()
    audio_url = None
    yield {"type": "progress", "stage": "preparing_audio"}
    try:
        remaining = reply["text"][len(first_sentence):].strip() if first_sentence and reply["text"].startswith(first_sentence) else reply["text"]
        if remaining:
            audio_url = await sarvam.tts_to_file(remaining, language)
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
            async with request.form(max_files=1, max_fields=5) as form:
                values = {k: form[k] for k in ("profile_id", "text", "lang") if k in form}
                if "action" in form:
                    values["action"] = json.loads(str(form["action"]))
                if "context" in form:
                    values["context"] = json.loads(str(form["context"]))
                if "stream_audio" in form:
                    values["stream_audio"] = form["stream_audio"]
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
