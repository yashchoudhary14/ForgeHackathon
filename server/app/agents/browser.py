"""playwright helpers: page snapshot for the llm, live screencast, actions"""
import asyncio
import base64
import logging
from typing import Awaitable, Callable
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

from ..config import get_settings

log = logging.getLogger(__name__)

VIEWPORT = {"width": 1280, "height": 800}

# tags every visible interactive element with data-agent-id and returns a compact description
SNAPSHOT_JS = r"""
() => {
  const sel = 'a[href], button, input, select, textarea, [role=button], [role=link], [role=checkbox], [role=radio], [role=combobox], [role=tab], [onclick], [contenteditable=true], label[for]';
  const vis = el => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const labelOf = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return l.innerText.trim(); }
    const p = el.closest('label'); if (p) return p.innerText.trim();
    const al = el.getAttribute('aria-label'); if (al) return al;
    const lb = el.getAttribute('aria-labelledby'); if (lb) { const n = document.getElementById(lb); if (n) return n.innerText.trim(); }
    // table layouts: label in previous cell
    const td = el.closest('td'); if (td && td.previousElementSibling) return td.previousElementSibling.innerText.trim();
    return '';
  };
  let n = 0; const out = [];
  document.querySelectorAll('[data-agent-id]').forEach(e => e.removeAttribute('data-agent-id'));
  for (const el of document.querySelectorAll(sel)) {
    if (!vis(el) || el.closest('[aria-hidden=true]')) continue;
    if (el.tagName === 'LABEL' && el.htmlFor) continue;
    const id = ++n; el.setAttribute('data-agent-id', id);
    const d = { id, tag: el.tagName.toLowerCase() };
    const t = el.getAttribute('type'); if (t) d.type = t;
    const role = el.getAttribute('role'); if (role) d.role = role;
    const txt = (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    if (txt && !['input', 'select', 'textarea'].includes(d.tag)) d.text = txt;
    const lab = labelOf(el).replace(/\s+/g, ' ').slice(0, 80); if (lab) d.label = lab;
    for (const a of ['name', 'placeholder', 'title']) { const v = el.getAttribute(a); if (v) d[a] = v.slice(0, 60); }
    if (d.tag === 'input' || d.tag === 'textarea') {
      if (['checkbox', 'radio'].includes(t)) d.checked = el.checked;
      else if (t !== 'password' && el.value) d.value = el.value.slice(0, 40);
      if (t === 'password' && el.value) d.value = '••••';
    }
    if (d.tag === 'select') {
      d.options = [...el.options].slice(0, 40).map(o => o.text.trim()).filter(Boolean);
      d.value = el.options[el.selectedIndex]?.text?.trim();
    }
    if (el.required || el.getAttribute('aria-required') === 'true') d.required = true;
    if (el.disabled) d.disabled = true;
    if (el.getAttribute('aria-invalid') === 'true') d.invalid = true;
    out.push(d);
    if (n >= 150) break;
  }
  const errs = [...document.querySelectorAll('[role=alert], .error, .errors, .invalid-feedback, .text-danger, .field-validation-error, .alert-danger, .help-block.error')]
    .filter(vis).map(e => e.innerText.trim()).filter(Boolean).slice(0, 8);
  const heads = [...document.querySelectorAll('h1,h2,h3,legend')].filter(vis).map(e => e.innerText.trim()).filter(Boolean).slice(0, 8);
  const captcha = !!document.querySelector('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], img[src*="captcha" i], img[id*="captcha" i], input[name*="captcha" i], input[id*="captcha" i]');
  const body = document.body ? document.body.innerText.replace(/\s+/g, ' ').slice(0, 2500) : '';
  return { elements: out, errors: errs, headings: heads, captcha, text: body };
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

    async def start(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=get_settings().agent_headless, args=["--disable-blink-features=AutomationControlled"]
        )
        self.ctx = await self._browser.new_context(viewport=VIEWPORT, locale="en-IN", accept_downloads=True)
        await self.ctx.route("**/*", self._guard)
        self.ctx.on("page", lambda p: asyncio.create_task(self._adopt(p)))
        await self._adopt(await self.ctx.new_page())

    async def _guard(self, route):
        req = route.request
        # sub-resources (cdn, fonts) are fine, but never let the agent navigate off government sites
        if req.is_navigation_request() and not allowed(req.url):
            log.warning("blocked navigation to %s", req.url)
            await route.abort("blockedbyclient")
        else:
            await route.continue_()

    async def _adopt(self, page: Page):
        """portals love opening forms in new tabs - follow the newest tab"""
        if self._cdp:
            try:
                await self._cdp.send("Page.stopScreencast")
                await self._cdp.detach()
            except Exception:
                pass
        self.page = page
        page.set_default_timeout(15000)
        self._cdp = await self.ctx.new_cdp_session(page)
        self._cdp.on("Page.screencastFrame", lambda ev: asyncio.create_task(self._frame(ev)))
        await self._cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 55, "maxWidth": 1280, "maxHeight": 800, "everyNthFrame": 2})

    async def _frame(self, ev):
        try:
            await self._cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:
            return
        self.last_frame = base64.b64decode(ev["data"])
        await self.on_frame(ev["data"])

    async def goto(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await self.settle()

    async def settle(self):
        try:
            await self.page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass  # gov sites with long-polling never go idle, that's ok

    async def snapshot(self) -> dict:
        try:
            snap = await self.page.evaluate(SNAPSHOT_JS)
        except Exception as e:  # navigation mid-evaluate
            log.info("snapshot retry: %s", e)
            await self.settle()
            snap = await self.page.evaluate(SNAPSHOT_JS)
        snap["url"] = self.page.url
        snap["title"] = await self.page.title()
        return snap

    async def screenshot(self, path: str | None = None, quality: int = 60) -> bytes:
        return await self.page.screenshot(type="jpeg", quality=quality, path=path)

    def el(self, element_id: int):
        return self.page.locator(f'[data-agent-id="{element_id}"]').first

    async def click(self, element_id: int):
        loc = self.el(element_id)
        await loc.scroll_into_view_if_needed(timeout=5000)
        await loc.click(timeout=8000)
        await self.settle()

    async def fill(self, element_id: int, value: str):
        loc = self.el(element_id)
        await loc.scroll_into_view_if_needed(timeout=5000)
        try:
            await loc.fill(value, timeout=8000)
        except Exception:
            # date pickers / masked inputs reject fill(), type it like a human instead
            await loc.click()
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.type(value, delay=40)
        await loc.dispatch_event("change")
        await loc.dispatch_event("blur")

    async def select(self, element_id: int, value: str):
        loc = self.el(element_id)
        try:
            await loc.select_option(label=value, timeout=5000)
        except Exception:
            # fall back to fuzzy match on option text
            opts = await loc.evaluate("s => [...s.options].map(o => [o.value, o.text.trim()])")
            want = value.strip().lower()
            pick = next((v for v, t in opts if t.lower() == want), None) or next(
                (v for v, t in opts if want in t.lower() or t.lower() in want and t), None
            )
            if pick is None:
                raise ValueError(f"no option like {value!r}; options: {[t for _, t in opts][:15]}")
            await loc.select_option(value=pick)
        await self.settle()

    async def check(self, element_id: int, on: bool = True):
        await self.el(element_id).set_checked(on, timeout=5000)

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
