import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import LockerItem, Profile
from ..schemas import LockerOut
from ..services import locker

router = APIRouter(prefix="/locker", tags=["locker"])


def output(item: LockerItem) -> LockerOut:
    return LockerOut(id=item.id, doc_type=item.doc_type, title=item.title,
                     variants=locker.public_variants(item), meta=item.meta, created_at=item.created_at)


async def owner_id(profile_id: str | None = Query(None),
                   x_profile_id: str | None = Header(None)) -> str:
    # This app uses the unguessable profile ID as its owner capability, like /profile.
    owner = x_profile_id or profile_id
    if not owner:
        raise HTTPException(401, "Owner profile_id or X-Profile-ID is required")
    return owner


async def owned_item(db: AsyncSession, item_id: str, profile_id: str) -> LockerItem:
    item = await db.get(LockerItem, item_id)
    if not item or item.profile_id != profile_id:
        raise HTTPException(404, "document not found")
    return item


@router.post("", response_model=LockerOut)
async def upload(profile_id: str = Form(...), file: UploadFile = File(...),
                 doc_type: locker.DocType | None = Form(None), db: AsyncSession = Depends(get_db)):
    if not await db.get(Profile, profile_id):
        raise HTTPException(404, "profile not found")
    data = await file.read(locker.MAX_UPLOAD + 1)
    if len(data) > locker.MAX_UPLOAD:
        raise HTTPException(413, "Document exceeds 15 MB")
    try:
        item = await locker.store(db, profile_id, data, file.content_type or "application/octet-stream", doc_type)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return output(item)


@router.get("", response_model=list[LockerOut])
async def list_items(profile_id: str, db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(LockerItem).where(LockerItem.profile_id == profile_id)
                             .order_by(LockerItem.created_at.desc()))).scalars()
    return [output(item) for item in items]


@router.get("/{item_id}/file")
async def get_file(item_id: str, variant: Literal["jpg", "pdf", "original"] = "original",
                   profile_id: str = Depends(owner_id), db: AsyncSession = Depends(get_db)):
    item = await owned_item(db, item_id, profile_id)
    if variant == "original":
        path, mime, suffix = item.file_path, item.mime, ".bin"
    else:
        copy = next((v for v in item.variants if v["format"] == variant), None)
        if not copy:
            raise HTTPException(404, "variant not found")
        path, mime, suffix = copy["path"], {"jpg": "image/jpeg", "pdf": "application/pdf"}[variant], "." + variant
    content = await asyncio.to_thread(locker.decrypt_file, path)
    return Response(content, media_type=mime, headers={
        "Content-Disposition": f'attachment; filename="document{suffix}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: str, profile_id: str = Depends(owner_id), db: AsyncSession = Depends(get_db)):
    item = await owned_item(db, item_id, profile_id)
    paths = [item.file_path, *(v["path"] for v in item.variants)]
    for path in paths:
        await asyncio.to_thread(locker.remove_file, path)
    await db.delete(item)
    await db.commit()
