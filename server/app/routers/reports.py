"""Civic reports. Media URLs are served by the existing /files storage mount."""
import asyncio
import json
import logging
import math
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, HttpUrl, ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from ..agents import civic
from ..agents.browser import allowed
from ..agents.executor import RunSession, manager
from ..config import get_settings
from ..db import get_db
from ..models import AgentRun, Profile, Report, ReportEvent, ReportVote
from ..schemas import (CivicRunOut, CivicTriage, ComplaintDraft, ReportActorIn, ReportCategory,
                       ReportEventOut, ReportOut, ReportStatus, ReportVoteIn, TriageOut)
from ..services import crypto, geo, llm, sarvam

router = APIRouter(prefix="/reports", tags=["civic"])
log = logging.getLogger(__name__)
MAX_MEDIA = 20 * 1024 * 1024


class Submission(BaseModel):
    profile_id: str = Field(min_length=1)
    text: str = Field(default="", max_length=10000)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False)
    source_url: HttpUrl | None = None


async def get_profile(db, profile_id):
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "profile not found")
    return profile


async def get_report(db, report_id, lock=False):
    q = select(Report).where(Report.id == report_id)
    if lock:
        q = q.with_for_update()
    report = await db.scalar(q)
    if not report:
        raise HTTPException(404, "report not found")
    return report


def report_out(report, events=(), **extra):
    ai = report.ai or {}
    return ReportOut(
        id=report.id, profile_id=report.profile_id, category=report.category, title=report.title,
        title_local=ai.get("title_local") or report.title, description=report.description,
        severity=report.severity, severity_reason=ai.get("severity_reason") or "Reason not recorded",
        department=report.department, language=report.language, lat=report.lat, lng=report.lng,
        address=report.address, media=report.media or [], status=report.status, official_ref=report.official_ref,
        official_status=report.official_status, supporters=report.supporters,
        created_at=report.created_at, updated_at=report.updated_at,
        since_when=ai.get("since_when", "Not specified by the reporter"),
        people_affected=ai.get("people_affected", "Not specified by the reporter"),
        source_url=ai.get("source_url"), complaint_draft=ai.get("complaint_draft"),
        events=[ReportEventOut.model_validate(event) for event in events], **extra)


async def upload_bytes(upload, kind):
    if upload is None:
        return None
    if not isinstance(upload, UploadFile):
        raise HTTPException(422, f"{kind} must be a file")
    data = await upload.read(MAX_MEDIA + 1)
    if not data or len(data) > MAX_MEDIA:
        raise HTTPException(422, "Media must be nonempty and at most 20 MB")
    mime = (upload.content_type or "").split(";")[0].lower()
    if kind == "photo":
        signatures = {"image/jpeg": ("jpg", data.startswith(b"\xff\xd8\xff")),
                      "image/png": ("png", data.startswith(b"\x89PNG\r\n\x1a\n")),
                      "image/webp": ("webp", data[:4] == b"RIFF" and data[8:12] == b"WEBP")}
        if mime not in signatures or not signatures[mime][1]:
            raise HTTPException(422, "Photo must be a JPEG, PNG or WebP image")
        suffix = signatures[mime][0]
    else:
        formats = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav",
                   "audio/x-wav": "wav", "audio/mpeg": "mp3", "audio/mp4": "m4a",
                   "audio/flac": "flac", "audio/aac": "aac", "audio/opus": "opus"}
        if mime not in formats:
            raise HTTPException(422, "Unsupported audio type")
        suffix = formats[mime]
    return {"data": data, "mime": mime, "suffix": suffix, "type": kind}


