"""run the form agent from the terminal, no frontend needed.

  python scripts/try_agent.py <portal_url> "<goal>" "<free text about the citizen>"

set AGENT_HEADLESS=false in .env to watch the browser and solve captchas in it.
when the agent needs you it prints the request - type an answer (otp / missing info),
or just press enter after doing it in the browser window. type "abort" to stop.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents import executor, intake  # noqa: E402
from app.agents.executor import RunSession  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import AgentRun, Profile  # noqa: E402
from app.schemas import ProfileData, SensitiveData  # noqa: E402


class Console:
    def __init__(self, rs: RunSession):
        self.rs = rs

    async def send_json(self, m: dict):
        t = m["type"]
        if t == "frame":
            return
        if t == "step":
            s = m["step"]
            print(f"#{s['idx']:>2} [{s['status']}] {s['thought']}\n     {s['action']} -> {s.get('result')}", flush=True)
        elif t == "needs_human":
            asyncio.create_task(self.ask(m))
        else:
            print("  ", m, flush=True)

    async def ask(self, m: dict):
        prompt = f"\n>>> AGENT NEEDS YOU ({m['kind']}): {m['message']}\n"
        prompt += ">>> type y to approve, abort to stop: " if m["kind"] == "confirm_submit" else ">>> answer, or Enter when done in browser: "
        try:
            ans = (await asyncio.to_thread(input, prompt)).strip()
        except EOFError:
            await self.rs.inbox.put({"type": "abort"})
            return
        if ans == "abort":
            msg = {"type": "abort"}
        elif m["kind"] == "confirm_submit":
            msg = {"type": "approve"} if ans.lower().startswith("y") else {"type": "abort"}
        else:
            msg = {"type": "human_input", "value": ans} if ans else {"type": "resume"}
        await self.rs.inbox.put(msg)


async def main(url: str, goal: str, about: str):
    await init_db()
    data, sens = await intake.extract(about, ProfileData(), SensitiveData())
    print("profile:", data.model_dump(exclude_none=True))
    async with SessionLocal() as db:
        p = Profile(data=data.model_dump(exclude_none=True))
        db.add(p)
        await db.flush()
        run = AgentRun(profile_id=p.id, portal_url=url, goal=goal)
        db.add(run)
        await db.commit()
    rs = RunSession(run.id, goal, url, p.data, sens.model_dump(exclude_none=True))
    rs.subs.add(Console(rs))
    await executor.run(rs)
    async with SessionLocal() as db:
        r = await db.get(AgentRun, run.id)
        print("\nFINAL:", r.status, r.receipt or r.error)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(*sys.argv[1:4]))
