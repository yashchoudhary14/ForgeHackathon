import json
from pathlib import Path

from app.agents.matcher import target_text
from app.schemas import ProfileData, SchemeDetail


def recorded(slug):
    return SchemeDetail.model_validate(json.loads((Path(__file__).parent / "fixtures" / f"match-{slug}.json").read_text(encoding="utf-8")))


def test_pragati_course_requirement_is_in_description_not_eligibility():
    scheme = recorded("psgs-deg")
    assert "technical degree" not in scheme.eligibility_md.lower()
    assert "technical degree" in target_text(scheme).lower()
    assert "AICTE" in target_text(scheme)


def test_course_does_not_get_discarded_at_profile_boundary():
    profile = ProfileData(education_level="ug", course="B.Sc", study_year=1)
    assert profile.model_dump(exclude_none=True)["course"] == "B.Sc"


def test_both_recorded_post_matric_schemes_have_sc_and_income_rules():
    for slug in ("pmsfss", "pmsscstb"):
        scheme = recorded(slug)
        assert "Scheduled Caste" in scheme.eligibility_md
        assert "income" in scheme.eligibility_md
