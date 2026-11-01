import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.browser import allowed
from ..agents.executor import RunSession, manager
from ..db import get_db
from ..models import AgentRun, AgentStep, Profile
from ..schemas import RunIn, RunOut, RunStepOut
from ..services import crypto, locker
from .locker import owner_id

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


async def _run_out(db: AsyncSession, run: AgentRun, with_steps: bool) -> RunOut:
    steps = []
    if with_steps:
        rows = (await db.execute(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.idx, AgentStep.id))).scalars()
        steps = [RunStepOut(idx=s.idx, thought=s.thought, action=s.action, status=s.status, url=s.url, screenshot=s.screenshot) for s in rows]
    return RunOut(id=run.id, profile_id=run.profile_id, scheme_slug=run.scheme_slug, portal_url=run.portal_url,
                  goal=run.goal, status=run.status, receipt=run.receipt, error=run.error, steps=steps,
                  kind=run.kind, meta={k: v for k, v in (run.meta or {}).items() if k != "answers_encrypted"})


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

    run = AgentRun(profile_id=prof.id, scheme_slug=body.scheme_slug, portal_url=url, goal=body.goal.strip(),
                   kind=body.kind, meta={k: v for k, v in body.meta.items() if k != "answers_encrypted"})
    db.add(run)
    await db.commit()

    rs = RunSession(run.id, run.goal, url, dict(prof.data or {}), crypto.decrypt_json(prof.sensitive),
                    profile_id=prof.id, language=prof.language)
    manager.start(rs)
    return await _run_out(db, run, False)


@router.post("/runs/{run_id}/resume", response_model=RunOut)
async def resume_run(run_id: str, profile_id: str = Depends(owner_id), db: AsyncSession = Depends(get_db)):
    old = await db.get(AgentRun, run_id)
    if not old or old.profile_id != profile_id:
        raise HTTPException(404, "run not found")
    live = manager.get(run_id)
    if live and live.task and not live.task.done():
        raise HTTPException(409, "Run is still live; continue it through the WebSocket")
    if old.status == "done":
        raise HTTPException(409, "Completed runs cannot be resumed; their receipt is already saved")
    prof = await db.get(Profile, old.profile_id)
    if not prof:
        raise HTTPException(404, "profile not found")
    if not allowed(old.portal_url):
        raise HTTPException(422, "Portal is no longer allowed")
    run = AgentRun(profile_id=prof.id, scheme_slug=old.scheme_slug, portal_url=old.portal_url,
        goal=old.goal, kind=old.kind, meta={**(old.meta or {}), "resumed_from": old.id})
    db.add(run)
    await db.commit()
    rs = RunSession(run.id, run.goal, run.portal_url, dict(prof.data or {}), crypto.decrypt_json(prof.sensitive),
                    profile_id=prof.id, language=prof.language)
    rs.answers = crypto.decrypt_json((old.meta or {}).get("answers_encrypted"))
    manager.start(rs)
    return await _run_out(db, run, False)


@router.get("/runs", response_model=list[RunOut])
async def list_runs(profile_id: str = Depends(owner_id), db: AsyncSession = Depends(get_db)):
    q = select(AgentRun).where(AgentRun.profile_id == profile_id).order_by(AgentRun.created_at.desc()).limit(50)
    return [await _run_out(db, r, False) for r in (await db.execute(q)).scalars()]


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: str, profile_id: str = Depends(owner_id), db: AsyncSession = Depends(get_db)):
    run = await db.get(AgentRun, run_id)
    if not run or run.profile_id != profile_id:
        raise HTTPException(404, "run not found")
    return await _run_out(db, run, True)


@router.get("/runs/{run_id}/screenshots/{step}")
async def run_screenshot(run_id: str, step: int, profile_id: str = Depends(owner_id), db: AsyncSession = Depends(get_db)):
    run = await db.get(AgentRun, run_id)
    if not run or run.profile_id != profile_id or step < 0:
        raise HTTPException(404, "screenshot not found")
    path = locker.private_root().parent / "runs" / run.id / f"{step:03d}.enc"
    if not path.is_file():
        raise HTTPException(404, "screenshot not found")
    content = await asyncio.to_thread(locker.decrypt_file, str(path))
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/runs/{run_id}/abort", response_model=RunOut)
async def abort_run(run_id: str, profile_id: str = Depends(owner_id), db: AsyncSession = Depends(get_db)):
    run = await db.get(AgentRun, run_id)
    if not run or run.profile_id != profile_id:
        raise HTTPException(404, "run not found")
    if run.status not in {"done", "failed", "aborted"}:
        live = manager.get(run_id)
        if live:
            await manager.abort(live)
            await db.refresh(run)
        else:
            run.status = "aborted"
            run.error = "Run aborted by user"
            await db.commit()
    return await _run_out(db, run, False)


@router.websocket("/runs/{run_id}/ws")
async def run_ws(ws: WebSocket, run_id: str, profile_id: str = Depends(owner_id), db: AsyncSession = Depends(get_db)):
    saved = await db.get(AgentRun, run_id)
    if not saved or saved.profile_id != profile_id:
        await ws.close(code=1008)
        return
    await ws.accept()
    rs = manager.get(run_id)
    if not rs:
        await ws.send_json({"type": "error", "message": "run is not live (finished or server restarted)"})
        await ws.close()
        return
    rs.subscribe(ws)
    try:
        await ws.send_json({"type": "status", "status": rs.status})
        if rs.browser.last_frame:
            import base64
            await ws.send_json({"type": "frame", "jpeg": base64.b64encode(rs.browser.last_frame).decode()})
        if rs.pending:
            await ws.send_json(rs.pending)
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "abort":
                await manager.abort(rs)
            elif rs.pending:
                await rs.inbox.put(msg)
            # takeover input while the agent itself is driving is ignored on purpose
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as e:
        log.info("ws closed: %s", e)
    finally:
        rs.unsubscribe(ws)
