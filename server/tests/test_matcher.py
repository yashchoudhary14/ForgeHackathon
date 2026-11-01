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


async def test_specific_central_sc_hit_survives_the_shortlist_cap(monkeypatch):
    central = SchemeSummary(slug="pmsfss", name="Post-Matric Scholarship for SC students", state="All")

    async def search(kw, filters, offset, size):
        # A relevant record is deep in the unfiltered category pass, behind enough
        # different generic records to overflow an interleaved 32-entry shortlist.
        prefix = str(sorted(filters.items())) + kw
        items = [SchemeSummary(slug=f"{prefix}-{i}", name="General financial support", state="All") for i in range(size)]
        if not filters and kw == "post matric scholarship scheduled caste":
            items[-1] = central
        return SearchOut(total=len(items), items=items)

    monkeypatch.setattr(myscheme, "search", search)
    monkeypatch.setattr(myscheme, "semantic_search", AsyncMock(return_value=[]))
    found = await matcher.candidates(BIHAR_STUDENT, None, 8)
    assert len(found) == 32 and central in found[:4]
    assert matcher.relevance(BIHAR_STUDENT, central) > matcher.relevance(
        BIHAR_STUDENT, SchemeSummary(slug="other", name="Post Matric Scholarship For Scheduled Caste", state="Tamil Nadu"))


def test_life_stage_queries_and_ranking_do_not_depend_on_scheme_slugs():
    cases = [
        (ProfileData(state="Uttar Pradesh", occupation="farmer", land_acres=2), "kisan", "Kisan Credit Card"),
        (ProfileData(state="Rajasthan", age=68, marital_status="widowed"), "widow pension", "Widow Pension"),
        (ProfileData(state="Maharashtra", disability_percent=40, occupation="unemployed job seeker"), "disability", "Skill Development of Persons with Disabilities"),
        (ProfileData(state="Odisha", is_pregnant=True), "maternity", "Maternity Assistance for Pregnant Women"),
        (ProfileData(state="Delhi", occupation="street vendor"), "street vendor", "Street Vendor Working Capital"),
    ]
    for profile, query, title in cases:
        assert query in matcher.keywords_for(profile, None)
        specific = SchemeSummary(slug="unseen-specific", name=title, state=profile.state)
        generic = SchemeSummary(slug="unseen-generic", name="General assistance", state="All")
        assert matcher.relevance(profile, specific) > matcher.relevance(profile, generic)


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


async def test_explicit_mismatches_do_not_depend_on_model_availability(monkeypatch):
    generate = AsyncMock(side_effect=AssertionError("clear mismatch needs no model"))
    monkeypatch.setattr(llm, "generate_json", generate)
    scheme = detail("unseen", "Student support", "The applicant must be a student.")
    assert not await matcher.triage(ProfileData(is_student=False), scheme)
    scheme.state = "Punjab"
    assert not await matcher.triage(ProfileData(state="Bihar"), scheme)
    generate.assert_not_called()


async def test_vendor_recall_does_not_need_the_semantic_cache(monkeypatch):
    from tests.test_matcher_records import recorded

    credit = recorded("pmmy")
    credit.slug = "unseen-enterprise-credit"

    async def search(kw, **kwargs):
        return SearchOut(total=1 if kw == "micro enterprise" else 0,
                         items=[credit] if kw == "micro enterprise" else [])

    monkeypatch.setattr(myscheme, "search", search)
    monkeypatch.setattr(myscheme, "semantic_search", AsyncMock(return_value=[]))
    assert await matcher.candidates(ProfileData(state="Delhi", occupation="street vendor"), None, 8) == [credit]


