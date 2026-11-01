import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.agents.browser import Browser
from app.agents import executor


async def test_goto_waits_for_dom_without_networkidle():
    browser = Browser(AsyncMock())
    browser.page = SimpleNamespace(goto=AsyncMock(), locator=Mock(return_value=SimpleNamespace(count=AsyncMock(return_value=0))))
    browser.settle = AsyncMock()
    await browser.goto("https://portal.gov.in/")
    browser.page.goto.assert_awaited_once_with("https://portal.gov.in/", wait_until="domcontentloaded", timeout=45000)
    browser.settle.assert_awaited_once()


async def test_settle_waits_for_body_and_visible_loading_indicator():
    browser = Browser(AsyncMock())
    body = SimpleNamespace(wait_for=AsyncMock())
    busy = SimpleNamespace(count=AsyncMock(return_value=1), first=SimpleNamespace(wait_for=AsyncMock()))
    locator = Mock(side_effect=[body, SimpleNamespace(filter=Mock(return_value=busy))])
    browser.page = SimpleNamespace(wait_for_load_state=AsyncMock(), locator=locator)
    await browser.settle()
    browser.page.wait_for_load_state.assert_awaited_once_with("domcontentloaded", timeout=2500)
    body.wait_for.assert_awaited_once_with(state="visible", timeout=1000)
    busy.first.wait_for.assert_awaited_once_with(state="hidden", timeout=2000)


async def test_slow_frame_consumer_does_not_queue_more_sends():
    started, release = asyncio.Event(), asyncio.Event()

    async def send(frame):
        started.set()
        await release.wait()

    send = AsyncMock(side_effect=send)
    browser = Browser(send)
    browser._cdp = SimpleNamespace(send=AsyncMock())
    first = asyncio.create_task(browser._frame({"sessionId": 1, "data": base64.b64encode(b"first").decode()}))
    try:
        await asyncio.wait_for(started.wait(), 1)
        await browser._frame({"sessionId": 2, "data": base64.b64encode(b"latest").decode()})
        assert browser.last_frame == b"latest"
        assert browser._cdp.send.await_count == 2
        send.assert_awaited_once()
    finally:
        release.set()
        await first
    assert not browser._frame_sending


async def test_frame_send_error_releases_delivery_slot():
    browser = Browser(AsyncMock(side_effect=RuntimeError("Disconnected")))
    browser._cdp = SimpleNamespace(send=AsyncMock())
    with pytest.raises(RuntimeError):
        await browser._frame({"sessionId": 1, "data": base64.b64encode(b"frame").decode()})
    assert not browser._frame_sending


async def test_human_guidance_crop_and_private_translation_overlap(monkeypatch):
    rs = executor.RunSession("human-speed", "", "https://portal.gov.in/", {}, {}, language="hi")
    crop_started, translation_started = asyncio.Event(), asyncio.Event()

    async def generate(*args, **kwargs):
        await crop_started.wait()
        return executor.HumanGuide(title="Help", steps=["Complete this step"], lang="hi")

    async def crop(*args):
        crop_started.set()
        await translation_started.wait()
        return "crop"

    async def translate(*args, **kwargs):
        translation_started.set()
        return "translated"

    rs.browser = SimpleNamespace(human_crop=AsyncMock(side_effect=crop))
    model = AsyncMock(side_effect=generate)
    speech = AsyncMock(return_value="/files/audio/guide.wav")
    monkeypatch.setattr(executor.llm, "generate_json", model)
    monkeypatch.setattr(executor.sarvam, "tts_to_file", speech)
    monkeypatch.setattr(executor.sarvam, "translate", AsyncMock(side_effect=translate))
    event = await asyncio.wait_for(rs.human_event("missing_field", 1, message="Private portal question"), 1)
    assert event["crop"] == "crop" and event["message"] == "translated"
    assert event["audio_url"] == "/files/audio/guide.wav"
    assert "Private portal question" not in str(model.call_args)
    speech.assert_awaited_once_with("Complete this step", "hi")


async def test_crop_failure_cannot_prevent_approval_event(monkeypatch):
    rs = executor.RunSession("human-speed", "", "https://portal.gov.in/", {}, {}, language="xx")
    rs.browser = SimpleNamespace(human_crop=AsyncMock(side_effect=ValueError("No crop")))
    monkeypatch.setattr(executor.llm, "generate_json", AsyncMock(return_value=
        executor.HumanGuide(title="Review", steps=["Review before approving"], lang="xx")))
    event = await rs.human_event("confirm_submit", 1)
    assert event["type"] == "needs_human" and event["kind"] == "confirm_submit"
    assert event["crop"] is None
