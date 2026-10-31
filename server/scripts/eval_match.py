"""Live matcher regressions using official myScheme data and the configured LLM.

From server/: python scripts/eval_match.py --fresh --model gemini-3.8-flash --rpm 600
Exits nonzero on missing candidates, wrong verdicts, or target-group leakage.
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents import matcher  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.schemas import ProfileData  # noqa: E402
from app.services import llm, myscheme  # noqa: E402


CASES = {
    "bihar-sc-student": {
        "profile": ProfileData(
            state="Bihar", gender="female", caste="sc", age=19,
            course="B.Sc", education_level="ug", study_year=1,
            annual_income=140000, residence="rural", occupation="student", is_student=True,
        ),
        "required": {"pmsfss", "pmsscstb"},
        "excluded": {"kcc", "psgs-deg", "psgs-dip"},
    },
}


async def evaluate(case_name: str, limit: int) -> dict:
    case = CASES[case_name]
    profile = case["profile"]
    candidates = await matcher.candidates(profile, None, limit)
    candidate_slugs = {s.slug for s in candidates}
    results = await matcher.match(profile, limit=limit)
    by_slug = {r.scheme.slug: r for r in results}
    checks = {}
    for slug in sorted(case["required"]):
        checks[f"recall:{slug}"] = slug in candidate_slugs
        checks[f"result:{slug}"] = slug in by_slug and by_slug[slug].verdict in {"eligible", "likely"}

    # Exercise bad targets directly even when retrieval did not return them.
    # Absence from search alone must not count as successful triage.
    async def rejected(slug):
        try:
            scheme = await myscheme.get_scheme(slug)
            return not await matcher.triage(profile, scheme)
        except Exception:
            logging.exception("could not evaluate excluded target %s", slug)
            return False

    excluded = sorted(case["excluded"])
    for slug, dropped in zip(excluded, await asyncio.gather(*(rejected(s) for s in excluded))):
        checks[f"triage:{slug}"] = dropped
        checks[f"no_positive:{slug}"] = slug not in by_slug or by_slug[slug].verdict == "not_eligible"

    # Contrast cases protect dual occupations and technical students from broad
    # rules such as "all students cannot farm" or "unknown AICTE approval fails".
    async def kept(slug, updates):
        try:
            scheme = await myscheme.get_scheme(slug)
            return await matcher.triage(profile.model_copy(update=updates), scheme)
        except Exception:
            logging.exception("could not evaluate positive control %s", slug)
            return False

    checks["keep:student-farmer"] = await kept("kcc", {"occupation": "student and tenant farmer"})
    checks["keep:technical-student"] = await kept("psgs-deg", {"course": "B.Tech"})
    return {
        "case": case_name, "profile": profile.model_dump(exclude_none=True),
        "passed": all(checks.values()), "checks": checks,
        "candidates": [{"slug": s.slug, "name": s.name, "state": s.state} for s in candidates],
        "results": [r.model_dump(mode="json") for r in results],
    }


async def run(args) -> dict:
    settings = get_settings()
    if args.model:
        settings.gemini_model_pool = args.model
    if args.rpm:
        settings.gemini_rpm = args.rpm
    # --fresh bypasses answer caches, while leaving source/embedding caches intact.
    original_cached = llm.cached

    async def cached(namespace, parts, factory):
        if args.fresh and namespace.startswith("matcher."):
            return await factory()
        return await original_cached(namespace, parts, factory)

    try:
        await init_db()
        with patch.object(llm, "cached", cached):
            reports = [await evaluate(case, args.limit) for case in args.case or CASES]
        return {"backend": settings.gemini_backend, "models": settings.model_pool,
                "fresh": args.fresh, "passed": all(r["passed"] for r in reports), "cases": reports}
    finally:
        await myscheme.client().aclose()
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", choices=CASES)
    parser.add_argument("--limit", type=int, choices=range(1, 21), default=8)
    parser.add_argument("--model", help="Pin a model; defaults to the configured pool")
    parser.add_argument("--rpm", type=int, help="Per-model local RPM budget for a paid-quota run")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--output", type=Path, help="Write the complete JSON report")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)
    report = asyncio.run(run(args))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
