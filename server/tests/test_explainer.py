"""Verify both versions and remove unsupported claims, not just their citations."""
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.agents import explainer
from app.db import get_db
from app.routers import assist
from app.schemas import ExplainIn, ProfileData


def explained(**updates):
    fields = dict(title="Notice", summary="", key_points=[], your_rights=[], what_it_means_for_you="",
                  deadlines=[], documents_needed=[], evidence=[])
    fields.update(updates)
    return explainer._Explained(**fields)


@pytest.fixture
def generation(monkeypatch):
    async def cached(namespace, parts, factory):
        return await factory()

    monkeypatch.setattr(explainer.llm, "cached", cached)
    generate = AsyncMock()
    monkeypatch.setattr(explainer.llm, "generate_json", generate)
    return generate


async def test_compare_requires_verified_quotes_from_each_correct_version(generation, monkeypatch):
    old = ("Old", "[page 2]\nThe income limit is Rs 100000. Application closes on 1 June.", "https://example.gov.in/old")
    new = ("New", "[page 3]\nThe income limit is Rs 200000. Application closes on 1 July.", "https://example.gov.in/new")
    monkeypatch.setattr(explainer, "_load_source", AsyncMock(side_effect=[old, new]))
    valid = dict(title="Income limit increased", description="The limit rose from Rs 100000 to Rs 200000.",
                 old_quote="The income limit is Rs 100000.", new_quote="The income limit is Rs 200000.",
                 affects_profile=True, impact="Your Rs 150000 income is within the new limit.")
    generation.return_value = explained(changes=[valid,
        {**valid, "old_quote": "The income limit is Rs 200000."},  # real quote, wrong version
        {**valid, "new_quote": "Every citizen is eligible."},
        {**valid, "old_quote": ""},
    ])
    body = ExplainIn(source={"type": "url", "url": old[2]}, compare_to={"type": "url", "url": new[2]}, with_audio=False)
    result = await explainer.explain(body, ProfileData(annual_income=150000))
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.affects_profile is True
    assert change.old_citation.source_url == old[2] and change.new_citation.source_url == new[2]
    assert change.old_citation.section == "page 2" and change.new_citation.section == "page 3"
    assert change.old_citation.quote in old[1] and change.new_citation.quote in new[1]
    assert "OLD SOURCE" in generation.await_args.args[0]
    assert generation.await_args.kwargs["model"] == "strong"


async def test_no_profile_never_claims_a_personal_effect(generation, monkeypatch):
    monkeypatch.setattr(explainer, "_load_source", AsyncMock(side_effect=[
        ("Old", "Old limit.", "old"), ("New", "New limit.", "new")]))
    generation.return_value = explained(what_it_means_for_you="You qualify.", evidence=[
        {"supports": "You qualify.", "quote": "New limit."}], changes=[
        dict(title="Limit", description="Limit changed.", old_quote="Old limit.", new_quote="New limit.",
             affects_profile=True, impact="You qualify.")])
    result = await explainer.explain(ExplainIn(source={"type": "document", "document_id": "old"},
        compare_to={"type": "document", "document_id": "new"}, with_audio=False), None)
    assert result.changes[0].affects_profile is None and result.changes[0].impact == ""
    assert result.what_it_means_for_you is None and result.personal_impacts == []


async def test_sections_and_legacy_fields_only_keep_supported_claims(generation, monkeypatch):
    text = ("## Benefits\nStudents receive support.\n## Eligibility\nResident students may apply.\n"
            "## Duties\nSubmit before 1 July.\n## Exclusions\nDuplicate claims are prohibited.\n"
            "## Documents required\nBring your income certificate.\n## How to apply (Online)\nRegister on the official portal.")
    monkeypatch.setattr(explainer, "_load_source", AsyncMock(return_value=("Source", text, "https://example.gov.in")))
    pairs = [("Support for students.", "Students receive support."),
             ("Submit by July.", "Submit before 1 July."),
             ("No duplicates.", "Duplicate claims are prohibited."),
             ("Take income proof.", "Bring your income certificate."),
             ("Register first.", "Register on the official portal."),
             ("As a student, check residence.", "Resident students may apply.")]
    generation.return_value = explained(summary=pairs[0][0], key_points=[pairs[0][0], "Invented benefit."],
        your_rights=[pairs[0][0]], duties=[pairs[1][0]], restrictions=[pairs[2][0]],
        deadlines=[pairs[1][0], "Apply tomorrow."], documents_needed=[pairs[3][0], "Take a passport."],
        how_to_apply=[pairs[4][0], pairs[0][0]], what_it_means_for_you=pairs[5][0], evidence=[
            *[{"supports": claim, "quote": quote} for claim, quote in pairs],
            {"supports": "Invented benefit.", "quote": "Everyone receives Rs 5000."},
            {"supports": "Take a passport.", "quote": "Bring a passport."},
        ])
    result = await explainer.explain(ExplainIn(source={"type": "scheme", "slug": "source"}, with_audio=False),
                                     ProfileData(is_student=True))
    assert result.summary == pairs[0][0] and result.key_points == [pairs[0][0]]
    assert result.your_rights == [item.text for item in result.rights]
    assert len(result.duties) == len(result.restrictions) == len(result.deadline_details) == 1
    assert result.documents_needed == [pairs[3][0]]
    assert [item.text for item in result.how_to_apply] == [pairs[4][0]]  # benefits quote cannot support application steps
    assert result.personal_impacts[0].text == pairs[5][0]
    assert all(explainer.quote_found(item.quote, text) for item in result.citations)


async def test_compare_validates_both_sources_before_network(monkeypatch):
    app = FastAPI()
    app.include_router(assist.router, prefix="/api")

    async def session():
        yield None

    app.dependency_overrides[get_db] = session
    forbidden = AsyncMock(side_effect=AssertionError("must validate before loading"))
    monkeypatch.setattr(explainer, "explain", forbidden)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post("/api/explain/compare", json={"old": {"type": "url", "url": "https://example.gov.in"},
                                                               "new": {"type": "document"}})
    assert result.status_code == 422
    forbidden.assert_not_called()
