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

from google.genai import types  # noqa: E402

from app import db, models  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.services import llm, myscheme  # noqa: E402


all_slugs = myscheme.all_slugs


async def fresh_slugs() -> set[str]:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    async with db.SessionLocal() as session:
        rows = await session.execute(select(models.Scheme.slug).where(
            models.Scheme.lang == "en", models.Scheme.fetched_at > since, models.Scheme.embedding.is_not(None)))
        return set(rows.scalars())


async def embed(details) -> list[list[float]]:
    """one embedding call per 100 schemes, skipping the per-text cache writes llm.embed does"""
    settings = get_settings()
    vectors = []
    for i in range(0, len(details), 100):
        texts = [f"{d.name}\n{d.brief or ''}\n{d.eligibility_md}" for d in details[i:i + 100]]
        response, *_ = await llm._run_call(lambda name: llm.client().aio.models.embed_content(
            model=name, contents=texts, config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT", output_dimensionality=settings.embed_dim)), kind="embedding")
        vectors += [e.values for e in response.embeddings]
    return vectors


async def save(rows: list[dict]):
    # one statement per batch: a round trip per scheme is far too slow on a remote db
    if not rows:
        return
    stmt = insert(models.Scheme).values(rows)
    stmt = stmt.on_conflict_do_update(index_elements=[models.Scheme.slug, models.Scheme.lang],
                                      set_={c: stmt.excluded[c] for c in ("scheme_id", "name", "data", "embedding", "fetched_at")})
    async with db.SessionLocal() as session:
        await session.execute(stmt)
        await session.commit()


async def main(limit: int | None, batch: int):
    started = time.monotonic()
    myscheme._limit = asyncio.Semaphore(24)  # one bulk job, myScheme handles this fine
    await db.init_db()
    slugs = await all_slugs(limit)
    fresh = await fresh_slugs()
    todo = [slug for slug in slugs if slug not in fresh]
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
        try:
            vectors = await embed([detail for detail, _ in fetched])
        except Exception as e:  # rows still help matching without the semantic index
            print("embedding batch failed:", type(e).__name__, flush=True)
            vectors = [None] * len(fetched)
        await save([{**values, "embedding": vector} for (_, values), vector in zip(fetched, vectors)])
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
