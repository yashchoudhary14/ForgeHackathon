"""in-app notifications; any module can call notify() and the client polls /api/notifications"""
import logging

from ..db import SessionLocal
from ..models import Notification

log = logging.getLogger(__name__)


async def notify(profile_id: str | None, kind: str, title: str, body: str = "",
                 link: str | None = None, meta: dict | None = None) -> None:
    if not profile_id:
        return
    try:
        async with SessionLocal() as db:
            db.add(Notification(profile_id=profile_id, kind=kind, title=title, body=body, link=link, meta=meta or {}))
            await db.commit()
    except Exception as e:  # a missed alert must never break the flow that raised it
        log.warning("notify %s failed: %s", kind, e)
