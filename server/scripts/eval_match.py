"""Live matcher regressions using official myScheme data and the configured LLM.

From server/: python scripts/eval_match.py --fresh --model gemini-3.8-flash --rpm 600
Exits nonzero on missing candidates, wrong verdicts, or target-group leakage.
"""
import argparse
import asyncio
import json
import logging
import re
import sys
from time import perf_counter
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
        "required": {"pmsfss", "pmsscstb", "pmssc"},
        "excluded": {"kcc", "psgs-deg", "psgs-dip"},
    },
}

# Expected recommendations, not guaranteed awards: unknown documentation,
# enrolment, land title and contribution conditions should produce "likely".
# Match official titles to avoid pinning undocumented catalogue slug aliases.
CASES.update({
    "up-small-farmer": {
        "profile": ProfileData(state="Uttar Pradesh", age=35, gender="male", residence="rural",
                               occupation="small farmer", land_acres=2, annual_income=90000),
        "expected": {"PM-KISAN": r"kisan samman nidhi", "Kisan Credit Card": r"kisan credit card",
                     "PM Fasal Bima Yojana": r"fasal bima"},
    },
    "rajasthan-bpl-widow": {
        "profile": ProfileData(state="Rajasthan", age=68, gender="female", residence="rural",
                               marital_status="widow", is_bpl=True, annual_income=24000),
        "expected": {"Indira Gandhi National Old Age Pension": r"indira gandhi national old age pension",
                     "Rajasthan widow pension": r"(ekal nari|widow.*pension)"},
    },
    "maharashtra-disabled-graduate": {
        "profile": ProfileData(state="Maharashtra", age=24, gender="male", residence="urban",
                               disability_percent=40, education_level="graduate", course="B.A completed",
                               occupation="unemployed graduate job seeker", is_student=False, annual_income=60000),
        "expected": {"Assistance for aids and appliances (ADIP)": r"(adip|assistance.*(aids|appliances))",
                     "Financial assistance for disabled self-employment": r"(self employment.*(disab|divyang)|(disab|divyang).*self employment)"},
    },
    "mp-obc-class11": {
        "profile": ProfileData(state="Madhya Pradesh", age=16, gender="male", caste="obc",
                               education_level="class 11", course="class 11", occupation="student",
                               is_student=True, annual_income=100000),
        "expected": {"OBC post-matric scholarship": r"post matric.*(obc|other backward|backward class)"},
    },
    "odisha-pregnant": {
        "profile": ProfileData(state="Odisha", age=25, gender="female", residence="rural",
                               is_pregnant=True, is_bpl=True, annual_income=60000),
        "expected": {"MAMATA": r"mamata", "Janani Suraksha Yojana": r"janani suraksha",
                     "Janani Shishu Suraksha Karyakram": r"janani shishu suraksha"},
    },
    "delhi-street-vendor": {
        "profile": ProfileData(state="Delhi", age=35, gender="male", residence="urban",
                               occupation="street vendor", annual_income=120000),
        "expected": {"PM SVANidhi": r"(svanidhi|street vendor.*atma.*nirbhar)"},
    },
})


async def evaluate(case_name: str, limit: int, max_seconds: float = 60) -> dict:
    case = CASES[case_name]
    profile = case["profile"]
    candidates = await matcher.candidates(profile, None, limit)
    candidate_slugs = {s.slug for s in candidates}
    started = perf_counter()
    results = await matcher.match(profile, limit=limit)
    elapsed = perf_counter() - started
    by_slug = {r.scheme.slug: r for r in results}
    checks = {"latency": elapsed <= max_seconds}
    for slug in sorted(case.get("required", set())):
        checks[f"recall:{slug}"] = slug in candidate_slugs
        checks[f"result:{slug}"] = slug in by_slug and by_slug[slug].verdict in {"eligible", "likely"}
    for name, pattern in case.get("expected", {}).items():
        def matches(scheme):
            return bool(re.search(pattern, matcher._norm(scheme.name))) and (
                not scheme.state or scheme.state in {profile.state, "All"})
        checks[f"recall:{name}"] = any(matches(s) for s in candidates)
        checks[f"result:{name}"] = any(matches(r.scheme) and r.verdict in {"eligible", "likely"} for r in results)

    # Exercise bad targets directly even when retrieval did not return them.
    # Absence from search alone must not count as successful triage.
    async def rejected(slug):
        try:
            scheme = await myscheme.get_scheme(slug)
            return not await matcher.triage(profile, scheme)
        except Exception:
            logging.exception("could not evaluate excluded target %s", slug)
            return False

    excluded = sorted(case.get("excluded", set()))
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

    if case_name == "bihar-sc-student":
        checks["keep:student-farmer"] = await kept("kcc", {"occupation": "student and tenant farmer"})
        checks["keep:technical-student"] = await kept("psgs-deg", {"course": "B.Tech"})
    return {
        "case": case_name, "profile": profile.model_dump(exclude_none=True),
        "passed": all(checks.values()), "checks": checks,
        "match_seconds": round(elapsed, 2),
        "expected": sorted(case.get("required", set())) + list(case.get("expected", {})),
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
            reports = [await evaluate(case, args.limit, args.max_seconds) for case in args.case or CASES]
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
    parser.add_argument("--max-seconds", type=float, default=60, help="Per-profile match latency budget")
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
