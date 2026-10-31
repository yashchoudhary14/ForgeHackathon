import json
from pathlib import Path

from app.agents.matcher import (occupational_target_mismatch, educational_target_mismatch,
                               target_text, qualified_restriction, explicit_target_mismatch, relevance)
from app.schemas import ProfileData, SchemeDetail


def recorded(slug):
    return SchemeDetail.model_validate(json.loads((Path(__file__).parent / "fixtures" / f"match-{slug}.json").read_text(encoding="utf-8")))


def test_pragati_course_requirement_is_in_description_not_eligibility():
    scheme = recorded("psgs-deg")
    assert "technical degree" not in scheme.eligibility_md.lower()
    assert "technical degree" in target_text(scheme).lower()
    assert "AICTE" in target_text(scheme)


def test_technical_title_excludes_general_courses_without_excluding_specialisations():
    scheme = recorded("psgs-deg")
    assert educational_target_mismatch(ProfileData(course="B.Sc"), scheme)
    for course in ("B.Tech", "B.Sc Nursing", "B.Sc Agriculture", None):
        assert not educational_target_mismatch(ProfileData(course=course), scheme)
    assert not educational_target_mismatch(ProfileData(course="B.Sc"), recorded("pmsfss"))


def test_course_does_not_get_discarded_at_profile_boundary():
    profile = ProfileData(education_level="ug", course="B.Sc", study_year=1)
    assert profile.model_dump(exclude_none=True)["course"] == "B.Sc"


def test_both_recorded_post_matric_schemes_have_sc_and_income_rules():
    for slug in ("pmsfss", "pmsscstb"):
        scheme = recorded(slug)
        assert "Scheduled Caste" in scheme.eligibility_md
        assert "income" in scheme.eligibility_md


def test_farmer_credit_needs_farming_evidence_but_student_can_also_farm():
    student = ProfileData(is_student=True, occupation="student", course="B.Sc")
    assert occupational_target_mismatch(student, recorded("kcc"))
    student.land_acres = 2
    assert not occupational_target_mismatch(student, recorded("kcc"))
    assert not occupational_target_mismatch(student, recorded("pmsscstb"))


def test_vendor_credit_recommendations_need_a_separate_farming_role_for_kcc():
    vendor = ProfileData(occupation="street vendor", is_student=False)
    assert occupational_target_mismatch(vendor, recorded("kcc"))
    vendor.occupation = "street vendor and tenant farmer"
    assert not occupational_target_mismatch(vendor, recorded("kcc"))


def test_class11_restriction_cannot_be_separated_from_its_matriculation_exception():
    source = recorded("yasasvi-obc").eligibility_md
    quote = "Students studying in the XI Class of the Higher Secondary School courses or the XII class of the Multipurpose High School will not be eligible for it being a continuous school course."
    assert qualified_restriction(quote, source)
    assert not qualified_restriction("Farmers", recorded("kcc").eligibility_md)


def test_jurisdiction_uses_official_metadata_even_when_prose_is_generic():
    scheme = recorded("pmssc")
    assert explicit_target_mismatch(ProfileData(state="Bihar"), scheme) in target_text(scheme)
    assert explicit_target_mismatch(ProfileData(state="Punjab"), scheme) is None
    assert explicit_target_mismatch(ProfileData(), scheme) is None
    scheme.state = "Punjab, Bihar"
    assert explicit_target_mismatch(ProfileData(state="Bihar"), scheme) is None
    for state in (None, "All", "All India"):
        scheme.state = state
        assert explicit_target_mismatch(ProfileData(state="Bihar"), scheme) is None


def test_nonstudent_mismatch_needs_an_explicit_applicant_rule():
    nonstudent = ProfileData(is_student=False)
    for slug in ("pre-sc", "psgs-deg"):
        scheme = recorded(slug)
        assert explicit_target_mismatch(nonstudent, scheme) in scheme.eligibility_md
        assert explicit_target_mismatch(ProfileData(is_student=True), scheme) is None
        assert explicit_target_mismatch(ProfileData(), scheme) is None
    scheme.eligibility_md = "The applicant's children must be students."
    assert explicit_target_mismatch(nonstudent, scheme) is None
    scheme.eligibility_md = "The applicant must be a student unless applying as a worker."
    assert explicit_target_mismatch(nonstudent, scheme) is None


def test_vendor_enterprise_credit_ranking_uses_official_description():
    vendor = ProfileData(occupation="street vendor", state="Delhi")
    scheme = recorded("pmmy")
    scheme.slug = "unseen-credit-scheme"
    generic = scheme.model_copy(update={"name": "General Loan Scheme", "brief": "A loan scheme", "tags": [], "state": "Delhi"})
    assert relevance(vendor, scheme) > relevance(vendor, generic)
