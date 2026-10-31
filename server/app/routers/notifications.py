"""Citizen-scoped inbox and manual monitor trigger."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Notification, Profile
from ..schemas import MonitorOut, NotificationsOut, NotificationsReadIn, NotificationsReadOut
from ..services import monitor

router = APIRouter(tags=["alerts"])


async def require_profile(session: AsyncSession, profile_id: str):
    if await session.get(Profile, profile_id) is None:
        raise HTTPException(404, "profile not found")


async def unread_count(session: AsyncSession, profile_id: str) -> int:
    return await session.scalar(select(func.count()).select_from(Notification).where(
        Notification.profile_id == profile_id, Notification.read.is_(False))) or 0


@router.get("/notifications", response_model=NotificationsOut)
async def list_notifications(profile_id: str, offset: int = Query(0, ge=0),
                             limit: int = Query(100, ge=1, le=500), session: AsyncSession = Depends(get_db)):
    await require_profile(session, profile_id)
    rows = (await session.scalars(select(Notification).where(Notification.profile_id == profile_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc()).offset(offset).limit(limit))).all()
    return NotificationsOut(items=rows, unread_count=await unread_count(session, profile_id))


@router.post("/notifications/read", response_model=NotificationsReadOut)
async def read_notifications(body: NotificationsReadIn, session: AsyncSession = Depends(get_db)):
    await require_profile(session, body.profile_id)
    statement = update(Notification).where(Notification.profile_id == body.profile_id, Notification.read.is_(False))
    if body.ids is not None:
        statement = statement.where(Notification.id.in_(body.ids))
    result = await session.execute(statement.values(read=True))
    await session.commit()
    return NotificationsReadOut(updated=result.rowcount, unread_count=await unread_count(session, body.profile_id))


@router.post("/monitor/run", response_model=MonitorOut)
async def run_monitor():
    try:
        return await monitor.run_monitor()
    except monitor.MonitorBusy as exc:
        raise HTTPException(409, "monitor is already running") from exc
