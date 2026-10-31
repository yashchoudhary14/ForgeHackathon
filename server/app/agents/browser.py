"""playwright helpers: page snapshot for the llm, live screencast, actions"""
import asyncio
import base64
import logging
import json
import re
from datetime import datetime
from typing import Awaitable, Callable
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeout, async_playwright, expect

from ..config import get_settings

log = logging.getLogger(__name__)

VIEWPORT = {"width": 1280, "height": 800}


def _same_date(value, fmt, expected):
    try:
        return datetime.strptime(value, fmt).date() == expected
    except ValueError:
        return False


def option_index(texts: list[str], value: str) -> int:
    """Prefer exact labels and reject ambiguous substring matches."""
    normalize = lambda s: re.sub(r"[\W_]+", "", s.casefold())
    words = lambda s: " " + " ".join(re.findall(r"\w+", s.casefold())) + " "
    want = normalize(value)
    # A supplied numeric zero can represent false on a binary Yes/No control.
    # Keep numeric dropdowns (including percentage fields) matched literally.
    if value.strip() == "0" and {normalize(text) for text in texts} == {"yes", "no"}:
        want = "no"
    exact = [i for i, text in enumerate(texts) if normalize(text) == want]
    matches = exact or [i for i, text in enumerate(texts)
        if want and normalize(text) and (words(value) in words(text) or words(text) in words(value))]
    if len(matches) != 1:
        raise ValueError(f"Choose one exact option from {texts}; requested {value!r}")
    return matches[0]

