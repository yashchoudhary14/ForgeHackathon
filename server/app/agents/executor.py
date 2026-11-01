"""autonomous form-filling agent on real government portals.

graph:  observe -> decide -> guard -> act -> (observe | human | approval | finish)
- llm never sees PII: it says value_from="full_name" and we substitute locally
- captcha / otp / login always go to the human, we never try to solve them
- anything that looks like a final submit needs explicit approval from the user
"""
import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Literal, TypedDict

from google.genai import types
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from ..config import get_settings
from ..db import SessionLocal
from ..models import AgentRun, AgentStep, LockerItem
from ..schemas import ProfileData, SensitiveData
from ..services import crypto, llm, locker, sarvam
from ..services.notify import notify
from .browser import Browser, allowed

log = logging.getLogger(__name__)

MAX_STEPS = 45
MAX_FAILS = 3
HUMAN_TIMEOUT = 15 * 60
UNWATCHED_TIMEOUT = 120
UNWATCHED_MESSAGE = "Stopped: nobody was watching"


class Aborted(Exception):
    """user pressed abort while we were waiting on them. not CancelledError, langgraph turns that into a node failure"""

SUBMIT_RE = re.compile(r"\b(final\s*submit|submit|confirm|apply now|register|pay|proceed to pay|save\s*&\s*submit|send)\b", re.I)

SYSTEM = """You are an agent operating a real Indian government web portal in a browser, on behalf of a citizen
who is watching live. You see the page as a list of interactive elements (id, tag, label, ...) plus a screenshot.
Return an actions list containing 1 to 8 actions, in execution order, for fields visible in this observation.
Batch independent type/select/check actions to fill as many known fields as possible in ONE call.
Fill stable text/date fields first; put choices likely to reveal cascading fields last.
Never mix navigation/dropdown-opening clicks, scroll, wait, ask_human, request_approval, done or fail
with other actions: these must be singleton lists. Navigation/Next/Check Eligibility stays single-action.
Only data-entry clicks on already visible radio/checkbox/option controls may join a field batch.
Every click/type/select/check/request_approval action must include the visible target's element_id.
value_from identifies the citizen fact, never the portal target. After a human answer,
choose the matching visible option's element_id as well as its recorded value_from key.
Do not plan actions for fields or options that are not in this observation. Use select directly on a
combobox rather than opening it in a separate click when you already know the required option label.
The executor checks every action, stops at the first error or structural page change, and re-observes.

Actions:
- click(element_id)
- type(element_id, value | value_from)   value_from = name of a citizen field, e.g. "full_name", "phone", "dob".
     Personal fields are hidden from you as "<set>"; use value_from for them, never invent values.
- select(element_id, value | value_from)  value must be one of the element's options (pick the closest).
- check(element_id, value="true"/"false")
- upload(element_id, doc_type)  attach a matching document from the citizen's locker, after their approval.
     Use even if the locker has no suitable document: Buddy will pause and open document capture.
- scroll(value="down"/"up"), wait
- ask_human(kind, message, element_id?)  kind: captcha | otp | login | missing_field | payment.
     Use for ANY captcha, OTP, password/login, DigiLocker/Aadhaar consent, or info you do not have.
     For captcha/otp/missing_field give element_id of the input to fill with the human's answer.
     For a missing document without a file input, include doc_type with kind=missing_field.
- request_approval(element_id, message)  REQUIRED before clicking any button that finally submits/applies/pays.
     message = short summary of what will be submitted.
- done(message, reference_no)  when the acknowledgement / application number / status page is shown,
     or the goal is achieved. reference_no = exact number shown on page, else "".
- fail(message)  only if the goal is truly impossible on this site.

Rules:
- Read validation errors in the observation and fix them (self-correct) instead of repeating the same action.
- If the same action failed before, try something different (another element, scroll, select instead of type).
- Never navigate away from government (.gov.in/.nic.in) sites.
- Prefer filling all visible required fields before clicking next/continue.
- Elements show their state (checked / selected / value). If an option is already checked or a field already
  has the right value, do NOT click/type it again — move to the next field or click Next.
- Trust the history: "NOTHING CHANGED" means your last action had no effect; do something different.
- network_errors reports actual failed portal requests, not missing citizen information. If a lookup
  dialog fails, close and reopen it once to retry loading its data. Never repeatedly wait or scroll
  through a stuck loading overlay. If recovery fails, ask_human with the exact portal error.
- For an ARIA combobox, use select directly when the required label is known (including Yes/No,
  state, gender and caste). The local helper opens the overlay and validates the label. Only click
  to inspect options when their labels are unknown. Never type into a closed dropdown.
- Cascading fields may appear after each choice. Use the new observation, never reuse earlier ids.
- Do not interact with disabled controls. Complete enabled prerequisite fields first.
- Use citizen keys from the supplied profile, not portal control names. Social community uses caste;
  hostel status uses is_hosteller, and explicit disability_percent=0 means not disabled.
- On search_field inputs, a type action may supply value as a whole-word fragment of value_from
  to broaden an empty search (for example a town from an institution name). Ordinary form fields
  always receive the complete supplied value. Do not keep retrying the same empty search.
- Translate portal education categories from course/education_level: undergraduate study is post-matric.
  A workflow choice explicitly requested in the GOAL can use value_from="goal" and its exact option label.
- Human answers are available in CITIZEN under their recorded keys. Use those keys; never ask the same
  question again after an answer is recorded. Personal answers remain hidden as <set>.
- <set> means the fact IS KNOWN locally, not missing. Never ask for it again: use value_from with
  exactly that key. For example dob:<set> must be entered using type(value_from="dob").
- For date inputs use the displayed date format. Never invent a date of birth from age; ask for it.
- When DOB is supplied as <set>, use type(value_from="dob") on its input, even if readonly.
  The local helper operates supported calendars without exposing the DOB to you.
- Other readonly text fields often open a lookup dialog. Click them to select a value;
  do not try to type into a readonly institution, university or board lookup.
- Fill ordinary required fields before requesting CAPTCHA help. Never read or transcribe CAPTCHA images.
  After the human resumes, preserve their CAPTCHA entry and continue with the requested check.
- A results list satisfies an eligibility-checking goal; do not apply to a scholarship from that list.
  If the goal requests a count, reference_no must be the observed list count, including zero results.
- Every action entering citizen data (type/select/check, or clicking an option/radio) MUST name
  value_from as the supplied citizen field supporting that answer. For select, value may translate
  that supplied fact into an exact option label. Navigation buttons need no value_from.
- Missing facts NEVER mean No/False. Ask for single-child, disability, hostel status, DOB, scores,
  college identity, etc. if not supplied. Never select a date just to dismiss a calendar; use Escape.
- Keep `thought` to one short sentence a citizen can understand."""

