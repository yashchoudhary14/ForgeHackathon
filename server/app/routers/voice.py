import httpx
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from ..schemas import Lang, SttOut, TtsIn
from ..services import sarvam

router = APIRouter(tags=["voice"])


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, RuntimeError):
        return HTTPException(503, str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(422, str(exc))
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (400, 413, 422):
        return HTTPException(422, "Speech service rejected this input; STT clips must be under 30 seconds")
    return HTTPException(502, "Speech service is temporarily unavailable")


@router.post("/voice/stt", response_model=SttOut)
async def speech_to_text(audio: UploadFile = File(...), language: Lang | None = Form(None)):
    try:
        data = await audio.read(sarvam.MAX_AUDIO_BYTES + 1)
        if len(data) > sarvam.MAX_AUDIO_BYTES:
            raise HTTPException(413, "Audio exceeds the 20 MB limit")
        return await sarvam.stt(data, audio.content_type or "audio/webm", language)
    except (RuntimeError, ValueError, httpx.HTTPError) as exc:
        raise _error(exc) from exc
    finally:
        await audio.close()


@router.post("/voice/tts", responses={200: {"content": {"audio/wav": {}}}}, response_class=Response)
async def text_to_speech(body: TtsIn):
    try:
        return Response(await sarvam.tts(body.text, body.language), media_type="audio/wav")
    except (RuntimeError, ValueError, httpx.HTTPError) as exc:
        raise _error(exc) from exc
