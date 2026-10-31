import pytest
from types import SimpleNamespace

from app.agents.browser import Browser, option_index
from app.agents.executor import Decision, RunSession, require_source, explicitly_requested_option


def test_option_match_does_not_confuse_male_and_female():
    assert option_index(["Female", "Male", "Transgender"], "male") == 1
    with pytest.raises(ValueError):
        option_index(["Male"], "Female")


def test_portal_errors_expose_status_and_path_only_and_clear_on_recovery():
    browser = Browser(None)
    request = SimpleNamespace(resource_type="xhr", method="POST")
    response = SimpleNamespace(request=request, status=503,
                               url="https://scholarships.gov.in/api/states?token=private")
    browser._response(response)
    assert browser.network_errors == {"POST /api/states": 503}
    response.status = 200
    browser._response(response)
    assert not browser.network_errors
    for url in ("https://scholarships.gov.in/api/otp", "https://example.com/analytics"):
        response.url, response.status = url, 503
        browser._response(response)
    assert not browser.network_errors
    response.url = "https://scholarships.gov.in/api/imageCaptcha"
    browser._response(response)
    assert browser.network_errors == {"POST /api/imageCaptcha": 503}


def test_negated_option_with_internal_space_matches_exactly():
    assert option_index(["Divorced", "Married", "Un Married", "Widow"], "Unmarried") == 2


def test_option_match_normalizes_overlay_whitespace():
    assert option_index([" Bihar \n", "Uttar   Pradesh"], "uttar pradesh") == 1


def test_zero_matches_no_only_on_binary_yes_no_controls():
    assert option_index(["Yes", "No"], "0") == 1
    assert option_index(["0", "40", "100"], "0") == 0
    with pytest.raises(ValueError):
        option_index(["Yes", "No", "Unknown"], "0")


def test_option_match_rejects_ambiguous_and_empty_choices():
    for value in ("", "graduate", "unknown"):
        with pytest.raises(ValueError):
            option_index(["Undergraduate", "Postgraduate"], value)


def test_unsupplied_answer_is_sent_to_human():
    d = Decision(thought="Not specified, choose No", action="select", element_id=1, value="No")
    got = require_source(d, {"role": "combobox", "label": "Single child", "formcontrolname": "single_child"}, {})
    assert got.action == "ask_human" and got.value_from == "single_child"


def test_age_does_not_authorize_entering_birth_date():
    d = Decision(thought="Open calendar", action="click", element_id=1)
    got = require_source(d, {"label": "Open calendar", "field_label": "Date of Birth"}, {"age": 19})
    assert got.action == "ask_human" and got.value_from == "dob"


def test_supplied_fact_allows_option_translation():
    d = Decision(thought="Select caste", action="select", value="Scheduled Caste", value_from="caste")
    assert require_source(d, {"role": "combobox", "label": "Caste"}, {"caste": "sc"}) == d


@pytest.mark.parametrize("key", ["instituteName", "college_name", "InstitutionName"])
def test_portal_institute_names_reuse_known_institution(key):
    d = Decision(thought="Search college", action="type", element_id=1, value_from=key)
    known = {"institution_name": "IIT Guwahati"}
    got = require_source(d, {"tag": "input", "label": "Institute Name"}, known)
    assert got.action == "type" and got.value_from == "institution_name"


@pytest.mark.parametrize("answer,label", [(True, "Yes"), (False, "No")])
def test_boolean_sources_use_portal_yes_no_labels(answer, label):
    rs = RunSession("unit", "", "https://scholarships.gov.in/", {"is_single_child": answer}, {})
    decision = Decision(thought="Select supplied answer", action="select", value_from="is_single_child")
    assert rs.resolve(decision) == label


def test_human_answers_visible_except_personal_fields():
    rs = RunSession("unit", "", "https://scholarships.gov.in/", {}, {})
    rs.answers.update(scheme_type_id="Post Matric/Top Class/MCM", dob="23/04/2007")
    assert rs.citizen_view()["scheme_type_id"] == "Post Matric/Top Class/MCM"
    assert rs.citizen_view()["dob"] == "<set>"


def test_search_fragments_do_not_truncate_ordinary_fields_or_invent_text():
    rs = RunSession("unit", "", "https://scholarships.gov.in/", {"institution_name": "IIT Guwahati"}, {})
    d = Decision(thought="Broaden search", action="type", value="GUWAHATI", value_from="institution_name")
    assert rs.resolve(d, search_field=True) == "GUWAHATI"
    assert rs.resolve(d) == "IIT Guwahati"
    with pytest.raises(ValueError):
        rs.resolve(d.model_copy(update={"value": "Delhi"}), search_field=True)


def test_goal_cannot_supply_unspecified_application_history():
    rs = RunSession("unit", "Check scholarship eligibility", "https://scholarships.gov.in/", {}, {})
    assert rs.resolve(Decision(thought="Workflow choice", action="select", value_from="goal", value="Scholarship")) == "Scholarship"
    with pytest.raises(ValueError):
        rs.resolve(Decision(thought="Unknown history", action="select", value_from="goal", value="Renewal"))


def test_goal_supports_only_explicitly_named_overlay_options():
    d = Decision(thought="Choose requested service", action="click", value_from="goal")
    assert explicitly_requested_option(d, {"role": "option", "text": "Scholarship"}, "Check scholarship eligibility")
    assert not explicitly_requested_option(d, {"role": "option", "text": "Renewal"}, "Check scholarship eligibility")
    assert not explicitly_requested_option(d, {"role": "button", "text": "Scholarship"}, "Check scholarship eligibility")


def test_missing_source_on_named_workflow_option_uses_goal_only_for_workflow_fields():
    d = Decision(thought="Select requested service", action="click", element_id=1)
    el = {"role": "option", "text": "Scholarship", "field_label": "Application Type"}
    result = require_source(d, el, {"goal": "Check scholarship eligibility"})
    assert result.action == "click" and result.value_from == "goal"
    el = {"role": "option", "text": "No", "field_label": "Is disabled"}
    assert require_source(d, el, {"goal": "Parents not alive: No"}).action == "ask_human"
