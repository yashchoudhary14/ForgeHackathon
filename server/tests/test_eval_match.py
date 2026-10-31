from unittest.mock import AsyncMock

import pytest

from app.agents import matcher
from app.schemas import MatchResult, ProfileData
from app.services import myscheme
from scripts import eval_match
from tests.test_matcher_records import recorded


@pytest.mark.parametrize("fails", [False, True])
async def test_eval_reports_each_judge_duration_and_failure(monkeypatch, fails):
    scheme = recorded("pmsfss")
    monkeypatch.setitem(eval_match.CASES, "recorded", {
        "profile": ProfileData(state="Bihar", is_student=True, caste="sc"),
        "required": {scheme.slug}, "expected": {}, "excluded": set(),
    })
    monkeypatch.setattr(matcher, "candidates", AsyncMock(return_value=[scheme]))
    monkeypatch.setattr(matcher, "triage", AsyncMock(return_value=True))
    monkeypatch.setattr(myscheme, "get_scheme", AsyncMock(return_value=scheme))
    monkeypatch.setattr(myscheme, "index_schemes", AsyncMock())
    result = MatchResult(scheme=scheme, verdict="likely", confidence=0.9, reasons=[])
    judge = AsyncMock(side_effect=RuntimeError("unavailable")) if fails else AsyncMock(return_value=result)
    monkeypatch.setattr(matcher, "judge", judge)

    report = await eval_match.evaluate("recorded", 8)

    assert report["passed"] is not fails
    timing = report["judge_timings"][scheme.slug]
    assert timing["seconds"] >= 0
    assert timing["status"] == ("error" if fails else "ok")
    assert (scheme.slug in report["judgements"]) is not fails