# tags every visible interactive element with data-agent-id and returns a compact description
SNAPSHOT_JS = r"""
() => {
  const sel = 'a[href], button, input, select, textarea, mat-radio-button, mat-checkbox, [role=button], [role=link], [role=checkbox], [role=radio], [role=combobox], [role=tab], [role=option], [role=menuitem], [role=listbox], [onclick], [contenteditable=true], label[for]';
  const vis = el => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const contextLabel = el => {
    for (let group = el.parentElement; group && !group.matches('form, body'); group = group.parentElement) {
      const captions = group.querySelectorAll(':scope > label');
      if (captions.length === 1) return captions[0].innerText.trim();
    }
    return '';
  };
  const labelOf = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return l.innerText.trim(); }
    const p = el.closest('label'); if (p) return p.innerText.trim();
    const al = el.getAttribute('aria-label'); if (al) return al;
    const context = contextLabel(el); if (context) return context;
    const lb = el.getAttribute('aria-labelledby'); if (lb) { const n = document.getElementById(lb); if (n) return n.innerText.trim(); }
    const field = el.closest('mat-form-field, .form-group, .form-field');
    const caption = field?.querySelector('mat-label, label');
    if (caption) return caption.innerText.trim();
    if (el.matches('[role=radio], input[type=radio], mat-radio-button')) {
      const row = el.closest('tr, [role=row]');
      if (row) return row.innerText.trim();
    }
    // table layouts: label in previous cell
    const td = el.closest('td'); if (td && td.previousElementSibling) return td.previousElementSibling.innerText.trim();
    return '';
  };
  const registry = window.__adhikaarAgentIds ||= { ids: new WeakMap(), next: 1 };
  const dialogs = [...document.querySelectorAll('[role=dialog], [role=alertdialog], [aria-modal=true], mat-dialog-container, .modal')].filter(vis);
  const root = dialogs.at(-1) || document;
  const roots = [root, ...document.querySelectorAll('[role=listbox], mat-calendar')].filter(r => r === document || vis(r));
  const out = [];
  document.querySelectorAll('[data-agent-id]').forEach(e => e.removeAttribute('data-agent-id'));
  // react/angular portals attach click handlers to plain divs - catch those via cursor:pointer
  const cands = new Set(roots.flatMap(r => [...r.querySelectorAll(sel)]));
  for (const el of roots.flatMap(r => [...r.querySelectorAll('div, span, li, img, td')])) {
    if (getComputedStyle(el).cursor !== 'pointer') continue;
    if (el.parentElement && getComputedStyle(el.parentElement).cursor === 'pointer') continue;
    if (el.closest(sel) || el.querySelector(sel)) continue;
    cands.add(el);
  }
  for (const el of cands) {
    // Some portals leave the application aria-hidden after closing nested dialogs.
    // With no active dialog, visible controls remain usable despite that stale ancestor.
    if (!vis(el) || el.getAttribute('aria-hidden') === 'true' ||
        (root !== document && el.closest('[aria-hidden=true]'))) continue;
    if (el.tagName === 'LABEL' && el.htmlFor) {
      // styled radios/checkboxes: the real input is hidden, so the label is what you click
      const target = document.getElementById(el.htmlFor);
      if (target && vis(target)) continue;
    }
    let id = registry.ids.get(el);
    if (!id) { id = registry.next++; registry.ids.set(el, id); }
    el.setAttribute('data-agent-id', id);
    const d = { id, tag: el.tagName.toLowerCase() };
    const t = el.getAttribute('type'); if (t) d.type = t;
    const role = el.getAttribute('role') || (el.matches('mat-radio-button') ? 'radio' : el.matches('mat-checkbox') ? 'checkbox' : null);
    if (role) d.role = role;
    if (el.matches('mat-radio-button, mat-checkbox')) d.checked = !!el.querySelector('input')?.checked;
    const alt = el.tagName === 'IMG' ? el.alt : (el.querySelector('img[alt]')?.alt || '');
    const txt = (el.innerText || el.value || alt || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    for (const [a, k] of [['aria-checked', 'checked'], ['aria-selected', 'selected'], ['aria-pressed', 'pressed'], ['aria-expanded', 'expanded']]) {
      const v = el.getAttribute(a); if (v === 'true' || v === 'false') d[k] = v === 'true';
    }
    if (el.tagName === 'LABEL') {
      const inp = el.htmlFor ? document.getElementById(el.htmlFor) : (el.querySelector('input') || (el.previousElementSibling?.tagName === 'INPUT' ? el.previousElementSibling : null));
      if (inp && ['checkbox', 'radio'].includes(inp.type)) d.checked = inp.checked;
    }
    if (/\b(selected|active|checked)\b/.test(el.className?.toString?.() || '') && d.checked === undefined) d.selected = true;
    if (txt && !['input', 'select', 'textarea'].includes(d.tag)) d.text = txt;
    const lab = labelOf(el).replace(/\s+/g, ' ').slice(0, 80); if (lab) d.label = lab;
    const context = contextLabel(el).replace(/\s+/g, ' ').slice(0, 80);
    if (context && context !== lab) d.field_label = context;
    if (role === 'option') {
      const panel = el.closest('[role=listbox]');
      const owner = panel?.id && [...document.querySelectorAll('[aria-controls], [aria-owns]')]
        .find(e => (e.getAttribute('aria-controls') || e.getAttribute('aria-owns') || '').split(/\s+/).includes(panel.id));
      if (owner) d.field_label = labelOf(owner);
    }
    for (const a of ['name', 'placeholder', 'title', 'formcontrolname']) { const v = el.getAttribute(a); if (v) d[a] = v.slice(0, 60); }
    if (d.tag === 'input' || d.tag === 'textarea') {
      const searchGroup = el.closest('[role=search], [role=dialog], mat-dialog-container, .modal, form');
      if (t === 'search' || role === 'searchbox' || searchGroup?.matches('[role=search]') ||
          [...(searchGroup?.querySelectorAll('button, [role=button]') || [])]
            .some(b => /^search$/i.test(b.innerText.trim()))) d.search_field = true;
      if (['checkbox', 'radio'].includes(t)) d.checked = el.checked;
      else if (t !== 'password' && el.value) d.value = el.value.slice(0, 40);
      if (t === 'password' && el.value) d.value = '••••';
    }
    if (d.tag === 'select') {
      d.options = [...el.options].slice(0, 40).map(o => o.text.trim()).filter(Boolean);
      d.value = el.options[el.selectedIndex]?.text?.trim();
    }
    if (role === 'combobox') {
      d.value = (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 100);
      const list = document.getElementById(el.getAttribute('aria-controls'));
      if (list) d.options = [...list.querySelectorAll('[role=option]')].filter(vis).map(o => o.innerText.trim());
    }
    if (el.required || el.getAttribute('aria-required') === 'true') d.required = true;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true' || el.closest('fieldset[disabled]')) d.disabled = true;
    if (el.readOnly || el.getAttribute('aria-readonly') === 'true') d.readonly = true;
    for (const a of ['min', 'max', 'pattern']) { const v = el.getAttribute(a); if (v) d[a] = v; }
    if (el.getAttribute('aria-invalid') === 'true') d.invalid = true;
    out.push(d);
    if (out.length >= 150) break;
  }
  const errs = [...document.querySelectorAll('mat-error, [role=alert], .error, .errors, .invalid-feedback, .text-danger, .field-validation-error, .alert-danger, .help-block.error')]
    .filter(vis).map(e => e.innerText.trim()).filter(Boolean).slice(0, 8);
  const heads = [...document.querySelectorAll('h1,h2,h3,legend')].filter(vis).map(e => e.innerText.trim()).filter(Boolean).slice(0, 8);
  const captcha = !!document.querySelector('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], img[src*="captcha" i], img[id*="captcha" i], input[name*="captcha" i], input[id*="captcha" i], input[formcontrolname*="captcha" i], input[placeholder*="captcha" i]');
  const textRoot = root === document ? document.body : root;
  const body = textRoot ? textRoot.innerText.replace(/\s+/g, ' ').slice(0, 2500) : '';
  const steps = [...document.querySelectorAll('[aria-current="step"], [role="tab"][aria-selected="true"]')]
    .filter(vis).map(e => e.innerText.trim());
  const loading = [...document.querySelectorAll('[aria-busy=true], mat-progress-spinner, mat-spinner, .ngx-spinner-overlay, .loading-overlay, .spinner-overlay')].some(vis);
  return { elements: out, errors: errs, headings: heads, steps, captcha, loading, text: body };
}
"""


def allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in get_settings().allowed_domains)


class Browser:
    """one chromium context per agent run, streams jpeg frames to `on_frame`"""

    def __init__(self, on_frame: Callable[[str], Awaitable[None]]):
        self.on_frame = on_frame
        self._pw = None
        self._browser = None
        self.ctx: BrowserContext | None = None
        self.page: Page | None = None
        self._cdp = None
        self.last_frame: bytes | None = None
        self._adopt_lock = asyncio.Lock()
        self.navigation_id = 0
        self.network_errors: dict[str, int] = {}
        self._api_slots = asyncio.Semaphore(3)

    async def start(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=get_settings().agent_headless, channel=get_settings().agent_browser_channel,
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.ctx = await self._browser.new_context(viewport=VIEWPORT, locale="en-IN", accept_downloads=True)
        await self.ctx.route("**/*", self._guard)
        self.ctx.on("page", lambda p: asyncio.create_task(self._adopt(p)))
        await self._adopt(await self.ctx.new_page())

    async def _guard(self, route):
        req = route.request
        # sub-resources (cdn, fonts) are fine, but never let the agent navigate off government sites
        top_level = req.is_navigation_request() and req.frame.parent_frame is None
        if top_level and not allowed(req.url):
            log.warning("blocked navigation to %s", req.url)
            await route.abort("blockedbyclient")
        elif req.resource_type in ("xhr", "fetch"):
            # Government backends can reject a burst of parallel lookup requests.
            # Gate the original requests; never duplicate or retry a POST.
            async with self._api_slots:
                await route.continue_()
                try:
                    await asyncio.wait_for(req.response(), timeout=15)
                except (TimeoutError, PlaywrightTimeout):
                    pass
        else:
            await route.continue_()

    async def _adopt(self, page: Page):
        """portals love opening forms in new tabs - follow the newest tab"""
        async with self._adopt_lock:
            if self.page is page and self._cdp is not None:
                return
            await self._adopt_page(page)

    async def _adopt_page(self, page: Page):
        if self._cdp:
            try:
                await self._cdp.send("Page.stopScreencast")
                await self._cdp.detach()
            except Exception:
                pass
        self.page = page
        self.network_errors.clear()
        self.navigation_id += 1
        page.on("framenavigated", lambda frame: self._navigated(page, frame))
        page.on("response", self._response)
        page.set_default_timeout(15000)
        self._cdp = await self.ctx.new_cdp_session(page)
        self._cdp.on("Page.screencastFrame", lambda ev: asyncio.create_task(self._frame(ev)))
        await self._cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 55, "maxWidth": 1280, "maxHeight": 800, "everyNthFrame": 2})

    def _navigated(self, page, frame):
        if self.page is page and frame == page.main_frame:
            self.navigation_id += 1
            self.network_errors.clear()

    def _response(self, response):
        request = response.request
        if not allowed(response.url) or request.resource_type not in ("xhr", "fetch") or re.search(r"otp|password", response.url, re.I):
            return
        # Only method/path/status are exposed; response bodies and query values stay private.
        key = f"{request.method} {urlparse(response.url).path}"
        if response.status >= 400:
            self.network_errors[key] = response.status
        else:
            self.network_errors.pop(key, None)

    async def _frame(self, ev):
        try:
            await self._cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:
            return
        self.last_frame = base64.b64decode(ev["data"])
        await self.on_frame(ev["data"])

    async def goto(self, url: str):
        for attempt in range(3):
            await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await self.settle()
            try:
                await self.page.wait_for_load_state("networkidle", timeout=5000)
            except PlaywrightTimeout:
                pass  # polling pages need not become idle
            blocked = await self.page.locator('.ngx-spinner-overlay:visible, .loading-overlay:visible, .spinner-overlay:visible').count()
            if attempt == 2 or not (blocked or any(status in (502, 503, 504) for status in self.network_errors.values())):
                break
            # Recover only during initial page loading, before any citizen data is entered.
            # Do not replay POST requests or refresh a partially completed form.
            await asyncio.sleep(0.5 * (attempt + 1))

    async def settle(self):
        # Analytics and polling need not finish before a form can be used.
        await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        await self.page.wait_for_timeout(150)
        busy = self.page.locator('[aria-busy="true"], mat-progress-spinner, mat-spinner, .ngx-spinner-overlay, .loading-overlay, .spinner-overlay').filter(visible=True)
        if await busy.count():
            try:
                await busy.first.wait_for(state="hidden", timeout=2000)
            except Exception:
                pass  # report the current state rather than waiting forever

    async def _snap_once(self) -> dict:
        try:
            return await self.page.evaluate(SNAPSHOT_JS)
        except Exception as e:  # navigation mid-evaluate
            log.info("snapshot retry: %s", e)
            await self.settle()
            return await self.page.evaluate(SNAPSHOT_JS)

    async def snapshot(self) -> dict:
        # SPAs animate between steps without any network, so wait until two reads agree
        snap = await self._snap_once()
        for _ in range(4):
            await asyncio.sleep(0.15)
            again = await self._snap_once()
            if again == snap:
                snap = again
                break
            snap = again
        snap["url"] = self.page.url
        snap["title"] = await self.page.title()
        snap["navigation_id"] = self.navigation_id
        snap["network_errors"] = [f"HTTP {status}: {path}" for path, status in self.network_errors.items()]
        return snap

    async def decision_screenshot(self) -> bytes:
        """Scale the entire visible viewport, preserving the user's browser geometry."""
        metrics = await self._cdp.send("Page.getLayoutMetrics")
        viewport = metrics.get("cssVisualViewport") or metrics["visualViewport"]
        response = await self._cdp.send("Page.captureScreenshot", {
            "format": "jpeg", "quality": 40, "captureBeyondViewport": False,
            "clip": {"x": viewport["pageX"], "y": viewport["pageY"],
                     "width": viewport["clientWidth"], "height": viewport["clientHeight"],
                     "scale": min(1, 1024 / viewport["clientWidth"])},
        })
        return base64.b64decode(response["data"])

    async def screenshot(self, path: str | None = None, quality: int = 60) -> bytes:
        return await self.page.screenshot(type="jpeg", quality=quality, path=path)

    def el(self, element_id: int):
        return self.page.locator(f'[data-agent-id="{element_id}"]').first

    async def click(self, element_id: int):
        await self.page.bring_to_front()
        loc = self.el(element_id)
        await loc.scroll_into_view_if_needed(timeout=5000)
        if await loc.get_attribute("role") == "combobox":
            await self._open_combobox(loc)
        else:
            await loc.click(timeout=8000)
        await self.settle()

    async def _open_combobox(self, loc):
        if await loc.get_attribute("aria-disabled") == "true":
            raise ValueError("This control is disabled; complete its enabled prerequisite fields first")
        if await loc.get_attribute("aria-expanded") == "true":
            return
        try:
            await loc.scroll_into_view_if_needed(timeout=3000)
            arrow = loc.locator('.mat-mdc-select-arrow-wrapper, .mat-select-arrow-wrapper').first
            target = arrow if await arrow.count() else loc
            box = await target.bounding_box()
            # The arrow side is clear of floating labels that cover the center.
            position = {"x": max(1, box["width"] - 15), "y": box["height"] / 2} if box else None
            await target.click(position=position, timeout=1000)
        except PlaywrightTimeout:
            pass
        if await loc.get_attribute("aria-expanded") != "true":
            # Do not toggle a panel that a delayed click already opened.
            await loc.focus()
            await loc.press("Alt+ArrowDown")
            try:
                await expect(loc).to_have_attribute("aria-expanded", "true", timeout=300)
            except AssertionError:
                await loc.press("Space")
        await expect(loc).to_have_attribute("aria-expanded", "true", timeout=2000)

    async def fill(self, element_id: int, value: str):
        await self.page.bring_to_front()
        loc = self.el(element_id)
        await loc.scroll_into_view_if_needed(timeout=5000)
        if await loc.evaluate("e => !!e.readOnly"):
            hints = await loc.evaluate("e => [e.name,e.id,e.getAttribute('formcontrolname'),e.placeholder].join(' ')")
            if re.search(r"date|dob|birth", hints, re.I):
                await self._fill_calendar(loc, value)
                return
            raise ValueError("Readonly field: open its chooser instead of typing")
        try:
            await loc.fill(value, timeout=8000)
        except Exception:
            # date pickers / masked inputs reject fill(), type it like a human instead
            await loc.click()
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.type(value, delay=40)
        await loc.dispatch_event("change")
        await loc.dispatch_event("blur")

    async def _fill_calendar(self, loc, value: str):
        date = None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                date = datetime.strptime(value, fmt).date()
                break
            except ValueError:
                pass
        if date is None:
            raise ValueError("Date must be DD/MM/YYYY or YYYY-MM-DD")
        field = loc.locator('xpath=ancestor::mat-form-field[1]')
        if not await field.count():
            raise ValueError("Readonly date field needs a supported calendar chooser")
        await field.get_by_role("button", name=re.compile("open calendar", re.I)).click()
        cal = self.page.locator('mat-calendar:visible').first
        await cal.wait_for(state="visible", timeout=3000)
        await cal.get_by_role("button", name="Choose month and year", exact=True).click()
        year = cal.get_by_role("button", name=str(date.year), exact=True)
        for _ in range(12):
            if await year.count():
                break
            years = [int(y) for y in await cal.get_by_role("button").all_text_contents()
                     if y.strip().isdigit() and len(y.strip()) == 4]
            if not years:
                raise ValueError("Calendar did not expose a year grid")
            direction = "Previous" if date.year < min(years) else "Next"
            await cal.get_by_role("button", name=re.compile(direction + r".*years", re.I)).click()
        await year.click(timeout=2000)
        await cal.get_by_role("button", name=f"{date.strftime('%B')} {date.year}", exact=True).click()
        await cal.get_by_role("button", name=f"{date.day} {date.strftime('%B')} {date.year}", exact=True).click()
        await self.settle()
        entered = await loc.input_value()
        formats = ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y")
        if not any(_same_date(entered, fmt, date) for fmt in formats):
            raise ValueError("Calendar did not retain the requested date")

    async def select(self, element_id: int, value: str):
        await self.page.bring_to_front()
        loc = self.el(element_id)
        if await loc.evaluate("el => el.tagName !== 'SELECT'"):
            if await loc.get_attribute("role") == "option":
                option_index([await loc.inner_text()], value)
                await loc.click(timeout=5000)
                await self.settle()
                return
            if await loc.get_attribute("role") != "combobox":
                raise ValueError("Target is not a select or combobox; use the current observation's field id")
            # ARIA comboboxes (including Angular Material) render options in a portal.
            if await loc.get_attribute("aria-expanded") != "true":
                await self._open_combobox(loc)
            # Native <option> nodes elsewhere in the page can appear "visible" to
            # Playwright even with their select closed. Scope to an actual open listbox.
            options = self.page.locator('[role="listbox"]:visible [role="option"]:visible')
            controls = await loc.get_attribute("aria-controls") or await loc.get_attribute("aria-owns")
            if controls:
                options = self.page.locator(f'[id={json.dumps(controls.split()[0])}] [role="option"]')
            await options.first.wait_for(state="visible", timeout=5000)
            texts = await options.all_inner_texts()
            choice = option_index(texts, value)
            await options.nth(choice).click(timeout=5000)
            await self.settle()
            if await loc.count() and await loc.evaluate("e => e.tagName !== 'INPUT'"):
                selected = await loc.inner_text()
                if option_index([selected], texts[choice]) != 0:
                    raise ValueError("The requested selection was not retained")
            return
        try:
            await loc.select_option(label=value, timeout=5000)
        except Exception:
            # fall back to fuzzy match on option text
            opts = await loc.evaluate("s => [...s.options].map(o => [o.value, o.text.trim()])")
            pick = opts[option_index([text for _, text in opts], value)][0]
            await loc.select_option(value=pick)
        await self.settle()

    async def check(self, element_id: int, on: bool = True):
        await self.page.bring_to_front()
        loc = self.el(element_id)
        if await loc.evaluate("e => e.matches('mat-checkbox, mat-radio-button')"):
            native = loc.locator('input').first
            if await native.is_checked() != on:
                await loc.click(timeout=5000)
            await expect(native).to_be_checked(checked=on)
        else:
            await loc.set_checked(on, timeout=5000)

    async def upload(self, element_id: int, path: str):
        await self.el(element_id).set_input_files(path)

    async def scroll(self, down: bool = True):
        await self.page.mouse.wheel(0, 600 if down else -600)
        await asyncio.sleep(0.4)

    # --- human takeover (coords are fractions of the viewport) ---
    async def human_click(self, fx: float, fy: float):
        await self.page.mouse.click(fx * VIEWPORT["width"], fy * VIEWPORT["height"])

    async def human_type(self, text: str):
        await self.page.keyboard.type(text, delay=30)

    async def human_key(self, key: str):
        await self.page.keyboard.press(key)

    async def close(self):
        for fn in (lambda: self.ctx and self.ctx.close(), lambda: self._browser and self._browser.close(), lambda: self._pw and self._pw.stop()):
            try:
                r = fn()
                if r:
                    await r
            except Exception:
                pass
