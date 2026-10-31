import pytest

from app.agents.browser import option_index


def test_option_match_does_not_confuse_male_and_female():
    assert option_index(["Female", "Male", "Transgender"], "male") == 1


def test_option_match_normalizes_overlay_whitespace():
    assert option_index([" Bihar \n", "Uttar   Pradesh"], "uttar pradesh") == 1


def test_option_match_rejects_ambiguous_and_empty_choices():
    for value in ("", "graduate", "unknown"):
        with pytest.raises(ValueError):
            option_index(["Undergraduate", "Postgraduate"], value)
