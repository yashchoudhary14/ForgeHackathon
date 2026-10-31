"""24-hour Postgres cache with per-key single-flight across concurrent callers."""
import asyncio
import hashlib
import json
import logging
import time
import weakref
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from ..config import get_settings
from ..db import SessionLocal
from ..models import LLMCache

log = logging.getLogger(__name__)
_locks = weakref.WeakValueDictionary()
stats = {"hits": 0, "misses": 0, "writes": 0, "errors": 0}


def cache_key(namespace: str, parts) -> str:
    encoded = json.dumps([namespace, parts], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def read(key: str):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=get_settings().llm_cache_ttl_hours)
    try:
        async with SessionLocal() as session:
            row = await session.scalar(select(LLMCache).where(LLMCache.key == key, LLMCache.created_at >= cutoff))
            return row.value if row is not None else None
    except (SQLAlchemyError, OSError):
        stats["errors"] += 1
        log.warning("llm cache read unavailable")
        return None


async def write(key: str, value):
    statement = insert(LLMCache).values(key=key, value=value, created_at=datetime.now(timezone.utc))
    statement = statement.on_conflict_do_update(
        index_elements=[LLMCache.key], set_={"value": statement.excluded.value, "created_at": statement.excluded.created_at},
    )
    try:
        async with SessionLocal() as session:
            await session.execute(statement)
            await session.commit()
        stats["writes"] += 1
    except (SQLAlchemyError, OSError):
        stats["errors"] += 1
        log.warning("llm cache write unavailable")


async def cached(namespace: str, parts, factory):
    key = cache_key(namespace, parts)
    lock = _locks.setdefault(key, asyncio.Lock())
    started = time.monotonic()
    async with lock:
        value = await read(key)
        if value is not None:
            stats["hits"] += 1
            log.info("llm model=cache ms=%d cached=true limited=false namespace=%s",
                     (time.monotonic() - started) * 1000, namespace)
            return value
        stats["misses"] += 1
        value = await factory()
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        await write(key, value)
        return value
