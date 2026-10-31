"""Real civic smoke check against a running local API; stops at CPGRAMS login.

Run from server/: python scripts/try_civic.py [--profile-id EXISTING_ID]
Uses a real Commons photo, its published camera coordinates and attribution.
The photo is historical: this is verification evidence, not a claim about today.
No OTP/CAPTCHA answer or submission approval is ever sent by this script.
"""
import argparse
import asyncio
import json
from pathlib import Path

import httpx
import websockets

SOURCE = "https://commons.wikimedia.org/wiki/File:Broken_Roads_in_India%27s_Capital_New_Delhi.jpg"
PHOTO = ("https://upload.wikimedia.org/wikipedia/commons/thumb/1/14/"
         "Broken_Roads_in_India%27s_Capital_New_Delhi.jpg/960px-"
         "Broken_Roads_in_India%27s_Capital_New_Delhi.jpg")
LAT, LNG = 28.606356, 77.046806
CREDIT = "Rrthakur22, 6 November 2018, CC BY-SA 4.0; Wikimedia 960px thumbnail"
LICENSE = "https://creativecommons.org/licenses/by-sa/4.0/"


async def main(args):
    folder = Path("storage/civic-live")
    folder.mkdir(parents=True, exist_ok=True)
    photo_path = folder / "commons-road.jpg"
    result = {"source_url": SOURCE, "credit": CREDIT, "license": LICENSE, "photo": str(photo_path)}
    async with httpx.AsyncClient(base_url=args.base_url, timeout=180) as client:
        if not photo_path.exists():
            image = await client.get(PHOTO, headers={"User-Agent": "Adhikaar-Civic/2.0 (local verification)"})
            image.raise_for_status()
            if len(image.content) > 2 * 1024 * 1024:
                raise RuntimeError("Unexpectedly large photo")
            photo_path.write_bytes(image.content)
        profile_id = args.profile_id
        if not profile_id:
            response = await client.post("/api/profile", json={"data": {}, "sensitive": {}, "language": "hi"})
            response.raise_for_status()
            profile_id = response.json()["id"]
        fields = {"profile_id": profile_id, "lat": str(LAT), "lng": str(LNG), "source_url": SOURCE,
                  "text": "Road surface has a deep open hole and exposed rebar. "
                          "Historical photograph for local feature verification; present condition is unknown. " + CREDIT}
        photo = photo_path.read_bytes()
        files = {"photo": (photo_path.name, photo, "image/jpeg")}
        response = await client.post("/api/reports/triage", data=fields, files=files)
        response.raise_for_status()
        triage = response.json()
        result["triage"] = triage
        print("TRIAGE", json.dumps(triage, ensure_ascii=False), flush=True)
        response = await client.post("/api/reports", data={**fields, "triage": json.dumps(triage)}, files=files)
        response.raise_for_status()
        report = response.json()
        result["report_id"] = report["id"]
        result["media_served"] = (await client.get(report["media"][0]["url"])).status_code == 200
        assert result["media_served"], "Saved photo must be served"
        nearby = {**fields, "lat": str(LAT + .0001)}
        response = await client.post("/api/reports", data={**nearby, "triage": json.dumps(triage)}, files=files)
        response.raise_for_status()
        second = response.json()
        result["nearby_report_id"] = second["id"]
        response = await client.post("/api/reports/triage", data=nearby, files=files)
        response.raise_for_status()
        detected = response.json()["duplicates"]
        assert report["id"] in {item["id"] for item in detected}, "First report must be detected within 300m"
        assert second["id"] in {item["id"] for item in detected}, "Second nearby report must be detected"
        result["duplicates"] = [{"id": d["id"], "distance_m": d["distance_m"], "similarity": d["similarity"]} for d in detected]
        detail = await client.get(f"/api/reports/{report['id']}")
        detail.raise_for_status()
        assert detail.json()["events"][0]["source"] == "citizen"
        print("CREATED AND DUPLICATE CHECKED", result["report_id"], result["duplicates"], flush=True)
        response = await client.post(f"/api/reports/{report['id']}/file", json={"profile_id": profile_id})
        response.raise_for_status()
        result["run_id"] = response.json()["run_id"]
        websocket = args.base_url.replace("http://", "ws://").replace("https://", "wss://") + f"/api/agent/runs/{result['run_id']}/ws"
        last_url = ""
        try:
            async with websockets.connect(websocket, max_size=5 * 1024 * 1024) as ws:
                async with asyncio.timeout(240):
                    async for raw in ws:
                        event = json.loads(raw)
                        if event["type"] == "frame":
                            continue
                        if event["type"] == "step":
                            step = event["step"]
                            last_url = step.get("url") or last_url
                            print("STEP", step["idx"], step.get("thought"), last_url, flush=True)
                        if event["type"] == "needs_human":
                            persisted = await client.get(f"/api/agent/runs/{result['run_id']}")
                            persisted.raise_for_status()
                            steps = persisted.json().get("steps", [])
                            if steps:
                                last_url = steps[-1].get("url") or last_url
                            result["human_step"] = {"kind": event["kind"], "url": last_url,
                                                    "message": event.get("message")}
                            print("HUMAN STEP — STOPPING", result["human_step"], flush=True)
                            await ws.send(json.dumps({"type": "abort"}))
                            # Wait for persisted abort; do not leave a browser waiting for 15 minutes.
                            for _ in range(30):
                                terminal = json.loads(await ws.recv())
                                if terminal.get("type") == "error":
                                    break
                            break
                        if event["type"] in {"done", "error"}:
                            raise RuntimeError("Agent stopped before the login handoff: " + str(event))
            human = result.get("human_step", {})
            assert human.get("kind") in {"login", "otp", "captcha", "missing_field"}
            assert "pgportal.gov.in" in human.get("url", "")
            assert any(token in (human.get("message", "") + " " + human.get("url", "")).lower()
                       for token in ("login", "signin", "otp", "captcha", "mobile", "phone", "security code")), human
        finally:
            (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS — saved evidence in", folder / "result.json", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--profile-id")
    asyncio.run(main(parser.parse_args()))
