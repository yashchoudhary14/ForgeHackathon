"""One process-wide sliding-window scheduler, shared by all Gemini callers."""
import asyncio
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field

from google.genai import types

log = logging.getLogger(__name__)


class QueueTimeout(TimeoutError):
    pass


@dataclass
class ModelState:
    name: str
    rpm: int = 12
    kind: str = "generation"
    enabled: bool = False
    requests: deque = field(default_factory=deque)
    cooldown_until: float = 0
    total: int = 0
    failures: int = 0
    last_selected: float = 0
    status: str = "not_probed"


def status_code(error: Exception) -> int | None:
    code = getattr(error, "code", None)
    if isinstance(code, int):
        return code
    match = re.search(r"\b(400|401|403|404|429|500|502|503|504)\b", str(error))
    return int(match[1]) if match else None


def retry_delay(error: Exception) -> float | None:
    def find(value):
        if isinstance(value, dict):
            delay = value.get("retryDelay")
            if isinstance(delay, dict) and "seconds" in delay:
                return max(0, float(delay["seconds"]) + float(delay.get("nanos", 0)) / 1e9)
            if isinstance(delay, (str, int, float)):
                match = re.fullmatch(r"([\d.]+)s?", str(delay))
                if match:
                    return float(match[1])
            for child in value.values():
                result = find(child)
                if result is not None:
                    return result
        elif isinstance(value, (list, tuple)):
            for child in value:
                result = find(child)
                if result is not None:
                    return result
        return None

    for attribute in ("response_json", "details", "error_details"):
        result = find(getattr(error, attribute, None))
        if result is not None:
            return result
    match = re.search(r"(?:retryDelay[\"'\s:]+|retry (?:in|after)\s+)([\d.]+)s", str(error), re.I)
    return float(match[1]) if match else None


def cooldown_seconds(error: Exception) -> float:
    if status_code(error) == 404:
        return 3600
    if status_code(error) == 429:
        # RPD exhaustion cannot be cured by rotating back to the same model each minute.
        details = str(getattr(error, "response_json", "")) + str(getattr(error, "details", "")) + str(error)
        daily = re.search(r"per.?day|daily|requestsperday", details, re.I)
        delay = retry_delay(error)
        return delay if delay is not None else (86400 if daily else 60)
    return 5 if isinstance(error, TimeoutError) else 60


