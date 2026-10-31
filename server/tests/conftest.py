import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pytest_configure(config):
    config.addinivalue_line("markers", "live: calls live official services (requires network)")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_llm_pool():
    # the pool's asyncio locks belong to one event loop, tests each get a new loop
    from app.services import llm
    llm._pool = None
    yield
    llm._pool = None
