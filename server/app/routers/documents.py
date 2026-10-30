import asyncio
from typing import Literal

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select

from .. import db, models
from ..schemas import DocumentOut, FeedItem
from ..services import feeds, ingest, rag

router = APIRouter(tags=["documents"])


@router.get("/feed", response_model=list[FeedItem])
async def government_feed(lang: Literal["en", "hi"] = "en", limit: int = Query(20, ge=1, le=100)):
    try:
        return await feeds.get_feed(lang, limit)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "PIB feed is temporarily unavailable") from exc


class DocumentPreview(DocumentOut):
    text: str


async def _out(document: models.Document) -> DocumentOut:
    async with db.SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(models.Chunk).where(
            models.Chunk.document_id == document.id))
    return DocumentOut(id=document.id, title=document.title, source_type=document.source_type,
                       source_url=document.source_url, pages=document.pages, chunks=count or 0)


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(file: UploadFile | None = File(None), url: str | None = Form(None)):
    if (file is None) == (not url):
        raise HTTPException(422, "Supply exactly one file or URL")
    try:
        if file is not None:
            data = await file.read(ingest.MAX_BYTES + 1)
            document = await ingest.ingest_file(file.filename or "Uploaded document", data,
                                                file.content_type or "application/octet-stream")
        else:
            document = await ingest.ingest_url(url)
        return await _out(document)
    except ValueError as exc:
        status = 413 if "20 MB" in str(exc) else 422
        raise HTTPException(status, str(exc)) from exc
    except (httpx.HTTPError, TimeoutError) as exc:
        raise HTTPException(502, "Could not download the source document") from exc
    except RuntimeError as exc:
        raise HTTPException(503, "Document ingestion requires an available Gemini service") from exc
    finally:
        if file is not None:
            await file.close()


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    async with db.SessionLocal() as session:
        rows = (await session.execute(select(models.Document, func.count(models.Chunk.id)).outerjoin(
            models.Chunk, models.Chunk.document_id == models.Document.id).group_by(models.Document.id)
            .order_by(models.Document.created_at.desc()).offset(offset).limit(limit))).all()
    return [DocumentOut(id=doc.id, title=doc.title, source_type=doc.source_type, source_url=doc.source_url,
                        pages=doc.pages, chunks=count) for doc, count in rows]


@router.get("/documents/{document_id}", response_model=DocumentPreview)
async def document_detail(document_id: str):
    try:
        document = await ingest.get_document(document_id)
        result, text = await asyncio.gather(_out(document), rag.document_text(document_id, 2000))
        return DocumentPreview(**result.model_dump(), text=text)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
