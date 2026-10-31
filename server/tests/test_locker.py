from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image
from pypdf import PdfReader

from app.db import get_db
from app.models import LockerItem
from app.routers import locker as router
from app.services import locker


def scan():
    image = Image.effect_noise((1800, 2400), 40).convert("RGB")
    out = BytesIO()
    image.save(out, "JPEG", quality=95)
    return out.getvalue()


def test_variants_are_valid_bounded_documents():
    variants = locker.variants_for(locker.image_from_upload(scan()))
    assert 0 < len(variants["jpg"]) <= 200_000
    assert 0 < len(variants["pdf"]) <= 300_000
    with Image.open(BytesIO(variants["jpg"])) as jpg:
        jpg.verify()
    assert len(PdfReader(BytesIO(variants["pdf"])).pages) == 1


def test_exif_orientation_and_metadata_are_removed():
    image = Image.new("RGB", (120, 240), "white")
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "Private Citizen"
    out = BytesIO()
    image.save(out, "JPEG", exif=exif)
    fixed = locker.image_from_upload(out.getvalue())
    assert fixed.size == (240, 120)
    with Image.open(BytesIO(locker.variants_for(fixed)["jpg"])) as variant:
        assert not variant.getexif()


def test_encrypted_files_round_trip_and_are_not_public(monkeypatch, tmp_path):
    monkeypatch.setattr(locker, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path / "storage"))
    root = locker.private_root()
    root.mkdir(parents=True)
    target = root / "original.enc"
    raw = b"PRIVATE ORIGINAL CONTENT"
    locker.encrypt_file(target, raw)
    assert raw not in target.read_bytes()
    assert locker.decrypt_file(str(target)) == raw
    assert not root.is_relative_to(tmp_path / "storage")
    with pytest.raises(ValueError):
        locker.remove_file(str(tmp_path / "outside"))


@pytest.mark.parametrize("accept,hint,want", [("application/pdf", "max 300 KB", "pdf"), ("image/jpeg", "200KB", "jpg"),
    ("image/jpg", "between 20 KB and 200 KB", "jpg"), ("", "", "jpg")])
def test_portal_variant_selection(accept, hint, want):
    item = SimpleNamespace(variants=[{"format": "jpg", "bytes": 150_000}, {"format": "pdf", "bytes": 250_000}])
    assert locker.choose_variant(item, accept, hint)["format"] == want
    for accept, hint in [("image/png", ""), ("application/pdf", "maximum 100 KB")]:
        with pytest.raises(ValueError):
            locker.choose_variant(item, accept, hint)


async def test_vision_only_sees_safe_document_headings(monkeypatch):
    image = Image.new("RGB", (800, 1000), "white")
    out = BytesIO()
    image.save(out, "PNG")
    monkeypatch.setattr(locker, "local_words", lambda im: [
        {"text": "Income", "x": 10, "y": 10, "width": 80, "height": 20},
        {"text": "Certificate", "x": 100, "y": 10, "width": 90, "height": 20},
        {"text": "PRIVATE_NAME", "x": 10, "y": 50, "width": 160, "height": 20},
        {"text": "123456789012", "x": 10, "y": 100, "width": 160, "height": 20}])
    generate = AsyncMock(return_value=locker.DocumentCheck(doc_type="income_certificate", readable=True))
    monkeypatch.setattr(locker.llm, "generate_json", generate)
    result, facts, copies = await locker.prepare(out.getvalue())
    assert result.doc_type == "income_certificate"
    assert facts["detected_headings"] == ["certificate", "income"]
    prompt = generate.call_args.args[0]
    assert "PRIVATE_NAME" not in prompt[0] and "123456789012" not in prompt[0]
    # The model receives a rebuilt image, not a scan with potentially missed PII.
    with Image.open(BytesIO(prompt[1].inline_data.data)) as preview:
        assert preview.getpixel((20, 60))[0] in range(210, 235)
    assert generate.call_args.kwargs["model"] == "lite"
    assert set(copies) == {"jpg", "pdf"}


async def test_owner_only_download_delete_and_no_private_paths(monkeypatch):
    item = LockerItem(id="item", profile_id="owner", doc_type="income_certificate", title="Income certificate",
        file_path="private/original.enc", mime="image/jpeg", variants=[{"format": "jpg", "bytes": 1800, "path": "private/jpg.enc"}],
        meta={"readable": True, "issues": []}, created_at=datetime.now(timezone.utc))
    db = SimpleNamespace(get=AsyncMock(return_value=item), delete=AsyncMock(), commit=AsyncMock())
    async def dependency(): yield db
    app = FastAPI()
    app.include_router(router.router, prefix="/api")
    app.dependency_overrides[get_db] = dependency
    decrypt = lambda path: b"document"
    monkeypatch.setattr(locker, "decrypt_file", decrypt)
    monkeypatch.setattr(locker, "remove_file", lambda path: None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/locker/item/file")).status_code == 401
        assert (await client.get("/api/locker/item/file?profile_id=other")).status_code == 404
        assert (await client.delete("/api/locker/item?profile_id=other")).status_code == 404
        download = await client.get("/api/locker/item/file?profile_id=owner&variant=jpg")
        assert download.content == b"document" and download.headers["cache-control"] == "no-store"
        assert "path" not in router.output(item).model_dump()["variants"][0]
        assert (await client.delete("/api/locker/item", headers={"X-Profile-ID": "owner"})).status_code == 204
        db.delete.assert_awaited_once_with(item)
