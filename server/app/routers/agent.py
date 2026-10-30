import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.browser import allowed
from ..agents.executor import RunSession, manager
from ..db import get_db
from ..models import AgentRun, AgentStep, Profile
from ..schemas import RunIn, RunOut, RunStepOut
from ..services import crypto

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


async def _run_out(db: AsyncSession, run: AgentRun, with_steps: bool) -> RunOut:
    steps = []
    if with_steps:
        rows = (await db.execute(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.idx, AgentStep.id))).scalars()
        steps = [RunStepOut(idx=s.idx, thought=s.thought, action=s.action, status=s.status, url=s.url, screenshot=s.screenshot) for s in rows]
    return RunOut(id=run.id, profile_id=run.profile_id, scheme_slug=run.scheme_slug, portal_url=run.portal_url,
                  goal=run.goal, status=run.status, receipt=run.receipt, error=run.error, steps=steps)


@router.post("/runs", response_model=RunOut)
async def create_run(body: RunIn, db: AsyncSession = Depends(get_db)):
    url = body.portal_url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not allowed(url):
        raise HTTPException(422, "For safety the agent only works on official government sites (.gov.in / .nic.in)")
    if not body.goal.strip():
        raise HTTPException(422, "goal is required")
    prof = await db.get(Profile, body.profile_id)
    if not prof:
        raise HTTPException(404, "profile not found")

    run = AgentRun(profile_id=prof.id, scheme_slug=body.scheme_slug, portal_url=url, goal=body.goal.strip())
    db.add(run)
    await db.commit()

    rs = RunSession(run.id, run.goal, url, dict(prof.data or {}), crypto.decrypt_json(prof.sensitive))
    manager.start(rs)
    return await _run_out(db, run, False)


@router.get("/runs", response_model=list[RunOut])
async def list_runs(profile_id: str | None = None, db: AsyncSession = Depends(get_db)):
    q = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(50)
    if profile_id:
        q = q.where(AgentRun.profile_id == profile_id)
    return [await _run_out(db, r, False) for r in (await db.execute(q)).scalars()]


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return await _run_out(db, run, True)


@router.websocket("/runs/{run_id}/ws")
async def run_ws(ws: WebSocket, run_id: str):
    await ws.accept()
    rs = manager.get(run_id)
    if not rs:
        await ws.send_json({"type": "error", "message": "run is not live (finished or server restarted)"})
        await ws.close()
        return
    rs.subs.add(ws)
    await ws.send_json({"type": "status", "status": rs.status})
    if rs.browser.last_frame:
        import base64
        await ws.send_json({"type": "frame", "jpeg": base64.b64encode(rs.browser.last_frame).decode()})
    if rs.pending:
        await ws.send_json(rs.pending)
    try:
        while True:
            msg = await ws.receive_json()
            if rs.pending:
                await rs.inbox.put(msg)
            elif msg.get("type") == "abort" and rs.task:
                rs.task.cancel()
            # takeover input while the agent itself is driving is ignored on purpose
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        log.info("ws closed: %s", e)
    finally:
        rs.subs.discard(ws)
