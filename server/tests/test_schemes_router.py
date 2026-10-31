import httpx
import pytest
from fastapi import FastAPI

from app.routers import schemes
from app.services import myscheme
from test_myscheme import recorded


@pytest.mark.asyncio
async def test_search_route_filters(monkeypatch):
    requests = []
    async def recorded_get(path, **params):
        requests.append(params)
        return recorded("myscheme-search.json")
    monkeypatch.setattr(myscheme, "_get", recorded_get)
    app = FastAPI()
    app.include_router(schemes.router, prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/schemes/search", params={
            "state": "Uttar Pradesh", "is_student": "true", "age": 20})
        assert response.status_code == 200
        assert response.json()["items"][0]["slug"] == recorded("myscheme-search.json")["hits"]["items"][0]["fields"]["slug"]
        assert '"isStudent"' in requests[0]["q"]
        assert (await client.get("/api/schemes/search?size=0")).status_code == 422
        assert (await client.get("/api/schemes/search?age=-1")).status_code == 422
