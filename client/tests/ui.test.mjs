import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const server = await createServer({
  server: { middlewareMode: true, hmr: false },
  appType: "custom",
  optimizeDeps: { noDiscovery: true, include: [] },
});
after(() => server.close());
const { tt } = await server.ssrLoadModule("/src/ui-strings.ts");
const { VerdictChip, StatTile, Orb, EmptyState } =
  await server.ssrLoadModule("/src/ui.tsx");
const { SwipeToConfirm } = await server.ssrLoadModule("/src/guide.tsx");

test("tt falls back to English when a language lacks a key", () => {
  assert.equal(tt("hi", "navTalk"), "बोलें");
  assert.equal(tt("as", "navSchemes"), "আঁচনি");
  assert.equal(tt("as", "navExplain"), "Explain");
  assert.equal(tt("xx", "navTalk"), "Talk");
});

test("components render accessible markup", () => {
  assert.match(
    renderToStaticMarkup(createElement(VerdictChip, { verdict: "eligible" })),
    /Eligible/,
  );
  assert.match(
    renderToStaticMarkup(createElement(StatTile, { value: 3, label: "docs" })),
    /docs/,
  );
  assert.match(
    renderToStaticMarkup(createElement(Orb, { state: "listening" })),
    /data-state="listening"/,
  );
  assert.match(
    renderToStaticMarkup(createElement(EmptyState, { title: "Nothing" })),
    /role="status"/,
  );
  const swipe = renderToStaticMarkup(
    createElement(SwipeToConfirm, { label: "Swipe", onConfirm() {} }),
  );
  assert.match(swipe, /role="slider"/);
  assert.match(swipe, /tabindex="0"/);
});
