from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["en", "hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa", "od"]


# ---------- profile ----------

class ProfileData(BaseModel):
    age: int | None = None
    gender: Literal["male", "female", "transgender"] | None = None
    state: str | None = None
    district: str | None = None
    residence: Literal["urban", "rural"] | None = None
    caste: Literal["general", "obc", "sc", "st", "pvtg", "dnt"] | None = None
    annual_income: int | None = None  # INR
    occupation: str | None = None
    is_student: bool | None = None
    is_pregnant: bool | None = None
    education_level: str | None = None  # "class 10", "ug", "pg", ...
    course: str | None = None  # preserve the degree, e.g. B.Sc rather than only "ug"
    study_year: int | None = None
    disability_percent: int | None = None
    marital_status: str | None = None
    is_bpl: bool | None = None
    is_pregnant: bool | None = None
    land_acres: float | None = None
    is_minority: bool | None = None
    religion: str | None = None
    course: str | None = None
    study_year: int | None = None
    institution_type: str | None = None
    parent_occupation: str | None = None
    is_single_child: bool | None = None
    is_hosteller: bool | None = None
    institution_name: str | None = None
    institution_state: str | None = None
    institution_district: str | None = None
    study_mode: str | None = None
    previous_class_percentage: float | None = Field(default=None, ge=0, le=100)
    previous_board: str | None = None
    previous_passing_year: int | None = None


class SensitiveData(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    dob: str | None = None
    address: str | None = None
    father_name: str | None = None
    bank_ifsc: str | None = None


class ProfileIn(BaseModel):
    data: ProfileData = ProfileData()
    sensitive: SensitiveData = SensitiveData()
    language: Lang = "en"


class ProfileOut(ProfileIn):
    id: str


class ProfileExtractIn(BaseModel):
    text: str
    language: Lang = "en"
    profile_id: str | None = None  # merge into existing profile


class ProfileExtractOut(BaseModel):
    profile: ProfileOut
    missing_fields: list[str]
    follow_up_question: str | None = None  # in the user's language


# ---------- schemes ----------

class Citation(BaseModel):
    source_url: str
    title: str | None = None
    quote: str  # exact text span from the source
    section: str | None = None  # "eligibility", "benefits", page number...


class ApplicationMode(BaseModel):
    mode: str  # "Online", "Offline", "Online - via CSC"
    steps_md: str
    url: str | None = None


class SchemeSummary(BaseModel):
    slug: str
    name: str
    ministry: str | None = None
    state: str | None = None
    tags: list[str] = []
    brief: str | None = None


class SchemeDetail(SchemeSummary):
    id: str
    details_md: str = ""
    benefits_md: str = ""
    eligibility_md: str = ""
    exclusions_md: str = ""
    application: list[ApplicationMode] = []
    documents_md: str = ""
    faqs: list[dict] = []
    references: list[dict] = []
    source_url: str


class SearchOut(BaseModel):
    total: int
    items: list[SchemeSummary]


class MatchIn(BaseModel):
    profile_id: str
    keyword: str | None = None
    limit: int = Field(default=8, le=20)


class Reason(BaseModel):
    claim: str
    met: bool | None  # None = unknown, need more info
    citation: Citation | None = None


class MatchResult(BaseModel):
    scheme: SchemeSummary
    verdict: Literal["eligible", "likely", "not_eligible", "unknown"]
    confidence: float
    reasons: list[Reason]
    missing_info: list[str] = []
    documents_needed: list[str] = []


# ---------- explain / documents ----------

class ExplainSource(BaseModel):
    type: Literal["scheme", "document", "url"]
    slug: str | None = None
    document_id: str | None = None
    url: str | None = None


class ExplainIn(BaseModel):
    source: ExplainSource
    profile_id: str | None = None
    language: Lang = "en"
    with_audio: bool = True


class ExplainOut(BaseModel):
    title: str
    summary: str
    key_points: list[str]
    your_rights: list[str]
    what_it_means_for_you: str | None = None
    deadlines: list[str] = []
    documents_needed: list[str] = []
    citations: list[Citation]
    language: Lang
    audio_url: str | None = None


class DocumentOut(BaseModel):
    id: str
    title: str
    source_type: str
    source_url: str | None = None
    pages: int
    chunks: int


class FeedItem(BaseModel):
    title: str
    url: str
    published: str | None = None
    ministry: str | None = None
    source: str  # "PIB", "eGazette"


# ---------- chat ----------

class ChatIn(BaseModel):
    session_id: str
    message: str
    language: Lang = "en"
    profile_id: str | None = None
    document_ids: list[str] = []


# SSE events from POST /api/chat:
#   {"type":"token","text":"..."}
#   {"type":"tool_call","name":"search_schemes","args":{...}}
#   {"type":"tool_result","name":"search_schemes","summary":"..."}
#   {"type":"citation","citation":{Citation}}
#   {"type":"done","message_id":1}
#   {"type":"error","message":"..."}


# ---------- voice ----------

class SttOut(BaseModel):
    text: str
    language: Lang


class TtsIn(BaseModel):
    text: str
    language: Lang = "hi"


# ---------- execution agent ----------

class RunIn(BaseModel):
    profile_id: str
    portal_url: str
    goal: str
    scheme_slug: str | None = None


class RunStepOut(BaseModel):
    idx: int
    thought: str | None
    action: dict | None
    status: str
    url: str | None
    screenshot: str | None


class RunOut(BaseModel):
    id: str
    profile_id: str | None
    scheme_slug: str | None
    portal_url: str
    goal: str
    status: str
    receipt: dict | None = None
    error: str | None = None
    steps: list[RunStepOut] = []


# WebSocket /api/agent/runs/{id}/ws
# server -> client:
#   {"type":"frame","jpeg":"<base64>"}
#   {"type":"step","step":{RunStepOut}}
#   {"type":"status","status":"running"}
#   {"type":"needs_human","kind":"captcha|otp|missing_field|confirm_submit|login","message":"...","field":"..."}
#   {"type":"done","receipt":{"reference_no":"...","screenshot":"...","url":"...","summary":"..."}}
#   {"type":"error","message":"..."}
# client -> server:
#   {"type":"human_input","value":"..."}          answer for missing_field / otp
#   {"type":"click","x":0.5,"y":0.3}              takeover click, coords as fraction of viewport
#   {"type":"type","text":"..."} / {"type":"key","key":"Enter"}
#   {"type":"resume"}                             after user solved captcha / logged in
#   {"type":"approve"} / {"type":"abort"}         final submit gate


# ---------- civic ----------

ReportCategory = Literal["water", "roads", "electricity", "sanitation", "streetlight", "drainage", "safety", "other"]
ReportStatus = Literal["open", "filed", "in_progress", "resolved", "closed"]


class CivicTriage(BaseModel):
    model_config = {"str_strip_whitespace": True}
    category: ReportCategory
    title: str = Field(min_length=1, max_length=200)
    title_local: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=6000)
    severity: Literal["low", "medium", "high", "urgent"]
    severity_reason: str = Field(min_length=1, max_length=500)
    department: str = Field(min_length=1, max_length=200)
    since_when: str = Field(default="Not specified by the reporter", max_length=1000)
    people_affected: str = Field(default="Not specified by the reporter", max_length=1000)