async def submission(request: Request, db, require_evidence=True):
    try:
        if request.headers.get("content-type", "").split(";")[0] == "application/json":
            fields = await request.json()
        else:
            fields = dict(await request.form(max_part_size=MAX_MEDIA))
        body = Submission.model_validate(fields)
        accepted = fields.get("triage")
        if isinstance(accepted, str):
            accepted = json.loads(accepted)
        if accepted is None and fields.get("category"):
            accepted = {key: fields[key] for key in CivicTriage.model_fields if key in fields}
    except (ValidationError, ValueError, TypeError) as error:
        raise HTTPException(422, "Invalid civic submission: " + str(error)) from error
    profile = await get_profile(db, body.profile_id)
    photo = await upload_bytes(fields.get("photo"), "photo")
    audio = await upload_bytes(fields.get("audio"), "audio")
    if require_evidence and not (body.text.strip() or photo or audio):
        raise HTTPException(422, "Provide text, a photo or audio")
    personal = crypto.decrypt_json(profile.sensitive)
    text = civic.redact(body.text, personal)
    language = profile.language
    if audio:
        if not get_settings().sarvam_api_key:
            raise HTTPException(503, "Audio triage requires SARVAM_API_KEY")
        try:
            transcript = await sarvam.stt(audio["data"], audio["mime"], None)
        except (ValueError, RuntimeError, httpx.HTTPError) as error:
            raise HTTPException(502, "Audio transcription unavailable") from error
        text += "\n" + civic.redact(transcript.text, personal)
        language = transcript.language
    return body, profile, personal, text, language, photo, audio, accepted


async def classify(body, text, language, photo, personal, accepted=None):
    try:
        address = await geo.reverse_geocode(body.lat, body.lng)
    except (httpx.HTTPError, ValueError):
        log.warning("Nominatim unavailable; preserving coordinates without inventing an address")
        address = None
    try:
        if accepted is not None:
            triage = civic.parse_triage(accepted)
        else:
            triage = await civic.triage(text, language, civic.redact(address or "", personal),
                                       photo["data"] if photo else None, photo["mime"] if photo else None)
        triage = civic.redact_triage(triage, personal)
        vector = (await llm.embed([triage.title + "\n" + triage.description]))[0]
    except (ValueError, TypeError, AttributeError) as error:
        if accepted is not None:
            raise HTTPException(422, "Invalid accepted triage") from error
        raise HTTPException(502, "Civic triage returned an invalid response") from error
    except Exception as error:
        log.warning("Civic model service unavailable: %s", type(error).__name__)
        raise HTTPException(502, "Civic AI service unavailable; please retry") from error
    return triage, address, vector


async def save_media(media):
    result = []
    for item in media:
        if not item:
            continue
        relative = f"reports/{uuid4().hex}.{item['suffix']}"
        target = Path(get_settings().storage_dir) / relative
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, item["data"])
        result.append({"type": item["type"], "path": relative, "url": "/files/" + relative,
                       "mime": item["mime"], "bytes": len(item["data"])})
    return result


@router.post("/triage", response_model=TriageOut)
async def triage_report(request: Request, db: AsyncSession = Depends(get_db)):
    body, _, personal, text, lang, photo, _, _ = await submission(request, db)
    result, address, vector = await classify(body, text, lang, photo, personal)
    matches = await civic.duplicates(db, result.category, body.lat, body.lng, vector)
    return TriageOut(**result.model_dump(), language=lang, address=address,
        duplicates=[report_out(r, distance_m=round(d, 2), similarity=s, duplicate_score=score)
                    for r, d, s, score in matches])


@router.post("", response_model=ReportOut, status_code=201)
async def create_report(request: Request, db: AsyncSession = Depends(get_db)):
    body, _, personal, text, lang, photo, audio, accepted = await submission(request, db)
    result, address, vector = await classify(body, text, lang, photo, personal, accepted)
    ai = result.model_dump()
    if body.source_url:
        ai["source_url"] = str(body.source_url)
    media = await save_media([photo, audio])
    report = Report(profile_id=body.profile_id, category=result.category, title=result.title,
                    description=result.description, language=lang, severity=result.severity,
                    department=result.department, lat=body.lat, lng=body.lng, address=address,
                    media=media, ai=ai, embedding=vector, supporters=1)
    db.add(report)
    await db.flush()
    # The reporter's initial support is a real vote, so repeat support cannot add another.
    db.add(ReportVote(report_id=report.id, profile_id=body.profile_id, kind="support"))
    db.add(ReportEvent(report_id=report.id, source="citizen", kind="created",
                       text="Citizen reported this issue", meta={"profile_id": body.profile_id,
                       "source_url": ai.get("source_url")}))
    await db.commit()
    await db.refresh(report)
    return report_out(report)


