"""thin wrapper over gemini so the rest of the code doesnt care about the sdk"""
import asyncio
import hashlib
import json
import logging
import time
from typing import Any, TypeVar
from contextlib import AsyncExitStack, suppress
from weakref import WeakValueDictionary

from google import genai
from google.genai import types
from pydantic import BaseModel

from ..config import get_settings
from . import llm_cache
from .llm_cache import cached, cache_key
from .llm_pool import ModelPool, QueueTimeout, retry_delay, status_code

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_client: genai.Client | None = None
_pool: ModelPool | None = None
_embedding_key_locks = WeakValueDictionary()
_cooldown: dict[str, float] = {}  # compatibility view of provider cooldowns


def client() -> genai.Client:
    global _client
    if _client is None:
        s = get_settings()
        # Hidden SDK retries would bypass RPM accounting and provider cooldowns.
        http = types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))
        if s.gemini_backend == "vertex" and s.vertex_api_key:
            _client = genai.Client(vertexai=True, api_key=s.vertex_api_key, http_options=http)
        elif s.gemini_backend == "vertex":
            creds, project = _gcp_credentials(s.gcp_credentials)
            project = s.gcp_project or project
            if not project:
                raise RuntimeError("GCP_PROJECT not set")
            _client = genai.Client(vertexai=True, project=project, location=s.gcp_location,
                                   credentials=creds, http_options=http)
        else:
            if not s.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY not set")
            _client = genai.Client(api_key=s.gemini_api_key, http_options=http)
    return _client


def _gcp_credentials(value: str):
    """service account json (file path or raw json). empty -> default credentials from gcloud / the host"""
    if not value:
        return None, None
    from pathlib import Path

    from google.oauth2 import credentials, service_account

    info = json.loads(value) if value.lstrip().startswith("{") else json.loads(Path(value).read_text())
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    if info.get("type") == "authorized_user":  # gcloud application-default login file
        return credentials.Credentials.from_authorized_user_info(info, scopes), info.get("quota_project_id")
    return service_account.Credentials.from_service_account_info(info, scopes=scopes), info.get("project_id")


def pool() -> ModelPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ModelPool(settings.model_pool, settings.gemini_embed_model, settings.gemini_rpm,
                          limits=settings.gemini_model_rpm, best_first=settings.gemini_backend == "vertex")
    return _pool


async def initialize_pool() -> ModelPool:
    scheduler = pool()
    settings = get_settings()
    # AI Studio and Vertex projects/locations have separate availability/quotas.
    # Hash credentials so neither keys nor credential JSON are stored in cache keys.
    credential = (settings.vertex_api_key or settings.gcp_credentials
                  if settings.gemini_backend == "vertex" else settings.gemini_api_key)
    fingerprint = hashlib.sha256(credential.encode()).hexdigest()
    key = cache_key("model_probe_v2", [settings.gemini_backend, settings.gcp_project,
                                     settings.gcp_location, fingerprint, settings.model_pool,
                                     settings.gemini_rpm, settings.gemini_model_rpm])

    async def load():
        return await llm_cache.read(key, ttl_hours=1)

    async def save(value):
        await llm_cache.write(key, value)

    await scheduler.probe(client, settings.gemini_probe_timeout, load=load, save=save)
    return scheduler


async def health_status() -> dict:
    result = await pool().snapshot()
    result["cache"] = dict(llm_cache.stats)
    return result


def _transient(e: Exception) -> bool:
    return isinstance(e, TimeoutError) or status_code(e) in {429, 500, 502, 503, 504} or any(
        word in str(e).lower() for word in ("unavailable", "resource_exhausted", "deadline", "overloaded", "empty gemini"))


async def _retry(fn, *args, tries: int = 3, **kwargs):
    # Kept for compatibility; all internal SDK traffic goes through _run_call.
    for attempt in range(tries):
        try:
            return await asyncio.wait_for(fn(*args, **kwargs), get_settings().gemini_call_timeout)
        except Exception as error:
            if attempt + 1 == tries or not _transient(error):
                raise
            delay = retry_delay(error)
            await asyncio.sleep(delay if delay is not None else 1.5 * 2 ** attempt)


def _available_models(model: str | None) -> list[str]:
    scheduler = pool()
    names = [name for name in scheduler.names() if scheduler.states[name].cooldown_until <= time.monotonic()]
    if model in {"lite", "strong"}:
        return sorted(names, key=lambda name: ("lite" in name) != (model == "lite"))
    return sorted(names, key=lambda name: name != model) if model else names


def _log_call(name, started, limited, status):
    log.info("llm model=%s ms=%d cached=false limited=%s status=%s", name,
             (time.monotonic() - started) * 1000, str(bool(limited)).lower(), status)


