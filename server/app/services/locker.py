"""Encrypted document storage and bounded portal variants.

Only locally allowlisted document headings reach vision. Personal text and
photographs are never copied into the preview. OCR runs on this server.
"""
import asyncio
import base64
import csv
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from io import BytesIO, StringIO
from pathlib import Path
from typing import Literal

from google.genai import types
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError
from pydantic import BaseModel, Field
from pypdf import PdfReader

from ..config import get_settings
from ..models import LockerItem
from . import crypto, llm

DocType = Literal["aadhaar", "income_certificate", "caste_certificate", "domicile", "marksheet", "photo", "land_record", "bank_passbook", "other"]
MAX_UPLOAD = 15 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000


class DocumentCheck(BaseModel):
    doc_type: DocType
    readable: bool
    issues: list[Literal["blurry", "cut_off", "glare", "unreadable"]] = Field(default_factory=list)


def private_root() -> Path:
    # A sibling of /files, never inside the public StaticFiles mount.
    return Path(str(Path(get_settings().storage_dir).resolve()) + "-private") / "locker"


def encrypt_file(path: Path, data: bytes):
    path.write_text(crypto.encrypt_json({"bytes": base64.b64encode(data).decode("ascii")}), encoding="ascii")


def decrypt_file(path: str) -> bytes:
    return base64.b64decode(crypto.decrypt_json(Path(path).read_text(encoding="ascii"))["bytes"], validate=True)


def remove_file(path: str):
    target = Path(path).resolve()
    if not target.is_relative_to(private_root().resolve()):
        raise ValueError("Invalid private document path")
    target.unlink(missing_ok=True)


def image_from_upload(data: bytes) -> Image.Image:
    if data.startswith(b"%PDF-"):
        # Camera scanners commonly produce one full-page image inside a PDF.
        # Never silently drop pages or render only one image from a composed page.
        try:
            pdf = PdfReader(BytesIO(data))
            if pdf.is_encrypted or len(pdf.pages) != 1:
                raise ValueError("Upload one unencrypted page at a time")
            page = pdf.pages[0]
            images = list(page.images)
            operations = page.get_contents().operations if page.get_contents() else []
            if (len(images) != 1 or (page.extract_text() or "").strip() or
                    any(operator not in {b"q", b"Q", b"cm", b"Do"} for _, operator in operations)):
                raise ValueError("For this PDF, upload a photo/scan of each page instead")
            image = image_from_upload(images[0].data)
            return image.rotate(-page.rotation, expand=True) if page.rotation else image
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Cannot read this PDF; upload a photo/scan instead") from exc
    try:
        with Image.open(BytesIO(data)) as source:
            if getattr(source, "n_frames", 1) != 1:
                raise ValueError("Upload one page at a time; animated/multipage images are not supported")
            source.load()
            image = ImageOps.exif_transpose(source)
            # Flatten transparent scans onto white before conversion.
            rgba = image.convert("RGBA")
            rgb = Image.new("RGB", rgba.size, "white")
            rgb.paste(rgba, mask=rgba.getchannel("A"))
            return rgb
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Upload a JPG, PNG, WEBP or TIFF scan/photo, one page at a time") from exc


def bounded_image(image: Image.Image, fmt: str, limit: int) -> bytes:
    image = image.copy()
    image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
    while True:
        for quality in (88, 75, 60, 45):
            out = BytesIO()
            image.save(out, fmt, quality=quality, **({"optimize": True} if fmt == "JPEG" else {}))
            if len(out.getvalue()) <= limit:
                return out.getvalue()
        if min(image.size) < 200:
            break
        image = image.resize((max(1, int(image.width * .8)), max(1, int(image.height * .8))), Image.Resampling.LANCZOS)
    raise ValueError("Cannot make a readable variant within the portal size limit")


def variants_for(image: Image.Image) -> dict[str, bytes]:
    return {"jpg": bounded_image(image, "JPEG", 200_000),
            "pdf": bounded_image(image, "PDF", 300_000)}


def local_words(image: Image.Image) -> list[dict]:
    """Use installed local OCR; fail closed rather than sending a raw scan to AI."""
    with tempfile.TemporaryDirectory(prefix="adhikaar-ocr-") as folder:
        path = Path(folder) / "scan.png"
        image.save(path)
        if os.name == "nt":
            script = Path(__file__).with_name("locker_ocr.ps1").read_text(encoding="utf-8")
            # Invoke our own command block without changing machine execution policy.
            command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                       "& {\n" + script + "\n} -ImagePath $env:ADHIKAAR_OCR_IMAGE"]
            result = subprocess.run(command, capture_output=True, timeout=40, check=False,
                                    env={**os.environ, "ADHIKAAR_OCR_IMAGE": str(path)})
            if result.returncode:
                raise RuntimeError("Local Windows OCR is unavailable; document was not sent to AI")
            words = json.loads(result.stdout.decode("utf-8-sig"))
            return words if isinstance(words, list) else [words] if words else []
        if not shutil.which("tesseract"):
            raise RuntimeError("Local OCR is unavailable; configure Tesseract before classifying documents")
        result = subprocess.run(["tesseract", str(path), "stdout", "tsv"],
                                capture_output=True, timeout=40, check=True)
        return [{"text": row["text"], "x": int(row["left"]), "y": int(row["top"]),
                 "width": int(row["width"]), "height": int(row["height"])}
                for row in csv.DictReader(StringIO(result.stdout.decode()), delimiter="\t") if row["text"].strip()]


