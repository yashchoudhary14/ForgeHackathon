import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .config import get_settings
from .db import Base

DIM = get_settings().embed_dim


def _id() -> str:
    return uuid.uuid4().hex


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    # non-sensitive fields used for matching (age, state, category, income band...)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    # name, phone, aadhaar-last4 etc. - fernet encrypted json
    sensitive: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="en")
    mode: Mapped[str] = mapped_column(String(10), default="manual")  # talk | manual
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Scheme(Base):
    """cache of schemes pulled live from myscheme.gov.in"""

    __tablename__ = "schemes"

    slug: Mapped[str] = mapped_column(String(200), primary_key=True)
    lang: Mapped[str] = mapped_column(String(8), primary_key=True, default="en")
    scheme_id: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON)
    embedding = mapped_column(Vector(DIM), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    title: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(20))  # upload | url | pib | scheme
    source_url: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(DIM))


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    profile_id: Mapped[str | None] = mapped_column(ForeignKey("profiles.id"))
    scheme_slug: Mapped[str | None] = mapped_column(String(200))
    portal_url: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # queued | running | needs_human | awaiting_approval | done | failed | aborted
    kind: Mapped[str] = mapped_column(String(20), default="application")  # application | complaint | status_check
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. {"report_id": ...}
    receipt: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    thought: Mapped[str | None] = mapped_column(Text)
    action: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))  # ok | retry | failed | human
    url: Mapped[str | None] = mapped_column(Text)
    screenshot: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LLMCache(Base):
    __tablename__ = "llm_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class LockerItem(Base):
    """a citizen's saved document; files are encrypted on disk, variants are portal-ready copies"""

    __tablename__ = "locker_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    # aadhaar | income_certificate | caste_certificate | domicile | marksheet | photo | land_record | bank_passbook | other
    doc_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(String(60))
    # portal-ready copies: [{"format": "jpg", "bytes": 180000, "width": 1200, "height": 1600, "path": "..."}]
    variants: Mapped[list] = mapped_column(JSON, default=list)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # AI checks: readable, issues, non-sensitive facts
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Report(Base):
    """a civic issue reported by a citizen"""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    profile_id: Mapped[str | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"), index=True)
    category: Mapped[str] = mapped_column(String(40))  # water | roads | electricity | sanitation | streetlight | drainage | other
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="en")
    severity: Mapped[str] = mapped_column(String(10))  # low | medium | high | urgent
    department: Mapped[str] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(Text)
    media: Mapped[list] = mapped_column(JSON, default=list)  # [{"type": "photo" | "audio" | "video", "path": "..."}]
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | filed | in_progress | resolved | closed
    official_ref: Mapped[str | None] = mapped_column(String(64))  # CPGRAMS registration number
    official_status: Mapped[str | None] = mapped_column(Text)
    supporters: Mapped[int] = mapped_column(Integer, default=1)
    ai: Mapped[dict] = mapped_column(JSON, default=dict)  # raw triage output with reasons
    embedding = mapped_column(Vector(DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ReportVote(Base):
    __tablename__ = "report_votes"
    __table_args__ = (UniqueConstraint("report_id", "profile_id", "kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))  # support | still_broken | fixed | follow
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportEvent(Base):
    """one entry on a report's timeline; source keeps official portal data apart from citizens"""

    __tablename__ = "report_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(20))  # official | citizen | system
    kind: Mapped[str] = mapped_column(String(30))  # created | support | evidence | filed | status | fixed_claim | resolved
    text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # new_scheme | pib | run_status | report_update | deadline
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(Text)  # client route, e.g. /schemes/pmsfss or /reports/<id>
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
