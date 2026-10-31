"""The citizen's applications, complaints and alerts in one timeline."""
from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import AgentRun, Notification, Report, ReportVote
from ..schemas import ActivityItem
from .notifications import require_profile

router = APIRouter(tags=["activity"])


def merge_activity(runs, reports, notifications) -> list[ActivityItem]:
    items = [ActivityItem(type="run", id=r.id, title=r.goal, status=r.status,
                          official=bool(r.receipt) and r.status == "done", updated_at=r.updated_at,
                          link=f"/runs/{r.id}") for r in runs]
    items += [ActivityItem(type="report", id=r.id, title=r.title, status=r.status,
                           official=bool(r.official_ref or r.official_status), updated_at=r.updated_at,
                           link=f"/reports/{r.id}") for r in reports]
    items += [ActivityItem(type="notification", id=str(n.id), title=n.title,
                           status="read" if n.read else "unread", official=(n.meta or {}).get("source") == "official",
                           updated_at=n.created_at, link=n.link) for n in notifications]
    # Type + id provides a deterministic order when timestamps tie.
    return sorted(items, key=lambda item: (item.updated_at, item.type, item.id), reverse=True)


@router.get("/activity", response_model=list[ActivityItem])
async def activity(profile_id: str, session: AsyncSession = Depends(get_db)):
    await require_profile(session, profile_id)
    runs = (await session.scalars(select(AgentRun).where(AgentRun.profile_id == profile_id))).all()
    followed = select(ReportVote.report_id).where(ReportVote.profile_id == profile_id, ReportVote.kind == "follow")
    reports = (await session.scalars(select(Report).where(or_(Report.profile_id == profile_id,
                                                            Report.id.in_(followed))))).all()
    notifications = (await session.scalars(select(Notification).where(Notification.profile_id == profile_id))).all()
    return merge_activity(runs, reports, notifications)
