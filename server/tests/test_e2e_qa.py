"""Offline regression checks for QA helpers; never launch Playwright or call live APIs."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def qa(tmp_path, monkeypatch):
    path = Path(__file__).parents[2] / "client" / ".qa" / "e2e.py"
    if not path.is_file():
        pytest.skip("Local .qa script is git-ignored and not present in this checkout")
    pytest.importorskip("playwright.sync_api")
    pytest.importorskip("PIL")
    spec = importlib.util.spec_from_file_location("adhikaar_live_qa", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OUT", tmp_path)
    return module


@pytest.mark.parametrize("message,expected", [
    ("Please provide your gender and age.", "gender: Male; age: 35"),
    ("Please state your gender (Male, Female, or Transgender).", "Male"),
    ("Please provide your age in years (e.g., 25).", "35"),
    ("Are you disabled?", "No"),
    ("Disability percentage", "0"),
    ("Are you below poverty line?", "Yes"),
    ("Which state are you from?", "Uttar Pradesh"),
])
def test_human_answers_use_declared_facts(qa, message, expected):
    assert qa.Demo.answer({"kind": "missing_field", "message": message}) == expected


@pytest.mark.parametrize("human", [
    {"kind": "missing_field", "message": "What is your bank account?"},
    {"kind": "missing_field", "message": "What is your DOB?"},
    {"kind": "otp", "message": "Enter OTP"},
    {"kind": "captcha", "message": "Read CAPTCHA"},
])
def test_unknown_or_verification_prompts_require_person(qa, human):
    with pytest.raises(AssertionError):
        qa.Demo.answer(human)


def test_civic_uses_local_photo_without_network_and_preserves_attribution(qa):
    demo = object.__new__(qa.Demo)
    # No browser or HTTP context is available to this helper.
    assert demo.commons_photo() == qa.COMMONS_PHOTO
    metadata = json.loads((qa.OUT / "commons-source.json").read_text())
    assert metadata["author"] == "Rrthakur22"
    assert metadata["license"] == "CC BY-SA 4.0"


def test_failure_snapshot_sends_owner(qa):
    response = SimpleNamespace(ok=True, json=lambda: {"status": "running", "steps": []})
    get = Mock(return_value=response)
    demo = object.__new__(qa.Demo)
    demo.profile_id = "owner id"
    demo.page = SimpleNamespace(url=qa.FRONTEND + "/runs/run-1")
    demo.context = SimpleNamespace(request=SimpleNamespace(get=get))
    demo.snapshot_run()
    get.assert_called_once_with(qa.API + "/api/agent/runs/run-1", params={"profile_id": "owner id"})
    assert json.loads((qa.OUT / "agent-snapshot.json").read_text())["status"] == "running"


def test_stream_request_assertion_does_not_depend_on_body_completion(qa):
    demo = object.__new__(qa.Demo)
    demo.page, demo.profile_id = object(), "citizen"
    demo.stream_requests = [{"page": demo.page, "path": "/api/schemes/match/stream",
                             "method": "POST", "input": {"profile_id": "citizen", "limit": 8}}]
    demo.assert_stream_request("/api/schemes/match/stream", 0)
    demo.profile_id = "other"
    with pytest.raises(AssertionError, match="Wrong method/profile"):
        demo.assert_stream_request("/api/schemes/match/stream", 0)


def test_farmer_fixture_is_one_real_write_with_client_storage_keys(qa):
    response = SimpleNamespace(ok=True, json=lambda: {"id": "farmer-1"})
    post, init = Mock(return_value=response), Mock()
    demo = object.__new__(qa.Demo)
    demo.context = SimpleNamespace(request=SimpleNamespace(post=post))
    demo.page = SimpleNamespace(add_init_script=init)
    demo.saved_profile = Mock(return_value=dict(qa.PROFILE_FACTS))
    demo.create_farmer()
    post.assert_called_once_with(qa.API + "/api/profile", data={
        "data": qa.PROFILE_FACTS, "language": "en", "mode": "manual",
    }, timeout=60000)
    assert demo.profile_id == "farmer-1"
    script = init.call_args.args[0]
    for key in ("adhikaar-profile", "adhikaar-mode", "adhikaar-language", "buddy-onboarding"):
        assert key in script
    assert '"farmer-1"' in script and "'false'" in script


def test_failed_farmer_fixture_is_not_retried_or_installed(qa):
    response = SimpleNamespace(ok=False, status=503, text=lambda: "Service unavailable")
    post, init = Mock(return_value=response), Mock()
    demo = object.__new__(qa.Demo)
    demo.profile_id = None
    demo.context = SimpleNamespace(request=SimpleNamespace(post=post))
    demo.page = SimpleNamespace(add_init_script=init)
    with pytest.raises(AssertionError, match="Farmer fixture HTTP 503"):
        demo.create_farmer()
    post.assert_called_once()
    init.assert_not_called()
    assert demo.profile_id is None


def test_onboarding_failure_restores_main_page_context_and_farmer(qa):
    demo = object.__new__(qa.Demo)
    main_page, main_context = object(), object()
    demo.page, demo.context, demo.profile_id = main_page, main_context, "farmer-1"
    guest_page = Mock()
    guest_context = Mock()
    guest_context.new_page.return_value = guest_page
    demo.browser = SimpleNamespace(new_context=Mock(return_value=guest_context))
    demo.watch_page = Mock()

    def failed_step(name, action):
        assert name == "01_home_manual_profile"
        assert demo.context is guest_context and demo.page is guest_page
        raise AssertionError("Manual form failure")

    demo.step = failed_step
    with pytest.raises(AssertionError, match="Manual form failure"):
        demo.onboarding_check()
    assert demo.page is main_page and demo.context is main_context
    assert demo.profile_id == "farmer-1"
    demo.browser.new_context.assert_called_once_with(viewport={"width": 390, "height": 844}, locale="en-IN")
    guest_page.add_init_script.assert_not_called()
    guest_context.close.assert_called_once()


def test_buddy_without_fixture_fails_before_constructing_profile_url(qa):
    demo = object.__new__(qa.Demo)
    demo.profile_id = None
    with pytest.raises(AssertionError, match="API-created farmer fixture"):
        demo.buddy("hi")
