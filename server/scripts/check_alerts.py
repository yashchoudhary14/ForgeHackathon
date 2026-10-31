"""Live alerts acceptance check; no fabricated profiles, schemes or model results.

From server/: python scripts/check_alerts.py --replay-latest
Optional: --profile-id ID --old-url GOV_URL --new-url GOV_URL

Uses the local PostgreSQL configured by .env and the real ASGI API routes. If
discovery finds no new schemes, --replay-latest temporarily queues the three
most recently fetched English catalogue entries for the chosen existing citizen.
The temporary queue/check rows are removed; real notifications are retained.
No profile or eligibility result is invented, so unsuitable schemes yield no alert.
Evidence is written under ignored storage/checks/alerts-live.json.
"""
import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import delete, func, select  # noqa: E402

from app import db, models  # noqa: E402
from app.agents.matcher import quote_found  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import ExplainIn, ProfileData  # noqa: E402
from app.agents.explainer import _load_source  # noqa: E402
from app.services import llm, monitor, myscheme  # noqa: E402


def official_url(value):
    host = urlsplit(value).hostname or ""
    if urlsplit(value).scheme != "https" or not (host.endswith(".gov.in") or host.endswith(".nic.in")):
        raise argparse.ArgumentTypeError("Use an official https gov.in/nic.in URL")
    return value


async def check(args):
    settings = get_settings()
    if db.url.host not in {"localhost", "127.0.0.1", "::1", "db", "postgres"}:
        raise RuntimeError("This acceptance script requires a local database; no remote rows were changed")
    await db.init_db()
    await llm.initialize_pool()
    async with db.SessionLocal() as session:
        profiles = (await session.scalars(select(models.Profile).order_by(models.Profile.updated_at.desc()))).all()
        profiles = [row for row in profiles if (not args.profile_id or row.id == args.profile_id) and
                    ProfileData.model_validate(row.data or {}).model_dump(exclude_none=True)]
        if not profiles:
            raise RuntimeError("No existing profile with matching data; create a real citizen profile first")
        profile = profiles[0]
        before = await session.scalar(select(func.max(models.Notification.id))) or 0

    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "profile_id": profile.id}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://local", timeout=180) as client:
        response = await client.post("/api/monitor/run")
        response.raise_for_status()
        result["monitor"] = response.json()
        print("monitor:", json.dumps(result["monitor"]))

        if args.replay_latest and result["monitor"]["stored"] == 0:
            async with db.SessionLocal() as session:
                latest = (await session.scalars(select(models.Scheme).where(models.Scheme.lang == "en")
                    .order_by(models.Scheme.fetched_at.desc(), models.Scheme.slug).limit(3))).all()
            if not latest:
                raise RuntimeError("No cached schemes to replay; sync the real catalogue first")
            items = [models.MonitorItem(id=monitor.item_key("live-replay", f"{uuid.uuid4().hex}:{scheme.slug}"),
                        kind="new_scheme", source=scheme.slug, data={}) for scheme in latest]
            async with db.SessionLocal() as session:
                session.add_all(items)
                await session.commit()
            try:
                replay_counts = monitor.MonitorOut(profiles=1)
                try:
                    async with asyncio.timeout(monitor.RUN_SECONDS):
                        sem = asyncio.Semaphore(3)
                        await asyncio.gather(*(monitor._scheme_check(profile, item, replay_counts, sem) for item in items))
                except TimeoutError:
                    replay_counts.timed_out = True
                result["replay"] = {"slugs": [item.source for item in items], **replay_counts.model_dump()}
                print("temporary latest-three replay:", json.dumps(result["replay"]))
            finally:
                async with db.SessionLocal() as session:
                    ids = [item.id for item in items]
                    await session.execute(delete(models.MonitorCheck).where(models.MonitorCheck.item_id.in_(ids)))
                    await session.execute(delete(models.MonitorItem).where(models.MonitorItem.id.in_(ids)))
                    await session.commit()

        async with db.SessionLocal() as session:
            rows = (await session.scalars(select(models.Notification).where(
                models.Notification.profile_id == profile.id, models.Notification.id > before)
                .order_by(models.Notification.id))).all()
        result["notifications"] = [{"id": row.id, "kind": row.kind, "title": row.title,
                                    "body": row.body, "link": row.link, "meta": row.meta} for row in rows]
        print("real notifications:", json.dumps(result["notifications"], ensure_ascii=False))

        body = {"old": {"type": "url", "url": args.old_url}, "new": {"type": "url", "url": args.new_url},
                "profile_id": profile.id, "with_audio": False}
        response = await client.post("/api/explain/compare", json=body)
        response.raise_for_status()
        compared = response.json()
        if not compared["changes"]:
            raise AssertionError("Compare returned no verified changes; inspect source extraction/model availability")
        old, new = await asyncio.gather(
            _load_source(ExplainIn(source=body["old"], with_audio=False)),
            _load_source(ExplainIn(source=body["new"], with_audio=False)))
        for change in compared["changes"]:
            assert quote_found(change["old_citation"]["quote"], old[1])
            assert quote_found(change["new_citation"]["quote"], new[1])
        result["compare"] = compared
        print("verified comparison:", json.dumps(compared["changes"], ensure_ascii=False))
        inbox = await client.get("/api/notifications", params={"profile_id": profile.id})
        timeline = await client.get("/api/activity", params={"profile_id": profile.id})
        inbox.raise_for_status()
        timeline.raise_for_status()
        timestamps = [datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00")) for item in timeline.json()]
        assert timestamps == sorted(timestamps, reverse=True)
        result["inbox_unread_count"] = inbox.json()["unread_count"]
        result["activity_count"] = len(timeline.json())

    path = Path(settings.storage_dir) / "checks" / "alerts-live.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Evidence: {path}")


async def main(args):
    try:
        await check(args)
    finally:
        await myscheme.client().aclose()
        await db.engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-id")
    parser.add_argument("--replay-latest", action="store_true")
    parser.add_argument("--old-url", type=official_url,
                        default="https://www.pib.gov.in/PressReleasePage.aspx?PRID=2105745&lang=1&reg=3")
    parser.add_argument("--new-url", type=official_url,
                        default="https://www.pib.gov.in/PressNoteDetails.aspx?ModuleId=3&NoteId=154960&lang=1&reg=3")
    asyncio.run(main(parser.parse_args()))