SYSTEM += "\nNever operate payment controls, UPI apps or netbanking. Ask the human with kind=payment."


class HumanGuide(BaseModel):
    title: str = Field(max_length=120)
    steps: list[str] = Field(min_length=1, max_length=3)
    lang: str


class Decision(BaseModel):
    thought: str
    action: Literal["click", "type", "select", "check", "upload", "scroll", "wait", "ask_human", "request_approval", "done", "fail"]
    element_id: int | None = None
    value: str | None = None
    value_from: str | None = None
    kind: Literal["captcha", "otp", "login", "missing_field", "payment"] | None = None
    doc_type: locker.DocType | None = None
    message: str | None = None
    reference_no: str | None = None


class ActionPlan(BaseModel):
    actions: list[Decision] = Field(min_length=1, max_length=8)


FIELD_ACTIONS = frozenset({"type", "select", "check"})


def execution_prefix(actions: list[Decision], elements: list[dict] | None = None) -> list[Decision]:
    """Enforce singleton navigation/control actions even if a model mixes a plan."""
    by_id = {el["id"]: el for el in elements or []}
    def field_action(action):
        el = by_id.get(action.element_id, {})
        return action.action in FIELD_ACTIONS or (action.action == "click" and
            (el.get("role") in ("radio", "checkbox", "option") or
             (el.get("tag") == "label" and "checked" in el)))
    if not field_action(actions[0]):
        return actions[:1]
    result = []
    for action in actions:
        if not field_action(action):
            break
        result.append(action)
    return result


def page_changed(before: dict, after: dict) -> bool:
    """Field values may change within a batch; navigation, steps and new controls may not."""
    def structure(snap):
        keys = ("id", "tag", "role", "label", "field_label", "name", "formcontrolname", "placeholder", "disabled")
        return (snap.get("url"), snap.get("navigation_id"), snap.get("title"),
                tuple(snap.get("headings", [])), tuple(snap.get("steps", [])),
                tuple(tuple(el.get(key) for key in keys) +
                      (el.get("text") if el.get("tag") == "button" or el.get("role") == "tab" else None,)
                      for el in snap["elements"]
                      if el.get("tag") in ("input", "textarea", "select", "button") or
                      el.get("role") in ("combobox", "checkbox", "radio", "tab", "dialog")))
    return structure(before) != structure(after) or bool(set(after.get("errors", [])) - set(before.get("errors", [])))


class State(TypedDict, total=False):
    stagnant: int
    step: int
    fails: int
    snap: dict
    shot: bytes
    decision: Decision
    remaining: list[Decision]
    stale: bool
    history: list[dict]
    digest: str
    outcome: str  # next | human | approval | done | failed
    receipt: dict
    error: str


def explicitly_requested_option(d: Decision, el: dict | None, goal: str) -> bool:
    if d.action == "select":
        label = d.value
    elif d.action == "click" and el and el.get("role") == "option":
        label = el.get("text")
    else:
        return False
    return bool(label and re.search(r"(?<!\w)" + re.escape(label.strip()) + r"(?!\w)", goal, re.I))


def require_source(d: Decision, el: dict | None, known: dict) -> Decision:
    """A model's default answer is not evidence about a citizen."""
    if not el or d.action not in ("type", "select", "check", "click"):
        return d
    field = el.get("field_label") or el.get("label") or ""
    workflow = re.search(r"application|service|benefit|scholarship|language|workflow|scheme|sort|page", field, re.I)
    if not d.value_from and workflow and explicitly_requested_option(d, el, known.get("goal", "")):
        d = d.model_copy(update={"value_from": "goal"})
    aliases = {"community": "caste", "hosteler": "is_hosteller", "hosteller": "is_hosteller",
               "single_girl_child": "is_single_child", "college": "institution_name",
               "institute_name": "institution_name", "college_name": "institution_name",
               "date_of_birth": "dob", "parent_profession": "parent_occupation"}
    if d.value_from and known.get(d.value_from) in (None, ""):
        normalize = lambda key: re.sub(r"[^a-z0-9]", "", key.casefold())
        normalized = {normalize(key): key for key in known}
        normalized.update({normalize(key): value for key, value in aliases.items()})
        alias = normalized.get(normalize(d.value_from))
        if alias and known.get(alias) not in (None, ""):
            d = d.model_copy(update={"value_from": alias})
    label = el.get("field_label") or el.get("label") or el.get("name") or el.get("placeholder") or "this field"
    birth = bool(re.search(r"date\s*of\s*birth|\bdob\b|birth\s*date", label, re.I))
    data_entry = (d.action in ("type", "select", "check") or el.get("role") in ("option", "radio", "checkbox")
                  or (el.get("tag") == "label" and "checked" in el))
    if birth and not known.get("dob"):
        key = "dob"
    elif data_entry and (not d.value_from or known.get(d.value_from) in (None, "")):
        key = d.value_from or el.get("formcontrolname") or el.get("name")
    else:
        return d
    return Decision(thought="This answer was not supplied by the citizen.", action="ask_human",
        kind="missing_field", value_from=key, element_id=d.element_id,
        message=f"Please provide {label}; it is not in the supplied profile. You can also fill it in the browser.")


