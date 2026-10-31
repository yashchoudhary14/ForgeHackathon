import asyncio
from unittest.mock import AsyncMock

from app.agents import matcher
from app.schemas import ProfileData, SchemeDetail, SchemeSummary, SearchOut
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
            if kw == "post matric scholarship sc":
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
