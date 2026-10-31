"""Live matcher regressions using official myScheme data and the configured LLM.

From server/: python scripts/eval_match.py --fresh --model gemini-3.8-flash --rpm 600
Exits nonzero on missing candidates, wrong verdicts, or target-group leakage.
"""
import argparse
import asyncio
import json
import logging
import sys
import time
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
        "expected": {
            "pmsfss": "Central SC post-matric support: undergraduate SC student below the income ceiling.",
            "pmsscstb": "Bihar SC/ST post-matric support for a domiciled SC undergraduate.",
        },
        "excluded": {"kcc", "psgs-deg", "psgs-dip", "pmssc"},
        "controls": [
            ("student-farmer", "kcc", {"occupation": "student and tenant farmer"}),
            ("technical-student", "psgs-deg", {"course": "B.Tech", "state": "Assam"}),
            ("punjab-sc-student", "pmssc", {"state": "Punjab"}),
        ],
    },
    "up-small-farmer": {
        "profile": ProfileData(state="Uttar Pradesh", age=35, gender="male", caste="general",
            occupation="farmer", land_acres=2, annual_income=120000, residence="rural", is_student=False),
        "required": {"pm-kisan", "kcc", "pmkmdy"},
        "expected": {
            "pm-kisan": "Cultivating landholder; income support, subject to official exclusions.",
            "kcc": "Working-capital credit for a farmer/owner-cultivator.",
            "pmkmdy": "Age 35 with 2 acres (about 0.81 hectares), below the 2-hectare ceiling; contribution and records remain conditions.",
        },
        "excluded": {"psgs-deg", "pmsfss"},
    },
    "rajasthan-bpl-widow": {
        "profile": ProfileData(state="Rajasthan", age=68, gender="female", caste="general",
            marital_status="widowed", occupation="unemployed", annual_income=24000,
            residence="rural", is_bpl=True, is_student=False),
        "required": {"cmenspy", "ignwps", "nsap-ignoaps", "ignvpyr"},
        "expected": {
            "cmenspy": "Rajasthan widow over 18 with income below Rs 48,000.",
            "ignwps": "BPL widow aged 40-79.",
            "nsap-ignoaps": "BPL person aged at least 60.",
            "ignvpyr": "Rajasthan implementation of BPL old-age pension at 60+.",
        },
        "notes": "Pensions are alternatives/implementations, not a promise that benefits can be stacked.",
        "excluded": {"psgs-deg", "pre-sc"},
    },
    "maharashtra-disabled-jobseeker": {
        "profile": ProfileData(state="Maharashtra", age=24, gender="male", caste="general",
            disability_percent=40, education_level="graduate", course="B.A (completed)",
            occupation="unemployed job seeker", annual_income=60000, residence="urban", is_student=False),
        "required": {"nap-sdp", "fadse", "dky"},
        "expected": {
            "nap-sdp": "Skill development for PwDs at 40% or more, aged 15-59; approved-course and prior-training checks remain.",
            "fadse": "Maharashtra self-employment support: 40% disability, age 18-50, income under Rs 1 lakh.",
            "dky": "Disability-focused livelihood skilling; an announced programme is not proof that applications are open.",
        },
        "excluded": {"psgs-deg", "post-dis"},
    },
    "mp-obc-class11": {
        "profile": ProfileData(state="Madhya Pradesh", age=16, gender="male", caste="obc",
            education_level="class 11", course="Class 11 after Class 10 matriculation",
            occupation="student", is_student=True, annual_income=120000, residence="rural",
            previous_board="Madhya Pradesh Board", previous_class_percentage=75, previous_passing_year=2026),
        "required": {"pvpmc", "pm-yasasvipmsobcebcdnts", "pm-yasasvitcseobcebcdnts"},
        "expected": {
            "pvpmc": "MP backward-class post-matric support; passed Class 10 and income below Rs 3 lakh.",
            "pm-yasasvipmsobcebcdnts": "OBC post-matric route after a matriculation-equivalent Class 10; read the Class XI exception with its rule.",
            "pm-yasasvitcseobcebcdnts": "OBC Class XI top-class school route; notified-school/selection conditions remain unknown.",
        },
        "excluded": {"pmsm", "pre-sc"},
    },
    "odisha-pregnant-rural": {
        "profile": ProfileData(state="Odisha", age=25, gender="female", caste="general",
            occupation="daily wage worker", is_pregnant=True, marital_status="married",
            annual_income=120000, residence="rural", is_student=False),
        "required": {"mamata", "pmmvy", "jsy1", "jssk"},
        "expected": {
            "mamata": "Odisha maternity support at 19+; birth order and employment exclusions need confirmation.",
            "pmmvy": "Low-income pregnant worker; income is one alternative socioeconomic route, not a requirement to meet every listed category.",
            "jsy1": "Odisha is a low-performing-state route; HPS caste/BPL rules must not be applied to that route.",
            "jssk": "Pregnancy care and institutional delivery in a government facility; facility choice remains unknown.",
        },
        "notes": "Odisha jointly implements MAMATA-PMMVY from April 2025: https://mamata-pmmvy.odisha.gov.in/",
        "excluded": {"pmssc", "psgs-deg"},
    },
    "delhi-street-vendor": {
        "profile": ProfileData(state="Delhi", age=35, gender="male", caste="general",
            occupation="street vendor", annual_income=120000, residence="urban", is_student=False),
        "required": {"pm-svanidhi", "pm-sym", "pmmy"},
        "expected": {
            "pm-svanidhi": "Urban street-vendor working capital; vending certificate/survey/LoR is an alternative documentation route.",
            "pm-sym": "Unorganised worker aged 18-40 earning Rs 10,000/month; pension/tax exclusions need confirmation.",
            "pmmy": "Microenterprise credit for a vendor; credit history and proposed activity remain conditions.",
        },
        "excluded": {"kcc", "psgs-deg"},
    },
}