class RunAborted(Aborted):
    """User-requested stop, propagated through graph nodes without cancellation wrapping."""


class RunSession:
    """live state of one run: websocket subscribers + inbox for human messages"""

    def __init__(self, run_id: str, goal: str, portal_url: str, profile: dict, sensitive: dict,
                 *, profile_id: str | None = None, language: str = "en"):
        self.id = run_id
        self.goal = goal
        self.portal_url = portal_url
        self.profile = profile
        self.profile_id = profile_id
        self.language = language
        self.sensitive = {k: str(v) for k, v in sensitive.items() if v}
        self.answers: dict[str, str] = {}
        self.private_values: set[str] = set(self.sensitive.values())
        self.private_values.update(str(v) for k, v in profile.items() if v is not None and
            re.search(r"name|phone|mobile|email|dob|birth|address|bank|ifsc|aadhaar|account", k, re.I))
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.subs: set = set()
        self.last_subscriber_at = time.monotonic()
        self._abort_requested = False
        self.status = "queued"
        self.pending: dict | None = None  # current needs_human event, replayed to late joiners
        self.browser = Browser(self._on_frame)
        self.task: asyncio.Task | None = None
        self._last_frame_sent = 0.0
        self.llm_calls = 0
        self.steps = 0
        self.uploads: list[dict] = []
        self.human_wait_seconds = 0.0

    # ---------- pub/sub ----------
    def subscribe(self, ws):
        self.subs.add(ws)
        self.last_subscriber_at = time.monotonic()

    def unsubscribe(self, ws):
        if ws in self.subs:
            self.subs.discard(ws)
            # Start the grace period when the last viewer leaves, even if they
            # watched for longer than UNWATCHED_TIMEOUT before disconnecting.
            self.last_subscriber_at = time.monotonic()

    async def emit(self, msg: dict):
        dead = []
        for ws in list(self.subs):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unsubscribe(ws)

    async def _on_frame(self, b64: str):
        now = time.monotonic()
        if now - self._last_frame_sent < 0.12 or not self.subs:  # ~8fps cap, plenty for a demo
            return
        self._last_frame_sent = now
        await self.emit({"type": "frame", "jpeg": b64})

    async def set_status(self, status: str, **extra):
        changed = self.status != status
        self.status = status
        async with SessionLocal() as db:
            run = await db.get(AgentRun, self.id)
            run.status = status
            for k, v in extra.items():
                setattr(run, k, v)
            await db.commit()
        if changed and status in {"done", "failed", "needs_human", "awaiting_approval"}:
            await notify(self.profile_id, "run_status", {
                "done": "Application completed", "failed": "Application needs attention",
                "needs_human": "Your help is needed", "awaiting_approval": "Please review your application",
            }[status], body=extra.get("error", ""), link=f"/runs/{self.id}",
                meta={"run_id": self.id, "status": status})
        await self.emit({"type": "status", "status": status})

    async def save_answers(self):
        async with SessionLocal() as db:
            run = await db.get(AgentRun, self.id)
            run.meta = {**(run.meta or {}), "answers_encrypted": crypto.encrypt_json(self.answers)}
            await db.commit()

    async def human_event(self, kind: str, element_id: int | None = None, **details) -> dict:
        # Only the step category goes to the model: no page pixels, citizen values,
        # portal text, filenames, or the planner's potentially personal message.
        field = details.get("field")
        safe_field = field if field in (set(ProfileData.model_fields) | set(SensitiveData.model_fields)) else None
        try:
            guide = await llm.generate_json(
                f"Write guidance in language {self.language} for step {kind}. "
                + (f"Ask for the citizen's {safe_field.replace('_', ' ')} in this language. " if kind == "missing_field" and safe_field else "") +
                "The citizen has never used a website. Use 1-3 very short, simple steps. "
                "For CAPTCHA say look at the big letters and say or type them, including capitals; never solve it. "
                "For OTP say read the 6 digits from the SMS on their own phone into the portal voice input. For login they enter passwords themselves. "
                "For payment explain opening UPI on their phone or netbanking, checking the amount and "
                "payee and approving there themselves. Never ask to share a PIN, password or OTP. "
                "For confirm_submit ask them to review before approving. For confirm_upload ask them "
                "to check the document shown before allowing attachment. Return lang exactly as requested.",
                HumanGuide, model="lite", temperature=0,
                system="Write accessible instructions only. No personal information is supplied.")
            if not isinstance(guide, HumanGuide):
                raise ValueError("Invalid guidance response")
            guide.lang = self.language
        except Exception:
            # A failed model must not prevent a citizen taking control.
            steps = (["स्क्रीन पर दिखाया गया कदम खुद पूरा करें।", "फिर आगे बढ़ें दबाएँ।"]
                     if self.language == "hi" else
                     ["Complete the step shown on the screen yourself.", "Then press Continue."])
            guide = HumanGuide(title="आपकी मदद चाहिए" if self.language == "hi" else "Your help is needed",
                               steps=steps, lang=self.language)
        if kind == "missing_field" and details.get("message") and self.language != "en":
            try:
                # The question can contain private portal data: Sarvam only, never
                # the generic translation fallback to Gemini, and no public TTS file.
                details["message"] = await sarvam.translate(details["message"], "en", self.language, allow_llm=False)
            except Exception:
                log.warning("Private portal question translation unavailable")
        audio_url = None
        try:
            if self.language in sarvam.LANG_CODES:
                audio_url = await sarvam.tts_to_file(" ".join(guide.steps), self.language)
        except Exception:
            log.warning("Guidance speech unavailable for %s", self.language)
        crop = None
        if hasattr(self.browser, "human_crop"):
            crop = await self.browser.human_crop(kind, element_id)
        from uuid import uuid4
        return {"type": "needs_human", "request_id": uuid4().hex, "kind": kind, "guide": guide.model_dump(),
                "crop": crop, "audio_url": audio_url, **details}

    async def document_for_upload(self, doc_type: str, element_id: int | None, accept: str, hint: str):
        """Pause for capture, then select a readable, portal-sized encrypted variant.

        A capture completion only resumes the search. Attachment still requires the
        separate confirm_upload approval below.
        """
        while True:
            async with SessionLocal() as db:
                items = (await db.execute(select(LockerItem).where(
                    LockerItem.profile_id == self.profile_id, LockerItem.doc_type == doc_type
                ).order_by(LockerItem.created_at.desc()))).scalars().all()
            for item in items:
                meta = item.meta or {}
                if meta.get("readable") is not True or (meta.get("detected_doc_type") and meta["detected_doc_type"] != doc_type):
                    continue
                try:
                    return item, locker.choose_variant(item, accept, hint)
                except ValueError:
                    continue
            await self.set_status("needs_human")
            event = await self.human_event("confirm_upload", element_id,
                message="A readable document that fits this portal is needed. Photograph or choose the document.",
                doc_type=doc_type, capture_required=True, document=None)
            await self.wait_human(event, {"resume"})

    async def duplicate_runs(self) -> list[str]:
        if not self.profile_id:
            return []
        async with SessionLocal() as db:
            current = await db.get(AgentRun, self.id)
            if current.kind != "application":
                return []
            match = AgentRun.portal_url == current.portal_url
            if current.scheme_slug:
                match = or_(match, AgentRun.scheme_slug == current.scheme_slug)
            rows = await db.execute(select(AgentRun.id).where(
                AgentRun.profile_id == self.profile_id, AgentRun.id != self.id,
                AgentRun.kind == "application", AgentRun.status == "done", match))
            return list(rows.scalars())

    # ---------- llm view of the citizen ----------
    def redact(self, value):
        if isinstance(value, dict):
            return {k: self.redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        if not isinstance(value, str):
            return value
        for secret in sorted(self.private_values | set(self.answers.values()), key=len, reverse=True):
            if secret:
                value = value.replace(secret, "<private>")
        value = re.sub(r"\b\d{10,16}\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "<private>", value)
        return value

    def citizen_view(self) -> dict:
        personal = re.compile(r"name|phone|mobile|email|dob|birth|address|bank|ifsc|aadhaar|account|password|otp|human_answer_", re.I)
        view = {k: "<set>" if personal.search(k) else v for k, v in self.profile.items() if v is not None}
        view.update({k: "<set>" for k in self.sensitive})
        safe_keys = set(ProfileData.model_fields) | {"scheme_type_id"}
        view.update({k: v if k in safe_keys and not personal.search(k) else "<set>" for k, v in self.answers.items()})
        return view

    def resolve(self, d: Decision, *, search_field: bool = False) -> str:
        if d.value_from:
            key = d.value_from.strip()
            if key == "goal" and key not in self.answers:
                if d.action != "select" or not d.value or not re.search(r"(?<!\w)" + re.escape(d.value) + r"(?!\w)", self.goal, re.I):
                    raise ValueError("Workflow choice must be explicitly named in the goal")
                return d.value
            for src in (self.sensitive, self.answers, self.profile):
                if key in src and src[key] not in (None, ""):
                    if d.action == "type" and search_field and d.value and key not in self.sensitive:
                        fragment = d.value.strip()
                        if re.search(r"(?<!\w)" + re.escape(fragment) + r"(?!\w)", str(src[key]), re.I):
                            return fragment
                        raise ValueError("Search text must be a whole-word fragment of the supplied source")
                    if d.action == "select" and d.value and key not in self.sensitive:
                        return d.value  # e.g. supplied sc -> displayed Scheduled Caste
                    if d.action == "select" and isinstance(src[key], bool):
                        return "Yes" if src[key] else "No"
                    return str(src[key])
            raise KeyError(f"citizen field '{key}' is not known — ask the human")
        return d.value or ""

    # ---------- human in the loop ----------
    async def wait_human(self, event: dict, expect: set[str]) -> dict:
        waiting_since = time.monotonic()
        self.pending = event
        await self.emit(event)
        deadline = waiting_since + HUMAN_TIMEOUT
        try:
            while True:
                now = time.monotonic()
                if self.subs:
                    self.last_subscriber_at = now
                unwatched_left = UNWATCHED_TIMEOUT - (now - self.last_subscriber_at)
                if not self.subs and unwatched_left <= 0:
                    raise RunAborted(UNWATCHED_MESSAGE)
                left = deadline - now
                if left <= 0:
                    raise TimeoutError("Human response timed out after 15 minutes")
                try:
                    # Recheck viewers even when nobody sends an inbox message.
                    msg = await asyncio.wait_for(self.inbox.get(), timeout=min(left, 1, unwatched_left))
                except TimeoutError:
                    continue
                t = msg.get("type")
                if event.get("request_id") and t in {"human_input", "resume", "approve", "approve_duplicate"} and msg.get("request_id") != event["request_id"]:
                    continue  # a late voice confirmation must never fill the next field
                if t == "abort":
                    raise RunAborted("Run aborted by user")
                if t == "click":
                    await self.browser.human_click(float(msg["x"]), float(msg["y"]))
                elif t == "type":
                    self.private_values.add(str(msg.get("text", "")))
                    await self.browser.human_type(str(msg.get("text", "")))
                elif t == "key":
                    await self.browser.human_key(str(msg.get("key", "Enter")))
                if t in expect:
                    return msg
        finally:
            self.human_wait_seconds += time.monotonic() - waiting_since
            self.pending = None


# ---------- graph nodes ----------

def _digest(snap: dict) -> str:
    els = [(e.get("tag"), e.get("text") or e.get("label"), e.get("value"), e.get("checked"),
            e.get("selected"), e.get("disabled"), e.get("expanded")) for e in snap["elements"]]
    return str(hash((snap["url"], tuple(snap["headings"]), tuple(snap["errors"]),
                     tuple(snap.get("network_errors", [])), snap.get("text", ""), tuple(els))))


def _el_name(snap: dict, element_id: int | None) -> str:
    el = next((e for e in snap["elements"] if e["id"] == element_id), None) if element_id else None
    if not el:
        return ""
    return (el.get("label") or el.get("text") or el.get("placeholder") or el.get("name") or el["tag"])[:40]


def _history_text(h: list[dict]) -> str:
    lines = []
    for s in h[-10:]:
        lines.append(f"#{s['step']} {s['action']} -> {s['result']}")
    return "\n".join(lines) or "(none yet)"


def build_graph(rs: RunSession):
    shots_dir = Path(str(Path(get_settings().storage_dir).resolve()) + "-private") / "runs" / rs.id
    shots_dir.mkdir(parents=True, exist_ok=True)

    async def record(st: State, d: Decision | None, status: str, result: str) -> str:
        shot_path = shots_dir / f"{st['step']:03d}.enc"
        try:
            image = await rs.browser.screenshot(quality=50)
            await asyncio.to_thread(locker.encrypt_file, shot_path, image)
            shot_url = f"/api/agent/runs/{rs.id}/screenshots/{st['step']}?profile_id={rs.profile_id}"
        except Exception:
            shot_url = None
        action = d.model_dump(exclude_none=True, exclude={"thought"}) if d else None
        if action and action.get("value") and action.get("action") == "type" and d.kind == "otp":
            action["value"] = "••••"
        async with SessionLocal() as db:
            db.add(AgentStep(run_id=rs.id, idx=st["step"], thought=d.thought if d else None, action=action,
                             status=status, url=rs.browser.page.url, screenshot=shot_url))
            await db.commit()
        await rs.emit({"type": "step", "step": {"idx": st["step"], "thought": d.thought if d else None, "action": action,
                                                  "status": status, "url": rs.browser.page.url, "screenshot": shot_url,
                                                  "result": result}})
        return shot_url

    async def observe(st: State) -> State:
        snap = await rs.browser.snapshot()
        if snap.get("loading"):
            await rs.browser.settle()
            snap = await rs.browser.snapshot()
        shot = await rs.browser.decision_screenshot()
        dig = _digest(snap)
        hist = list(st.get("history", []))
        # "ok" from playwright only means the click didn't throw - tell the model when the page didn't react
        if hist and st.get("digest") == dig and hist[-1]["result"] == "ok" and not hist[-1]["action"].startswith(("scroll", "wait")):
            hist[-1] = {**hist[-1], "result": "ok but NOTHING CHANGED on the page"}
            same = [h for h in hist[-4:] if h["action"] == hist[-1]["action"] and "NOTHING CHANGED" in h["result"]]
            if len(same) >= 2:
                hist.append({"step": hist[-1]["step"], "action": "note",
                             "result": "You are repeating an action that has no effect. It is probably already done "
                                       "(check checked/selected/value). Move on (e.g. click Next) or try a different element."})
        return {"snap": snap, "shot": shot, "digest": dig, "history": hist,
                "stagnant": st.get("stagnant", 0) + 1 if st.get("digest") == dig else 0}

    async def decide(st: State) -> State:
        snap = st["snap"]
        if snap.get("loading"):
            errors = "; ".join(snap.get("network_errors", []))
            return {"decision": Decision(thought="The portal loading overlay is blocking the form.",
                    action="ask_human", kind="missing_field",
                    message="The portal is still blocked by its loading overlay. " + (errors or "Please check the live browser.")), "remaining": []}
        if st.get("stagnant", 0) >= 3:
            errors = "; ".join(snap.get("network_errors", []))
            message = "The portal has not changed after three attempts. " + (errors or "Please check the live browser before continuing.")
            return {"decision": Decision(thought="The portal is not responding; stopping repeated actions.",
                    action="ask_human", kind="missing_field", message=message), "remaining": []}
        elements = []
        for element in snap["elements"]:
            safe = dict(element)
            if safe.get("tag") in ("input", "textarea") and safe.get("value"):
                safe["value"] = "<set>"
            elements.append(safe)
        obs = rs.redact({
            "url": snap["url"], "title": snap["title"], "headings": snap["headings"],
            "validation_errors": snap["errors"], "captcha_detected": snap["captcha"],
            "network_errors": snap.get("network_errors", []),
            "elements": elements, "page_text": snap["text"][:1500],
        })
        doc_types = []
        if rs.profile_id:
            async with SessionLocal() as db:
                doc_types = list((await db.execute(select(LockerItem.doc_type).where(
                    LockerItem.profile_id == rs.profile_id))).scalars())
        prompt = [
            f"GOAL: {rs.redact(rs.goal)}\n\nCITIZEN (personal fields hidden): {json.dumps(rs.citizen_view(), ensure_ascii=False)}\n\n"
            f"PREVIOUS STEPS:\n{rs.redact(_history_text(st.get('history', [])))}\n\n"
            f"OBSERVATION:\n{json.dumps(obs, ensure_ascii=False)}",
            f"LOCKER document types available: {json.dumps(doc_types)}",
        ]
        rs.llm_calls += 1
        plan = await llm.generate_json(prompt, ActionPlan, system=SYSTEM, temperature=0.1, model=get_settings().agent_model)
        actions = execution_prefix(plan.actions, snap["elements"])
        return {"decision": actions[0], "remaining": actions[1:]}

    async def guard(st: State) -> State:
        """deterministic safety rails on top of whatever the model decided"""
        d = st["decision"]
        snap = await rs.browser.snapshot()
        missing_target = d.element_id is not None and not any(e["id"] == d.element_id for e in snap["elements"])
        if page_changed(st["snap"], snap) or missing_target:
            return {"snap": snap, "stale": True, "remaining": []}
        el = next((e for e in snap["elements"] if e["id"] == d.element_id), None) if d.element_id else None
        label = json.dumps(el or {})
        payment = re.search(r"\b(upi|net\s*banking|pay|make\s*payment)\b", label, re.I)
        payment_page = re.search(r"upi|net.?banking|payment|checkout", snap.get("url", "") + " " + snap.get("title", ""), re.I)
        payment_page = payment_page or re.search(r"pay using|select payment method|card number|\bcvv\b|upi pin", snap.get("text", ""), re.I)
        if d.action in ("click", "type", "select", "check", "upload", "request_approval") and (payment or payment_page):
            d = d.model_copy(update={"action": "ask_human", "kind": "payment", "message": "Complete payment yourself on your phone or netbanking, then continue."})
        if d.action == "click" and el:
            label = str(el.get("text") or el.get("value") or el.get("title") or el.get("label") or "")
            # any clickable thing that reads like "submit" counts - portals style divs as buttons
            strong = re.search(r"submit|apply|pay\b", label, re.I)
            weak_ok = re.search(r"\b(otp|search|check|next|continue|login|sign in|verify)\b", label, re.I)
            if SUBMIT_RE.search(label) and len(label.strip()) < 40 and (strong or not weak_ok):
                d = d.model_copy(update={"action": "request_approval", "message": d.message or f"Submit the form ('{label.strip()[:40]}')?"})
        if d.action in ("type", "click", "select", "check") and snap["captcha"] and el and re.search(r"captcha", json.dumps(el), re.I):
            d = d.model_copy(update={"action": "ask_human", "kind": "captcha", "message": "Please solve the CAPTCHA, then press Continue."})
        if d.action == "type" and el and el.get("type") == "password":
            d = d.model_copy(update={"action": "ask_human", "kind": "login", "message": "Please enter your password yourself, then press Continue."})
        if d.action == "type" and el and re.search(r"\botp\b|one.time|verification.code", json.dumps(el), re.I):
            d = d.model_copy(update={"action": "ask_human", "kind": "otp", "message": "Enter the code received on your phone."})
        known = {**rs.profile, **rs.sensitive, **rs.answers}
        if explicitly_requested_option(d, el, rs.goal):
            known["goal"] = rs.goal
        d = require_source(d, el, known)
        return {"decision": d, "snap": snap, "stale": False}

    async def act(st: State) -> State:
        d: Decision = st["decision"]
        b = rs.browser
        if st.get("stale"):
            hist = list(st.get("history", []))
            hist.append({"step": st.get("step", 0), "action": "batch stopped",
                         "result": "The page changed before execution; plan discarded"})
            return {"history": hist, "outcome": "next", "remaining": [], "stale": False}
        step = st.get("step", 0) + 1
        rs.steps = step
        st = {**st, "step": step}
        hist = list(st.get("history", []))
        # History uses visible names; node ids stay stable while the document lives.
        target = _el_name(st["snap"], d.element_id)
        val = f" = {d.value_from or d.value}" if d.action in ("type", "select", "check") and (d.value_from or d.value) else ""
        desc = f"{d.action} '{target}'{val}" if target else f"{d.action}{val}"

        if d.action in ("ask_human", "request_approval", "done", "fail"):
            outcome = {"ask_human": "human", "request_approval": "approval", "done": "done", "fail": "failed"}[d.action]
            return {"step": step, "outcome": outcome, "remaining": []}

        try:
            if d.action == "click":
                await b.click(d.element_id)
            elif d.action == "type":
                element = next((e for e in st["snap"]["elements"] if e["id"] == d.element_id), {})
                await b.fill(d.element_id, rs.resolve(d, search_field=element.get("search_field", False)))
            elif d.action == "select":
                await b.select(d.element_id, rs.resolve(d))
            elif d.action == "check":
                value = rs.resolve(d) if d.value_from else (d.value or "true")
                await b.check(d.element_id, value.strip().lower() in ("true", "yes", "1"))
            elif d.action == "upload":
                if not rs.profile_id or not d.doc_type:
                    raise ValueError("A profile and document type are required for upload")
                element = next((e for e in st["snap"]["elements"] if e["id"] == d.element_id), {})
                if element.get("type") != "file":
                    raise ValueError("Upload target must be a file input")
                hint = str(element.get("size_hint", ""))
                if element.get("data-max-size", "").isdigit():
                    hint += f" {int(element['data-max-size']) / 1000} KB"
                item, variant = await rs.document_for_upload(d.doc_type, d.element_id, element.get("accept", ""), hint)
                attachment = {"id": item.id, "title": item.title, "doc_type": item.doc_type,
                              "format": variant["format"], "bytes": variant["bytes"], "meta": item.meta}
                await rs.set_status("needs_human")
                await record(st, d, "human", "confirm_upload")
                event = await rs.human_event("confirm_upload", d.element_id,
                    message=f"Attach {item.title} from your locker?", document=attachment)
                await rs.wait_human(event, {"approve"})
                # Revalidate the owner and target after an unbounded human pause.
                async with SessionLocal() as db:
                    fresh = await db.get(LockerItem, item.id)
                    if (not fresh or fresh.profile_id != rs.profile_id or (fresh.meta or {}).get("readable") is not True
                            or ((fresh.meta or {}).get("detected_doc_type") and fresh.meta["detected_doc_type"] != d.doc_type)):
                        raise ValueError("Document is no longer available")
                now = await b.snapshot()
                if page_changed(st["snap"], now):
                    raise ValueError("Portal changed while awaiting upload approval; please review again")
                content = await asyncio.to_thread(locker.decrypt_file, variant["path"])
                await b.upload(d.element_id, {"name": f"{item.doc_type}.{variant['format']}",
                    "mimeType": {"jpg": "image/jpeg", "pdf": "application/pdf"}[variant["format"]],
                    "buffer": content})
                rs.uploads.append({k: v for k, v in attachment.items() if k != "meta"})
                await rs.set_status("running")
            elif d.action == "scroll":
                await b.scroll((d.value or "down") != "up")
            elif d.action == "wait":
                await asyncio.sleep(2)
            if not allowed(b.page.url):
                raise RuntimeError("left government site")
            hist.append({"step": step, "action": desc, "result": "ok"})
            await record(st, d, "ok", "ok")
            after = await b.snapshot()
            remaining = st.get("remaining", [])
            changed = page_changed(st["snap"], after)
            if remaining and changed:
                hist.append({"step": step, "action": "batch stopped", "result": "Page structure changed; remaining actions discarded"})
            if remaining and not changed:
                return {"step": step, "history": hist, "fails": 0, "outcome": "batch",
                        "snap": after, "digest": _digest(st["snap"]),
                        "decision": remaining[0], "remaining": remaining[1:]}
            return {"step": step, "history": hist, "fails": 0, "outcome": "next",
                    "snap": after, "digest": _digest(st["snap"]), "remaining": []}
        except RunAborted:
            raise
        except Exception as e:
            err = str(e).split("\n")[0][:200]
            hist.append({"step": step, "action": desc, "result": f"ERROR: {err}"})
            await record(st, d, "retry", err)
            fails = st.get("fails", 0) + 1
            if fails >= MAX_FAILS:
                # stuck: hand over to the human rather than flail
                d2 = Decision(thought="I'm stuck on this step, can you help?", action="ask_human", kind="missing_field",
                              message=f"I couldn't do this: {err}. Please do this step in the live view, then press Continue.")
                return {"step": step, "history": hist, "fails": 0, "decision": d2, "outcome": "human", "remaining": []}
            return {"step": step, "history": hist, "fails": fails, "outcome": "next", "remaining": []}

    async def human(st: State) -> State:
        d: Decision = st["decision"]
        kind = d.kind or "missing_field"
        if kind in ("captcha", "otp"):
            target = next((e for e in st["snap"]["elements"] if e["id"] == d.element_id), {})
            if target.get("tag") not in ("input", "textarea"):
                target = next((e for e in st["snap"]["elements"] if e.get("tag") in ("input", "textarea")
                    and re.search("captcha" if kind == "captcha" else r"otp|one.time|verification", json.dumps(e), re.I)), {})
                d = d.model_copy(update={"element_id": target.get("id")})
        await rs.set_status("needs_human")
        if kind == "missing_field" and d.doc_type:
            await rs.document_for_upload(d.doc_type, d.element_id, "", "")
            await rs.set_status("running")
            return {"history": list(st.get("history", [])), "stagnant": 0, "digest": ""}
        ev = await rs.human_event(kind, d.element_id, message=d.message or "Your help is needed", field=d.value_from)
        await record(st, d, "human", kind)
        msg = await rs.wait_human(ev, {"resume", "human_input"})
        hist = list(st.get("history", []))
        if msg["type"] == "human_input" and msg.get("value"):
            val = str(msg["value"])
            rs.private_values.add(val)
            el = next((e for e in st["snap"]["elements"] if e["id"] == d.element_id), {})
            source_key = d.value_from if d.value_from != "goal" else None
            answer_key = source_key or el.get("formcontrolname") or el.get("name") or f"human_answer_{st['step']}"
            if kind == "missing_field":
                rs.answers[answer_key] = val
                if rs.profile_id:
                    await rs.save_answers()
            if kind not in ("login", "payment") and d.element_id and el.get("tag") in ("input", "textarea") and not el.get("readonly"):
                await rs.browser.fill(d.element_id, val)  # OTP never goes to the model
            result = (f"Human supplied an answer; use value_from={answer_key} to enter it" if kind == "missing_field"
                      else "Human completed verification in the page; preserve their entry unless the portal rejects it")
            hist.append({"step": st["step"], "action": f"ask_human({kind}): {d.message or ''}", "result": result})
        else:
            hist.append({"step": st["step"], "action": f"ask_human({kind})", "result": "human finished it in the live view"})
        await rs.browser.settle()
        await rs.set_status("running")
        return {"history": hist, "stagnant": 0, "digest": ""}

    async def approval(st: State) -> State:
        d: Decision = st["decision"]
        await rs.set_status("awaiting_approval")
        await record(st, d, "human", "approval")
        duplicates = await rs.duplicate_runs()
        event = await rs.human_event("confirm_submit", d.element_id, message=d.message or "Submit now?",
            duplicate_warning=("An application was already completed for this scheme or portal. Check before submitting again." if duplicates else None),
            duplicate_run_ids=duplicates)
        # Repeating a completed application needs a separate, explicit override.
        if duplicates:
            await rs.wait_human(event, {"approve_duplicate"})
        else:
            await rs.wait_human(event, {"approve"})
        await rs.set_status("running")
        hist = list(st.get("history", []))
        try:
            if page_changed(st["snap"], await rs.browser.snapshot()):
                raise ValueError("Portal changed while waiting for approval; review the new page")
            await rs.browser.click(d.element_id)
            hist.append({"step": st["step"], "action": f"click({d.element_id}) [approved submit]", "result": "ok"})
        except Exception as e:
            hist.append({"step": st["step"], "action": f"click({d.element_id}) [approved submit]", "result": f"ERROR: {e}"})
        return {"history": hist}

    async def finish(st: State) -> State:
        d: Decision = st["decision"]
        shot = await record(st, d, "ok", "done")
        receipt = {
            "reference_no": (d.reference_no or "").strip(),
            "summary": d.message,
            "url": rs.browser.page.url,
            "title": st["snap"].get("title"),
            "screenshot": shot,
            "planning_calls": rs.llm_calls,
            "attachments": rs.uploads,
        }
        return {"receipt": receipt, "outcome": "done"}

    def after_act(st: State) -> str:
        if st.get("step", 0) >= MAX_STEPS and st["outcome"] in ("next", "batch"):
            return "out_of_steps"
        return st["outcome"]

    g = StateGraph(State)
    for name, fn in [("observe", observe), ("decide", decide), ("guard", guard), ("act", act),
                     ("human", human), ("approval", approval), ("finish", finish)]:
        g.add_node(name, fn)
    g.set_entry_point("observe")
    g.add_edge("observe", "decide")
    g.add_edge("decide", "guard")
    g.add_edge("guard", "act")
    g.add_conditional_edges("act", after_act, {
        "next": "observe", "batch": "guard", "human": "human", "approval": "approval", "done": "finish",
        "failed": END, "out_of_steps": END,
    })
    g.add_edge("human", "observe")
    g.add_edge("approval", "observe")
    g.add_edge("finish", END)
    return g.compile()


async def run(rs: RunSession):
    try:
        await rs.set_status("running")
        await rs.browser.start()
        await rs.browser.goto(rs.portal_url)
        graph = build_graph(rs)
        final: dict[str, Any] = await graph.ainvoke({"step": 0, "fails": 0, "history": []}, {"recursion_limit": MAX_STEPS * 6})
        if final.get("outcome") == "done":
            await rs.set_status("done", receipt=final["receipt"])
            await rs.emit({"type": "done", "receipt": final["receipt"]})
        else:
            d = final.get("decision")
            msg = d.message if d and d.action == "fail" else "Stopped: step limit reached"
            await rs.set_status("failed", error=msg)
            await rs.emit({"type": "error", "message": msg})
    except (RunAborted, asyncio.CancelledError) as e:
        await rs.set_status("aborted", error=str(e) or "aborted")
        await rs.emit({"type": "error", "message": UNWATCHED_MESSAGE if str(e) == UNWATCHED_MESSAGE else "Run aborted"})
    except Exception as e:
        log.exception("run %s crashed", rs.id)
        await rs.set_status("failed", error=str(e)[:500])
        await rs.emit({"type": "error", "message": f"Agent error: {str(e)[:200]}"})
    finally:
        await rs.browser.close()


class RunManager:
    def __init__(self, max_parallel: int = 3):
        self.sessions: dict[str, RunSession] = {}
        self.sem = asyncio.Semaphore(max_parallel)

    def start(self, rs: RunSession):
        self.sessions[rs.id] = rs

        async def go():
            async with self.sem:
                await run(rs)

        rs.task = asyncio.create_task(go())

    def get(self, run_id: str) -> RunSession | None:
        return self.sessions.get(run_id)

    async def abort(self, rs: RunSession):
        if rs.status in {"done", "failed", "aborted"}:
            return
        if rs.task and not rs.task.done():
            if not rs._abort_requested:
                rs._abort_requested = True
                if rs.pending:
                    rs.inbox.put_nowait({"type": "abort"})
                else:
                    rs.task.cancel("Run aborted by user")
            try:
                await asyncio.shield(rs.task)
            except asyncio.CancelledError:
                if not rs.task.cancelled():
                    raise
        # A task cancelled before it entered run() (including while queued)
        # never reaches that function's status/cleanup handler.
        if rs.status not in {"done", "failed", "aborted"}:
            await rs.set_status("aborted", error="Run aborted by user")
            await rs.emit({"type": "error", "message": "Run aborted"})

    def set_language(self, profile_id: str, language: str):
        for session in self.sessions.values():
            if session.profile_id == profile_id:
                session.language = language


manager = RunManager()