@router.get("/stats")
async def report_stats(db: AsyncSession = Depends(get_db)):
    async def grouped(column):
        rows = (await db.execute(select(column, func.count()).group_by(column))).all()
        return {key: count for key, count in rows}
    by_status, by_department, by_category = await grouped(Report.status), await grouped(Report.department), await grouped(Report.category)
    return {"total": sum(by_status.values()), "by_status": by_status, "by_department": by_department,
            "by_category": by_category,
            "confirmed_by_others": await db.scalar(select(func.count()).select_from(Report).where(Report.supporters > 1)),
            "official_number": await db.scalar(select(func.count()).select_from(Report).where(Report.official_ref.is_not(None))),
            "resolved_confirmed": await db.scalar(select(func.count()).select_from(Report).where(
                Report.status.in_(["resolved", "closed"]), Report.id.in_(select(ReportVote.report_id).where(ReportVote.kind == "fixed")))),
            "open_by_department": dict((await db.execute(select(Report.department, func.count()).where(
                Report.status.in_(["open", "filed", "in_progress"])).group_by(Report.department))).all())}


@router.get("", response_model=list[ReportOut])
async def list_reports(lat: float | None = Query(None, ge=-90, le=90),
                       lng: float | None = Query(None, ge=-180, le=180),
                       radius_km: float | None = Query(None, gt=0, le=100), bbox: str | None = None,
                       category: ReportCategory | None = None, status: ReportStatus | None = None,
                       profile_id: str | None = None, limit: int = Query(100, ge=1, le=500),
                       db: AsyncSession = Depends(get_db)):
    if any(value is not None and not math.isfinite(value) for value in (lat, lng, radius_km)):
        raise HTTPException(422, "Coordinates and radius must be finite")
    radial = lat is not None or lng is not None or radius_km is not None
    if radial and (lat is None or lng is None):
        raise HTTPException(422, "Radius search requires both lat and lng")
    if radial and bbox:
        raise HTTPException(422, "Choose radius or bbox")
    q = select(Report)
    if category:
        q = q.where(Report.category == category)
    if status:
        q = q.where(Report.status == status)
    if profile_id:
        q = q.where(Report.profile_id == profile_id)
    if bbox:
        try:
            west, south, east, north = map(float, bbox.split(","))
            if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "bbox must be west,south,east,north")
        q = q.where(Report.lat.between(south, north), Report.lng.between(west, east))
    if radial:
        radius = (radius_km or 5) * 1000
        south, north, west, east = geo.bounds(lat, lng, radius)
        q = q.where(Report.lat.between(south, north))
        if west >= -180 and east <= 180:
            q = q.where(Report.lng.between(west, east))
        # Filter exact circles before applying a limit: bounding-box corners must not crowd out real matches.
        rows = (await db.scalars(q)).all()
        nearby = sorted(((r, geo.distance_m(lat, lng, r.lat, r.lng)) for r in rows), key=lambda row: row[1])
        return [report_out(r, distance_m=round(d, 2)) for r, d in nearby if d <= radius][:limit]
    return [report_out(r) for r in (await db.scalars(q.order_by(Report.created_at.desc()).limit(limit))).all()]


@router.get("/{report_id}", response_model=ReportOut)
async def detail_report(report_id: str, db: AsyncSession = Depends(get_db)):
    report = await get_report(db, report_id)
    events = (await db.scalars(select(ReportEvent).where(ReportEvent.report_id == report_id)
                              .order_by(ReportEvent.created_at, ReportEvent.id))).all()
    return report_out(report, events)


