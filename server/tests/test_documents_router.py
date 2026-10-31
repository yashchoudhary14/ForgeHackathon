from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.routers import documents


@pytest.mark.asyncio
async def test_upload_rejects_ambiguous_or_missing_source():
    app = FastAPI()
    app.include_router(documents.router, prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/documents")).status_code == 422
        data = (Path(__file__).parent / "fixtures" / "pib-panchayati-raj.pdf").read_bytes()
        response = await client.post("/api/documents", files={"file": ("guidelines.pdf", data, "application/pdf")},
                                    data={"url": "https://www.myscheme.gov.in/"})
        assert response.status_code == 422