class ModelPool:
    def __init__(self, names: list[str], embedding_model: str, rpm: int = 12, window: float = 60,
                 limits: dict[str, int] | None = None):
        limits = limits or {}
        self.states = {name: ModelState(name, rpm=limits.get(name, rpm)) for name in names}
        self.states[embedding_model] = ModelState(embedding_model, rpm=limits.get(embedding_model, rpm),
                                                   kind="embedding", enabled=True, status="ready")
        self.rpm, self.window = rpm, window
        self.condition = asyncio.Condition()
        self.probe_lock = asyncio.Lock()
        self.initialized = False
        self.waiters: list[tuple[object, set[str]]] = []
        self.limited = 0

    async def probe(self, client, timeout: float):
        async with self.probe_lock:
            if self.initialized:
                return

            async def one(state):
                started = time.monotonic()
                state.requests.append(started)
                state.total += 1
                try:
                    response = await asyncio.wait_for(client().aio.models.generate_content(
                        model=state.name, contents="Reply with exactly OK.",
                        config=types.GenerateContentConfig(temperature=0, max_output_tokens=128),
                    ), timeout)
                    state.enabled = bool(response.text and response.text.strip())
                    state.status = "ready" if state.enabled else "empty_probe"
                except Exception as error:
                    state.failures += 1
                    state.status = "probe_timeout" if isinstance(error, TimeoutError) else f"probe_error_{status_code(error) or 'unknown'}"
                    state.cooldown_until = time.monotonic() + cooldown_seconds(error)
                log.info("llm model=%s ms=%d cached=false limited=false status=%s",
                         state.name, (time.monotonic() - started) * 1000, state.status)

            await asyncio.gather(*(one(state) for state in self.states.values() if state.kind == "generation"))
            self.initialized = True

    def names(self, kind: str = "generation") -> list[str]:
        return [state.name for state in self.states.values() if state.enabled and state.kind == kind]

    def _prune(self, state: ModelState, now: float):
        while state.requests and state.requests[0] <= now - self.window:
            state.requests.popleft()

    async def acquire(self, preference: str | None = None, *, names: list[str] | None = None,
                      exclude: set[str] | None = None, timeout: float = 45) -> tuple[str, float]:
        names = [name for name in (self.names() if names is None else names)
                 if name not in (exclude or set()) and self.states[name].enabled]
        if not names:
            raise RuntimeError("No Gemini models are available for this request")
        ticket = object(), set(names)
        started = time.monotonic()
        deadline = started + timeout
        limited = False
        async with self.condition:
            self.waiters.append(ticket)
            try:
                while True:
                    now = time.monotonic()
                    names = [name for name in names if self.states[name].enabled]
                    if not names:
                        raise RuntimeError("No Gemini models are available for this request")
                    for name in names:
                        self._prune(self.states[name], now)
                    ready = [self.states[name] for name in names
                             if len(self.states[name].requests) < self.states[name].rpm and self.states[name].cooldown_until <= now]
                    # FIFO between requests sharing a pool; embeddings don't block text calls.
                    earlier = self.waiters[:self.waiters.index(ticket)]
                    has_priority = not any(ticket[1] & previous[1] for previous in earlier)
                    if ready and has_priority:
                        def rank(state):
                            wants_lite = preference == "lite" or (preference not in {None, "strong"} and "lite" in preference)
                            preferred = ("lite" in state.name) == wants_lite
                            return (not preferred if preference else False, len(state.requests),
                                    state.name != preference if preference not in {None, "lite", "strong"} else False,
                                    state.last_selected)

                        state = min(ready, key=rank)
                        state.requests.append(now)
                        state.total += 1
                        state.last_selected = now
                        return state.name, (now - started if limited else 0)
                    if not limited:
                        limited = True
                        self.limited += 1
                    remaining = deadline - now
                    if remaining <= 0:
                        raise QueueTimeout("Gemini capacity is busy. Please retry shortly.")
                    wake = min(max(self.states[name].cooldown_until,
                                   self.states[name].requests[0] + self.window if len(self.states[name].requests) >= self.states[name].rpm else now)
                               for name in names)
                    delay = min(remaining, max(0.01, wake - now)) if has_priority else remaining
                    try:
                        await asyncio.wait_for(self.condition.wait(), delay)
                    except TimeoutError:
                        pass
            finally:
                self.waiters.remove(ticket)
                self.condition.notify_all()

    async def failed(self, name: str, error: Exception):
        async with self.condition:
            state = self.states[name]
            state.failures += 1
            state.cooldown_until = max(state.cooldown_until, time.monotonic() + cooldown_seconds(error))
            state.status = "cooldown"
            if status_code(error) == 404:
                state.enabled = False
                state.status = "not_found"
            self.condition.notify_all()

    async def snapshot(self) -> dict:
        async with self.condition:
            now = time.monotonic()
            for state in self.states.values():
                self._prune(state, now)
            return {
                "ready": bool(self.names()), "initialized": self.initialized,
                "scope": "process", "waiting": len(self.waiters), "limited": self.limited,
                "available_now": sum(state.enabled and state.kind == "generation"
                                     and state.cooldown_until <= now and len(state.requests) < state.rpm
                                     for state in self.states.values()),
                "models": [{
                    "model": state.name, "class": "embedding" if state.kind == "embedding" else (
                        "lite" if "lite" in state.name else "strong"),
                    "enabled": state.enabled, "used_last_minute": len(state.requests), "rpm_limit": state.rpm,
                    "cooldown_seconds": round(max(0, state.cooldown_until - now), 3),
                    "total_requests": state.total, "failures": state.failures,
                    "status": "ready" if state.enabled and state.cooldown_until <= now else state.status,
                } for state in self.states.values()],
            }