@router.post("/{report_id}/vote", response_model=ReportOut)
async def vote(report_id: str, body: ReportVoteIn, db: AsyncSession = Depends(get_db)):
    await get_profile(db, body.profile_id)
    report = await get_report(db, report_id, lock=True)
    inserted = await db.scalar(insert(ReportVote).values(report_id=report_id, profile_id=body.profile_id, kind=body.kind)
        .on_conflict_do_nothing(index_elements=["report_id", "profile_id", "kind"]).returning(ReportVote.id))
    if inserted:
        if body.kind == "support":
            report.supporters += 1
        kinds = {"support": "support", "still_broken": "still_broken", "fixed": "fixed_claim", "follow": "follow"}
        texts = {"support": "A citizen supports this report", "still_broken": "A citizen says this issue is still broken (unverified)",
                 "fixed": "A citizen says this issue is fixed (unverified)", "follow": "A citizen followed this report"}
        db.add(ReportEvent(report_id=report_id, source="citizen", kind=kinds[body.kind], text=texts[body.kind],
                           meta={"profile_id": body.profile_id}))
    await db.commit()
    await db.refresh(report)
    return report_out(report)


@router.post("/{report_id}/evidence", response_model=ReportOut)
async def evidence(report_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    fields = dict(await request.form(max_part_size=MAX_MEDIA))
    profile_id = fields.get("profile_id")
    if not isinstance(profile_id, str):
        raise HTTPException(422, "profile_id is required")
    await get_profile(db, profile_id)
    photo = await upload_bytes(fields.get("photo") or fields.get("file"), "photo")
    audio = await upload_bytes(fields.get("audio"), "audio")
    text = fields.get("text", "")
    if not isinstance(text, str) or len(text) > 10000 or not (photo or audio or text.strip()):
        raise HTTPException(422, "Provide evidence text, a photo or audio")
    report = await get_report(db, report_id, lock=True)
    media = await save_media([photo, audio])
    report.media = [*(report.media or []), *media]
    db.add(ReportEvent(report_id=report_id, source="citizen", kind="evidence", text=text or "Citizen added evidence",
                       meta={"profile_id": profile_id, "media": media}))
    await db.commit()
    await db.refresh(report)
    return report_out(report)


async def start_civic_run(report_id, body, db, kind):
    profile = await get_profile(db, body.profile_id)
    report = await get_report(db, report_id, lock=True)
    if report.profile_id != body.profile_id:
        raise HTTPException(403, "Only the reporter can operate the official grievance")
    if kind == "complaint" and report.official_ref:
        raise HTTPException(409, "This report already has an official registration number")
    if kind == "status_check" and not report.official_ref:
        raise HTTPException(409, "File this report first to obtain a registration number")
    active = await db.scalar(select(AgentRun).where(AgentRun.kind.in_(["complaint", "status_check"]),
        AgentRun.meta["report_id"].as_string() == report.id,
        AgentRun.status.in_(["queued", "running", "needs_human", "awaiting_approval"])).limit(1))
    if active:
        return CivicRunOut(run_id=active.id, draft=(report.ai or {}).get("complaint_draft"))
    personal = crypto.decrypt_json(profile.sensitive)
    draft = None
    portal = "https://pgportal.gov.in/Status"
    facts = {}
    if kind == "complaint":
        try:
            cached_draft = (report.ai or {}).get("complaint_draft")
            draft = ComplaintDraft.model_validate(cached_draft) if cached_draft else await civic.draft_complaint(report, personal)
        except Exception as error:
            raise HTTPException(502, "Complaint drafting unavailable; please retry") from error
        report.ai = {**(report.ai or {}), "complaint_draft": draft.model_dump()}
        goal = civic.complaint_goal(report, draft)
        portal = "https://pgportal.gov.in/"
        facts = {"complaint_subject": draft.subject, "complaint_text": draft.english,
                 "issue_location": report.address or f"{report.lat}, {report.lng}",
                 "department": report.department,
                 "issue_photo": next((m["url"] for m in report.media or [] if m.get("type") == "photo"), "")}
    else:
        goal = civic.status_goal()
        facts = {"registration_number": report.official_ref}
    run = AgentRun(profile_id=profile.id, portal_url=portal, goal=goal, kind=kind,
                   meta={"report_id": report.id, "official_ref": report.official_ref})
    db.add(run)
    await db.commit()
    # Report location and complaint are public issue data; profile PII stays local.
    rs = RunSession(run.id, run.goal, portal, {**(profile.data or {}), **facts}, personal)
    manager.start(rs)
    civic.watch_run(rs)
    return CivicRunOut(run_id=run.id, draft=draft)


@router.post("/{report_id}/file", response_model=CivicRunOut)
async def file_report(report_id: str, body: ReportActorIn, db: AsyncSession = Depends(get_db)):
    return await start_civic_run(report_id, body, db, "complaint")


@router.post("/{report_id}/check-status", response_model=CivicRunOut)
async def check_status(report_id: str, body: ReportActorIn, db: AsyncSession = Depends(get_db)):
    return await start_civic_run(report_id, body, db, "status_check")


@router.post("/{report_id}/draft")
async def preview_draft(report_id: str, body: ReportActorIn, db: AsyncSession = Depends(get_db)):
    profile = await get_profile(db, body.profile_id)
    report = await get_report(db, report_id, lock=True)
    if report.profile_id != profile.id:
        raise HTTPException(403, "Only the reporter can draft this grievance")
    try:
        draft = await civic.draft_complaint(report, crypto.decrypt_json(profile.sensitive))
    except Exception as error:
        raise HTTPException(502, "Complaint drafting unavailable; please retry") from error
    report.ai = {**(report.ai or {}), "complaint_draft": draft.model_dump()}
    await db.commit()
    return draft


class AttachmentIn(ReportActorIn):
    run_id: str
    media_index: int = Field(default=0, ge=0)
    approved: bool = False


@router.post("/{report_id}/attach")
async def attach_photo(report_id: str, body: AttachmentIn, db: AsyncSession = Depends(get_db)):
    """Citizen-approved bridge for the current executor, which has no upload action.

    UI shows report.media[media_index] then posts approved=true. Only an agent
    paused specifically for the photo can receive it; this never submits a form.
    """
    report = await get_report(db, report_id)
    run = await db.get(AgentRun, body.run_id)
    if report.profile_id != body.profile_id or not run or run.profile_id != body.profile_id:
        raise HTTPException(403, "Only the reporter can approve this attachment")
    if run.kind != "complaint" or (run.meta or {}).get("report_id") != report_id:
        raise HTTPException(409, "Run does not belong to this complaint")
    if not body.approved:
        raise HTTPException(409, "Review the photo and explicitly approve its upload")
    rs = manager.get(run.id)
    if not rs or not rs.pending or rs.pending.get("field") != "issue_photo" or rs.status != "needs_human":
        raise HTTPException(409, "Agent must be paused for issue_photo upload")
    if body.media_index >= len(report.media or []) or report.media[body.media_index].get("type") != "photo":
        raise HTTPException(422, "Select a report photo")
    media = report.media[body.media_index]
    root = Path(get_settings().storage_dir).resolve()
    target = (root / media["path"]).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(404, "Stored photo not found")
    page = rs.browser.page
    if not page or not allowed(page.url):
        raise HTTPException(409, "Portal is not ready for an attachment")
    inputs = page.locator('input[type="file"]')
    if await inputs.count() != 1:
        raise HTTPException(409, "Portal must show exactly one attachment input")
    field = inputs.first
    accept = (await field.get_attribute("accept") or "").lower()
    accepted_types = {token.strip() for token in accept.split(",")}
    photo_types = {"image/*", media["mime"], target.suffix.lower()}
    if media["mime"] == "image/jpeg":
        photo_types.update({".jpg", ".jpeg"})
    if accept and not accepted_types.intersection(photo_types):
        raise HTTPException(422, "Portal does not accept this photo format")
    try:
        await field.set_input_files(str(target))
    except Exception as error:
        raise HTTPException(502, "The portal rejected the attachment; check its file-size requirements") from error
    db.add(ReportEvent(report_id=report_id, source="system", kind="attachment",
                       text="Citizen approved sending the report photo to the portal",
                       meta={"run_id": run.id, "media": media}))
    await db.commit()
    await rs.inbox.put({"type": "resume"})
    return {"uploaded": True, "run_id": run.id, "media": media}
