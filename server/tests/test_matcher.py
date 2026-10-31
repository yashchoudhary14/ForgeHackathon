import asyncio
from unittest.mock import AsyncMock

import pytest

from app.agents import matcher
from app.schemas import MatchResult, ProfileData, SchemeDetail, SchemeSummary, SearchOut
from app.services import llm, myscheme


BIHAR_STUDENT = ProfileData(
    state="Bihar", gender="female", caste="sc", age=19, course="B.Sc",
    education_level="ug", study_year=1, annual_income=140000,
    residence="rural", occupation="student", is_student=True,
)


async def test_category_and_state_recall_survives_missing_facets_and_crowding(monkeypatch):
    central = SchemeSummary(slug="pmsfss", name="Post-Matric Scholarship for SC students", state="All")
    state = SchemeSummary(slug="pmsscstb", name="SC/ST post-matric Bihar", state="Bihar")

    async def search(kw, filters, offset, size):
        items = [SchemeSummary(slug=f"generic-{i}", name="Generic") for i in range(size)]
        if filters == {"state": "Bihar"}:
            if kw == "post matric scholarship scheduled caste":
                items = [central]
            elif kw == "Bihar post matric scholarship":
                items = [state]
        return SearchOut(total=len(items), items=items)

    search_mock = AsyncMock(side_effect=search)
    monkeypatch.setattr(myscheme, "search", search_mock)
    monkeypatch.setattr(myscheme, "semantic_search", AsyncMock(return_value=[]))
    found = await matcher.candidates(BIHAR_STUDENT, None, 8)
    assert {"pmsfss", "pmsscstb"} <= {s.slug for s in found}
    assert len({s.slug for s in found}) == len(found)
    assert "Bihar scholarship" in {call.args[0] for call in search_mock.await_args_list}


async def test_recall_keeps_working_when_a_search_fails(monkeypatch):
    central = SchemeSummary(slug="pmsfss", name="SC post-matric", state="All")

    async def search(kw, **kwargs):
        raise RuntimeError("search unavailable")

    monkeypatch.setattr(myscheme, "search", search)
    monkeypatch.setattr(myscheme, "semantic_search", AsyncMock(return_value=[central]))
    assert await matcher.candidates(BIHAR_STUDENT, None, 8) == [central]


async def test_specific_central_hit_below_interleaved_cap_is_promoted(monkeypatch):
    central = SchemeSummary(slug="pmssc", name="Post Matric Scholarship For Scheduled Caste", state="All")

    async def search(kw, filters, **kwargs):
        items = [SchemeSummary(slug=f"{kw}-{len(filters)}-{i}", name="Generic scholarship") for i in range(12)]
        if kw == "post matric scholarship scheduled caste" and not filters:
            items[-1] = central
        return SearchOut(total=len(items), items=items)

    monkeypatch.setattr(myscheme, "search", search)
    monkeypatch.setattr(myscheme, "semantic_search", AsyncMock(return_value=[]))
    found = await matcher.candidates(BIHAR_STUDENT, None, 8)
    assert len(found) == 32
    assert found[0].slug == "pmssc"


@pytest.mark.parametrize("profile,query", [
    (ProfileData(land_acres=2), "kisan samman nidhi"),
    (ProfileData(age=68, marital_status="widow"), "old age pension"),
    (ProfileData(disability_percent=40), "disabled self employment"),
    (ProfileData(is_pregnant=True), "janani suraksha"),
    (ProfileData(occupation="street vendor"), "svanidhi"),
])
async def test_special_groups_get_relaxed_and_national_recall(monkeypatch, profile, query):
    search = AsyncMock(return_value=SearchOut(total=0, items=[]))
    monkeypatch.setattr(myscheme, "search", search)
    monkeypatch.setattr(myscheme, "semantic_search", AsyncMock(return_value=[]))
    await matcher.candidates(profile.model_copy(update={"state": "Delhi"}), None, 8)
    assert any(c.args[0] == query and c.kwargs["filters"] == {} for c in search.await_args_list)


def test_noisy_state_metadata_does_not_bury_specific_category_hit():
    central = SchemeSummary(slug="pmssc", name="Post Matric Scholarship For Scheduled Caste", state="Punjab")
    generic = SchemeSummary(slug="generic", name="Scholarship", state="All")
    assert matcher.candidate_priority(BIHAR_STUDENT, central) > matcher.candidate_priority(BIHAR_STUDENT, generic)


