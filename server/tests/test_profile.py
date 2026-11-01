"""Profile editing distinguishes omitted fields from an explicit clear."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.routers import profile as route
from app.schemas import ProfileUpdate


def test_profile_patch_preserves_omitted_fields_and_clears_null(monkeypatch):
    row = SimpleNamespace(
        id="profile-test", data={"age": 32, "state": "Assam", "course": "BA", "institution_type": "government"},
        sensitive=b"encrypted", language="en", mode="manual",
    )
    session = SimpleNamespace(get=AsyncMock(return_value=row), commit=AsyncMock())

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr(route.db, "SessionLocal", factory)
    monkeypatch.setattr(route.crypto, "decrypt_json", lambda _: {"full_name": "Private Citizen"})
    body = ProfileUpdate.model_validate({"data": {"age": None, "annual_income": 0, "is_student": False}, "language": "as", "mode": "talk"})
    result = asyncio.run(route.update_profile(row.id, body))
    assert row.data == {"age": None, "state": "Assam", "course": "BA", "institution_type": "government", "annual_income": 0, "is_student": False}
    assert result.sensitive.full_name == "Private Citizen"
    assert row.sensitive == b"encrypted"
    assert result.language == "as"
    assert result.mode == "talk"
    session.commit.assert_awaited_once()
