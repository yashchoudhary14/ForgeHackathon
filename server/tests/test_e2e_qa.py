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
