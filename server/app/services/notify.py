"""in-app notifications; any module can call notify() and the client polls /api/notifications"""
import logging
import hashlib

from sqlalchemy.dialects.postgresql import insert

from ..db import SessionLocal
from ..models import Notification

log = logging.getLogger(__name__)


async def notify(profile_id: str | None, kind: str, title: str, body: str = "",
                 link: str | None = None, meta: dict | None = None) -> bool:
    if not profile_id:
        return False
    try:
        async with SessionLocal() as db:
            # The monitor supplies a stable source key. Scope it to the citizen
            # and alert kind, so concurrent/retried deliveries remain idempotent.
            source_key = (meta or {}).get("dedup_key")
            key = hashlib.sha256(f"{profile_id}:{kind}:{source_key}".encode()).hexdigest() if source_key else None
            result = await db.execute(insert(Notification).values(
                profile_id=profile_id, kind=kind, title=title, body=body, link=link,
                meta=meta or {}, dedup_key=key,
            ).on_conflict_do_nothing(index_elements=[Notification.dedup_key]).returning(Notification.id))
            created = result.scalar_one_or_none() is not None
            await db.commit()
            return created
    except Exception as e:  # a missed alert must never break the flow that raised it
        log.warning("notify %s failed (%s)", kind, type(e).__name__)
        # The caller can retry later; existing callers may ignore the return value.
        raise_delivery = (meta or {}).get("dedup_key")
        if raise_delivery:
            raise
        return False
