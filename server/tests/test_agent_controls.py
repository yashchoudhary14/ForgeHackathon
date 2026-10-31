import pytest

from app.agents.browser import option_index
from app.agents.executor import Decision, RunSession, require_source


def test_option_match_does_not_confuse_male_and_female():
    assert option_index(["Female", "Male", "Transgender"], "male") == 1
    with pytest.raises(ValueError):
        option_index(["Male"], "Female")


def test_negated_option_with_internal_space_matches_exactly():
    assert option_index(["Divorced", "Married", "Un Married", "Widow"], "Unmarried") == 2


def test_option_match_normalizes_overlay_whitespace():
    assert option_index([" Bihar \n", "Uttar   Pradesh"], "uttar pradesh") == 1


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


@pytest.mark.parametrize("answer,label", [(True, "Yes"), (False, "No")])
def test_boolean_sources_use_portal_yes_no_labels(answer, label):
    rs = RunSession("unit", "", "https://scholarships.gov.in/", {"is_single_child": answer}, {})
    decision = Decision(thought="Select supplied answer", action="select", value_from="is_single_child")
    assert rs.resolve(decision) == label
