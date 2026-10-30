"""thin wrapper over gemini so the rest of the code doesnt care about the sdk"""
import asyncio
import json
import logging
import time
from typing import Any, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from ..config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_client: genai.Client | None = None
_cooldown: dict[str, float] = {}  # model -> monotonic time until which we don't try it


def client() -> genai.Client:
    global _client
    if _client is None:
        key = get_settings().gemini_api_key
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _client = genai.Client(api_key=key)
    return _client


def _transient(e: Exception) -> bool:
    s = str(e)
    return any(c in s for c in ("429", "500", "503", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE", "overloaded"))


async def _retry(fn, *args, tries: int = 3, **kwargs):
    delay = 1.5
    for i in range(tries):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:  # 429 / 503 from gemini happen a lot on free tier
            if i == tries - 1 or not _transient(e):
                raise
            log.warning("gemini call failed (%s), retrying in %.1fs", e, delay)
            await asyncio.sleep(delay)
            delay *= 2


async def _generate(contents, cfg, model: str | None):
    """primary model first, then fallbacks - 'high demand' 503s are common and a demo can't wait"""
    s = get_settings()
    chain = list(dict.fromkeys(m for m in [model, s.gemini_model, *s.fallback_models] if m))
    now = time.monotonic()
    # skip models that were overloaded a moment ago, but never skip all of them
    live = [m for m in chain if _cooldown.get(m, 0) < now] or chain[-1:]
    last: Exception | None = None
    for i, m in enumerate(live):
        try:
            return await _retry(client().aio.models.generate_content, model=m, contents=contents, config=cfg,
                                tries=1 if i < len(live) - 1 else 3)
        except Exception as e:
            last = e
            if not (_transient(e) or "404" in str(e)):
                raise
            _cooldown[m] = time.monotonic() + (3600 if "404" in str(e) else 60)
            log.warning("model %s unavailable, falling back", m)
    raise last


async def generate(
    prompt: str | list[Any],
    system: str | None = None,
    temperature: float = 0.2,
    model: str | None = None,
) -> str:
    cfg = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
    resp = await _generate(prompt, cfg, model)
    return resp.text or ""


async def generate_json(
    prompt: str | list[Any],
    schema: type[T],
    system: str | None = None,
    temperature: float = 0.1,
    model: str | None = None,
) -> T:
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=schema,
    )
    resp = await _generate(prompt, cfg, model)
    if resp.parsed is not None:
        return resp.parsed
    return schema.model_validate(json.loads(resp.text))


async def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    s = get_settings()
    out: list[list[float]] = []
    for i in range(0, len(texts), 100):
        resp = await _retry(
            client().aio.models.embed_content,
            model=s.gemini_embed_model,
            contents=texts[i : i + 100],
            config=types.EmbedContentConfig(task_type=task, output_dimensionality=s.embed_dim),
        )
        out.extend(e.values for e in resp.embeddings)
    return out


async def embed_query(text: str) -> list[float]:
    return (await embed([text], task="RETRIEVAL_QUERY"))[0]
