"""Carry asyncpg's Postgres session over Neon's verified TLS WebSocket (443).

Neon's official serverless driver uses the same /v2 binary transport. Only
the short-lived loopback hop is plaintext; all network traffic uses WSS.
"""
import asyncio
from contextlib import suppress

import asyncpg
from websockets.asyncio.client import connect as websocket_connect


async def connect(url):
    ws = await websocket_connect(f"wss://{url.host}/v2", max_size=None, open_timeout=20)
    tasks = set()

    async def relay(reader, writer):
        async def upstream():
            while data := await reader.read(65536):
                await ws.send(data)

        async def downstream():
            async for data in ws:
                writer.write(data)
                await writer.drain()

        pumps = [asyncio.create_task(upstream()), asyncio.create_task(downstream())]
        try:
            await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for pump in pumps:
                pump.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
            await ws.close()
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()

    def accepted(reader, writer):
        task = asyncio.create_task(relay(reader, writer))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    listener = None
    try:
        listener = await asyncio.start_server(accepted, "127.0.0.1", 0)
        return await asyncpg.connect(
            host="127.0.0.1", port=listener.sockets[0].getsockname()[1],
            user=url.username, password=url.password, database=url.database,
            ssl=False, timeout=30, command_timeout=60,
            statement_cache_size=0,  # Neon transaction pooler compatibility
        )
    except BaseException:
        await ws.close()
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        if listener is not None:
            # wait_closed() drains active connections on Python 3.12, so it
            # must not block returning this still-live asyncpg connection.
            listener.close()