SAFE_HEADINGS = frozenset("aadhaar aadhar uidai income certificate caste domicile residence marksheet marks memorandum statement examination board university school revenue land record rights passbook bank photograph photo प्रमाण आय जाति निवास आधार अंक प्रमाणपत्र भूमि खतौनी खसरा".split())


def classification_preview(image: Image.Image) -> tuple[bytes, dict]:
    small = image.copy()
    small.thumbnail((1800, 1800))
    words = local_words(small)
    # Reconstruct, rather than blacking out OCR matches: missed OCR cannot leak PII.
    preview = Image.new("RGB", small.size, "white")
    draw = ImageDraw.Draw(preview)
    headings = []
    for word in words:
        text = re.sub(r"[^\w]", "", word["text"]).lower()
        x, y, w, h = (int(word[k]) for k in ("x", "y", "width", "height"))
        if text in SAFE_HEADINGS:
            headings.append(text)
            # Only permitted tokens, never arbitrary OCR or filenames.
            draw.text((x, y), text, fill="black")
        else:
            draw.rectangle((x, y, x + w, y + h), fill="#dedede")
    gray = small.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    sharpness = ImageStat.Stat(edges).var[0]
    facts = {"page_count": 1, "width": image.width, "height": image.height,
             "detected_headings": sorted(set(headings)), "local_sharpness": round(sharpness, 2),
             "local_ocr_word_count": len(words)}
    out = BytesIO()
    preview.save(out, "JPEG", quality=85)
    return out.getvalue(), facts


async def prepare(data: bytes, doc_type: str | None = None) -> tuple[DocumentCheck, dict, dict[str, bytes]]:
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError("Document must be nonempty and at most 15 MB")
    image = await asyncio.to_thread(image_from_upload, data)
    preview, facts = await asyncio.to_thread(classification_preview, image)
    check = await llm.generate_json([
        "Classify this privacy-filtered document layout from the permitted headings. "
        "Gray blocks replace private text; they do not mean the original is unreadable. "
        "Assess readability conservatively from the local OCR and sharpness evidence. "
        "Flag blurry, cut_off or glare only with evidence; flag unreadable when OCR failed. "
        "Return other when type cannot be determined. Do not extract personal data. "
        + json.dumps(facts), types.Part.from_bytes(data=preview, mime_type="image/jpeg")],
        DocumentCheck, model="lite", temperature=0)
    copies = await asyncio.to_thread(variants_for, image)
    return check, facts, copies


async def store(db, profile_id: str, data: bytes, mime: str, doc_type: str | None = None) -> LockerItem:
    check, facts, copies = await prepare(data, doc_type)
    item_id = uuid.uuid4().hex
    folder = private_root() / item_id
    await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=False)
    try:
        original = folder / "original.enc"
        await asyncio.to_thread(encrypt_file, original, data)
        variants = []
        for fmt, content in copies.items():
            path = folder / (fmt + ".enc")
            await asyncio.to_thread(encrypt_file, path, content)
            variants.append({"format": fmt, "bytes": len(content), "path": str(path)})
        actual_type = doc_type or check.doc_type
        if data.startswith(b"%PDF-"):
            mime = "application/pdf"
        else:
            with Image.open(BytesIO(data)) as original_image:
                mime = Image.MIME.get(original_image.format, "application/octet-stream")
        item = LockerItem(id=item_id, profile_id=profile_id, doc_type=actual_type,
            title=actual_type.replace("_", " ").title(), file_path=str(original), mime=mime,
            variants=variants, meta={"readable": check.readable, "issues": check.issues,
                "detected_doc_type": check.doc_type, "facts": facts})
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item
    except BaseException:
        if folder.resolve().is_relative_to(private_root().resolve()):
            await asyncio.to_thread(shutil.rmtree, folder)
        raise


def public_variants(item: LockerItem) -> list[dict]:
    return [{k: v for k, v in variant.items() if k != "path"} for variant in item.variants]


def choose_variant(item: LockerItem, accept: str = "", hint: str = "") -> dict:
    accepts = [part.strip().lower() for part in accept.split(",") if part.strip()]
    formats = set()
    for part in accepts:
        if part in {".jpg", ".jpeg", "image/jpeg", "image/jpg", "image/*", "*/*"}:
            formats.add("jpg")
        if part in {".pdf", "application/pdf", "application/*", "*/*"}:
            formats.add("pdf")
    if not accepts:
        formats = {"jpg", "pdf"}
    limits = [int(float(n) * (1_000_000 if unit.lower().startswith("m") else 1_000))
              for n, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(KB|MB|kbytes|mbytes)\b", hint, re.I)]
    limit = min(limits) if limits else None
    minimum = 0
    size_range = re.search(r"(\d+(?:\.\d+)?)\s*(KB|MB)\s*(?:to|and|[-–])\s*(\d+(?:\.\d+)?)\s*(KB|MB)", hint, re.I)
    if size_range:
        low, low_unit, high, high_unit = size_range.groups()
        minimum = int(float(low) * (1_000_000 if low_unit.lower() == "mb" else 1_000))
        limit = int(float(high) * (1_000_000 if high_unit.lower() == "mb" else 1_000))
    choices = [v for v in item.variants if v["format"] in formats and minimum <= v["bytes"] and (limit is None or v["bytes"] <= limit)]
    if not choices:
        raise ValueError("No locker variant fits this portal's accepted format and size limit")
    return min(choices, key=lambda v: v["bytes"])