async def evaluate(case_name: str, limit: int, max_seconds: float = 60) -> dict:
    case = CASES[case_name]
    profile = case["profile"]
    candidates = []
    candidate_seconds = 0
    original_candidates = matcher.candidates

    async def observed_candidates(*args, **kwargs):
        nonlocal candidates, candidate_seconds
        started = time.monotonic()
        candidates = await original_candidates(*args, **kwargs)
        candidate_seconds = time.monotonic() - started
        return candidates

    started = time.monotonic()
    with patch.object(matcher, "candidates", observed_candidates):
        results = await matcher.match(profile, limit=limit)
    match_seconds = time.monotonic() - started
    candidate_slugs = {s.slug for s in candidates}
    by_slug = {r.scheme.slug: r for r in results}
    checks = {}
    checks["latency"] = match_seconds <= max_seconds
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

    for name, slug, updates in case.get("controls", []):
        checks[f"keep:{name}"] = await kept(slug, updates)
        if name == "punjab-sc-student":
            detail = await myscheme.get_scheme(slug)
            checks["judge:punjab-sc-student"] = (await matcher.judge(profile.model_copy(update=updates), detail)).verdict in {"eligible", "likely"}
    logging.info("eval %s: %.2fs match, %.2fs recall; failures=%s", case_name, match_seconds,
                 candidate_seconds, [name for name, ok in checks.items() if not ok])
    return {
        "case": case_name, "profile": profile.model_dump(exclude_none=True),
        "passed": all(checks.values()), "checks": checks,
        "timings": {"match_seconds": round(match_seconds, 2), "candidate_seconds": round(candidate_seconds, 2),
                    "max_seconds": max_seconds},
        "expected": [{"slug": slug, "reason": reason, "source": f"https://www.myscheme.gov.in/schemes/{slug}"}
                     for slug, reason in case["expected"].items()],
        "notes": case.get("notes"),
        "candidates": [{"slug": s.slug, "name": s.name, "state": s.state} for s in candidates],
        "results": [r.model_dump(mode="json") for r in results],
    }


async def run(args) -> dict:
    settings = get_settings()
    if args.model:
        # Keep lightweight screening models when pinning the detailed judge.
        settings.gemini_model_pool = ",".join(dict.fromkeys([args.model, *(m for m in settings.model_pool if "lite" in m)]))
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
    parser.add_argument("--max-seconds", type=float, default=60, help="Maximum end-to-end match time per profile")
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
