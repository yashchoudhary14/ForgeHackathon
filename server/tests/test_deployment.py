import asyncio
import ssl
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import make_url
from websockets.asyncio.client import connect as real_websocket_connect
from websockets.asyncio.server import serve

from app import db, main, neon
from app.services import llm


def test_neon_console_url_and_tls():
    value = "postgresql://user:password@ep-demo.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    url, options = db.database_options(value)
    assert url.drivername == "postgresql+asyncpg"
    assert not url.query
    assert callable(options["async_creator"])
    _, options = db.database_options(value, "tcp")
    context = options["connect_args"]["ssl"]
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    local, options = db.database_options("postgres://postgres:postgres@localhost/adhikaar")
    assert local.drivername == "postgresql+asyncpg" and options["connect_args"] == {}
    with pytest.raises(ValueError, match="Neon host"):
        db.database_options("postgresql://localhost/test", "websocket")


async def test_neon_binary_transport_and_connection_cleanup(monkeypatch):
    disconnected = asyncio.Event()

    async def remote(ws):
        try:
            async for payload in ws:
                assert isinstance(payload, bytes)
                await ws.send(payload[::-1])
        finally:
            disconnected.set()

    async with serve(remote, "127.0.0.1", 0, close_timeout=1) as server:
        port = server.sockets[0].getsockname()[1]

        async def websocket(url, **kwargs):
            assert url == "wss://ep-demo.aws.neon.tech/v2"
            return await real_websocket_connect(f"ws://127.0.0.1:{port}", **kwargs)

        async def postgres(**kwargs):
            assert kwargs["ssl"] is False  # external hop is verified WSS
            reader, writer = await asyncio.open_connection(kwargs["host"], kwargs["port"])
            writer.write(b"\x00\x01postgres")
            await writer.drain()
            assert await asyncio.wait_for(reader.readexactly(10), 3) == b"sergtsop\x01\x00"
            return writer

        monkeypatch.setattr(neon, "websocket_connect", websocket)
        monkeypatch.setattr(neon.asyncpg, "connect", postgres)
        writer = await asyncio.wait_for(neon.connect(make_url("postgresql://user:pass@ep-demo.aws.neon.tech/db")), 5)
        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(disconnected.wait(), 2)


async def test_health_pings_do_not_touch_gemini_or_database(monkeypatch):
    forbidden = AsyncMock(side_effect=AssertionError("liveness cannot call providers"))
    monkeypatch.setattr(llm, "initialize_pool", forbidden)
    monkeypatch.setattr(llm, "client", forbidden)
    monkeypatch.setattr(main, "init_db", forbidden)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        for _ in range(5):
            response = await client.get("/api/health")
            assert response.status_code == 200 and response.json()["ok"]
    forbidden.assert_not_called()
