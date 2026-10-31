from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.agents.executor import ActionPlan, Decision, execution_prefix, page_changed, _digest


def action(kind="type", element_id=1):
    return Decision(thought="Use the supplied fact", action=kind, element_id=element_id, value_from="state")


def snapshot():
    return {"url": "https://scholarships.gov.in/scholarshipEligibility", "navigation_id": 1,
            "headings": ["Check Your Eligibility"], "errors": [],
            "elements": [{"id": 1, "tag": "input", "label": "Parent Annual Income*", "value": ""}]}


def test_plan_limits_are_one_through_eight():
    assert len(ActionPlan(actions=[action()] * 8).actions) == 8
    for actions in ([], [action()] * 9):
        with pytest.raises(ValidationError):
            ActionPlan(actions=actions)


@pytest.mark.parametrize("kind", ["click", "ask_human", "request_approval", "done", "fail", "scroll", "wait"])
def test_control_or_navigation_action_never_runs_inside_batch(kind):
    assert execution_prefix([action(kind), action()]) == [action(kind)]
    assert execution_prefix([action(), action(kind), action()]) == [action()]


def test_filling_a_value_does_not_end_batch():
    before = snapshot()
    after = deepcopy(before)
    after["elements"][0]["value"] = "144000"
    assert not page_changed(before, after)


def test_pagination_text_is_progress_even_when_controls_are_reused():
    before = snapshot()
    before["text"] = "first ten institutes; 1-10 of 13"
    after = deepcopy(before)
    after["text"] = "Indian Institute of Technology Guwahati; 11-13 of 13"
    assert _digest(before) != _digest(after)


def test_visible_radio_can_share_batch_but_next_button_cannot():
    radio = action("click", 2)
    next_page = action("click", 3)
    elements = [{"id": 2, "role": "radio"}, {"id": 3, "tag": "button", "text": "Next"}]
    assert execution_prefix([radio, action(), next_page], elements) == [radio, action()]
    assert execution_prefix([next_page, radio], elements) == [next_page]


@pytest.mark.parametrize("change", ["navigation", "same_url_reload", "new_field", "new_step", "validation", "enabled"])
def test_batch_stops_when_the_plan_becomes_stale(change):
    before = snapshot()
    after = deepcopy(before)
    if change == "navigation":
        after["url"] += "/results"
    elif change == "same_url_reload":
        after["navigation_id"] += 1
    elif change == "new_field":
        after["elements"].append({"id": 2, "tag": "input", "label": "Single child"})
    elif change == "new_step":
        after["steps"] = ["Education"]
    elif change == "validation":
        after["errors"] = ["Required field"]
    else:
        before["elements"][0]["disabled"] = True
        after["elements"][0]["disabled"] = False
    assert page_changed(before, after)