class ComplaintDraft(BaseModel):
    model_config = {"str_strip_whitespace": True}
    subject: str = Field(min_length=1, max_length=200)
    english: str = Field(min_length=1, max_length=8000)
    local: str = Field(min_length=1, max_length=8000)
    language: str


class ReportEventOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    source: str
    kind: str
    text: str
    meta: dict = Field(default_factory=dict)
    created_at: datetime


class ReportOut(CivicTriage):
    id: str
    profile_id: str | None
    language: str
    lat: float
    lng: float
    address: str | None
    media: list[dict] = Field(default_factory=list)
    status: ReportStatus
    official_ref: str | None
    official_status: str | None
    supporters: int
    created_at: datetime
    updated_at: datetime
    events: list[ReportEventOut] = Field(default_factory=list)
    distance_m: float | None = None
    similarity: float | None = None
    duplicate_score: float | None = None
    source_url: str | None = None
    complaint_draft: ComplaintDraft | None = None


class TriageOut(CivicTriage):
    language: str
    address: str | None
    geocoding_attribution: str = "© OpenStreetMap contributors (ODbL)"
    duplicates: list[ReportOut] = Field(default_factory=list)


class ReportVoteIn(BaseModel):
    profile_id: str
    kind: Literal["support", "still_broken", "fixed", "follow"]


class ReportActorIn(BaseModel):
    profile_id: str


class CivicRunOut(BaseModel):
    run_id: str
    draft: ComplaintDraft | None = None
