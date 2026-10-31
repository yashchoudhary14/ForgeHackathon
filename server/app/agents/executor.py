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

from ..config import get_settings
from ..db import SessionLocal
from ..models import AgentRun, AgentStep
from ..services import llm
from .browser import Browser, allowed

log = logging.getLogger(__name__)

MAX_STEPS = 45
MAX_FAILS = 3
HUMAN_TIMEOUT = 15 * 60

SUBMIT_RE = re.compile(r"\b(final\s*submit|submit|confirm|apply now|register|pay|proceed to pay|save\s*&\s*submit|send)\b", re.I)

SYSTEM = """You are an agent operating a real Indian government web portal in a browser, on behalf of a citizen
who is watching live. You see the page as a list of interactive elements (id, tag, label, ...) plus a screenshot.
Return an actions list containing 1 to 8 actions, in execution order, for fields visible in this observation.
Batch independent type/select/check actions to fill as many known fields as possible in ONE call.
Fill stable text/date fields first; put choices likely to reveal cascading fields last.
Never mix navigation/dropdown-opening clicks, scroll, wait, ask_human, request_approval, done or fail
with other actions: these must be singleton lists. Navigation/Next/Check Eligibility stays single-action.
Only data-entry clicks on already visible radio/checkbox/option controls may join a field batch.
Do not plan actions for fields or options that are not in this observation. Use select directly on a
combobox rather than opening it in a separate click when you already know the required option label.
The executor checks every action, stops at the first error or structural page change, and re-observes.

Actions:
- click(element_id)
- type(element_id, value | value_from)   value_from = name of a citizen field, e.g. "full_name", "phone", "dob".
     Personal fields are hidden from you as "<set>"; use value_from for them, never invent values.
- select(element_id, value | value_from)  value must be one of the element's options (pick the closest).
- check(element_id, value="true"/"false")
- scroll(value="down"/"up"), wait
- ask_human(kind, message, element_id?)  kind: captcha | otp | login | missing_field.
     Use for ANY captcha, OTP, password/login, DigiLocker/Aadhaar consent, or info you do not have.
     For otp/missing_field give element_id of the input to fill with the human's answer.
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
- For an ARIA combobox, click it to inspect its overlay options, then select the exact option text.
  `select` handles both native selects and custom overlay dropdowns. Never type into a closed dropdown.
- Cascading fields may appear after each choice. Use the new observation, never reuse earlier ids.
- Do not interact with disabled controls. Complete enabled prerequisite fields first.
- Use citizen keys from the supplied profile, not portal control names. Social community uses caste;
  hostel status uses is_hosteller, and explicit disability_percent=0 means not disabled.
- Translate portal education categories from course/education_level: undergraduate study is post-matric.
  A workflow choice explicitly requested in the GOAL can use value_from="goal" and its exact option label.
- Human answers are available in CITIZEN under their recorded keys. Use those keys; never ask the same
  question again after an answer is recorded. Personal answers remain hidden as <set>.
- For date inputs use the displayed date format. Never invent a date of birth from age; ask for it.
- When DOB is supplied as <set>, use type(value_from="dob") on its input, even if readonly.
  The local helper operates supported calendars without exposing the DOB to you.
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


class Decision(BaseModel):
    thought: str
    action: Literal["click", "type", "select", "check", "scroll", "wait", "ask_human", "request_approval", "done", "fail"]
    element_id: int | None = None
    value: str | None = None
    value_from: str | None = None
    kind: Literal["captcha", "otp", "login", "missing_field"] | None = None
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


def require_source(d: Decision, el: dict | None, known: dict) -> Decision:
    """A model's default answer is not evidence about a citizen."""
    if not el or d.action not in ("type", "select", "check", "click"):
        return d
    aliases = {"community": "caste", "hosteler": "is_hosteller", "hosteller": "is_hosteller",
               "single_girl_child": "is_single_child", "college": "institution_name",
               "date_of_birth": "dob", "parent_profession": "parent_occupation"}
    if d.value_from and known.get(d.value_from) in (None, ""):
        alias = aliases.get(d.value_from)
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