async def test_match_drops_mismatches_before_judging_and_allows_twelve_judges(monkeypatch):
    schemes = [detail(str(i), "Post-matric scholarship", "SC students") for i in range(12)]
    schemes += [detail("kcc", "Kisan Credit Card", "Farmers"),
                detail("psgs-deg", "Pragati Technical Degree", "Technical degree students")]
    monkeypatch.setattr(matcher, "candidates", AsyncMock(return_value=schemes))
    monkeypatch.setattr(myscheme, "get_scheme", AsyncMock(side_effect=lambda slug, **kw: next(s for s in schemes if s.slug == slug)))
    monkeypatch.setattr(myscheme, "index_schemes", AsyncMock())
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
    assert myscheme.index_schemes.await_count == 1
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
    assert generate.await_args.kwargs["model"] == matcher.get_settings().gemini_judge_model


@pytest.mark.parametrize("quote,source,found", [
    ("parents' income", "**parents&#39; income**", True),
    ("Only students resident may apply", "Only resident students may apply", False),
    ("The applicant is eligible", "The applicant is not eligible", False),
    ("men", "women", False),
    ("", "Official source", False),
])
def test_quotes_require_a_contiguous_official_span(quote, source, found):
    assert matcher.quote_found(quote, source) is found


async def test_an_unverified_failure_cannot_decide_the_verdict(monkeypatch):
    scheme = detail("unseen", "Support", "The applicant must be a student and must not have graduated.")
    judgement = matcher._Judgement(verdict="not_eligible", confidence=0.9, missing_info=[], documents_needed=[], reasons=[
        matcher._Reason(claim="Student", met=True, quote="The applicant must be a student", section="eligibility"),
        matcher._Reason(claim="Graduation required", met=False, quote="The applicant must have graduated", section="eligibility"),
    ])
    monkeypatch.setattr(llm, "generate_json", AsyncMock(return_value=judgement))
    result = await matcher._judge(BIHAR_STUDENT, scheme)
    assert result.verdict == "likely"
    assert [reason.claim for reason in result.reasons] == ["Student"]


@pytest.mark.parametrize("repaired", [True, False])
async def test_judge_retries_merged_quotes_once_without_weakening_verification(monkeypatch, repaired):
    from tests.test_matcher_records import recorded

    official = recorded("kcc")
    bad = matcher._Judgement(verdict="eligible", confidence=.9, missing_info=[], documents_needed=[], reasons=[
        matcher._Reason(claim="Farmer", met=True, section="eligibility",
            quote="Farmers who are owner cultivators, tenant farmers, oral lessees, or share croppers.")])
    good = bad.model_copy(update={"reasons": [matcher._Reason(claim="Owner cultivator", met=True,
        section="eligibility", quote="Farmers - individual/joint borrowers who are owner cultivators;")]})
    generate = AsyncMock(side_effect=[bad, good if repaired else bad])
    monkeypatch.setattr(llm, "generate_json", generate)
    result = await matcher._judge(ProfileData(occupation="farmer", land_acres=2), official)
    assert generate.await_count == 2
    assert result.verdict == ("eligible" if repaired else "unknown")
    assert all(matcher.quote_found(r.citation.quote, official.eligibility_md) for r in result.reasons)


async def test_time_budget_keeps_completed_results_and_cancels_slow_work(monkeypatch):
    schemes = [detail("ready", "Relevant scholarship", "SC students"), detail("slow", "Other scholarship", "SC students")]
    monkeypatch.setattr(matcher, "MATCH_SECONDS", 0.05)
    monkeypatch.setattr(matcher, "candidates", AsyncMock(return_value=schemes))
    monkeypatch.setattr(myscheme, "get_scheme", AsyncMock(side_effect=lambda slug, **kw: next(s for s in schemes if s.slug == slug)))
    monkeypatch.setattr(myscheme, "index_schemes", AsyncMock())
    monkeypatch.setattr(matcher, "triage", AsyncMock(return_value=True))
    cancelled = asyncio.Event()

    async def judge(p, scheme):
        if scheme.slug == "slow":
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        return MatchResult(scheme=scheme, verdict="likely", confidence=0.9, reasons=[])

    monkeypatch.setattr(matcher, "judge", judge)
    results = await matcher.match(BIHAR_STUDENT)
    assert [r.scheme.slug for r in results] == ["ready"]
    assert cancelled.is_set()


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
