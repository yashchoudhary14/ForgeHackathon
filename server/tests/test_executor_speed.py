"""Exercise real graph routing: batching must never bypass a per-action guard."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.agents import executor
from app.agents.executor import ActionPlan, Decision, RunSession


def decision(action="type", element_id=1, **kwargs):
    return Decision(thought="Use the supplied fact", action=action, element_id=element_id, **kwargs)


@pytest.fixture
def graph_run(monkeypatch, tmp_path):
    rs = RunSession("speed-test", "Check eligibility", "https://portal.gov.in/", {
        "age": 25, "state": "Bihar", "is_student": True,
    }, {})
    snap = {"url": rs.portal_url, "title": "Eligibility", "headings": [], "errors": [],
            "captcha": False, "text": "", "navigation_id": 1,
            "elements": [{"id": 1, "tag": "input", "label": "Age", "value": ""},
                         {"id": 2, "tag": "select", "label": "State", "options": ["Bihar", "Goa"]},
                         {"id": 3, "tag": "input", "type": "checkbox", "label": "Student", "checked": False}]}

    async def fill(element_id, value):
        next(el for el in snap["elements"] if el["id"] == element_id)["value"] = value

    async def check(element_id, value):
        next(el for el in snap["elements"] if el["id"] == element_id)["checked"] = value

    rs.browser = SimpleNamespace(page=SimpleNamespace(url=rs.portal_url),
        snapshot=AsyncMock(side_effect=lambda: deepcopy(snap)), screenshot=AsyncMock(return_value=b"image"),
        decision_screenshot=AsyncMock(), fill=AsyncMock(side_effect=fill), select=AsyncMock(side_effect=fill),
        check=AsyncMock(side_effect=check), click=AsyncMock(), settle=AsyncMock())
    rs.set_status = AsyncMock()
    rs.human_event = AsyncMock(return_value={"type": "needs_human", "request_id": "request"})
    rs.wait_human = AsyncMock(side_effect=executor.RunAborted("Stop at human barrier"))
    rs.emit = AsyncMock()
    rs.duplicate_runs = AsyncMock(return_value=[])
    db = SimpleNamespace(add=Mock(), commit=AsyncMock())

    class Context:
        async def __aenter__(self): return db
        async def __aexit__(self, *args): pass

    monkeypatch.setattr(executor, "SessionLocal", Context)
    monkeypatch.setattr(executor.locker, "encrypt_file", Mock())
    monkeypatch.setattr(executor, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path, agent_model="strong"))
    generate = AsyncMock()
    monkeypatch.setattr(executor.llm, "generate_json", generate)
    return rs, snap, generate, db


def field_plan():
    return ActionPlan(actions=[decision(value_from="age"),
        decision("select", 2, value_from="state"), decision("check", 3, value_from="is_student")])


def done_plan():
    return ActionPlan(actions=[decision("done")])


async def test_three_fields_share_one_decision_with_fresh_guards_and_checkpoint_images(graph_run):
    rs, _, generate, db = graph_run
    generate.side_effect = [field_plan(), done_plan()]
    result = await executor.build_graph(rs).ainvoke({"step": 0, "history": []})
    assert result["outcome"] == "done"
    rs.browser.fill.assert_awaited_once_with(1, "25")
    rs.browser.select.assert_awaited_once_with(2, "Bihar")
    rs.browser.check.assert_awaited_once_with(3, True)
    assert rs.llm_calls == 2
    # Observe + each action's fresh guard, then observe/guard completion. Previously 9 reads.
    assert rs.browser.snapshot.await_count == 6
    assert rs.browser.screenshot.await_count == 2
    assert db.add.call_count == db.commit.await_count == 4
    rs.browser.decision_screenshot.assert_not_awaited()
    assert all(call.kwargs["model"] == "lite" and call.kwargs["thinking_level"] == "low"
               for call in generate.call_args_list)


async def test_unknown_source_on_second_action_stops_before_third_action(graph_run):
    rs, _, generate, _ = graph_run
    del rs.profile["state"]
    generate.return_value = field_plan()
    with pytest.raises(executor.RunAborted):
        await executor.build_graph(rs).ainvoke({"step": 0, "history": []})
    rs.browser.fill.assert_awaited_once_with(1, "25")
    rs.browser.select.assert_not_awaited()
    rs.browser.check.assert_not_awaited()
    assert rs.human_event.call_args.args[0] == "missing_field"
    assert rs.human_event.call_args.kwargs["field"] == "state"
    generate.assert_awaited_once()


@pytest.mark.parametrize("barrier", ["ask_human", "request_approval"])
async def test_explicit_barrier_discards_trailing_field_actions(graph_run, barrier):
    rs, _, generate, _ = graph_run
    stop = decision(barrier, 2, kind="missing_field" if barrier == "ask_human" else None)
    generate.side_effect = [ActionPlan(actions=[decision(value_from="age"), stop,
        decision("check", 3, value_from="is_student")]), ActionPlan(actions=[stop])]
    with pytest.raises(executor.RunAborted):
        await executor.build_graph(rs).ainvoke({"step": 0, "history": []})
    rs.browser.fill.assert_awaited_once()
    rs.browser.check.assert_not_awaited()
    rs.browser.click.assert_not_awaited()
    assert rs.human_event.call_args.args[0] == ("confirm_submit" if barrier == "request_approval" else "missing_field")


@pytest.mark.parametrize("change", ["new_field", "navigation", "validation", "enabled"])
async def test_guard_discards_remaining_batch_after_cascade(graph_run, change):
    rs, snap, generate, _ = graph_run

    async def fill(*args):
        if change == "new_field":
            snap["elements"].append({"id": 4, "tag": "input", "label": "New question"})
        elif change == "navigation":
            snap["navigation_id"] += 1
        elif change == "validation":
            snap["errors"] = ["Invalid age"]
        else:
            snap["elements"][1]["disabled"] = True

    rs.browser.fill.side_effect = fill
    generate.side_effect = [field_plan(), done_plan()]
    await executor.build_graph(rs).ainvoke({"step": 0, "history": []})
    rs.browser.select.assert_not_awaited()
    rs.browser.check.assert_not_awaited()


async def test_action_failure_escalates_next_decision_to_configured_model(graph_run):
    rs, _, generate, _ = graph_run
    rs.browser.fill.side_effect = ValueError("Portal rejected this entry")
    generate.side_effect = [field_plan(), done_plan()]
    await executor.build_graph(rs).ainvoke({"step": 0, "history": []})
    assert [call.kwargs["model"] for call in generate.call_args_list] == ["lite", "strong"]
    rs.browser.select.assert_not_awaited()


@pytest.mark.parametrize("tag", ["button", "a", "div"])
async def test_final_submit_uses_stronger_model_and_never_clicks_without_approval(graph_run, tag):
    rs, snap, generate, _ = graph_run
    snap["elements"] = [{"id": 1, "tag": tag, "text": "Final Submit"}]
    generate.return_value = ActionPlan(actions=[decision("click")])
    with pytest.raises(executor.RunAborted):
        await executor.build_graph(rs).ainvoke({"step": 0, "history": []})
    assert generate.call_args.kwargs["model"] == "strong"
    assert rs.human_event.call_args.args[0] == "confirm_submit"
    rs.browser.click.assert_not_awaited()


@pytest.mark.parametrize("kind", ["check", "click"])
async def test_second_checkbox_or_native_radio_requires_its_own_source(graph_run, kind):
    rs, snap, generate, _ = graph_run
    del rs.profile["is_student"]
    snap["elements"][2]["type"] = "radio" if kind == "click" else "checkbox"
    generate.return_value = ActionPlan(actions=[decision(value_from="age"),
        decision(kind, 3, value_from="is_student"), decision("select", 2, value_from="state")])
    with pytest.raises(executor.RunAborted):
        await executor.build_graph(rs).ainvoke({"step": 0, "history": []})
    rs.browser.fill.assert_awaited_once()
    rs.browser.check.assert_not_awaited()
    rs.browser.click.assert_not_awaited()
    rs.browser.select.assert_not_awaited()
    assert rs.human_event.call_args.kwargs["field"] == "is_student"


@pytest.mark.parametrize("kind", ["otp", "password", "captcha"])
async def test_sensitive_second_field_stops_batch_for_human(graph_run, kind):
    rs, snap, generate, _ = graph_run
    snap["elements"][1] = {"id": 2, "tag": "input", "type": kind if kind == "password" else "text", "name": kind}
    snap["captcha"] = kind == "captcha"
    generate.return_value = ActionPlan(actions=[decision(value_from="age"),
        decision("type", 2, value_from="state"), decision("check", 3, value_from="is_student")])
    with pytest.raises(executor.RunAborted):
        await executor.build_graph(rs).ainvoke({"step": 0, "history": []})
    rs.browser.fill.assert_awaited_once_with(1, "25")
    rs.browser.check.assert_not_awaited()
    assert rs.human_event.call_args.args[0] == ("login" if kind == "password" else kind)


def test_compact_planning_view_preserves_false_flags_and_redacts_input_values():
    original = [{"id": 1, "tag": "input", "label": "A" * 1000, "value": "Private citizen",
                 "checked": False, "options": ["B" * 1000], "name": ""}]
    compact = executor.planning_elements(original)
    assert compact[0]["value"] == "<set>"
    assert compact[0]["checked"] is False
    assert len(compact[0]["label"]) == 160 and len(compact[0]["options"][0]) == 100
    assert "name" not in compact[0]
    assert original[0]["value"] == "Private citizen"


def test_native_radio_click_requires_source_and_can_share_batch():
    radio = {"id": 1, "tag": "input", "type": "radio", "label": "Student"}
    click = decision("click")
    assert executor.execution_prefix([click, decision("type", 2)], [radio]) == [click, decision("type", 2)]
    assert executor.require_source(click, radio, {}).action == "ask_human"