class RunSession:
    """live state of one run: websocket subscribers + inbox for human messages"""

    def __init__(self, run_id: str, goal: str, portal_url: str, profile: dict, sensitive: dict):
        self.id = run_id
        self.goal = goal
        self.portal_url = portal_url
        self.profile = profile
        self.sensitive = {k: str(v) for k, v in sensitive.items() if v}
        self.answers: dict[str, str] = {}
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.subs: set = set()
        self.status = "queued"
        self.pending: dict | None = None  # current needs_human event, replayed to late joiners
        self.browser = Browser(self._on_frame)
        self.task: asyncio.Task | None = None
        self._last_frame_sent = 0.0
        self.llm_calls = 0

    # ---------- pub/sub ----------
    async def emit(self, msg: dict):
        dead = []
        for ws in list(self.subs):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.subs.discard(ws)

    async def _on_frame(self, b64: str):
        now = time.monotonic()
        if now - self._last_frame_sent < 0.12 or not self.subs:  # ~8fps cap, plenty for a demo
            return
        self._last_frame_sent = now
        await self.emit({"type": "frame", "jpeg": b64})

    async def set_status(self, status: str, **extra):
        self.status = status
        async with SessionLocal() as db:
            run = await db.get(AgentRun, self.id)
            run.status = status
            for k, v in extra.items():
                setattr(run, k, v)
            await db.commit()
        await self.emit({"type": "status", "status": status})

    # ---------- llm view of the citizen ----------
    def citizen_view(self) -> dict:
        view = {k: v for k, v in self.profile.items() if v is not None}
        view.update({k: "<set>" for k in self.sensitive})
        personal = re.compile(r"name|phone|mobile|email|dob|birth|address|bank|ifsc|aadhaar|account|password|otp|human_answer_", re.I)
        view.update({k: "<set>" if personal.search(k) else v for k, v in self.answers.items()})
        return view

    def resolve(self, d: Decision) -> str:
        if d.value_from:
            key = d.value_from.strip()
            if key == "goal" and key not in self.answers:
                if d.action != "select" or not d.value or not re.search(r"(?<!\w)" + re.escape(d.value) + r"(?!\w)", self.goal, re.I):
                    raise ValueError("Workflow choice must be explicitly named in the goal")
                return d.value
            for src in (self.sensitive, self.answers, self.profile):
                if key in src and src[key] not in (None, ""):
                    if d.action == "select" and d.value and key not in self.sensitive:
                        return d.value  # e.g. supplied sc -> displayed Scheduled Caste
                    if d.action == "select" and isinstance(src[key], bool):
                        return "Yes" if src[key] else "No"
                    return str(src[key])
            raise KeyError(f"citizen field '{key}' is not known — ask the human")
        return d.value or ""

    # ---------- human in the loop ----------
    async def wait_human(self, event: dict, expect: set[str]) -> dict:
        self.pending = event
        await self.emit(event)
        deadline = time.monotonic() + HUMAN_TIMEOUT
        try:
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("waited too long for the user")
                try:
                    msg = await asyncio.wait_for(self.inbox.get(), timeout=left)
                except TimeoutError as exc:
                    raise TimeoutError("Human response timed out after 15 minutes") from exc
                t = msg.get("type")
                if t == "abort":
                    raise asyncio.CancelledError("aborted by user")
                if t == "click":
                    await self.browser.human_click(float(msg["x"]), float(msg["y"]))
                elif t == "type":
                    await self.browser.human_type(str(msg.get("text", "")))
                elif t == "key":
                    await self.browser.human_key(str(msg.get("key", "Enter")))
                if t in expect:
                    return msg
        finally:
            self.pending = None


# ---------- graph nodes ----------

