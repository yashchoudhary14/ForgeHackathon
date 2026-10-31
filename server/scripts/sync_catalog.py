"""copy the whole myScheme catalogue (details + embeddings) into the database.

From server/: python scripts/sync_catalog.py [--limit N]
Live matching then reads schemes from the db instead of fetching ~30 of them per request,
which is too slow from Cloud Run. Run it again to refresh; rows synced in the last day are skipped.
"""
import argparse
import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from app import db, models  # noqa: E402
from app.services import myscheme  # noqa: E402


all_slugs = myscheme.all_slugs


async def fresh_slugs() -> set[str]:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    async with db.SessionLocal() as session:
        rows = await session.execute(select(models.Scheme.slug).where(
            models.Scheme.lang == "en", models.Scheme.fetched_at > since, models.Scheme.embedding.is_not(None)))
        return set(rows.scalars())


async def save(rows: list[dict]):
    # one session per batch: a session per scheme exhausts the pool on a remote db
    async with db.SessionLocal() as session:
        for values in rows:
            changed = {key: value for key, value in values.items() if key != "embedding"}
            await session.execute(insert(models.Scheme).values(**values).on_conflict_do_update(
                index_elements=[models.Scheme.slug, models.Scheme.lang], set_=changed))
        await session.commit()


async def main(limit: int | None, batch: int):
    started = time.monotonic()
    myscheme._limit = asyncio.Semaphore(24)  # one bulk job, myScheme handles this fine
    await db.init_db()
    slugs = await all_slugs(limit)
    todo = [slug for slug in slugs if slug not in await fresh_slugs()]
    print(f"catalogue: {len(slugs)} schemes, {len(todo)} to sync", flush=True)

    failed = []
    for offset in range(0, len(todo), batch):
        chunk = todo[offset:offset + batch]
        results = await asyncio.gather(*(myscheme.fetch_scheme(slug, "en") for slug in chunk), return_exceptions=True)
        fetched = []
        for slug, result in zip(chunk, results):
            if isinstance(result, Exception):
                failed.append((slug, f"{type(result).__name__}: {result}"[:120]))
            else:
                fetched.append(result)
        await save([values for _, values in fetched])
        details = [detail for detail, _ in fetched]
        for i in range(0, len(details), 100):
            await myscheme.index_schemes(details[i:i + 100])
        print(f"{min(offset + batch, len(todo))}/{len(todo)} done, {len(failed)} failed, "
              f"{time.monotonic() - started:.0f}s", flush=True)

    for slug, error in failed[:20]:
        print("failed", slug, error)
    print(f"finished: {len(todo) - len(failed)} synced, {len(failed)} failed in {time.monotonic() - started:.0f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only the first N schemes (for a quick test)")
    parser.add_argument("--batch", type=int, default=200)
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.batch))
