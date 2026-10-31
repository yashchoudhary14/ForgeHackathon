"""Run inside the API container: python scripts/smoke_deploy.py [--agent].

The optional real agent test consumes Gemini quota and stores one demo profile
and run. Its goal only reads the requested government page.
"""
import argparse
import asyncio
import json
import os
import uuid
import wave
from pathlib import Path

import httpx
from websockets.asyncio.client import connect


async def main(base: str, agent: bool):
    async with httpx.AsyncClient(base_url=base, timeout=60) as client:
        before = (await client.get("/api/health/llm")).json()
        for _ in range(5):
            health = await client.get("/api/health")
            health.raise_for_status()
            assert health.json()["ok"]
        after = (await client.get("/api/health/llm")).json()
        counts = lambda snapshot: {row["model"]: row["total_requests"] for row in snapshot["models"]}
        assert counts(before) == counts(after), "Health pings consumed model capacity"
        print("health: 200; five pings consumed zero Gemini requests", flush=True)

        response = await client.get("/api/schemes/search", params={"keyword": "farmer", "size": 2})
        response.raise_for_status()
        result = response.json()
        assert result["total"] > 0 and result["items"]
        print(f"schemes/search: 200; total={result['total']}", flush=True)

        # Exercise the actual writable storage mount and public audio route.
        folder = Path(os.environ["STORAGE_DIR"]) / "audio"
        folder.mkdir(parents=True, exist_ok=True)
        filename = "smoke-" + uuid.uuid4().hex + ".wav"
        path = folder / filename
        try:
            with wave.open(str(path), "wb") as output:
                output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                output.writeframes(b"\x00\x00" * 80)
            response = await client.get("/files/audio/" + filename)
            response.raise_for_status()
            assert response.content == path.read_bytes()
            print("audio: writable storage; /files/audio returns the WAV bytes", flush=True)
        finally:
            path.unlink(missing_ok=True)

        if not agent:
            return
        response = await client.post("/api/profile", json={"data": {"state": "Bihar"}})
        response.raise_for_status()
        response = await client.post("/api/agent/runs", json={
            "profile_id": response.json()["id"],
            "portal_url": "https://www.myscheme.gov.in/find-scheme",
            "goal": "Read the page title and visible heading. Immediately finish with action done, "
                    "reporting the title and heading in the message. Do not click, fill, scroll, "
                    "navigate or submit anything. The goal is achieved by reading this page.",
        })
        response.raise_for_status()
        run_id = response.json()["id"]
        ws_url = base.replace("http://", "ws://").replace("https://", "wss://")
        async with connect(ws_url + f"/api/agent/runs/{run_id}/ws", max_size=8 * 1024 * 1024) as ws:
            frames = 0

            async def receive():
                nonlocal frames
                async for message in ws:
                    if json.loads(message).get("type") == "frame":
                        frames += 1

            receiving = asyncio.create_task(receive())
            try:
                async with asyncio.timeout(180):
                    while True:
                        response = await client.get(f"/api/agent/runs/{run_id}")
                        response.raise_for_status()
                        run = response.json()
                        if run["status"] in {"done", "failed", "aborted"}:
                            assert run["status"] == "done", run.get("error")
                            receipt = run["receipt"]
                            assert receipt["url"].startswith("https://www.myscheme.gov.in/")
                            shot = await client.get(receipt["screenshot"])
                            shot.raise_for_status()
                            assert frames > 0, "No live browser frames received over WebSocket"
                            print("agent: " + json.dumps({"id": run_id, "status": run["status"],
                                  "frames": frames, "receipt": receipt}, ensure_ascii=False), flush=True)
                            break
                        await asyncio.sleep(1)
            except BaseException:
                await ws.send(json.dumps({"type": "abort"}))
                raise
            finally:
                receiving.cancel()
                await asyncio.gather(receiving, return_exceptions=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:" + os.getenv("PORT", "7860"))
    parser.add_argument("--agent", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.base_url.rstrip("/"), args.agent))
