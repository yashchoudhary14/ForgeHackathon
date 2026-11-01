"""Offline regressions for numeric hallucinations and organisational schemes."""
from unittest.mock import AsyncMock

import pytest

from app.agents import matcher
from app.agents.matching_rules import profile_text
from app.schemas import ProfileData, SchemeDetail
from app.services import llm


def scheme(text, name="Student support"):
    return SchemeDetail(id="support", slug="support", name=name, eligibility_md=text,
                        source_url="https://www.myscheme.gov.in/schemes/support")


@pytest.mark.parametrize("income,display", [(110000, "₹1,10,000 (1.1 lakh)"),
    (100000, "₹1,00,000 (1 lakh)"), (12500000, "₹1,25,00,000 (125 lakh)"),
    (0, "₹0 (0 lakh)")])
def test_indian_income_display(income, display):
    assert display in profile_text(ProfileData(annual_income=income))


@pytest.mark.parametrize("profile,quote,keep", [
    (ProfileData(annual_income=110000), "Annual income must not exceed ₹2,50,000.", True),
    (ProfileData(annual_income=110000), "Maximum annual income is ₹1,00,000.", False),
    (ProfileData(annual_income=100000), "Maximum annual income is ₹1,00,000.", True),
    (ProfileData(annual_income=250000), "Annual income must be below 2.5 lakh.", False),
    (ProfileData(annual_income=110000), "Annual income must be less than Rs. 2.5 lakh.", True),
    (ProfileData(annual_income=110000), "The **annual income of the family** must not be more than **₹ 8,00,000/- per annum**.", True),
    (ProfileData(annual_income=800000), "Annual income must not be greater than ₹8,00,000.", True),
    (ProfileData(annual_income=75000), "Annual income must be between 50,000 and 1 lakh.", True),
    (ProfileData(annual_income=110000), "Annual income must **not exceed** Rs 2 lakh.", True),
    (ProfileData(age=18), "Age should not be less than 18 years.", True),
    (ProfileData(annual_income=120000), "Monthly income must not exceed Rs 15,000.", True),
    (ProfileData(annual_income=240000), "Monthly income must not exceed Rs 15,000.", False),
    (ProfileData(annual_income=None), "Annual income must not exceed ₹1,00,000.", True),
    (ProfileData(age=20), "Age must be between 18 and 25 years.", True),
    (ProfileData(age=26), "Age must be between 18 and 25 years.", False),
    (ProfileData(age=18), "Minimum age is 18 years.", True),
    (ProfileData(age=17), "Minimum age is 18 years.", False),
    (ProfileData(age=25), "Age must be below 25 years.", False),
    (ProfileData(age=20), "Age must meet the prescribed limit.", True),
])
async def test_triage_checks_actual_profile_against_quoted_limit(monkeypatch, profile, quote, keep):
    result = matcher._Triage(drop=True, reason="The citizen's income or age exceeds the limit.", quote=quote)
    # Only mention the field actually being rejected; a second unverified numeric
    # claim must itself fail open.
    result.reason = ("Annual income of ₹1,100,000 exceeds the maximum limit."
                     if "income" in quote.lower() else "Age is outside the permitted range.")
    monkeypatch.setattr(llm, "cached", AsyncMock(return_value=result.model_dump()))
    assert await matcher.triage(profile, scheme(quote)) is keep


async def test_both_model_prompts_include_formatted_income(monkeypatch):
    async def fresh(namespace, parts, factory):
        return await factory()

    profile = ProfileData(annual_income=110000)
    official = scheme("Annual income must not exceed ₹2,50,000.")
    screen = AsyncMock(return_value=matcher._Triage(drop=False, reason="", quote=""))
    monkeypatch.setattr(llm, "cached", fresh)
    monkeypatch.setattr(llm, "generate_json", screen)
    await matcher.triage(profile, official)
    assert "₹1,10,000 (1.1 lakh)" in screen.await_args.args[0]
    screen.return_value = matcher._Judgement(verdict="not_eligible", confidence=.9,
        missing_info=[], documents_needed=[], reasons=[matcher._Reason(
            claim="Annual income of ₹1,100,000 exceeds the limit.", met=False,
            quote=official.eligibility_md, section="eligibility")])
    result = await matcher.judge(profile, official)
    assert "₹1,10,000 (1.1 lakh)" in screen.await_args.args[0]
    assert result.verdict == "likely"
    assert result.reasons[0].met is None
    assert "1,100,000" not in result.reasons[0].claim


