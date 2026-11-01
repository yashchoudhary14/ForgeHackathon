"""Offline cleanup regressions for the local live QA script."""
import importlib.util
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
    spec = importlib.util.spec_from_file_location("agent_cleanup_qa", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OUT", tmp_path)
    return module


@pytest.fixture
def demo(qa):
    demo = object.__new__(qa.Demo)
    demo.profile_id = "owner"
    demo.started_runs = set()
    demo.network_errors, demo.browser_errors, demo.results = [], [], []
    demo.snapshot_run = Mock()
    demo.page = Mock(url=qa.FRONTEND + "/runs/run-1")
    demo.context = SimpleNamespace(request=SimpleNamespace(
        get=Mock(return_value=SimpleNamespace(ok=True, json=lambda: [])),
        post=Mock(return_value=SimpleNamespace(ok=True, json=lambda: {"status": "aborted"}))))
    return demo


@pytest.mark.parametrize("outcome", ["confirm_submit", "done", "service_handoff", "failed"])
def test_every_finished_check_aborts_its_runs(qa, demo, outcome):
    demo.started_runs.add("run-1")

    def action():
        if outcome == "failed":
            raise AssertionError("Portal check failed")
        return outcome

    demo.step("07_agent", action)
    demo.context.request.post.assert_called_once_with(
        qa.API + "/api/agent/runs/run-1/abort", params={"profile_id": "owner"}, timeout=60000)
    assert not demo.started_runs
    assert demo.results[-1][1] == ("FAIL" if outcome == "failed" else "PASS")


def test_tracks_create_response_even_without_websocket(qa, demo):
    demo.observe_response(SimpleNamespace(url=qa.API + "/api/agent/runs", status=200, ok=True,
        request=SimpleNamespace(method="POST"), json=lambda: {"id": "created"}))
    assert demo.started_runs == {"created"}
    demo.abort_runs()
    assert not demo.started_runs


def test_tracks_service_run_from_websocket_and_deduplicates(qa, demo):
    socket = Mock(url=qa.API.replace("https://", "wss://") + "/api/agent/runs/service/ws?profile_id=owner")
    demo.observe_socket(socket)
    demo.observe_socket(socket)
    assert demo.started_runs == {"service"}


def test_discovers_service_run_even_if_redirect_and_socket_failed(qa, demo):
    demo.context.request.get.return_value = SimpleNamespace(ok=True, json=lambda: [
        {"id": "service", "status": "running"}, {"id": "finished", "status": "done"},
    ])
    demo.abort_runs()
    demo.context.request.get.assert_called_once_with(
        qa.API + "/api/agent/runs", params={"profile_id": "owner"}, timeout=30000)
    demo.context.request.post.assert_called_once_with(
        qa.API + "/api/agent/runs/service/abort", params={"profile_id": "owner"}, timeout=60000)


def test_cleanup_attempts_all_runs_and_retains_failures(demo):
    demo.started_runs = {"good", "bad"}

    def post(url, **kwargs):
        if url.endswith("/bad/abort"):
            return SimpleNamespace(ok=False, status=503, text=lambda: "Unavailable")
        return SimpleNamespace(ok=True, json=lambda: {"status": "done"})

    demo.context.request.post.side_effect = post
    with pytest.raises(AssertionError, match="Could not stop test runs: bad"):
        demo.abort_runs()
    assert demo.context.request.post.call_count == 2
    assert demo.started_runs == {"bad"}


def test_cleanup_failure_fails_the_check(demo):
    demo.started_runs = {"run-1"}
    demo.context.request.post.side_effect = RuntimeError("offline")
    demo.step("07_agent", lambda: "confirm_submit")
    assert demo.results[-1][1] == "FAIL"
    assert "cleanup:" in demo.results[-1][3]
    assert demo.started_runs == {"run-1"}
