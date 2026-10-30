"""pgvector retrieval and ordered, de-overlapped source text."""
from sqlalchemy import select

from .. import db, models
from . import ingest, llm


def join_chunks(chunks, offsets: list[int] | None = None) -> str:
    pages: list[tuple[int | None, str]] = []
    page, text = None, ""
    for chunk in chunks:
        if pages or text:
            if chunk.page != page:
                pages.append((page, text))
                text = ""
        page = chunk.page
        offset = offsets[chunk.position] if offsets and chunk.position < len(offsets) else None
        if offset is not None:
            text += chunk.text[max(0, len(text) - offset):]
        elif text:
            overlap = next((n for n in range(min(200, len(text), len(chunk.text)), 0, -1)
                            if text.endswith(chunk.text[:n])), 0)
            text += chunk.text[overlap:]
        else:
            text = chunk.text
    if text:
        pages.append((page, text))
    return "\n\n".join((f"[page {page}]\n" if page is not None else "") + text for page, text in pages)


async def document_text(document_id: str, max_chars: int) -> str:
    if max_chars < 0:
        raise ValueError("max_chars must be nonnegative")
    document = await ingest.get_document(document_id)
    async with db.SessionLocal() as session:
        chunks = (await session.scalars(select(models.Chunk).where(
            models.Chunk.document_id == document_id).order_by(models.Chunk.position))).all()
    return join_chunks(chunks, (document.meta or {}).get("chunk_offsets"))[:max_chars]


async def retrieve(query: str, document_ids: list[str] | None = None, k: int = 6) -> list[dict]:
    if not 1 <= k <= 100:
        raise ValueError("k must be 1–100")
    if document_ids == []:
        return []
    vector = await llm.embed_query(query)
    distance = models.Chunk.embedding.cosine_distance(vector)
    statement = select(models.Chunk, models.Document, distance.label("distance")).join(
        models.Document, models.Chunk.document_id == models.Document.id).where(
            models.Chunk.embedding.is_not(None))
    if document_ids is not None:
        statement = statement.where(models.Chunk.document_id.in_(document_ids))
    async with db.SessionLocal() as session:
        rows = (await session.execute(statement.order_by(distance).limit(k))).all()
    return [dict(text=chunk.text, page=chunk.page, document_id=document.id, title=document.title,
                 source_url=document.source_url, score=1 - float(distance))
            for chunk, document, distance in rows]