def _digest(snap: dict) -> str:
    els = [(e.get("tag"), e.get("text") or e.get("label"), e.get("value"), e.get("checked"), e.get("selected")) for e in snap["elements"]]
    return str(hash((snap["url"], tuple(snap["headings"]), tuple(snap["errors"]), tuple(els))))


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
    shots_dir = Path(get_settings().storage_dir) / "runs" / rs.id
    shots_dir.mkdir(parents=True, exist_ok=True)

    async def record(st: State, d: Decision | None, status: str, result: str) -> str:
        shot_path = shots_dir / f"{st['step']:03d}.jpg"
        try:
            await rs.browser.screenshot(str(shot_path), quality=50)
            shot_url = f"/files/runs/{rs.id}/{shot_path.name}"
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
        return {"snap": snap, "shot": shot, "digest": dig, "history": hist}

    async def decide(st: State) -> State:
        snap = st["snap"]
        obs = {
            "url": snap["url"], "title": snap["title"], "headings": snap["headings"],
            "validation_errors": snap["errors"], "captcha_detected": snap["captcha"],
            "elements": snap["elements"], "page_text": snap["text"][:1500],
        }
        prompt = [
            f"GOAL: {rs.goal}\n\nCITIZEN (personal fields hidden): {json.dumps(rs.citizen_view(), ensure_ascii=False)}\n\n"
            f"PREVIOUS STEPS:\n{_history_text(st.get('history', []))}\n\n"
            f"OBSERVATION:\n{json.dumps(obs, ensure_ascii=False)}",
            types.Part.from_bytes(data=st["shot"], mime_type="image/jpeg"),
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
        workflow = bool(el and re.search(r"application|service|benefit|scholarship|incentive|language|workflow|scheme|sort|page", el.get("label", ""), re.I))
        known = {**rs.profile, **rs.sensitive, **rs.answers}
        if workflow and d.action == "select" and d.value and re.search(r"(?<!\w)" + re.escape(d.value) + r"(?!\w)", rs.goal, re.I):
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
                await b.fill(d.element_id, rs.resolve(d))
            elif d.action == "select":
                await b.select(d.element_id, rs.resolve(d))
            elif d.action == "check":
                value = rs.resolve(d) if d.value_from else (d.value or "true")
                await b.check(d.element_id, value.strip().lower() in ("true", "yes", "1"))
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
        await rs.set_status("needs_human")
        ev = {"type": "needs_human", "kind": kind, "message": d.message or "Your help is needed", "field": d.value_from}
        await record(st, d, "human", kind)
        msg = await rs.wait_human(ev, {"resume", "human_input"})
        hist = list(st.get("history", []))
        if msg["type"] == "human_input" and msg.get("value"):
            val = str(msg["value"])
            el = next((e for e in st["snap"]["elements"] if e["id"] == d.element_id), {})
            source_key = d.value_from if d.value_from != "goal" else None
            answer_key = source_key or el.get("formcontrolname") or el.get("name") or f"human_answer_{st['step']}"
            if kind == "missing_field":
                rs.answers[answer_key] = val
            if d.element_id and el.get("tag") in ("input", "textarea") and not el.get("readonly"):
                await rs.browser.fill(d.element_id, val)  # OTP never goes to the model
            hist.append({"step": st["step"], "action": f"ask_human({kind}): {d.message or ''}",
                         "result": f"Human supplied an answer; use value_from={answer_key} to enter it"})
        else:
            hist.append({"step": st["step"], "action": f"ask_human({kind})", "result": "human finished it in the live view"})
        await rs.browser.settle()
        await rs.set_status("running")
        return {"history": hist}

    async def approval(st: State) -> State:
        d: Decision = st["decision"]
        await rs.set_status("awaiting_approval")
        await record(st, d, "human", "approval")
        await rs.wait_human({"type": "needs_human", "kind": "confirm_submit", "message": d.message or "Submit now?"}, {"approve"})
        await rs.set_status("running")
        hist = list(st.get("history", []))
        try:
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
    except asyncio.CancelledError as e:
        await rs.set_status("aborted", error=str(e) or "aborted")
        await rs.emit({"type": "error", "message": "Run aborted"})
    except Exception as e:
        log.exception("run %s crashed", rs.id)
        await rs.set_status("failed", error=str(e)[:500])
        await rs.emit({"type": "error", "message": f"Agent error: {str(e)[:200]}"})
    finally:
        await rs.browser.close()


class RunManager:
    def __init__(self, max_parallel: int = 2):
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


manager = RunManager()
