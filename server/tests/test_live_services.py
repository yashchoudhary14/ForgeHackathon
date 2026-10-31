"""Opt-in integration checks against configured Postgres, Gemini and official services.

Run from server/: .venv/Scripts/python -m pytest tests -m live -v
No substitute documents, scheme data, embeddings or speech responses are used.
"""
import wave
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete

from app import db, models
from app.main import app
from app.services import feeds, ingest, myscheme, rag, sarvam
from test_myscheme import recorded

pytestmark = [pytest.mark.live, pytest.mark.asyncio]


async def test_live_scheme_cache_and_semantic_search():
    try:
        detail = await myscheme.get_scheme("pm-kisan")
        assert detail.id and detail.eligibility_md and detail.documents_md
        assert (await myscheme.get_scheme("pm-kisan")).model_dump() == detail.model_dump()
        matches = await myscheme.semantic_search(detail.name, 3)
        assert any(item.slug == detail.slug for item in matches)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/schemes/pm-kisan?lang=hi")
            assert response.status_code == 200, response.text
            assert response.json()["eligibility_md"]
    finally:
        await myscheme.client().aclose()
        await db.engine.dispose()


async def test_live_feed_routes():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/docs")).status_code == 200
        assert (await client.get("/openapi.json")).status_code == 200
        for lang in ("en", "hi"):
            response = await client.get("/api/feed", params={"lang": lang, "limit": 2})
            assert response.status_code == 200, response.text
            assert len(response.json()) == 2


async def test_live_document_ingestion_and_retrieval():
    source = "https://static.pib.gov.in/WriteReadData/specificdocs/documents/2026/apr/doc2026424855601.pdf"
    try:
        document = await ingest.ingest_url(source)
        assert document.pages > 0
        assert (await ingest.ingest_url(source)).id == document.id
        text = await rag.document_text(document.id, 10000)
        assert "[page 1]" in text
        matches = await rag.retrieve("Who is eligible for income support?", [document.id])
        assert matches and all(row["document_id"] == document.id for row in matches)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/documents/" + document.id)
            assert response.status_code == 200, response.text
            assert 0 < len(response.json()["text"]) <= 2000
            assert (await client.get("/api/documents")).status_code == 200
    finally:
        await db.engine.dispose()


async def test_live_upload_and_image_ocr():
    fixtures = Path(__file__).parent / "fixtures"
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for filename, mime in (("pib-panchayati-raj.pdf", "application/pdf"),
                                   ("pib-panchayati-raj-scan.pdf", "application/pdf"),
                                   ("pib-panchayati-raj-page-1.png", "image/png")):
                response = await client.post("/api/documents", files={
                    "file": (filename, (fixtures / filename).read_bytes(), mime)})
                assert response.status_code == 201, response.text
                detail = await client.get("/api/documents/" + response.json()["id"])
                assert detail.status_code == 200 and detail.json()["text"]
    finally:
        await db.engine.dispose()


async def test_live_html_url_ingestion():
    fixtures = Path(__file__).parent / "fixtures"
    source = feeds.parse_feed((fixtures / "pib-1.xml").read_bytes())[0].url
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/documents", data={"url": source})
            assert response.status_code == 201, response.text
            doc = await ingest.get_document(response.json()["id"])
            assert doc.source_url == source and doc.file_path.endswith(".txt")
            assert await rag.document_text(doc.id, 2000)
    finally:
        await db.engine.dispose()


async def test_live_profile_routes():
    # An empty onboarding profile contains no fabricated personal details.
    profile_id = None
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/profile", json={})
            assert response.status_code == 201, response.text
            profile_id = response.json()["id"]
            assert (await client.get("/api/profile/" + profile_id)).status_code == 200
            response = await client.put("/api/profile/" + profile_id, json={"language": "hi"})
            assert response.status_code == 200, response.text
            assert response.json()["language"] == "hi"
    finally:
        if profile_id:
            async with db.SessionLocal() as session:
                await session.execute(delete(models.Profile).where(models.Profile.id == profile_id))
                await session.commit()
        await db.engine.dispose()


async def test_live_voice_and_translation(monkeypatch):
    text = recorded("myscheme-pm-kisan.json")["en"]["schemeContent"]["briefDescription"]
    try:
        translated = await sarvam.translate(text, "en", "hi")
        assert translated
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/voice/tts", json={"text": translated, "language": "hi"})
            assert response.status_code == 200, response.text
            assert response.content.startswith(b"RIFF")
            audio = response.content
            concatenated = sarvam.concatenate_wav([audio, audio])
            with wave.open(BytesIO(audio)) as original, wave.open(BytesIO(concatenated)) as joined:
                assert joined.getnframes() == original.getnframes() * 2
            response = await client.post("/api/voice/stt", files={
                "audio": ("speech.wav", response.content, "audio/wav")}, data={"language": "hi"})
            assert response.status_code == 200, response.text
            assert response.json()["text"] and response.json()["language"] == "hi"
            settings = sarvam.get_settings().model_copy(update={"sarvam_api_key": ""})
            monkeypatch.setattr(sarvam, "get_settings", lambda: settings)
            fallback = await sarvam.stt(audio, "audio/wav", "hi")
            assert fallback.text and fallback.language == "hi"
            assert await sarvam.translate(text, "en", "hi")
    finally:
        await sarvam.client().aclose()
