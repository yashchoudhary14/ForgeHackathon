"""Check a local container or live API: --base-url URL [--agent] [--hindi-explain].

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
from urllib.parse import urlsplit

import httpx
from websockets.asyncio.client import connect


async def main(base: str, agent: bool, hindi_explain: bool = False, origin: str | None = None):
    async with httpx.AsyncClient(base_url=base, timeout=180, follow_redirects=True) as client:
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

        if origin:
            response = await client.options("/api/explain", headers={
                "Origin": origin, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            })
            response.raise_for_status()
            assert response.headers.get("access-control-allow-origin") == origin
            print("cors: exact frontend origin accepted", flush=True)

        # Exercise the actual writable storage mount and public audio route.
        if urlsplit(base).hostname in {"localhost", "127.0.0.1", "::1"} and os.getenv("STORAGE_DIR"):
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

        if hindi_explain:
            response = await client.post("/api/explain", json={
                "source": {"type": "scheme", "slug": "pm-kisan"},
                "language": "hi", "with_audio": True,
            })
            response.raise_for_status()
            explained = response.json()
            assert explained["language"] == "hi" and explained["citations"]
            assert any("\u0900" <= ch <= "\u097f" for ch in explained["summary"])
            assert explained["audio_url"], "Hindi explanation did not produce speech audio"
            audio = await client.get(explained["audio_url"])
            audio.raise_for_status()
            assert audio.content[:4] == b"RIFF" and audio.content[8:12] == b"WAVE"
            print("hindi explain: " + json.dumps({
                "title": explained["title"], "summary": explained["summary"],
                "citations": len(explained["citations"]), "audio_url": explained["audio_url"],
                "audio_bytes": len(audio.content),
            }, ensure_ascii=False), flush=True)

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
        headers = {"Cookie": "; ".join(f"{name}={value}" for name, value in client.cookies.items())}
        async with connect(ws_url + f"/api/agent/runs/{run_id}/ws", additional_headers=headers,
                           max_size=8 * 1024 * 1024) as ws:
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
    parser.add_argument("--hindi-explain", action="store_true")
    parser.add_argument("--origin", help="Exact Vercel origin for a CORS preflight check")
    args = parser.parse_args()
    asyncio.run(main(args.base_url.rstrip("/"), args.agent, args.hindi_explain, args.origin))