async def test_numeric_exclusion_is_checked_in_its_own_polarity(monkeypatch):
    official = scheme("Students may apply.")
    official.exclusions_md = "Applicants with annual income above Rs 2.5 lakh are excluded."
    judgement = matcher._Judgement(verdict="not_eligible", confidence=.9, missing_info=[],
        documents_needed=[], reasons=[matcher._Reason(claim="Income exclusion", met=False,
            exclusion_applies=True, quote=official.exclusions_md, section="exclusions")])
    monkeypatch.setattr(llm, "generate_json", AsyncMock(return_value=judgement))
    assert (await matcher._judge(ProfileData(annual_income=110000), official)).verdict == "likely"
    assert (await matcher._judge(ProfileData(annual_income=300000), official)).verdict == "not_eligible"


@pytest.mark.parametrize("name,text", [
    ("Construction of Hostels for OBC Boys and Girls", "OBC boys and girls studying in recognised institutions."),
    ("Grants to Voluntary Organisations", "Support for educational projects."),
    ("Educational infrastructure", "Eligible applicants are State Governments, UT Administrations and NGOs."),
    ("Community support", "Grants are provided to voluntary organisations for welfare activities."),
])
async def test_institutional_schemes_are_rejected_with_official_evidence(monkeypatch, name, text):
    generate = AsyncMock(side_effect=AssertionError("An institutional grant needs no citizen judge"))
    monkeypatch.setattr(llm, "generate_json", generate)
    official = scheme(text, name)
    profile = ProfileData(age=20, caste="obc", occupation="student", is_student=True)
    assert not await matcher.triage(profile, official)
    result = await matcher.judge(profile, official)
    assert result.verdict == "not_eligible"
    reason = result.reasons[0]
    assert reason.met is False
    source = matcher.target_text(official) if reason.citation.section == "details" else text
    assert matcher.quote_found(reason.citation.quote, source)
    generate.assert_not_awaited()


@pytest.mark.parametrize("name,text", [
    ("Hostel admission for OBC students", "Students in recognised institutions may apply."),
    ("Construction workers scholarship", "Children of construction workers may apply through their institutions."),
    ("Construction workers hostel admission", "Construction workers may apply for hostel accommodation."),
    ("Student support", "Eligible applicants include individuals and organisations."),
])
async def test_citizen_benefits_are_not_mistaken_for_institutional_grants(monkeypatch, name, text):
    monkeypatch.setattr(llm, "cached", AsyncMock(return_value=matcher._Triage(drop=False, reason="", quote="").model_dump()))
    assert await matcher.triage(ProfileData(age=20, caste="obc", is_student=True), scheme(text, name))


async def test_recorded_obc_hostel_funding_is_not_a_student_entitlement(monkeypatch):
    from tests.test_matcher_records import recorded

    official = recorded("obc-hostels")
    profile = ProfileData(age=20, caste="obc", occupation="student", is_student=True)
    monkeypatch.setattr(llm, "generate_json", AsyncMock(side_effect=AssertionError("must reject before model")))
    assert not await matcher.triage(profile, official)
    result = await matcher.judge(profile, official)
    assert result.verdict == "not_eligible"
    citation = result.reasons[0].citation
    assert citation.section == "eligibility"
    assert "State Governments and UT Administrations" in citation.quote
    assert matcher.quote_found(citation.quote, official.eligibility_md)
