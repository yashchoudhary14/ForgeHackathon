import asyncio
import base64
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.agents import executor
from app.agents.browser import Browser


@pytest.mark.parametrize("kind", ["captcha", "otp", "login", "missing_field", "confirm_submit", "confirm_upload", "payment"])
async def test_human_guidance_uses_run_language_and_never_sends_values(monkeypatch, kind):
    rs = executor.RunSession("run", "private goal", "https://portal.gov.in", {}, {"phone": "9876543210"}, language="hi")
    rs.browser = SimpleNamespace(human_crop=AsyncMock(return_value="jpeg"))
    generate = AsyncMock(return_value=executor.HumanGuide(title="मदद", steps=["यह कदम खुद पूरा करें।"], lang="hi"))
    speech = AsyncMock(return_value="/files/audio/test.wav")
    monkeypatch.setattr(executor.llm, "generate_json", generate)
    monkeypatch.setattr(executor.sarvam, "tts_to_file", speech)
    event = await rs.human_event(kind, 3, message="9876543210")
    assert event["guide"]["lang"] == "hi" and len(event["guide"]["steps"]) == 1
    assert event["audio_url"].endswith(".wav") and event["crop"] == "jpeg"
    prompt = str(generate.call_args)
    assert "9876543210" not in prompt and "private goal" not in prompt
    assert generate.call_args.kwargs["model"] == "lite"
    rs.browser.human_crop.assert_awaited_once_with(kind, 3)
    speech.assert_awaited_once_with("यह कदम खुद पूरा करें।", "hi")


async def test_unsupported_audio_is_null(monkeypatch):
    rs = executor.RunSession("run", "", "https://portal.gov.in", {}, {}, language="xx")
    rs.browser = SimpleNamespace(human_crop=AsyncMock(return_value=None))
    monkeypatch.setattr(executor.llm, "generate_json", AsyncMock(return_value=executor.HumanGuide(title="Help", steps=["Continue"], lang="xx")))
    speech = AsyncMock()
    monkeypatch.setattr(executor.sarvam, "tts_to_file", speech)
    assert (await rs.human_event("login"))["audio_url"] is None
    speech.assert_not_awaited()


async def test_crop_is_target_image_enlarged_three_times():
    source = BytesIO()
    Image.new("RGB", (120, 40), "blue").save(source, "JPEG")
    image = SimpleNamespace(is_visible=AsyncMock(return_value=True), screenshot=AsyncMock(return_value=source.getvalue()))
    candidates = SimpleNamespace(all=AsyncMock(return_value=[image]))
    browser = Browser(None)
    browser.page = SimpleNamespace(locator=lambda selector: candidates)
    crop = await browser.human_crop("captcha")
    with Image.open(BytesIO(base64.b64decode(crop))) as enlarged:
        assert enlarged.size == (360, 120)
        assert enlarged.getpixel((180, 60))[2] > 240
    image.screenshot.assert_awaited_once()


def test_sensitive_values_and_one_time_codes_stay_out_of_planner():
    rs = executor.RunSession("run", "", "https://portal.gov.in", {}, {"full_name": "Private Citizen"})
    rs.private_values.add("904221")
    rs.answers["unknown_field"] = "Unclassified personal answer"
    assert rs.redact({"text": "Private Citizen 904221", "value": "904221"}) == {"text": "<private> <private>", "value": "<private>"}
    assert rs.citizen_view()["unknown_field"] == "<set>"


@pytest.mark.parametrize("kind", ["captcha", "otp"])
async def test_typed_one_time_answer_fills_page_without_model_access(monkeypatch, tmp_path, kind):
    rs = executor.RunSession("run", "check", "https://portal.gov.in", {}, {})
    snap = {"url": rs.portal_url, "title": "Form", "headings": [], "errors": [],
            "elements": [{"id": 7, "tag": "input", "name": kind}], "captcha": kind == "captcha", "text": ""}
    rs.browser = SimpleNamespace(page=SimpleNamespace(url=rs.portal_url),
        snapshot=AsyncMock(return_value=snap), screenshot=AsyncMock(return_value=b""),
        decision_screenshot=AsyncMock(return_value=b""), fill=AsyncMock(), settle=AsyncMock())
    rs.set_status = AsyncMock()
    rs.human_event = AsyncMock(return_value={"type": "needs_human", "kind": kind})
    rs.wait_human = AsyncMock(return_value={"type": "human_input", "value": "904221"})
    db = SimpleNamespace(add=lambda row: None, commit=AsyncMock())
    class DB:
        async def __aenter__(self): return db
        async def __aexit__(self, *args): pass
    monkeypatch.setattr(executor, "SessionLocal", DB)
    monkeypatch.setattr(executor, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path, agent_model="lite"))
    generate = AsyncMock(side_effect=[
        executor.ActionPlan(actions=[executor.Decision(thought="Human required", action="ask_human", kind=kind, element_id=7)]),
        executor.ActionPlan(actions=[executor.Decision(thought="Finished", action="done")])])
    monkeypatch.setattr(executor.llm, "generate_json", generate)
    result = await executor.build_graph(rs).ainvoke({"step": 0, "history": []})
    assert result["outcome"] == "done"
    rs.browser.fill.assert_awaited_once_with(7, "904221")
    assert rs.answers == {}
    assert all("904221" not in str(call) for call in generate.call_args_list)