async def _run_call(factory, model=None, *, kind="generation", log_success=True):
    scheduler = await initialize_pool()
    settings = get_settings()
    attempted = set()
    wait_remaining = settings.gemini_queue_timeout
    last = None
    # One pass plus one recovery pass. No immediate retries against a cooling model.
    for _ in range(2):
        attempted.clear()
        while True:
            names = scheduler.names(kind)
            if not set(names) - attempted:
                break
            acquiring = time.monotonic()
            try:
                name, waited = await scheduler.acquire(model, names=names, exclude=attempted, timeout=wait_remaining)
            except QueueTimeout:
                _log_call("pool", acquiring, True, "queue_timeout")
                raise
            wait_remaining = max(0, wait_remaining - waited)
            attempted.add(name)
            started = time.monotonic()
            try:
                value = await asyncio.wait_for(factory(name), settings.gemini_call_timeout)
                if log_success:
                    _log_call(name, started, waited, "ok")
                return value, name, bool(waited), started
            except asyncio.CancelledError:
                _log_call(name, started, waited, "cancelled")
                raise
            except Exception as error:
                last = error
                _log_call(name, started, waited, "timeout" if isinstance(error, TimeoutError) else str(status_code(error) or "error"))
                if not (_transient(error) or status_code(error) == 404):
                    raise
                await scheduler.failed(name, error)
                _cooldown[name] = scheduler.states[name].cooldown_until
    if last is not None:
        raise last
    raise RuntimeError("No Gemini models passed the startup probe. Check /api/health/llm.")


async def generate_content(contents, cfg, model: str | None = None):
    """Raw response, preserving tool calls and thought signatures. model may be lite/strong."""
    return await _generate(contents, cfg, model)


async def _generate(contents, cfg, model: str | None):
    response, *_ = await _run_call(lambda name: client().aio.models.generate_content(
        model=name, contents=contents, config=cfg,
    ), model)
    return response


async def _close_stream(stream):
    if stream is not None:
        with suppress(Exception):
            await asyncio.wait_for(stream.aclose(), 1)


async def stream_content(contents, cfg, model: str | None = None):
    """Reserve one RPM slot; fall back only before the first streamed chunk."""
    async def open_stream(name):
        stream = None
        try:
            stream = await client().aio.models.generate_content_stream(model=name, contents=contents, config=cfg)
            first = await anext(stream)
            return stream, first
        except StopAsyncIteration:
            await _close_stream(stream)
            raise RuntimeError("Empty Gemini stream")
        except BaseException:
            await _close_stream(stream)
            raise

    (stream, first), name, limited, started = await _run_call(open_stream, model, log_success=False)
    status = "cancelled"
    try:
        yield first
        async for chunk in stream:
            yield chunk
        status = "ok"
    except Exception as error:
        status = str(status_code(error) or "error")
        if _transient(error) or status_code(error) == 404:
            await pool().failed(name, error)
            _cooldown[name] = pool().states[name].cooldown_until
        raise  # never replay an answer after any chunk was exposed
    finally:
        await _close_stream(stream)
        _log_call(name, started, limited, status)


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
    settings = get_settings()
    keys = [cache_key("embedding", [settings.gemini_embed_model, settings.embed_dim, task, text]) for text in texts]
    found = {}
    # Coalesce duplicate texts in a batch, and overlapping concurrent batches.
    async with AsyncExitStack() as stack:
        # Independent cold scheme records must not queue behind every other
        # embedding. Sorted key locks still coalesce overlapping batches.
        for key in sorted(set(keys)):
            lock = _embedding_key_locks.setdefault(key, asyncio.Lock())
            await stack.enter_async_context(lock)
        missing = {}
        for key, text in zip(keys, texts):
            if key in found or key in missing:
                continue
            value = await llm_cache.read(key)
            if value is not None:
                llm_cache.stats["hits"] += 1
                log.info("llm model=%s ms=0 cached=true limited=false status=embedding_cache", settings.gemini_embed_model)
                found[key] = value
            else:
                llm_cache.stats["misses"] += 1
                missing[key] = text
        items = list(missing.items())
        for offset in range(0, len(items), 100):
            batch = items[offset:offset + 100]
            response, *_ = await _run_call(lambda name: client().aio.models.embed_content(
                model=name, contents=[text for _, text in batch],
                config=types.EmbedContentConfig(task_type=task, output_dimensionality=settings.embed_dim),
            ), kind="embedding")
            vectors = [embedding.values for embedding in response.embeddings or []]
            if len(vectors) != len(batch) or any(len(vector) != settings.embed_dim for vector in vectors):
                raise ValueError("Gemini returned invalid embedding dimensions or count")
            for (key, _), vector in zip(batch, vectors):
                found[key] = vector
                await llm_cache.write(key, vector)
    return [found[key] for key in keys]


async def embed_query(text: str) -> list[float]:
    return (await embed([text], task="RETRIEVAL_QUERY"))[0]
