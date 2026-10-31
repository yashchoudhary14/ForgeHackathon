"""run the form agent from the terminal, no frontend needed.

  python scripts/try_agent.py <portal_url> "<goal>" "<free text about the citizen>"

set AGENT_HEADLESS=false in .env to watch the browser and solve captchas in it.
when the agent needs you it prints the request - type an answer (otp / missing info),
or just press enter after doing it in the browser window. type "abort" to stop.
"""
import asyncio
import argparse
import base64
import json
import sys
import time
import wave
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents import executor, intake  # noqa: E402
from app.agents.executor import RunSession  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import AgentRun, Profile  # noqa: E402
from app.schemas import ProfileData, SensitiveData  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.services import crypto  # noqa: E402


class Console:
    def __init__(self, rs: RunSession, stop_at_captcha: bool = False, evidence_dir: Path | None = None):
        self.rs = rs
        self.stop_at_captcha = stop_at_captcha
        self.evidence_dir = evidence_dir
        self.captcha_event: dict | None = None

    async def send_json(self, m: dict):
        t = m["type"]
        if t == "frame":
            return
        if t == "step":
            s = m["step"]
            print(f"#{s['idx']:>2} [call {self.rs.llm_calls}, {s['status']}] {s['thought']}\n     {s['action']} -> {s.get('result')}", flush=True)
        elif t == "needs_human":
            if m["kind"] == "captcha":
                self.captcha_event = m
            print("GUIDANCE:", json.dumps({k: v for k, v in m.items() if k != "crop"}, ensure_ascii=False), flush=True)
            if self.evidence_dir:
                self.evidence_dir.mkdir(parents=True, exist_ok=True)
                (self.evidence_dir / "needs-human.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
                if m.get("crop"):
                    (self.evidence_dir / "crop.jpg").write_bytes(base64.b64decode(m["crop"]))
                if m.get("audio_url", "") and m["audio_url"].startswith("/files/audio/"):
                    source = Path(get_settings().storage_dir) / "audio" / Path(m["audio_url"]).name
                    (self.evidence_dir / "guidance.wav").write_bytes(source.read_bytes())
            if self.stop_at_captcha and m["kind"] == "captcha":
                await self.rs.inbox.put({"type": "abort"})
                return
            asyncio.create_task(self.ask(m))
        else:
            print("  ", m, flush=True)

    async def ask(self, m: dict):
        prompt = f"\n>>> AGENT NEEDS YOU ({m['kind']}): {m['message']}\n"
        prompt += ">>> type y to approve, abort to stop: " if m["kind"] in {"confirm_submit", "confirm_upload"} else ">>> answer, or Enter when done in browser: "
        try:
            ans = (await asyncio.to_thread(input, prompt)).strip()
        except EOFError:
            await self.rs.inbox.put({"type": "abort"})
            return
        if ans == "abort":
            msg = {"type": "abort"}
        elif m["kind"] in {"confirm_submit", "confirm_upload"}:
            approval = "approve_duplicate" if m.get("duplicate_run_ids") else "approve"
            msg = {"type": approval} if ans.lower() == "y" else {"type": "abort"}
        else:
            msg = {"type": "human_input", "value": ans} if ans else {"type": "resume"}
        await self.rs.inbox.put(msg)


async def main(url: str, goal: str, about: str, lang: str = "en", stop_at_captcha: bool = False,
               evidence_dir: Path | None = None, api: str = "http://127.0.0.1:8000"):
    started = time.monotonic()
    await init_db()
    data, sens = await intake.extract(about, ProfileData(), SensitiveData())
    print("profile:", data.model_dump(exclude_none=True))
    async with SessionLocal() as db:
        p = Profile(data=data.model_dump(exclude_none=True), language=lang,
                    sensitive=crypto.encrypt_json(sens.model_dump(exclude_none=True)))
        db.add(p)
        await db.flush()
        run = AgentRun(profile_id=p.id, portal_url=url, goal=goal)
        db.add(run)
        await db.commit()
    print("RUN ID:", run.id, flush=True)
    rs = RunSession(run.id, goal, url, p.data, sens.model_dump(exclude_none=True), profile_id=p.id, language=lang)
    console = Console(rs, stop_at_captcha, evidence_dir)
    rs.subs.add(console)
    agent_started = time.monotonic()
    await executor.run(rs)
    if stop_at_captcha:
        event = console.captcha_event
        assert event, "Run did not reach a CAPTCHA handoff"
        assert event["guide"]["lang"] == lang and 1 <= len(event["guide"]["steps"]) <= 3
        assert event["crop"], "CAPTCHA image could not be located"
        with Image.open(BytesIO(base64.b64decode(event["crop"]))) as image:
            assert image.format == "JPEG" and min(image.size) > 20
        assert event["audio_url"], "Guidance audio is unavailable"
        async with httpx.AsyncClient(base_url=api.rstrip("/")) as client:
            response = await client.get(event["audio_url"])
            response.raise_for_status()
        with wave.open(BytesIO(response.content), "rb") as audio:
            assert audio.getnframes() > 0 and audio.getframerate() > 0
        print("CAPTCHA evidence verified: JPEG crop, localized guide and playable HTTP WAV. Inspect crop.jpg visually.", flush=True)
    async with SessionLocal() as db:
        r = await db.get(AgentRun, run.id)
        print("\nFINAL:", r.status, r.receipt or r.error)
        print("Planning LLM calls:", rs.llm_calls)
        print("RUN METRICS:", {"steps": rs.steps, "planning_calls": rs.llm_calls,
              "wall_seconds": round(time.monotonic() - started, 2),
              "agent_seconds_excluding_human": round(time.monotonic() - agent_started - rs.human_wait_seconds, 2),
              "human_wait_seconds": round(rs.human_wait_seconds, 2)}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("goal")
    parser.add_argument("about")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--stop-at-captcha", action="store_true")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    options = parser.parse_args()
    asyncio.run(main(**vars(options)))
