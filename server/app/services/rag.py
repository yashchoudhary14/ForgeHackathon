"""Retrieve actual uploaded/ingested document chunks from Postgres/pgvector."""
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Chunk, Document
from . import llm


async def retrieve(query: str, document_ids: list[str] | None = None, k: int = 6) -> list[dict]:
    if not query.strip():
        return []
    async with SessionLocal() as db:
        available = select(Chunk.id).where(Chunk.embedding.is_not(None))
        if document_ids:
            available = available.where(Chunk.document_id.in_(document_ids))
        if not await db.scalar(available.limit(1)):
            return []
        vector = await llm.embed_query(query)
        distance = Chunk.embedding.cosine_distance(vector)
        statement = select(Chunk, Document, distance.label("distance")).join(Document, Chunk.document_id == Document.id)
        statement = statement.where(Chunk.embedding.is_not(None))
        if document_ids:
            statement = statement.where(Chunk.document_id.in_(document_ids))
        rows = await db.execute(statement.order_by(distance).limit(max(1, min(k, 20))))
        return [{
            "text": chunk.text, "page": chunk.page, "document_id": document.id,
            "title": document.title, "source_url": document.source_url,
            "score": 1.0 - float(score),
        } for chunk, document, score in rows]


async def document_text(document_id: str, max_chars: int = 120_000) -> str:
    async with SessionLocal() as db:
        chunks = (await db.execute(
            select(Chunk.text).where(Chunk.document_id == document_id)
            .order_by(Chunk.page, Chunk.position)
        )).scalars()
        return "\n\n".join(chunks)[:max(0, max_chars)]
