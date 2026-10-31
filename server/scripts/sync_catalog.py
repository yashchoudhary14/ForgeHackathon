"""copy the whole myScheme catalogue (details + embeddings) into the database.

From server/: python scripts/sync_catalog.py [--limit N]
Live matching then reads schemes from the db instead of fetching ~30 of them per request,
which is too slow from Cloud Run. Run it again to refresh; fresh rows are skipped.
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app import db, models  # noqa: E402
from app.services import myscheme  # noqa: E402


all_slugs = myscheme.all_slugs


async def main(limit: int | None, batch: int):
    started = time.monotonic()
    myscheme._limit = asyncio.Semaphore(24)  # one bulk job, myScheme handles this fine
    await db.init_db()
    async with db.SessionLocal() as session:
        before = set((await session.execute(select(models.Scheme.slug).where(models.Scheme.lang == "en"))).scalars())
    slugs = await all_slugs(limit)
    print(f"catalogue: {len(slugs)} schemes, {len(set(slugs) - before)} not in db yet", flush=True)

    failed = []
    for offset in range(0, len(slugs), batch):
        chunk = slugs[offset:offset + batch]
        results = await asyncio.gather(*(myscheme.get_scheme(slug, "en", index=False) for slug in chunk),
                                        return_exceptions=True)
        details = []
        for slug, result in zip(chunk, results):
            if isinstance(result, Exception):
                failed.append((slug, f"{type(result).__name__}: {result}"[:120]))
            else:
                details.append(result)
        async with db.SessionLocal() as session:
            missing = set((await session.execute(select(models.Scheme.slug).where(
                models.Scheme.lang == "en", models.Scheme.slug.in_([d.slug for d in details]),
                models.Scheme.embedding.is_(None)))).scalars())
        for i in range(0, len(missing), 100):
            await myscheme.index_schemes([d for d in details if d.slug in missing][i:i + 100])
        print(f"{min(offset + batch, len(slugs))}/{len(slugs)} done, {len(failed)} failed, "
              f"{time.monotonic() - started:.0f}s", flush=True)

    for slug, error in failed[:20]:
        print("failed", slug, error)
    print(f"finished: {len(slugs) - len(failed)} synced, {len(failed)} failed in {time.monotonic() - started:.0f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only the first N schemes (for a quick test)")
    parser.add_argument("--batch", type=int, default=200)
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.batch))
