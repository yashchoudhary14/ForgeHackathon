import pytest

from app.agents.browser import option_index
from app.agents.executor import Decision, require_source


def test_option_match_does_not_confuse_male_and_female():
    assert option_index(["Female", "Male", "Transgender"], "male") == 1


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