async def test_relevant_likely_result_precedes_generic_high_confidence(monkeypatch):
    profile = ProfileData(state="Uttar Pradesh", land_acres=2, occupation="farmer")
    schemes = [detail("generic", "General insurance", "All citizens"),
               detail("pmfby", "Pradhan Mantri Fasal Bima Yojna", "Farmers")]
    monkeypatch.setattr(matcher, "candidates", AsyncMock(return_value=schemes))
    monkeypatch.setattr(myscheme, "get_scheme", AsyncMock(side_effect=lambda slug, **kw: next(s for s in schemes if s.slug == slug)))
    monkeypatch.setattr(matcher, "triage", AsyncMock(return_value=True))
    monkeypatch.setattr(matcher, "judge", AsyncMock(side_effect=lambda p, s: MatchResult(
        scheme=s, verdict="likely", confidence=0.99 if s.slug == "generic" else 0.8, reasons=[])))
    assert (await matcher.match(profile, limit=1))[0].scheme.slug == "pmfby"


def detail(slug, name, eligibility):
    return SchemeDetail(id=slug, slug=slug, name=name, eligibility_md=eligibility,
                        source_url=f"https://www.myscheme.gov.in/schemes/{slug}")


@pytest.mark.parametrize("drop,quote,keep", [
    (True, "Farmers who are owner cultivators", False),
    (True, "Invented eligibility restriction", True),
    (True, "", True),
    (False, "", True),
])
async def test_triage_requires_official_target_evidence(monkeypatch, drop, quote, keep):
    # Isolate the model-evidence gate; the deterministic occupation gate has recorded-source tests.
    monkeypatch.setattr(matcher, "occupational_target_mismatch", lambda p, s: False)
    result = matcher._Triage(drop=drop, reason="Citizen is a student", quote=quote)
    monkeypatch.setattr(llm, "cached", AsyncMock(return_value=result.model_dump()))
    scheme = detail("farm", "Farm credit", "Farmers who are owner cultivators")
    assert await matcher.triage(BIHAR_STUDENT, scheme) is keep


async def test_triage_failure_keeps_candidate(monkeypatch):
    monkeypatch.setattr(llm, "cached", AsyncMock(side_effect=RuntimeError("provider unavailable")))
    assert await matcher.triage(BIHAR_STUDENT, detail("sc", "SC students", "SC students"))


async def test_match_drops_mismatches_before_judging_and_allows_twelve_judges(monkeypatch):
    schemes = [detail(str(i), "Post-matric scholarship", "SC students") for i in range(12)]
    schemes += [detail("kcc", "Kisan Credit Card", "Farmers"),
                detail("psgs-deg", "Pragati Technical Degree", "Technical degree students")]
    monkeypatch.setattr(matcher, "candidates", AsyncMock(return_value=schemes))
    monkeypatch.setattr(myscheme, "get_scheme", AsyncMock(side_effect=lambda slug, **kw: next(s for s in schemes if s.slug == slug)))
    monkeypatch.setattr(matcher, "triage", AsyncMock(side_effect=lambda p, s: s.slug not in {"kcc", "psgs-deg"}))
    active = peak = 0
    all_started = asyncio.Event()

    async def judge(p, s):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 12:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), 2)
        active -= 1
        return MatchResult(scheme=s, verdict="likely", confidence=0.9, reasons=[])

    judge_mock = AsyncMock(side_effect=judge)
    monkeypatch.setattr(matcher, "judge", judge_mock)
    results = await matcher.match(BIHAR_STUDENT)
    assert peak == 12 and judge_mock.await_count == 12
    assert not {"kcc", "psgs-deg"} & {r.scheme.slug for r in results}


async def test_judge_can_verify_course_restriction_in_description(monkeypatch):
    scheme = detail("technical", "Girl scholarship", "The applicant must be a girl student.")
    scheme.details_md = "Only students pursuing an AICTE technical degree may apply."
    result = matcher._Judgement(verdict="likely", confidence=0.9, missing_info=[], documents_needed=[], reasons=[
        matcher._Reason(claim="Technical degree required", met=False,
                        quote=scheme.details_md, section="details"),
    ])
    generate = AsyncMock(return_value=result)
    monkeypatch.setattr(llm, "generate_json", generate)
    judged = await matcher._judge(BIHAR_STUDENT, scheme)
    assert judged.verdict == "not_eligible"
    assert judged.reasons[0].citation.section == "details"
    assert scheme.details_md in generate.await_args.args[0]


@pytest.mark.parametrize("applies,expected", [(False, "eligible"), (True, "not_eligible"), (None, "likely")])
async def test_exclusion_polarity_is_explicit(monkeypatch, applies, expected):
    scheme = detail("study", "Post-matric", "The applicant should be a student.")
    scheme.exclusions_md = "A student who already completed an equivalent degree is excluded."
    result = matcher._Judgement(verdict="not_eligible", confidence=0.9, missing_info=[], documents_needed=[], reasons=[
        matcher._Reason(claim="Student", met=True, quote=scheme.eligibility_md, section="eligibility"),
        matcher._Reason(claim="Prior equivalent degree", met=False, quote=scheme.exclusions_md,
                        section="exclusions", exclusion_applies=applies),
    ])
    monkeypatch.setattr(llm, "generate_json", AsyncMock(return_value=result))
    assert (await matcher._judge(BIHAR_STUDENT, scheme)).verdict == expected
