"""Live locker check against a running local stack, with an actual local scan/photo.

python scripts/check_locker.py path/to/scan.jpg --expected-type income_certificate
Creates its own profile, uploads the file, then downloads and verifies both variants.
No mocks or fixture responses are used.
"""
import argparse
import asyncio
import json
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image
from pypdf import PdfReader


async def main(path: Path, api: str, expected_type: str | None, evidence_dir: Path | None):
    async with httpx.AsyncClient(base_url=api.rstrip("/"), timeout=120) as client:
        response = await client.post("/api/profile", json={"language": "hi"})
        response.raise_for_status()
        profile_id = response.json()["id"]
        with path.open("rb") as file:
            response = await client.post("/api/locker", data={"profile_id": profile_id},
                                         files={"file": (path.name, file, "application/octet-stream")})
        response.raise_for_status()
        item = response.json()
        if expected_type:
            assert item["meta"]["detected_doc_type"] == expected_type, item["meta"]
        assert "readable" in item["meta"] and isinstance(item["meta"]["issues"], list)
        for fmt, limit in (("jpg", 200_000), ("pdf", 300_000)):
            response = await client.get(f"/api/locker/{item['id']}/file",
                                        params={"variant": fmt}, headers={"X-Profile-ID": profile_id})
            response.raise_for_status()
            data = response.content
            assert 0 < len(data) <= limit, (fmt, len(data))
            assert len(data) == next(v["bytes"] for v in item["variants"] if v["format"] == fmt)
            if fmt == "jpg":
                with Image.open(BytesIO(data)) as image:
                    image.verify()
            else:
                assert len(PdfReader(BytesIO(data)).pages) == 1
            if evidence_dir:
                evidence_dir.mkdir(parents=True, exist_ok=True)
                (evidence_dir / f"variant.{fmt}").write_bytes(data)
        forbidden = await client.get(f"/api/locker/{item['id']}/file", params={"profile_id": "another-owner"})
        assert forbidden.status_code == 404
        if evidence_dir:
            (evidence_dir / "locker.json").write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"profile_id": profile_id, "locker": item}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--expected-type")
    parser.add_argument("--evidence-dir", type=Path)
    asyncio.run(main(**vars(parser.parse_args())))
